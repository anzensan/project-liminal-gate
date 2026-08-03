from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from liminal_gate.coin_creeps_banner import (
    ALIASES,
    CoinCreepsBannerError,
    _encrypt_enca,
    hashed_resource_name,
    prepare_coin_creeps_banners,
)
from liminal_gate.pact_banner_importer import decrypt_enca


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
