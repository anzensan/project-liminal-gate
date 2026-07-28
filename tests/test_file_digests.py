"""One immutable input is read once per run, however many consumers want it.

The guided setup inventories the resource tree twice, and on a multi-gigabyte
pack the second read was the slowest thing it did for no gain at all.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest

from liminal_gate.file_digests import DigestCache, count_files, sha256_file
from liminal_gate.input_importer import build_import_manifest
from liminal_gate.resource_catalog_builder import build_resource_manifest


class DigestCacheTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.file = self.root / "resource.bin"
        self.file.write_bytes(b"contents")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_matches_a_direct_hash(self) -> None:
        expected = hashlib.sha256(b"contents").hexdigest()
        self.assertEqual(expected, sha256_file(self.file))
        self.assertEqual(expected, DigestCache()(self.file))

    def test_reads_one_file_once_however_often_it_is_asked_for(self) -> None:
        digests = DigestCache()
        first = digests(self.file)
        for _ in range(4):
            self.assertEqual(first, digests(self.file))
        self.assertEqual(1, digests.hashed_files)
        self.assertEqual(4, digests.reused)
        self.assertEqual(len(b"contents"), digests.hashed_bytes)

    def test_the_same_file_by_a_different_path_is_still_one_read(self) -> None:
        # Consumers resolve the tree differently; the cache keys on the file.
        indirect = self.root / "." / "resource.bin"
        digests = DigestCache()
        self.assertEqual(digests(self.file), digests(indirect))
        self.assertEqual(1, digests.hashed_files)

    def test_reports_each_read_to_a_progress_callback(self) -> None:
        seen: list[tuple[int, int]] = []
        digests = DigestCache(on_hash=lambda files, read: seen.append((files, read)))
        digests(self.file)
        digests(self.file)
        self.assertEqual([(1, len(b"contents"))], seen, "a cache hit is not work worth reporting")

    def test_counts_files_without_reading_them(self) -> None:
        (self.root / "nested").mkdir()
        (self.root / "nested" / "second.bin").write_bytes(b"more")
        self.assertEqual(2, count_files(self.root))
        self.assertEqual(0, count_files(self.root / "absent"))


class SharedDigestTest(unittest.TestCase):
    """The two manifest builders must agree, and must not both read the tree."""

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.resources = self.root / "android"
        (self.resources / "BG").mkdir(parents=True)
        (self.resources / "BG" / "one.png").write_bytes(b"first")
        (self.resources / "BG" / "two.png").write_bytes(b"second")
        self.apk = self.root / "game.apk"
        self.apk.write_bytes(b"PK\x05\x06" + b"\x00" * 18)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_the_second_consumer_reads_no_file_the_first_already_read(self) -> None:
        digests = DigestCache()
        build_import_manifest(self.apk, self.resources, digests=digests)
        after_inventory = digests.hashed_files
        build_resource_manifest(self.resources, digests=digests)
        self.assertEqual(3, after_inventory, "two resources and the APK")
        self.assertEqual(
            after_inventory, digests.hashed_files,
            "the resource manifest must reuse the inventory's digests, not repeat them",
        )
        self.assertEqual(2, digests.reused)

    def test_sharing_digests_changes_neither_manifest(self) -> None:
        shared = build_resource_manifest(self.resources, digests=DigestCache())
        direct = build_resource_manifest(self.resources)
        self.assertEqual(direct, shared)
        inventory = build_import_manifest(self.apk, self.resources, digests=DigestCache())
        self.assertEqual(build_import_manifest(self.apk, self.resources), inventory)


if __name__ == "__main__":
    unittest.main()
