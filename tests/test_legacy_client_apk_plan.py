from __future__ import annotations

import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from liminal_gate.apk_patcher import apply_patch_plan, load_patch_plan
from liminal_gate.il2cpp_plan_generator import IL2CPP_METADATA_MAGIC, PlanGenerationError
from liminal_gate.legacy_client_apk_plan import (
    API_BASE_LITERAL,
    ARM64_SCUDO_ALLOCATOR_PATCHES,
    ARM64_UNITY_MEMBER,
    FINAL_ARM64_UNITY_SHA256,
    METADATA_MEMBER,
    RESOURCE_BASE_LITERAL,
    WEBSITE_BASE_LITERAL,
    CLIENT_DEX_MEMBER,
    FINAL_CLIENT_DEX_SHA256,
    GOOGLE_SERVICE_BIND_ACTIONS,
    PLAY_BILLING_BIND_ACTIONS,
    DISABLED_BIND_ACTIONS,
    INERT_ACTION_BYTE,
    _dex_string_table,
    _disabled_bind_action_patches,
    IAP_MODAL_PATCHES,
    TERMS_CONFIRMATION_PATCHES,
    COIN_CREEPS_BANNER_ALIASES,
    generate_legacy_client_plan,
    max_server_origin_length,
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
            archive.writestr("assets/bin/Data/data.unity3d", b"fixture Unity bundle")
            libraries = {}
            for member, offset, old, _new in (
                *IAP_MODAL_PATCHES,
                *TERMS_CONFIRMATION_PATCHES,
                *ARM64_SCUDO_ALLOCATOR_PATCHES,
            ):
                payload = libraries.setdefault(member, bytearray())
                if len(payload) < offset + len(bytes.fromhex(old)):
                    payload.extend(b"\0" * (offset + len(bytes.fromhex(old)) - len(payload)))
                payload[offset:offset + len(bytes.fromhex(old))] = bytes.fromhex(old)
            for member, payload in libraries.items():
                archive.writestr(member, payload)
        self.unity_hash = patch(
            "liminal_gate.legacy_client_apk_plan._sha256_member",
            return_value=FINAL_ARM64_UNITY_SHA256,
        )
        self.unity_hash.start()

    def tearDown(self) -> None:
        self.unity_hash.stop()
        self.temporary_directory.cleanup()

    def test_the_default_plan_never_touches_the_client_dex(self) -> None:
        """Play Services neutralization is opt-in; the default artifact is unchanged."""
        plan = generate_legacy_client_plan(self.source, "http://192.168.1.10:8642/")
        self.assertEqual([], [item for item in plan["patches"] if item["member"] == CLIENT_DEX_MEMBER])
        self.assertNotIn(
            "repair_dex_header", set().union(*(item.keys() for item in plan["patches"])),
        )

    def test_generates_and_applies_three_literal_local_routing_plan(self) -> None:
        plan = generate_legacy_client_plan(self.source, "http://192.168.1.10:8642/")
        self.assertEqual(12, len(plan["patches"]))
        plan_path = self.root / "plan.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        output = self.root / "patched.apk"
        with patch("liminal_gate.apk_patcher._apply_text_asset_json_aliases", side_effect=lambda data, _aliases: data):
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
        # Rejected while normalizing the origin, before any APK work, and with
        # the measured length rather than a generic literal-size failure.
        with self.assertRaisesRegex(PlanGenerationError, "is 59 characters; .* at most 27"):
            generate_legacy_client_plan(self.source, "https://a-very-long-hostname-that-will-not-fit.example:8642")
        self.assertEqual(27, max_server_origin_length())

    def test_plan_contains_routing_and_exact_local_startup_patches(self) -> None:
        plan = generate_legacy_client_plan(self.source, "http://192.168.1.10:8642")
        self.assertEqual(12, len(plan["patches"]))
        binary = plan["patches"][6:]
        expected = (
            *IAP_MODAL_PATCHES,
            *TERMS_CONFIRMATION_PATCHES,
            *ARM64_SCUDO_ALLOCATOR_PATCHES,
        )
        self.assertEqual(
            [(member, offset, old, new) for member, offset, old, new in expected],
            [
                (
                    item["member"],
                    item["offset"],
                    item["expected_hex"],
                    item["replacement_hex"],
                )
                for item in binary
            ],
        )
        self.assertNotIn("source_apk", plan)
        self.assertEqual([COIN_CREEPS_BANNER_ALIASES], plan["text_asset_json_aliases"])

    def test_rejects_a_different_arm64_unity_player(self) -> None:
        self.unity_hash.stop()
        try:
            with self.assertRaisesRegex(
                PlanGenerationError,
                "ARM64 Unity player does not match the supported final client",
            ):
                generate_legacy_client_plan(self.source, "http://192.168.1.10:8642")
        finally:
            self.unity_hash.start()

    def test_scudo_patch_replaces_the_exact_constructor_and_only_arm64(self) -> None:
        plan = generate_legacy_client_plan(self.source, "http://192.168.1.10:8642")
        plan_path = self.root / "plan.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        output = self.root / "patched.apk"
        with patch("liminal_gate.apk_patcher._apply_text_asset_json_aliases", side_effect=lambda data, _aliases: data):
            apply_patch_plan(self.source, output, load_patch_plan(plan_path))
        member, offset, expected, replacement = ARM64_SCUDO_ALLOCATOR_PATCHES[0]
        self.assertEqual(ARM64_UNITY_MEMBER, member)
        with zipfile.ZipFile(output) as archive:
            patched = archive.read(member)
        self.assertEqual(bytes.fromhex(replacement), patched[offset:offset + len(bytes.fromhex(replacement))])
        self.assertNotEqual(bytes.fromhex(expected), patched[offset:offset + len(bytes.fromhex(expected))])


#: A real dex has thousands of strings, so no patched action is ever the first
#: or last entry. These keep the minimal fixtures honest about that.
DEX_SENTINELS = (b"!first", b"~last")


def _dex(strings: list[bytes]) -> bytes:
    """A minimal dex whose string_ids table is sorted, as the format requires."""
    ordered = sorted({*strings, *DEX_SENTINELS})
    header = bytearray(112)
    header[0:8] = b"dex\n035\0"
    ids_offset = len(header)
    data_offset = ids_offset + 4 * len(ordered)
    blobs, offsets = bytearray(), []
    for value in ordered:
        offsets.append(data_offset + len(blobs))
        blobs += bytes([len(value)]) + value + b"\0"   # ULEB128 length under 128
    struct.pack_into("<II", header, 56, len(ordered), ids_offset)
    return bytes(header) + struct.pack(f"<{len(ordered)}I", *offsets) + bytes(blobs)


class GoogleServiceBindPatchTest(unittest.TestCase):
    """The opt-in patch that makes Play Services binds unresolvable.

    Unity 2017's ServiceConnection proxy cannot dispatch the overload Android 16
    added, and the crash needs a bind to *complete*, so an action that resolves
    to nothing prevents it.
    """

    #: Deliberately excluded: AIDL interface descriptors, not bind actions.
    DESCRIPTORS = (
        b"com.google.android.gms.common.internal.service.ICommonService",
        b"com.google.android.gms.common.internal.service.ICommonCallbacks",
    )
    #: An unrelated class name sharing the 23-byte prefix, which must survive.
    BYSTANDER = b"com.google.android.gms.common.api.internal.LifecycleCallback"

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.dex = _dex([*DISABLED_BIND_ACTIONS, *self.DESCRIPTORS, self.BYSTANDER])
        self.source = self._apk("source.apk", self.dex)
        self.digest = patch(
            "liminal_gate.legacy_client_apk_plan._sha256_member",
            side_effect=lambda apk, member: (
                FINAL_CLIENT_DEX_SHA256 if member == CLIENT_DEX_MEMBER else FINAL_ARM64_UNITY_SHA256
            ),
        )
        self.digest.start()
        self.addCleanup(self.digest.stop)

    def _apk(self, name: str, dex: bytes) -> Path:
        path = self.root / name
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(CLIENT_DEX_MEMBER, dex)
        return path

    def _apply(self, dex: bytes, patches: list[dict]) -> bytes:
        patched = bytearray(dex)
        for item in patches:
            offset = item["offset"]
            expected = bytes.fromhex(item["expected_hex"])
            self.assertEqual(expected, patched[offset:offset + len(expected)])
            patched[offset:offset + len(expected)] = bytes.fromhex(item["replacement_hex"])
        return bytes(patched)

    def test_every_action_becomes_a_single_byte_edit(self) -> None:
        patches = _disabled_bind_action_patches(self.source)
        self.assertEqual(len(DISABLED_BIND_ACTIONS), len(patches))
        self.assertEqual({CLIENT_DEX_MEMBER}, {item["member"] for item in patches})
        self.assertEqual(len(patches), len({item["offset"] for item in patches}))
        for item in patches:
            self.assertEqual(1, len(bytes.fromhex(item["expected_hex"])))
            self.assertEqual(INERT_ACTION_BYTE.hex(), item["replacement_hex"])
            self.assertTrue(item["repair_dex_header"])

    def test_the_patched_string_table_is_still_sorted(self) -> None:
        """The dex string table is sorted and the runtime enforces that.

        An edit that preserves every offset can still move a string's sort
        position, and the resulting dex is rejected outright — the app dies
        before any game code runs.
        """
        patched = self._apply(self.dex, _disabled_bind_action_patches(self.source))
        values = [value for _offset, value in _dex_string_table(patched)]
        self.assertEqual(sorted(values), values)

    def test_refuses_an_edit_that_would_unsort_the_table(self) -> None:
        action = b"com.google.android.gms.games.service.START"
        # Sorts after the action but before its rewritten form, so the edit
        # would jump the neighbour.
        blocker = action + b"X"
        source = self._apk("blocked.apk", _dex([*DISABLED_BIND_ACTIONS, blocker]))
        with self.assertRaisesRegex(PlanGenerationError, "unsorted"):
            _disabled_bind_action_patches(source)

    def test_applying_it_clears_the_actions_and_spares_everything_else(self) -> None:
        patched = self._apply(self.dex, _disabled_bind_action_patches(self.source))
        for action in DISABLED_BIND_ACTIONS:
            self.assertNotIn(action, patched)
        for descriptor in self.DESCRIPTORS:
            self.assertIn(descriptor, patched, "rewriting a binder descriptor would break the handshake")
        self.assertIn(self.BYSTANDER, patched)

    def test_refuses_a_dex_that_was_not_reviewed(self) -> None:
        self.digest.stop()
        with patch("liminal_gate.legacy_client_apk_plan._sha256_member", return_value="0" * 64):
            with self.assertRaisesRegex(PlanGenerationError, "client dex does not match"):
                _disabled_bind_action_patches(self.source)
        self.digest.start()

    def test_refuses_a_dex_missing_an_action(self) -> None:
        short = self._apk("short.apk", _dex([*DISABLED_BIND_ACTIONS[1:], *self.DESCRIPTORS]))
        with self.assertRaisesRegex(PlanGenerationError, "must contain"):
            _disabled_bind_action_patches(short)

    def test_the_two_binder_descriptors_are_not_in_the_patch_set(self) -> None:
        """Stated once here so shortening the set cannot quietly include them."""
        for descriptor in self.DESCRIPTORS:
            self.assertNotIn(descriptor, DISABLED_BIND_ACTIONS)

    def test_the_billing_bind_is_covered(self) -> None:
        """The action a physical Android 16 device was observed crashing on.

        `UnityIAP: Billing service connected.` is the last line before the VM
        dies. Play Billing is `com.android.vending`, so none of the Play
        Services actions reach it.
        """
        billing = b"com.android.vending.billing.InAppBillingService.BIND"
        self.assertIn(billing, PLAY_BILLING_BIND_ACTIONS)
        self.assertIn(billing, DISABLED_BIND_ACTIONS)
        patched = self._apply(self.dex, _disabled_bind_action_patches(self.source))
        self.assertNotIn(billing, patched)
        self.assertIn(billing[:-1] + INERT_ACTION_BYTE, patched)

    def test_the_two_action_sets_are_disjoint_and_complete(self) -> None:
        self.assertEqual(set(), set(GOOGLE_SERVICE_BIND_ACTIONS) & set(PLAY_BILLING_BIND_ACTIONS))
        self.assertEqual(
            set(DISABLED_BIND_ACTIONS),
            set(GOOGLE_SERVICE_BIND_ACTIONS) | set(PLAY_BILLING_BIND_ACTIONS),
        )
