from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from liminal_gate.coin_creeps_banner import (
    ALIASES,
    CoinCreepsBannerError,
    _encrypt_enca,
    _rename_serialized_file,
    _serialized_file_name,
    hashed_resource_name,
    prepare_coin_creeps_banners,
)
from liminal_gate.pact_banner_importer import decrypt_enca


class _SerializedFile:
    def __init__(self, name: str) -> None:
        self.name = name


class _Bundle:
    def __init__(self, files: dict[str, object]) -> None:
        self.files = files


class CoinCreepsBannerTest(unittest.TestCase):
    def test_hash_names_match_the_recovered_client_formula(self) -> None:
        self.assertEqual(
            (
                "824301495dd437d0dcd4392231844364sp1003-1.bin",
                "de26f7fec9c654a0c8a7302adf5c5a50sp1003-2.bin",
                "ba8859ea26aaefe705692282b438b0a2sp1003-3.bin",
            ),
            tuple(hashed_resource_name(alias) for alias in ALIASES),
        )

    def test_enca_encoder_is_the_exact_inverse_of_the_reviewed_decoder(self) -> None:
        forward = bytes((index * 73 + 19) % 256 for index in range(256))
        inverse = bytearray(256)
        for index, value in enumerate(forward):
            inverse[value] = index
        for payload in (b"x", bytes(range(256)), bytes(range(256)) * 3 + b"tail"):
            self.assertEqual(payload, decrypt_enca(_encrypt_enca(payload, forward), bytes(inverse)))

    def test_each_derived_bundle_gets_its_own_internal_unity_file(self) -> None:
        """Unity loads a bundle by the file inside it, so sharing one blanks cards.

        Three cards derived from a single retained bundle would otherwise all
        carry the source's internal name. The client keeps a bundle loaded
        while it reads the texture and unloads it on a delay, so whichever
        overlapped a neighbour would fail to load and render blank until the
        timing happened to change.
        """
        source = "CAB-14adb4c29162ab0d738835335430ce7e"
        derived = []
        for alias in ALIASES:
            filename = hashed_resource_name(alias)
            serialized = _SerializedFile(source)
            bundle = _Bundle({source: serialized})
            _rename_serialized_file(bundle, filename)
            self.assertEqual([_serialized_file_name(filename)], list(bundle.files))
            self.assertEqual(_serialized_file_name(filename), serialized.name)
            self.assertIs(serialized, bundle.files[serialized.name])
            derived.append(serialized.name)
        self.assertEqual(len(ALIASES), len(set(derived)))
        self.assertNotIn(source, derived)
        self.assertTrue(all(name.startswith("CAB-") for name in derived))

    def test_an_unreviewed_bundle_layout_is_refused_rather_than_renamed(self) -> None:
        for files in ({}, {"CAB-one": _SerializedFile("CAB-one"), "CAB-two": _SerializedFile("CAB-two")}):
            with self.assertRaisesRegex(CoinCreepsBannerError, "exactly one internal Unity file"):
                _rename_serialized_file(_Bundle(files), "card.bin")
        with self.assertRaisesRegex(CoinCreepsBannerError, "unexpected internal Unity file name"):
            _rename_serialized_file(_Bundle({"data.resS": _SerializedFile("data.resS")}), "card.bin")

    def test_exact_operator_bundles_need_no_fallback_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            banners = root / "resources" / "Banner"
            banners.mkdir(parents=True)
            generated = root / "public" / "banner_resources"
            generated.mkdir(parents=True)
            for alias in ALIASES:
                (banners / hashed_resource_name(alias)).write_bytes(b"exact")
                (generated / hashed_resource_name(alias)).write_bytes(b"stale fallback")
            output = prepare_coin_creeps_banners(root / "game.apk", root / "resources", root / "public")
            self.assertEqual([], list(output.iterdir()))

    def test_missing_exact_and_fallback_bundle_fails_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "resources" / "Banner").mkdir(parents=True)
            with self.assertRaisesRegex(CoinCreepsBannerError, "sp3003-1"):
                prepare_coin_creeps_banners(root / "game.apk", root / "resources", root / "public")
