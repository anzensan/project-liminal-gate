from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
import zlib

from liminal_gate.apk_patcher import (
    PATCH_PLAN_SCHEMA_VERSION,
    PatchPlan,
    PatchPlanError,
    TextAssetJsonAliases,
    _alias_text_asset_document,
    apply_patch_plan,
    load_patch_plan,
    native_abis,
    sha256_file,
)


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
            "schema_version": PATCH_PLAN_SCHEMA_VERSION,
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

    def test_copies_one_exact_text_asset_record_to_named_aliases(self) -> None:
        patch = TextAssetJsonAliases(
            "assets/bin/Data/data.unity3d", "AssetVersions", "SpecialBanner",
            "sp3003-1", ("sp1003-1", "sp1003-2", "sp1003-3"),
        )
        source = json.dumps({"SpecialBanner": [
            {"id": 0, "h": 140, "name": "sp3003-1", "w": 610, "ver": 110},
            {"id": 0, "h": 140, "name": "unrelated", "w": 610, "ver": 108},
        ]})
        entries = json.loads(_alias_text_asset_document(source, patch))["SpecialBanner"]
        self.assertEqual(
            ["sp3003-1", "unrelated", "sp1003-1", "sp1003-2", "sp1003-3"],
            [entry["name"] for entry in entries],
        )
        for entry in entries[2:]:
            self.assertEqual((0, 140, 610, 110), (entry["id"], entry["h"], entry["w"], entry["ver"]))
        with self.assertRaisesRegex(PatchPlanError, "already exists"):
            _alias_text_asset_document(json.dumps({"SpecialBanner": entries}), patch)

    def _alias_plan(self, **alias: object) -> Path:
        plan = self.root / "alias-plan.json"
        plan.write_text(json.dumps({
            "schema_version": PATCH_PLAN_SCHEMA_VERSION,
            "source_sha256": sha256_file(self.source),
            "patches": [{
                "member": "assets/payload.dat",
                "offset": 0,
                "expected_hex": "6265666f7265",
                "replacement_hex": "61667465722d",
            }],
            "text_asset_json_aliases": [{
                "member": "assets/bin/Data/data.unity3d",
                "asset_name": "AssetVersions",
                "collection": "SpecialBanner",
                "source_name": "sp3003-1",
                "aliases": ["sp1003-1"],
                **alias,
            }],
        }), encoding="utf-8")
        return plan

    def test_alias_overrides_are_parsed_as_ordered_pairs_and_strictly_checked(self) -> None:
        parsed = load_patch_plan(self._alias_plan(overrides={"ver": 111})).text_asset_json_aliases
        self.assertEqual((("ver", 111),), parsed[0].overrides)
        self.assertEqual((), load_patch_plan(self._alias_plan()).text_asset_json_aliases[0].overrides)
        for rejected in ({"name": "sp1003-1"}, {"": 1}, {"ver": 1.5}, {"ver": True}, {"ver": None}, []):
            with self.assertRaisesRegex(PatchPlanError, "alias overrides"):
                load_patch_plan(self._alias_plan(overrides=rejected))

    def test_an_alias_may_replace_named_fields_the_source_record_already_has(self) -> None:
        """A corrected bundle at an unchanged URL needs its own cache version.

        The client reuses `<asset>_<ver>.bin` without asking the server again,
        so replacing the copied version is the only way a rebuilt client stops
        reading the artwork it cached the first time.
        """
        patch = TextAssetJsonAliases(
            "assets/bin/Data/data.unity3d", "AssetVersions", "SpecialBanner",
            "sp3003-1", ("sp1003-1",), (("ver", 111),),
        )
        source = json.dumps({"SpecialBanner": [{"id": 0, "h": 140, "name": "sp3003-1", "w": 610, "ver": 110}]})
        entries = json.loads(_alias_text_asset_document(source, patch))["SpecialBanner"]
        self.assertEqual([("sp3003-1", 110), ("sp1003-1", 111)], [(e["name"], e["ver"]) for e in entries])
        self.assertEqual((0, 140, 610), (entries[1]["id"], entries[1]["h"], entries[1]["w"]))
        unknown = TextAssetJsonAliases(
            patch.member, patch.asset_name, patch.collection, patch.source_name,
            patch.aliases, (("ver", 111), ("unrecovered", 1)),
        )
        with self.assertRaisesRegex(PatchPlanError, "sp3003-1 does not have: unrecovered"):
            _alias_text_asset_document(source, unknown)


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
            "schema_version": PATCH_PLAN_SCHEMA_VERSION,
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


def _dex(body: bytes) -> bytes:
    """A minimal dex whose header fields are correct for its own contents."""
    data = bytearray(b"dex\n035\0" + b"\0" * 24 + body)
    data[12:32] = hashlib.sha1(bytes(data[32:])).digest()
    data[8:12] = (zlib.adler32(bytes(data[12:])) & 0xFFFFFFFF).to_bytes(4, "little")
    return bytes(data)


class DexHeaderRepairTest(unittest.TestCase):
    """Editing a dex invalidates its header; the plan must declare the repair."""

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.source = self.root / "source.apk"
        self.original = _dex(b"com.google.android.gms.games.service.START")
        with zipfile.ZipFile(self.source, "w") as archive:
            archive.writestr("classes.dex", self.original)
            # Patchable at offset 0, so the repair is what fails, not the edit.
            archive.writestr("assets/payload.dat", b"com.google.android.gms.but not a dex")

    def _plan(self, member: str, repair: bool, offset: int = 32) -> Path:
        plan = self.root / "plan.json"
        plan.write_text(json.dumps({
            "schema_version": PATCH_PLAN_SCHEMA_VERSION,
            "source_sha256": sha256_file(self.source),
            "patches": [{
                "member": member,
                "offset": offset,
                "expected_hex": b"com.google.android.gms.".hex(),
                "replacement_hex": b"org.liminalgate.unused.".hex(),
                "repair_dex_header": repair,
            }],
        }), encoding="utf-8")
        return plan

    def _patched(self, member: str, repair: bool, offset: int = 32) -> bytes:
        output = self.root / "out.apk"
        output.unlink(missing_ok=True)
        apply_patch_plan(self.source, output, load_patch_plan(self._plan(member, repair, offset)))
        with zipfile.ZipFile(output) as archive:
            return archive.read(member)

    def test_repair_restores_the_checksum_and_changes_the_identity(self) -> None:
        patched = self._patched("classes.dex", repair=True)
        self.assertEqual(len(self.original), len(patched))
        self.assertEqual(
            zlib.adler32(patched[12:]) & 0xFFFFFFFF,
            int.from_bytes(patched[8:12], "little"),
            "the runtime checks this checksum; a stale one is a rejected dex",
        )
        self.assertEqual(hashlib.sha1(patched[32:]).digest(), patched[12:32])
        self.assertNotEqual(
            self.original[12:32], patched[12:32],
            "ART caches compiled output against this field, so an edited dex needs a new identity",
        )
        self.assertIn(b"org.liminalgate.unused.games.service.START", patched)

    def test_without_the_declaration_the_header_is_left_stale(self) -> None:
        """The repair is opt-in per patch, so its absence must be observable."""
        patched = self._patched("classes.dex", repair=False)
        self.assertEqual(self.original[:32], patched[:32])
        self.assertNotEqual(
            zlib.adler32(patched[12:]) & 0xFFFFFFFF, int.from_bytes(patched[8:12], "little"),
        )

    def test_repair_refuses_a_member_that_is_not_a_dex(self) -> None:
        with self.assertRaisesRegex(PatchPlanError, "not a dex file"):
            self._patched("assets/payload.dat", repair=True, offset=0)

    def test_repair_declaration_must_be_a_boolean(self) -> None:
        plan = self.root / "bad.json"
        plan.write_text(json.dumps({
            "schema_version": PATCH_PLAN_SCHEMA_VERSION,
            "source_sha256": sha256_file(self.source),
            "patches": [{
                "member": "classes.dex", "offset": 32,
                "expected_hex": "00", "replacement_hex": "01",
                "repair_dex_header": "yes",
            }],
        }), encoding="utf-8")
        with self.assertRaisesRegex(PatchPlanError, "repair_dex_header must be a boolean"):
            load_patch_plan(plan)
