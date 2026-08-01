from __future__ import annotations

import json
from pathlib import Path
import struct
import tempfile
import unittest

from liminal_gate.daily_quest_importer import (
    DailyQuestImportError,
    DailyQuestRotation,
    _read_string_array,
    load_daily_quest_catalog,
    write_daily_quest_catalog,
)


def serialised(entries: tuple[str, ...], name: bytes = b"", trailing: bytes = b"") -> bytes:
    """Build the same layout Unity writes for DailyQuestData."""
    body = bytearray(b"\x00" * (12 + 4 + 12))
    body += struct.pack("<i", len(name)) + name
    body += b"\x00" * (-len(body) % 4)
    body += struct.pack("<i", len(entries))
    for entry in entries:
        encoded = entry.encode("ascii")
        body += struct.pack("<i", len(encoded)) + encoded
        body += b"\x00" * (-len(body) % 4)
    return bytes(body) + trailing


class DailyQuestImporterTest(unittest.TestCase):
    def test_reads_the_rotation_and_consumes_the_object_exactly(self) -> None:
        entries = ("6010-1", "6011-2", "6006-1")
        self.assertEqual(entries, _read_string_array(serialised(entries)))

    def test_a_named_object_still_parses(self) -> None:
        entries = ("6000-1", "6001-1")
        self.assertEqual(entries, _read_string_array(serialised(entries, name=b"DailyQuestData")))

    def test_trailing_fields_are_refused_rather_than_guessed(self) -> None:
        """The exact-consumption check is what makes a type-tree-free read safe."""
        with self.assertRaises(DailyQuestImportError):
            _read_string_array(serialised(("6000-1",), trailing=b"\x07\x00\x00\x00"))

    def test_an_implausible_length_is_refused(self) -> None:
        blob = bytearray(serialised(("6000-1",)))
        struct.pack_into("<i", blob, 12 + 4 + 12 + 4, 99999)
        with self.assertRaises(DailyQuestImportError):
            _read_string_array(bytes(blob))

    def test_catalog_round_trips_with_provenance(self) -> None:
        rotation = DailyQuestRotation(
            order=("6010-1", "6006-1", "6010-1"),
            stages=((6006, 1), (6010, 1)),
            apk_sha256="a" * 64,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "daily-quests.json"
            write_daily_quest_catalog(rotation, path)
            loaded = load_daily_quest_catalog(path)
        self.assertEqual(rotation.order, loaded.order)
        self.assertEqual(rotation.stages, loaded.stages)
        self.assertEqual("a" * 64, loaded.apk_sha256)

    def test_catalog_refuses_a_non_daily_chapter(self) -> None:
        document = {
            "schema_version": 1, "provenance": "user-derived",
            "source": {"apk_sha256": "b" * 64},
            "order": ["1-1"], "stages": [{"chapter": 1, "section": 1}],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "daily-quests.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(DailyQuestImportError):
                load_daily_quest_catalog(path)

    def test_catalog_refuses_stages_that_disagree_with_the_rotation(self) -> None:
        document = {
            "schema_version": 1, "provenance": "user-derived",
            "source": {"apk_sha256": "c" * 64},
            "order": ["6010-1"], "stages": [{"chapter": 6011, "section": 1}],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "daily-quests.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(DailyQuestImportError):
                load_daily_quest_catalog(path)

    def test_catalog_requires_apk_provenance(self) -> None:
        document = {
            "schema_version": 1, "provenance": "user-derived", "source": {},
            "order": ["6010-1"], "stages": [{"chapter": 6010, "section": 1}],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "daily-quests.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(DailyQuestImportError):
                load_daily_quest_catalog(path)

    def test_catalog_refuses_bundled_provenance(self) -> None:
        document = {
            "schema_version": 1, "provenance": "bundled",
            "source": {"apk_sha256": "d" * 64},
            "order": ["6010-1"], "stages": [{"chapter": 6010, "section": 1}],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "daily-quests.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(DailyQuestImportError):
                load_daily_quest_catalog(path)
