from __future__ import annotations

import unittest

from liminal_gate.pact_banner_importer import MAGIC, _calc_index, _transform_byte, decrypt_enca


class PactBannerImporterTest(unittest.TestCase):
    def test_decrypts_enca_with_the_client_index_permutation(self) -> None:
        plaintext = bytes(range(1, 250))
        encrypted = bytearray(MAGIC + bytes(len(plaintext)))
        for index, value in enumerate(plaintext):
            encrypted[len(plaintext) + 3 - _calc_index(index, len(plaintext))] = _transform_byte(value)
        self.assertEqual(plaintext, decrypt_enca(bytes(encrypted), bytes(range(256))))

    def test_passes_through_unencrypted_bundles(self) -> None:
        self.assertEqual(b"UnityFS\x00local", decrypt_enca(b"UnityFS\x00local", bytes(range(256))))
