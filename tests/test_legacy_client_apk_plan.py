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
    GOOGLE_SERVICE_PREFIX,
    INERT_SERVICE_PREFIX,
    _google_service_patches,
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

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.source = self.root / "source.apk"
        # A dex-shaped fixture holding every action once, the two descriptors,
        # and an unrelated class name sharing the same 23-byte prefix.
        body = b"\0".join((
            *GOOGLE_SERVICE_BIND_ACTIONS, *self.DESCRIPTORS,
            b"com.google.android.gms.common.api.internal.LifecycleCallback",
        ))
        self.dex = b"dex\n035\0" + b"\0" * 24 + body
        with zipfile.ZipFile(self.source, "w") as archive:
            archive.writestr("classes.dex", self.dex)
        self.digest = patch(
            "liminal_gate.legacy_client_apk_plan._sha256_member",
            side_effect=lambda apk, member: (
                FINAL_CLIENT_DEX_SHA256 if member == CLIENT_DEX_MEMBER else FINAL_ARM64_UNITY_SHA256
            ),
        )
        self.digest.start()
        self.addCleanup(self.digest.stop)

    def test_every_action_is_rewritten_exactly_once(self) -> None:
        patches = _google_service_patches(self.source)
        self.assertEqual(len(GOOGLE_SERVICE_BIND_ACTIONS), len(patches))
        self.assertEqual({CLIENT_DEX_MEMBER}, {item["member"] for item in patches})
        self.assertEqual(len(patches), len({item["offset"] for item in patches}))
        for item in patches:
            self.assertEqual(GOOGLE_SERVICE_PREFIX.hex(), item["expected_hex"])
            self.assertEqual(INERT_SERVICE_PREFIX.hex(), item["replacement_hex"])
            self.assertTrue(item["repair_dex_header"])

    def test_the_replacement_is_the_same_length_so_the_dex_cannot_reflow(self) -> None:
        self.assertEqual(len(GOOGLE_SERVICE_PREFIX), len(INERT_SERVICE_PREFIX))

    def test_applying_it_clears_the_actions_and_spares_the_descriptors(self) -> None:
        patched = bytearray(self.dex)
        for item in _google_service_patches(self.source):
            offset = item["offset"]
            patched[offset:offset + len(GOOGLE_SERVICE_PREFIX)] = INERT_SERVICE_PREFIX
        for action in GOOGLE_SERVICE_BIND_ACTIONS:
            self.assertNotIn(action, patched)
        for descriptor in self.DESCRIPTORS:
            self.assertIn(descriptor, patched, "rewriting a binder descriptor would break the handshake")
        self.assertIn(b"com.google.android.gms.common.api.internal.LifecycleCallback", patched)

    def test_refuses_a_dex_that_was_not_reviewed(self) -> None:
        self.digest.stop()
        with patch("liminal_gate.legacy_client_apk_plan._sha256_member", return_value="0" * 64):
            with self.assertRaisesRegex(PlanGenerationError, "client dex does not match"):
                _google_service_patches(self.source)
        self.digest.start()

    def test_refuses_a_dex_holding_an_action_twice(self) -> None:
        doubled = self.root / "doubled.apk"
        with zipfile.ZipFile(doubled, "w") as archive:
            archive.writestr(CLIENT_DEX_MEMBER, self.dex + b"\0" + GOOGLE_SERVICE_BIND_ACTIONS[0])
        with self.assertRaisesRegex(PlanGenerationError, "exactly one"):
            _google_service_patches(doubled)

    def test_the_two_binder_descriptors_are_not_in_the_patch_set(self) -> None:
        """Stated once here so shortening the set cannot quietly include them."""
        for descriptor in self.DESCRIPTORS:
            self.assertNotIn(descriptor, GOOGLE_SERVICE_BIND_ACTIONS)
