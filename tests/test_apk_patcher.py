from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from liminal_gate.apk_patcher import PatchPlanError, apply_patch_plan, load_patch_plan


class ApkPatcherTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.source = self.root / "source.apk"
        with zipfile.ZipFile(self.source, "w") as archive:
            archive.writestr("META-INF/MANIFEST.MF", b"original signature")
            archive.writestr("META-INF/CERT.SF", b"original signature")
            archive.writestr("assets/payload.dat", b"beforepatch")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write_plan(self, source_sha256: str, expected_hex: str = "6265666f7265") -> Path:
        plan = self.root / "plan.json"
        plan.write_text(json.dumps({
            "schema_version": 1,
            "source_sha256": source_sha256,
            "patches": [{
                "member": "assets/payload.dat",
                "offset": 0,
                "expected_hex": expected_hex,
                "replacement_hex": "61667465722d",
            }],
        }), encoding="utf-8")
        return plan

    def test_applies_user_plan_and_removes_original_signatures(self) -> None:
        source_sha256 = hashlib.sha256(self.source.read_bytes()).hexdigest()
        output = self.root / "patched.apk"
        apply_patch_plan(self.source, output, load_patch_plan(self.write_plan(source_sha256)))
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(["assets/payload.dat"], archive.namelist())
            self.assertEqual(b"after-patch", archive.read("assets/payload.dat"))

    def test_rejects_source_or_byte_mismatch(self) -> None:
        output = self.root / "patched.apk"
        with self.assertRaisesRegex(PatchPlanError, "SHA-256"):
            apply_patch_plan(self.source, output, load_patch_plan(self.write_plan("0" * 64)))
        source_sha256 = hashlib.sha256(self.source.read_bytes()).hexdigest()
        with self.assertRaisesRegex(PatchPlanError, "expectation"):
            apply_patch_plan(
                self.source,
                output,
                load_patch_plan(self.write_plan(source_sha256, expected_hex="000000000000")),
            )
