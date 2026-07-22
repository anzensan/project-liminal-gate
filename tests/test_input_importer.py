from __future__ import annotations

import json
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile

from liminal_gate.input_importer import (
    ImportError,
    REVIEWED_ANDROID_5_5_7_PROFILE,
    build_import_manifest,
    write_import_manifest,
)


class InputImporterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.apk = self.root / "client.apk"
        with zipfile.ZipFile(self.apk, "w") as archive:
            archive.writestr("assets/bootstrap.dat", b"user-owned data")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    @staticmethod
    def reviewed_metadata() -> bytes:
        literals = (
            b"https://gdappserver.appspot.com/",
            b"http://storage.googleapis.com/gdresources/data_u2017/android/",
            b"http://www.terra-battle.com",
        )
        table_offset = 24
        table_size = len(literals) * 8
        data_offset = table_offset + table_size
        data = b"".join(literals)
        table = bytearray()
        index = 0
        for literal in literals:
            table.extend(struct.pack("<II", len(literal), index))
            index += len(literal)
        return struct.pack("<IIIIII", 0xFAB11BAF, 29, table_offset, table_size, data_offset, len(data)) + bytes(table) + data

    def test_writes_metadata_without_source_path_or_content(self) -> None:
        resources = self.root / "resources"
        resources.mkdir()
        (resources / "image.dat").write_bytes(b"resource bytes")
        manifest = build_import_manifest(self.apk, resources)
        output = write_import_manifest(self.root / "user-data", manifest)
        text = output.read_text(encoding="utf-8")
        loaded = json.loads(text)
        self.assertEqual(1, loaded["apk"]["member_count"])
        self.assertEqual(1, loaded["resources"]["file_count"])
        self.assertNotIn(str(self.apk), text)
        self.assertNotIn("user-owned data", text)
        self.assertNotIn("resource bytes", text)

    def test_rejects_unsafe_zip_member(self) -> None:
        unsafe = self.root / "unsafe.apk"
        with zipfile.ZipFile(unsafe, "w") as archive:
            archive.writestr("../outside.dat", b"no")
        with self.assertRaisesRegex(ImportError, "unsafe APK member"):
            build_import_manifest(unsafe)

    def test_validates_reviewed_android_input_structure_without_retaining_content(self) -> None:
        reviewed = self.root / "reviewed.apk"
        with zipfile.ZipFile(reviewed, "w") as archive:
            archive.writestr("assets/bin/Data/Managed/Metadata/global-metadata.dat", self.reviewed_metadata())
            archive.writestr("lib/arm64-v8a/libil2cpp.so", b"arm64")
            archive.writestr("lib/armeabi-v7a/libil2cpp.so", b"armv7")
        resources = self.root / "resources"
        for category in ("BG", "BGM", "Banner", "BuddyImages", "BuddyThumbs", "Illust", "Pieces", "SE", "Scenario"):
            path = resources / category
            path.mkdir(parents=True)
            (path / "local.bin").write_bytes(b"local")
        manifest = build_import_manifest(reviewed, resources, reviewed_android_5_5_7=True)
        self.assertEqual(REVIEWED_ANDROID_5_5_7_PROFILE, manifest["reviewed_input"]["profile"])
        self.assertEqual("structural", manifest["reviewed_input"]["validation"])

    def test_rejects_reviewed_mode_with_missing_routing_literal_or_category(self) -> None:
        reviewed = self.root / "missing-literal.apk"
        with zipfile.ZipFile(reviewed, "w") as archive:
            archive.writestr("assets/bin/Data/Managed/Metadata/global-metadata.dat", b"missing literals")
            archive.writestr("lib/arm64-v8a/libil2cpp.so", b"arm64")
            archive.writestr("lib/armeabi-v7a/libil2cpp.so", b"armv7")
        resources = self.root / "resources"
        resources.mkdir()
        with self.assertRaisesRegex(ImportError, "routing-literal"):
            build_import_manifest(reviewed, resources, reviewed_android_5_5_7=True)

    def test_rejects_reviewed_mode_with_missing_resource_category(self) -> None:
        reviewed = self.root / "missing-category.apk"
        with zipfile.ZipFile(reviewed, "w") as archive:
            archive.writestr("assets/bin/Data/Managed/Metadata/global-metadata.dat", self.reviewed_metadata())
            archive.writestr("lib/arm64-v8a/libil2cpp.so", b"arm64")
            archive.writestr("lib/armeabi-v7a/libil2cpp.so", b"armv7")
        resources = self.root / "resources"
        resources.mkdir()
        with self.assertRaisesRegex(ImportError, "missing reviewed Android categories"):
            build_import_manifest(reviewed, resources, reviewed_android_5_5_7=True)
