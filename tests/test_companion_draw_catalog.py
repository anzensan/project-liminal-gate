from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from liminal_gate.companion_draw_catalog import _NORMAL_SLOT_CLASSES, _RARE_SLOT_CLASSES, build_bundled_companion_draw_policy, CompanionDrawCatalogError, load_companion_draw_catalog
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
    """The bundled pools must match the two recorded pool rosters."""

    def setUp(self) -> None:
        self.catalog = build_bundled_companion_draw_policy()

    def test_declares_the_recorded_rare_slot_pool(self) -> None:
        # The Companions of Truth roster: 177 of BuddyDatabase's 497 records.
        self.assertEqual(177, len(self.catalog.rare_draws))
        ids = [draw.companion_id for draw in self.catalog.rare_draws]
        self.assertEqual(sorted(set(ids)), ids)
        self.assertTrue(all(companion_id > 0 for companion_id in ids))

    def test_declares_the_recorded_normal_slot_pool(self) -> None:
        # The Companions of Fellowship roster: 145 records, the pool the Coin
        # pull and the Fellowship Ticket variant draw from.
        self.assertEqual(145, len(self.catalog.normal_draws))
        ids = [draw.companion_id for draw in self.catalog.normal_draws]
        self.assertEqual(sorted(set(ids)), ids)

    def test_the_two_pools_share_their_a_and_b_tier(self) -> None:
        # The pools are not disjoint, and reading `SlotKind` as though they
        # were is what stranded 63 Companions in neither pool. The Companions
        # of Fellowship page states the rule the slot field does not: "All A
        # and B Class Companions may also be found in the Companions of
        # Truth."
        normal = {draw.companion_id for draw in self.catalog.normal_draws}
        rare = {draw.companion_id for draw in self.catalog.rare_draws}
        a_and_b = set(_RARE_SLOT_CLASSES["a"]) | set(_RARE_SLOT_CLASSES["b"])
        self.assertEqual(63, len(normal & rare))
        # Everything the pools share is an A or a B. C and D stay Fellowship
        # -only; S upward stay Truth-only.
        self.assertEqual(normal & rare, normal & a_and_b)
        # 41 C, 40 D, and Skullsplitter -- the one B the Fellowship page lists
        # and the Truth page does not -- are what Truth never offers.
        self.assertEqual(82, len(normal - rare))
        self.assertIn(72, normal)
        self.assertNotIn(72, rare)
        # The Truth-only half of the shared tier: the "+" upgrade targets the
        # Fellowship page does not list.
        self.assertEqual(32, len(a_and_b - normal))

    def test_carries_the_recovered_costs_and_ceiling(self) -> None:
        self.assertEqual(181, self.catalog.item_slots)
        self.assertEqual(112, self.catalog.ticket_item_id)
        self.assertEqual(81, self.catalog.normal_ticket_item_id)
        self.assertEqual(2000, self.catalog.coin_cost)
        self.assertEqual(3, self.catalog.energy_cost)
        self.assertEqual(1000, self.catalog.max_owned)

    def test_each_wire_kind_names_its_own_pool_price_and_ticket(self) -> None:
        self.assertEqual(self.catalog.normal_draws, self.catalog.draws_for_kind(0))
        self.assertEqual(self.catalog.normal_draws, self.catalog.draws_for_kind(20))
        self.assertEqual(self.catalog.rare_draws, self.catalog.draws_for_kind(1))
        self.assertEqual(self.catalog.rare_draws, self.catalog.draws_for_kind(21))
        self.assertEqual([("coins", 2000), ("coins", 2000), ("energy", 3), ("energy", 3)], [self.catalog.cost_for_kind(kind) for kind in (0, 20, 1, 21)])
        self.assertEqual([81, 81, 112, 112], [self.catalog.ticket_item_for_kind(kind) for kind in (0, 20, 1, 21)])
        self.assertEqual(((), None, None), (self.catalog.draws_for_kind(10), self.catalog.cost_for_kind(10), self.catalog.ticket_item_for_kind(10)))

    def test_rare_pool_groups_match_the_recorded_class_counts(self) -> None:
        # The counts the Companions of Truth page states, class by class. A
        # group of the wrong size means the membership or the rarity was
        # transcribed wrong. A and B read 30 and 2 until 2026-08-18, because
        # the roster was recovered from `SlotKind` as though the two pools
        # partitioned the database; B holding two members handed Healing Wand
        # and Regen Bangle 24.5% of every pull each.
        self.assertEqual(
            {"z": 19, "ss": 13, "s": 50, "a": 56, "b": 39},
            {name: len(ids) for name, ids in _RARE_SLOT_CLASSES.items()},
        )
        grouped = [companion_id for ids in _RARE_SLOT_CLASSES.values() for companion_id in ids]
        self.assertEqual(len(grouped), len(set(grouped)))
        self.assertEqual(sorted(grouped), [draw.companion_id for draw in self.catalog.rare_draws])

    def test_rare_selection_follows_the_displayed_class_shares(self) -> None:
        # Z 3%, SS 8%, S 10%, A 30%, B 49% -- the rates the service displayed
        # in-game. Uniform selection over this pool would instead return 10.7%
        # Z and 22.0% B, inverting the two commonest outcomes.
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

    def test_no_rare_companion_dominates_its_class(self) -> None:
        # The share a class carries is split across its members, so no single
        # Companion may exceed its class share divided by the smallest class.
        # B at 49% over two members put Healing Wand at 24.5% of every pull --
        # about five of every ten-pull -- which is what testers reported.
        weights = {draw.companion_id: draw.weight for draw in self.catalog.rare_draws}
        total = sum(weights.values())
        self.assertAlmostEqual(0.49 / 39, weights[1] / total, places=6)
        self.assertAlmostEqual(0.49 / 39, weights[6] / total, places=6)
        self.assertLess(max(weights.values()) / total, 0.02)

    def test_normal_pool_groups_match_the_recorded_class_counts(self) -> None:
        self.assertEqual(
            {"a": 26, "b": 38, "c": 41, "d": 40},
            {name: len(ids) for name, ids in _NORMAL_SLOT_CLASSES.items()},
        )
        grouped = [companion_id for ids in _NORMAL_SLOT_CLASSES.values() for companion_id in ids]
        self.assertEqual(len(grouped), len(set(grouped)))
        self.assertEqual(sorted(grouped), [draw.companion_id for draw in self.catalog.normal_draws])

    def test_normal_selection_follows_the_chosen_class_shares(self) -> None:
        # A 8%, B 12%, C 30%, D 50% -- chosen policy, not a record. No
        # displayed rate for this pool survives.
        weights = {draw.companion_id: draw.weight for draw in self.catalog.normal_draws}
        total = sum(weights.values())
        for name, share in (("a", 0.08), ("b", 0.12), ("c", 0.30), ("d", 0.50)):
            drawn = sum(weights[companion_id] for companion_id in _NORMAL_SLOT_CLASSES[name])
            self.assertAlmostEqual(share, drawn / total, places=6)

    def test_normal_selection_is_even_within_a_class(self) -> None:
        for ids in _NORMAL_SLOT_CLASSES.values():
            weights = {draw.weight for draw in self.catalog.normal_draws if draw.companion_id in ids}
            self.assertEqual(1, len(weights))

    def test_energy_beats_coins_for_every_class_the_pools_share(self) -> None:
        """The property the Normal share table exists to satisfy.

        A and B are the same Companions in both pools, so a 2,000-Coin pull
        must not out-draw a 3-Energy one for either class. Uniform selection
        over the Normal roster failed this on A -- 0.690% against Truth's
        0.536% -- which is the whole reason that pool carries a table. This
        asserts the property rather than the numbers, so retuning either
        table stays free as long as the ordering survives.
        """
        rare = {draw.companion_id: draw.weight for draw in self.catalog.rare_draws}
        normal = {draw.companion_id: draw.weight for draw in self.catalog.normal_draws}
        rare_total, normal_total = sum(rare.values()), sum(normal.values())
        for name in ("a", "b"):
            shared = set(_RARE_SLOT_CLASSES[name]) & set(_NORMAL_SLOT_CLASSES[name])
            self.assertTrue(shared, name)
            for companion_id in shared:
                self.assertGreater(
                    rare[companion_id] / rare_total,
                    normal[companion_id] / normal_total,
                    f"Companion {companion_id} ({name.upper()}) is likelier on Coins than on Energy",
                )
