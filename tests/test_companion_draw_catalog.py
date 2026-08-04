from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from liminal_gate.companion_draw_catalog import build_bundled_companion_draw_policy, CompanionDrawCatalogError, load_companion_draw_catalog
from tests.support import write_json


class CompanionDrawCatalogTest(unittest.TestCase):
    def test_loads_ordered_user_local_pool(self) -> None:
        document = {"schema_version": 1, "provenance": "user-supplied", "item_slots": 1, "ticket_item_id": 1, "energy_cost": 3, "max_owned": 10, "draws": [{"companion_id": 1, "weight": 1}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "draw.json"
            write_json(path, document)
            catalog = load_companion_draw_catalog(path)
        self.assertEqual((1, 3), (catalog.ticket_item_id, catalog.energy_cost))

    def test_loads_equivalent_toml_pool(self) -> None:
        document = """schema_version = 1
provenance = "user-supplied"
item_slots = 1
ticket_item_id = 1
energy_cost = 3
max_owned = 10

[[draws]]
companion_id = 1
weight = 1
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "draw.toml"
            path.write_text(document, encoding="utf-8")
            catalog = load_companion_draw_catalog(path)
        self.assertEqual(1, catalog.draws[0].companion_id)

    def test_rejects_unordered_pool(self) -> None:
        document = {"schema_version": 1, "provenance": "user-supplied", "item_slots": 1, "ticket_item_id": 1, "energy_cost": 1, "max_owned": 1, "draws": [{"companion_id": 2, "weight": 1}, {"companion_id": 1, "weight": 1}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "draw.json"
            write_json(path, document)
            with self.assertRaises(CompanionDrawCatalogError):
                load_companion_draw_catalog(path)


class BundledCompanionDrawPolicyTest(unittest.TestCase):
    """The bundled pool must match the recovered rare-slot membership."""

    def setUp(self) -> None:
        self.catalog = build_bundled_companion_draw_policy()

    def test_declares_the_recovered_rare_slot_pool(self) -> None:
        # 114 of BuddyDatabase's 497 records carry SlotKind.Rare.
        self.assertEqual(114, len(self.catalog.draws))
        ids = [draw.companion_id for draw in self.catalog.draws]
        self.assertEqual(sorted(set(ids)), ids)
        self.assertTrue(all(companion_id > 0 for companion_id in ids))

    def test_carries_the_recovered_costs_and_ceiling(self) -> None:
        self.assertEqual(181, self.catalog.item_slots)
        self.assertEqual(112, self.catalog.ticket_item_id)
        self.assertEqual(3, self.catalog.energy_cost)
        self.assertEqual(1000, self.catalog.max_owned)

    def test_selection_is_uniform_local_policy_not_historical_odds(self) -> None:
        # The bundled Pact policy makes the same choice for the same reason:
        # pool membership is recovered, per-rarity base rates are not asserted.
        self.assertEqual({1}, {draw.weight for draw in self.catalog.draws})
