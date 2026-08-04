from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from liminal_gate.companion_catalog import build_bundled_companion_policy, CompanionCatalogError, load_companion_catalog
from tests.support import write_json


class CompanionCatalogTest(unittest.TestCase):
    def test_loads_ordered_user_local_masters(self) -> None:
        document = {"schema_version": 1, "provenance": "user-supplied", "coin_cap": 999, "masters": [{"companion_id": 1, "base_coins": 2}, {"companion_id": 2, "base_coins": 3}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "companions.json"
            write_json(path, document)
            catalog = load_companion_catalog(path)
        self.assertEqual((999, 3), (catalog.coin_cap, catalog.masters[2].base_coins))

    def test_rejects_unordered_or_duplicate_masters(self) -> None:
        document = {"schema_version": 1, "provenance": "user-supplied", "coin_cap": 0, "masters": [{"companion_id": 2, "base_coins": 0}, {"companion_id": 1, "base_coins": 0}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "companions.json"
            write_json(path, document)
            with self.assertRaises(CompanionCatalogError):
                load_companion_catalog(path)


class BundledCompanionPolicyTest(unittest.TestCase):
    """The bundled masters must match the recovered BuddyDatabase values."""

    def setUp(self) -> None:
        self.catalog = build_bundled_companion_policy()

    def test_declares_every_recovered_master(self) -> None:
        self.assertEqual(497, len(self.catalog.masters))
        ids = sorted(self.catalog.masters)
        self.assertEqual(list(range(1, 498)), ids)
        self.assertEqual(99999999, self.catalog.coin_cap)

    def test_every_master_has_a_positive_sale_value(self) -> None:
        # A sale pays base_coins times the instance level, so a zero here would
        # silently make a Companion worthless rather than refuse the sale.
        for companion_id, master in self.catalog.masters.items():
            with self.subTest(companion_id=companion_id):
                self.assertGreater(master.base_coins, 0)

    def test_carries_the_recovered_values(self) -> None:
        self.assertEqual(200, self.catalog.masters[1].base_coins)
        self.assertEqual(250, self.catalog.masters[2].base_coins)
        self.assertEqual(400, self.catalog.masters[3].base_coins)
