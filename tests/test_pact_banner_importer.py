from __future__ import annotations

import unittest
from pathlib import Path
import tempfile

from liminal_gate.pact_banner_importer import MAGIC, PactBannerImportError, _calc_index, _find_banner_bundle, _transform_byte, decrypt_enca


class PactBannerImporterTest(unittest.TestCase):
    def test_decrypts_enca_with_the_client_index_permutation(self) -> None:
        plaintext = bytes(range(1, 250))
        encrypted = bytearray(MAGIC + bytes(len(plaintext)))
        for index, value in enumerate(plaintext):
            encrypted[len(plaintext) + 3 - _calc_index(index, len(plaintext))] = _transform_byte(value)
        self.assertEqual(plaintext, decrypt_enca(bytes(encrypted), bytes(range(256))))

    def test_passes_through_unencrypted_bundles(self) -> None:
        self.assertEqual(b"UnityFS\x00local", decrypt_enca(b"UnityFS\x00local", bytes(range(256))))

    def test_locates_a_unique_banner_by_logical_suffix(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            banners = root / "Banner"
            banners.mkdir()
            expected = banners / "different-cache-prefixsl_truth_01.bin"
            expected.write_bytes(b"local")
            self.assertEqual(expected, _find_banner_bundle(root, "sl_truth_01"))
            with self.assertRaisesRegex(PactBannerImportError, "slb_truth_01"):
                _find_banner_bundle(root, "slb_truth_01")
