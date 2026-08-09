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
    DRAG_TIME_SITES,
    STOCK_DRAG_TIME_SECONDS,
    drag_time_patches,
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
    ARMV7_UNITY_MEMBER,
    DISABLED_BIND_ACTIONS,
    UNITY_ADVERTISING_ID_ACTION,
    UNITY_BIND_ACTION_MEMBERS,
    _disabled_unity_bind_action_patches,
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

    def test_drag_time_patches_both_abis_or_neither(self) -> None:
        """`BattleManager.DraggableTime` is reachable no other way.

        No config key, no master-data entry, no server field: it is a private
        static float written once in the class constructor. Both shipped ABIs
        carry the constant as the float's high half alone -- an AArch64 `MOVZ`
        with a 16-bit shift, and an ARM `MOVT` beside a `MOVW #0` -- so one
        instruction each changes. Both are patched or the knob would mean one
        thing on a 64-bit device and another on a 32-bit one.
        """
        self.assertEqual([], drag_time_patches(STOCK_DRAG_TIME_SECONDS))
        patches = drag_time_patches(6.0)
        self.assertEqual(
            [member for member, _ in DRAG_TIME_SITES],
            [entry["member"] for entry in patches],
        )
        self.assertEqual(
            ["0a10a852", "802044e3"], [entry["expected_hex"] for entry in patches],
        )
        self.assertEqual(
            ["0a18a852", "c02044e3"], [entry["replacement_hex"] for entry in patches],
        )
        # Every replacement decodes back to the seconds that produced it.
        for seconds in (1.0, 2.5, 4.0, 6.0, 8.0, 30.0):
            arm64, v7a = (entry["replacement_hex"] for entry in drag_time_patches(seconds)) if seconds != 4.0 else ("0a10a852", "802044e3")
            arm64_high = (struct.unpack("<I", bytes.fromhex(arm64))[0] >> 5) & 0xFFFF
            v7a_word = struct.unpack("<I", bytes.fromhex(v7a))[0]
            v7a_high = (((v7a_word >> 16) & 0xF) << 12) | (v7a_word & 0xFFF)
            with self.subTest(seconds):
                self.assertEqual(arm64_high, v7a_high, "the two ABIs must carry the same constant")
                self.assertEqual(
                    seconds,
                    struct.unpack("<f", struct.pack("<I", arm64_high << 16))[0],
                )

    def test_drag_time_expectations_match_the_reviewed_apk(self) -> None:
        """The offsets are only meaningful against the build they came from."""
        apk = Path("local-input/terra-battle-5.5.7-170.apk")
        if not apk.is_file():
            self.skipTest("reviewed APK is not present on this machine")
        with zipfile.ZipFile(apk) as archive:
            for entry in drag_time_patches(6.0):
                member = archive.read(entry["member"])
                offset = entry["offset"]
                with self.subTest(entry["member"]):
                    self.assertEqual(
                        entry["expected_hex"],
                        member[offset:offset + 4].hex(),
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
        """Still neutralized, but no longer believed to be the crash.

        A Galaxy S24 FE log put `UnityIAP: Billing service connected.` directly
        before the fatal and this project read it as the cause. Withdrawn:
        billing's connection is a real class in the dex, and a class inherits
        an interface's `default` methods, so it cannot raise this error. Only a
        `java.lang.reflect.Proxy` can, and Unity makes exactly one -- see
        `UnityNativeBindPatchTest`. Covering billing costs nothing, so it stays.
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


class UnityNativeBindPatchTest(unittest.TestCase):
    """The bind that carries the crash, which the dex edits cannot reach.

    Unity's own `libunity.so` binds Play Services from native code to read the
    advertising ID, using its own copy of the action string. A Galaxy S26 on
    Android 16 crashed with all eighteen dex actions already rewritten, which is
    what identified this one: the dex copy was inert and Unity's still resolved.
    """

    #: Unity's copy sits beside its package name as a separate NUL-terminated
    #: string rather than a merged suffix. The fixture reproduces that layout so
    #: a patch that reached into a neighbour would be visible here.
    NEIGHBOUR = b"com.google.android.gms"

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.payloads = {
            member: b"\0filler\0" + UNITY_ADVERTISING_ID_ACTION + b"\0" + self.NEIGHBOUR + b"\0"
            for member in UNITY_BIND_ACTION_MEMBERS
        }
        self.source = self.root / "source.apk"
        with zipfile.ZipFile(self.source, "w") as archive:
            for member, payload in self.payloads.items():
                archive.writestr(member, payload)
        self.digest = patch(
            "liminal_gate.legacy_client_apk_plan._sha256_member",
            side_effect=lambda apk, member: UNITY_BIND_ACTION_MEMBERS[member],
        )
        self.digest.start()
        self.addCleanup(self.digest.stop)

    def _apply(self, member: str, patches: list[dict]) -> bytes:
        payload = bytearray(self.payloads[member])
        for item in patches:
            if item["member"] != member:
                continue
            offset, expected = item["offset"], bytes.fromhex(item["expected_hex"])
            self.assertEqual(expected, payload[offset:offset + len(expected)])
            payload[offset:offset + len(expected)] = bytes.fromhex(item["replacement_hex"])
        return bytes(payload)

    def test_both_abis_are_patched(self) -> None:
        """A device running either one makes the same bind."""
        patches = _disabled_unity_bind_action_patches(self.source)
        self.assertEqual(
            sorted(UNITY_BIND_ACTION_MEMBERS), sorted(item["member"] for item in patches),
        )
        self.assertEqual(2, len(patches))

    def test_each_is_a_single_byte_edit_of_the_action_head(self) -> None:
        """The head, not the tail: a C toolchain may tail-merge string literals,
        so a shorter string can be a pointer into this one's suffix. A head is
        never shared that way."""
        for item in _disabled_unity_bind_action_patches(self.source):
            with self.subTest(member=item["member"]):
                self.assertEqual(UNITY_ADVERTISING_ID_ACTION[:1].hex(), item["expected_hex"])
                self.assertEqual(INERT_ACTION_BYTE.hex(), item["replacement_hex"])
                # Nothing here may repair a dex header; these are ELF members.
                self.assertNotIn("repair_dex_header", item)

    def test_applying_it_clears_the_action_and_spares_its_neighbour(self) -> None:
        patches = _disabled_unity_bind_action_patches(self.source)
        for member in UNITY_BIND_ACTION_MEMBERS:
            with self.subTest(member=member):
                patched = self._apply(member, patches)
                self.assertNotIn(UNITY_ADVERTISING_ID_ACTION, patched)
                self.assertIn(INERT_ACTION_BYTE + UNITY_ADVERTISING_ID_ACTION[1:], patched)
                # The package name is a separate string and must survive intact.
                self.assertIn(b"\0" + self.NEIGHBOUR + b"\0", patched)
                self.assertEqual(len(self.payloads[member]), len(patched))

    def test_refuses_a_member_that_was_not_reviewed(self) -> None:
        with patch(
            "liminal_gate.legacy_client_apk_plan._sha256_member", return_value="0" * 64,
        ):
            with self.assertRaises(PlanGenerationError) as raised:
                _disabled_unity_bind_action_patches(self.source)
        self.assertIn("does not match the supported final client", str(raised.exception))

    def test_refuses_a_member_carrying_the_action_twice(self) -> None:
        """Two would mean a second call site this reasoning never looked at."""
        member = ARMV7_UNITY_MEMBER
        doubled = self.root / "doubled.apk"
        with zipfile.ZipFile(doubled, "w") as archive:
            for name, payload in self.payloads.items():
                archive.writestr(
                    name, payload + UNITY_ADVERTISING_ID_ACTION + b"\0" if name == member else payload,
                )
        with self.assertRaises(PlanGenerationError) as raised:
            _disabled_unity_bind_action_patches(doubled)
        self.assertIn("exactly once, found 2", str(raised.exception))

    def test_refuses_a_member_missing_the_action(self) -> None:
        empty = self.root / "empty.apk"
        with zipfile.ZipFile(empty, "w") as archive:
            for name in self.payloads:
                archive.writestr(name, b"\0nothing here\0")
        with self.assertRaises(PlanGenerationError) as raised:
            _disabled_unity_bind_action_patches(empty)
        self.assertIn("exactly once, found 0", str(raised.exception))

    def test_the_dex_carries_its_own_separate_copy(self) -> None:
        """Both copies exist and both must be rewritten; patching either alone
        leaves a live bind. This is the defect the S26 report exposed."""
        self.assertIn(UNITY_ADVERTISING_ID_ACTION, DISABLED_BIND_ACTIONS)
