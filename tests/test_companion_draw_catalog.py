from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from liminal_gate.companion_draw_catalog import _RARE_SLOT_CLASSES, build_bundled_companion_draw_policy, CompanionDrawCatalogError, load_companion_draw_catalog
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


class CompanionDrawCatalogKindTest(unittest.TestCase):
    """A user-supplied catalog answers for the Rare pool and nothing else."""

    def setUp(self) -> None:
        document = {"schema_version": 1, "provenance": "user-supplied", "item_slots": 5, "ticket_item_id": 2, "energy_cost": 3, "max_owned": 10, "draws": [{"companion_id": 1, "weight": 1}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "draw.json"
            write_json(path, document)
            self.catalog = load_companion_draw_catalog(path)

    def test_answers_for_the_energy_pool_and_its_ticket(self) -> None:
        for kind in (1, 21):
            self.assertEqual(1, len(self.catalog.draws_for_kind(kind)))
            self.assertEqual(("energy", 3), self.catalog.cost_for_kind(kind))
            self.assertEqual(2, self.catalog.ticket_item_for_kind(kind))

    def test_leaves_the_coin_pool_undescribed(self) -> None:
        # Schema version 1 has no Normal pool, so the route must refuse those
        # kinds rather than settle them out of the Rare one.
        for kind in (0, 20):
            self.assertEqual((), self.catalog.draws_for_kind(kind))
            self.assertIsNone(self.catalog.cost_for_kind(kind))
            self.assertIsNone(self.catalog.ticket_item_for_kind(kind))


class BundledCompanionDrawPolicyTest(unittest.TestCase):
    """The bundled pools must match the recovered slot-kind membership."""

    def setUp(self) -> None:
        self.catalog = build_bundled_companion_draw_policy()

    def test_declares_the_recovered_rare_slot_pool(self) -> None:
        # 114 of BuddyDatabase's 497 records carry SlotKind.Rare.
        self.assertEqual(114, len(self.catalog.rare_draws))
        ids = [draw.companion_id for draw in self.catalog.rare_draws]
        self.assertEqual(sorted(set(ids)), ids)
        self.assertTrue(all(companion_id > 0 for companion_id in ids))

    def test_declares_the_recovered_normal_slot_pool(self) -> None:
        # 81 more carry SlotKind.Normal, the pool the Coin pull and the
        # Fellowship Ticket variant draw from. The two pools are disjoint.
        self.assertEqual(81, len(self.catalog.normal_draws))
        ids = [draw.companion_id for draw in self.catalog.normal_draws]
        self.assertEqual(sorted(set(ids)), ids)
        self.assertFalse({draw.companion_id for draw in self.catalog.normal_draws} & {draw.companion_id for draw in self.catalog.rare_draws})

    def test_carries_the_recovered_costs_and_ceiling(self) -> None:
        self.assertEqual(181, self.catalog.item_slots)
        self.assertEqual(112, self.catalog.ticket_item_id)
        self.assertEqual(81, self.catalog.normal_ticket_item_id)
        self.assertEqual(3000, self.catalog.coin_cost)
        self.assertEqual(3, self.catalog.energy_cost)
        self.assertEqual(1000, self.catalog.max_owned)

    def test_each_wire_kind_names_its_own_pool_price_and_ticket(self) -> None:
        self.assertEqual(self.catalog.normal_draws, self.catalog.draws_for_kind(0))
        self.assertEqual(self.catalog.normal_draws, self.catalog.draws_for_kind(20))
        self.assertEqual(self.catalog.rare_draws, self.catalog.draws_for_kind(1))
        self.assertEqual(self.catalog.rare_draws, self.catalog.draws_for_kind(21))
        self.assertEqual([("coins", 3000), ("coins", 3000), ("energy", 3), ("energy", 3)], [self.catalog.cost_for_kind(kind) for kind in (0, 20, 1, 21)])
        self.assertEqual([81, 81, 112, 112], [self.catalog.ticket_item_for_kind(kind) for kind in (0, 20, 1, 21)])
        self.assertEqual(((), None, None), (self.catalog.draws_for_kind(10), self.catalog.cost_for_kind(10), self.catalog.ticket_item_for_kind(10)))

    def test_rare_pool_groups_match_the_recovered_class_counts(self) -> None:
        # The community record and the recovered `BuddyData.rarity` field agree
        # on this split, which is what lets the bundle carry the map at all. A
        # group of the wrong size means one of the two was transcribed wrong.
        self.assertEqual(
            {"z": 19, "ss": 13, "s": 50, "a": 30, "b": 2},
            {name: len(ids) for name, ids in _RARE_SLOT_CLASSES.items()},
        )
        grouped = [companion_id for ids in _RARE_SLOT_CLASSES.values() for companion_id in ids]
        self.assertEqual(len(grouped), len(set(grouped)))
        self.assertEqual(sorted(grouped), [draw.companion_id for draw in self.catalog.rare_draws])

    def test_rare_selection_follows_the_displayed_class_shares(self) -> None:
        # Z 3%, SS 8%, S 10%, A 30%, B 49% -- the rates the service displayed
        # in-game. Uniform selection over this pool would instead return 16.7%
        # Z and 1.8% B, inverting the two commonest outcomes.
        weights = {draw.companion_id: draw.weight for draw in self.catalog.rare_draws}
        total = sum(weights.values())
        for name, share in (("z", 0.03), ("ss", 0.08), ("s", 0.10), ("a", 0.30), ("b", 0.49)):
            drawn = sum(weights[companion_id] for companion_id in _RARE_SLOT_CLASSES[name])
            self.assertAlmostEqual(share, drawn / total, places=6)

    def test_rare_selection_is_even_within_a_class(self) -> None:
        # The displayed table gave a per-Companion rate this record does not
        # preserve, so an even split within the class is the local policy.
        for ids in _RARE_SLOT_CLASSES.values():
            weights = {draw.weight for draw in self.catalog.rare_draws if draw.companion_id in ids}
            self.assertEqual(1, len(weights))

    def test_normal_selection_stays_uniform_local_policy(self) -> None:
        # No displayed-rate record was found for the Coin pool, so it keeps the
        # uniform weight rather than borrowing the Rare pool's table.
        self.assertEqual({1}, {draw.weight for draw in self.catalog.normal_draws})
