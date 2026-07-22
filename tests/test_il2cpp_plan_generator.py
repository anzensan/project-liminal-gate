from __future__ import annotations

import json
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile

from liminal_gate.apk_patcher import apply_patch_plan, load_patch_plan
from liminal_gate.il2cpp_plan_generator import IL2CPP_METADATA_MAGIC, PlanGenerationError, generate_plan


class Il2CppPlanGeneratorTest(unittest.TestCase):
    member = "user-selected/global-metadata.dat"

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.source = self.root / "source.apk"
        old = b"http://old.example/"
        self.metadata = bytearray(128)
        struct.pack_into("<IIIIII", self.metadata, 0, IL2CPP_METADATA_MAGIC, 24, 32, 8, 64, len(old))
        struct.pack_into("<II", self.metadata, 32, len(old), 0)
        self.metadata[64:64 + len(old)] = old
        with zipfile.ZipFile(self.source, "w") as archive:
            archive.writestr(self.member, self.metadata)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_generates_plan_applied_by_generic_patcher(self) -> None:
        plan = generate_plan(self.source, self.member, [(b"http://old.example/", b"http://local/")])
        self.assertEqual(2, len(plan["patches"]))
        plan_path = self.root / "plan.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        output = self.root / "patched.apk"
        apply_patch_plan(self.source, output, load_patch_plan(plan_path))
        with zipfile.ZipFile(output) as archive:
            patched = archive.read(self.member)
        self.assertEqual(len(b"http://local/"), struct.unpack_from("<I", patched, 32)[0])
        self.assertEqual(b"http://local/", patched[64:64 + len(b"http://local/")])
        self.assertEqual(
            b"http://old.example/"[len(b"http://local/"):],
            patched[64 + len(b"http://local/"):64 + len(b"http://old.example/")],
        )

    def test_rejects_ambiguous_or_growing_literal(self) -> None:
        with self.assertRaisesRegex(PlanGenerationError, "exactly one"):
            generate_plan(self.source, self.member, [(b"missing", b"local")])
        with self.assertRaisesRegex(PlanGenerationError, "no longer"):
            generate_plan(self.source, self.member, [(b"http://old.example/", b"http://a-longer-local-address.example/")])
