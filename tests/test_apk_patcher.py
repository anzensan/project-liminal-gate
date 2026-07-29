from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from liminal_gate.apk_patcher import PatchPlan, PatchPlanError, apply_patch_plan, load_patch_plan, native_abis, sha256_file


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


class DropAbiTest(unittest.TestCase):
    """An ABI tree can be removed without touching ABI-independent patches.

    The operation remains useful for explicitly compatible older targets, but
    a package with only armeabi-v7a cannot run on a 64-bit-app-only device.
    """

    def _archive(self, path: Path, members: dict[str, bytes]) -> None:
        with zipfile.ZipFile(path, "w") as archive:
            for name, payload in members.items():
                archive.writestr(name, payload)

    def _source(self, directory: Path) -> Path:
        source = directory / "source.apk"
        self._archive(source, {
            "assets/bin/Data/Managed/Metadata/global-metadata.dat": b"ROUTINGDATA",
            "lib/arm64-v8a/libil2cpp.so": b"AAAA",
            "lib/armeabi-v7a/libil2cpp.so": b"BBBB",
            "classes.dex": b"DEX",
        })
        return source

    #: The plan schema requires at least one patch, so cases that are not about
    #: patching use this identity edit on a member no ABI drop can remove.
    KEEPALIVE = {"member": "classes.dex", "offset": 0, "expected_hex": "444558", "replacement_hex": "444558"}

    def _plan(self, directory: Path, source: Path, patches: list[dict]) -> PatchPlan:
        document = {
            "schema_version": 1,
            "source_sha256": sha256_file(source),
            "patches": patches or [self.KEEPALIVE],
        }
        path = directory / "plan.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        return load_patch_plan(path)

    def test_reports_the_abis_a_source_carries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(("arm64-v8a", "armeabi-v7a"), native_abis(self._source(Path(directory))))

    def test_drops_only_the_named_tree_and_keeps_everything_else(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source(root)
            output = root / "out.apk"
            apply_patch_plan(source, output, self._plan(root, source, []), drop_abis=("arm64-v8a",))
            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())
            self.assertNotIn("lib/arm64-v8a/libil2cpp.so", names)
            self.assertIn("lib/armeabi-v7a/libil2cpp.so", names)
            # The routing literals live here, so a 32-bit build keeps them.
            self.assertIn("assets/bin/Data/Managed/Metadata/global-metadata.dat", names)
            self.assertIn("classes.dex", names)

    def test_discards_patches_aimed_at_a_dropped_tree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source(root)
            patches = [
                {"member": "lib/arm64-v8a/libil2cpp.so", "offset": 0, "expected_hex": "41414141", "replacement_hex": "5a5a5a5a"},
                {"member": "lib/armeabi-v7a/libil2cpp.so", "offset": 0, "expected_hex": "42424242", "replacement_hex": "59595959"},
            ]
            output = root / "out.apk"
            apply_patch_plan(source, output, self._plan(root, source, patches + [self.KEEPALIVE]), drop_abis=("arm64-v8a",))
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(b"YYYY", archive.read("lib/armeabi-v7a/libil2cpp.so"))

    def test_refuses_to_drop_every_abi(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source(root)
            with self.assertRaisesRegex(PatchPlanError, "no native code"):
                apply_patch_plan(source, root / "out.apk", self._plan(root, source, []),
                                 drop_abis=("arm64-v8a", "armeabi-v7a"))

    def test_refuses_an_abi_the_source_does_not_carry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source(root)
            with self.assertRaisesRegex(PatchPlanError, "no native code for"):
                apply_patch_plan(source, root / "out.apk", self._plan(root, source, []), drop_abis=("x86",))

    def test_dropping_nothing_leaves_the_archive_intact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source(root)
            output = root / "out.apk"
            apply_patch_plan(source, output, self._plan(root, source, []))
            with zipfile.ZipFile(source) as a, zipfile.ZipFile(output) as b:
                self.assertEqual(set(a.namelist()), set(b.namelist()))
