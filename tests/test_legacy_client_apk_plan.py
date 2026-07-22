from __future__ import annotations

import json
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile

from liminal_gate.apk_patcher import apply_patch_plan, load_patch_plan
from liminal_gate.il2cpp_plan_generator import IL2CPP_METADATA_MAGIC, PlanGenerationError
from liminal_gate.legacy_client_apk_plan import (
    API_BASE_LITERAL,
    METADATA_MEMBER,
    RESOURCE_BASE_LITERAL,
    WEBSITE_BASE_LITERAL,
    generate_legacy_client_plan,
    normalize_server_origin,
)


class LegacyClientApkPlanTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.source = self.root / "source.apk"
        literals = (API_BASE_LITERAL, RESOURCE_BASE_LITERAL, WEBSITE_BASE_LITERAL)
        data_offset = 128
        metadata = bytearray(data_offset + sum(len(literal) for literal in literals))
        struct.pack_into("<IIIIII", metadata, 0, IL2CPP_METADATA_MAGIC, 24, 32, len(literals) * 8, data_offset, len(metadata) - data_offset)
        cursor = 0
        for index, literal in enumerate(literals):
            struct.pack_into("<II", metadata, 32 + index * 8, len(literal), cursor)
            metadata[data_offset + cursor:data_offset + cursor + len(literal)] = literal
            cursor += len(literal)
        with zipfile.ZipFile(self.source, "w") as archive:
            archive.writestr(METADATA_MEMBER, metadata)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_generates_and_applies_three_literal_local_routing_plan(self) -> None:
        plan = generate_legacy_client_plan(self.source, "http://192.168.1.10:8642/")
        self.assertEqual(6, len(plan["patches"]))
        plan_path = self.root / "plan.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        output = self.root / "patched.apk"
        apply_patch_plan(self.source, output, load_patch_plan(plan_path))
        with zipfile.ZipFile(output) as archive:
            metadata = archive.read(METADATA_MEMBER)
        values = []
        for index in range(3):
            length, offset = struct.unpack_from("<II", metadata, 32 + index * 8)
            values.append(metadata[128 + offset:128 + offset + length])
        self.assertEqual(
            [
                b"http://192.168.1.10:8642/",
                b"http://192.168.1.10:8642/resources/",
                b"http://192.168.1.10:8642",
            ],
            values,
        )

    def test_rejects_non_origin_or_too_long_server_address(self) -> None:
        for origin in ("localhost:8642", "http://host/path", "https://user@host", "http://host/?query=1"):
            with self.subTest(origin=origin):
                with self.assertRaises(PlanGenerationError):
                    normalize_server_origin(origin)
        with self.assertRaisesRegex(PlanGenerationError, "no longer"):
            generate_legacy_client_plan(self.source, "https://a-very-long-hostname-that-will-not-fit.example:8642")

    def test_plan_contains_only_metadata_routing_patches(self) -> None:
        plan = generate_legacy_client_plan(self.source, "http://192.168.1.10:8642")
        self.assertEqual(6, len(plan["patches"]))
        self.assertTrue(all(patch["member"] == METADATA_MEMBER for patch in plan["patches"]))
        self.assertNotIn("source_apk", plan)
