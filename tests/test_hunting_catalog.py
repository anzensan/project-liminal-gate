from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from liminal_gate.hunting_catalog import (
    HuntingCatalogError, build_bundled_hunting_policy, hunting_settlement_within_bounds,
    load_hunting_catalog,
)
from liminal_gate.save_validation import ITEM_SLOTS, MAX_ITEM_STACK
from tests.support import write_json


def document(**overrides) -> dict:
    stage = {
        "family": "pudding", "chapter": 1001, "section": 1,
        "stamina": 3, "coins": 0, "entry_item_id": 0, "entry_item_count": 0,
        "unlock_chapter": 1, "unlock_section": 1, "max_coins": 0, "max_exp": 0,
        "max_items_total": 5, "item_maxima": {"2": 5},
    }
    stage.update(overrides.pop("stage", {}))
    base = {
        "schema_version": 1, "provenance": "user-supplied",
        "item_slots": 8, "max_stack": 99, "stages": [stage],
    }
    base.update(overrides)
    return base


class HuntingCatalogTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary_directory.name) / "hunting.json"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def load(self, doc: dict):
        write_json(self.path, doc)
        return load_hunting_catalog(self.path)

    def test_loads_a_well_formed_operator_catalog(self) -> None:
        catalog = self.load(document())
        stage = catalog.by_identity()[(1001, 1)]
        self.assertEqual(("pudding", 3, {2: 5}), (stage.family, stage.stamina, stage.item_maxima))
        self.assertEqual({}, stage.entry_items())

    def test_an_entry_item_is_declared_as_a_pair(self) -> None:
        catalog = self.load(document(stage={"entry_item_id": 5, "entry_item_count": 1}))
        self.assertEqual({5: 1}, catalog.by_identity()[(1001, 1)].entry_items())
        for half in ({"entry_item_id": 5}, {"entry_item_count": 1}):
            with self.subTest(half=half), self.assertRaises(HuntingCatalogError):
                self.load(document(stage=half))

    def test_rejects_provenance_schema_and_shape_errors(self) -> None:
        for label, doc in (
            ("bundled provenance", document(provenance="bundled")),
            ("future schema", document(schema_version=2)),
            ("no stages", document(stages=[])),
            ("unknown field", document(stage={"extra": 1})),
            ("negative stamina", document(stage={"stamina": -1})),
            ("zero section", document(stage={"section": 0})),
            ("zero unlock chapter", document(stage={"unlock_chapter": 0})),
        ):
            with self.subTest(label), self.assertRaises(HuntingCatalogError):
                self.load(doc)

    def test_rejects_bounds_outside_the_declared_inventory(self) -> None:
        for label, doc in (
            ("item beyond slots", document(stage={"item_maxima": {"99": 1}})),
            ("count beyond stack", document(stage={"item_maxima": {"2": 100}})),
            ("entry item beyond slots", document(stage={"entry_item_id": 99, "entry_item_count": 1})),
            ("non-decimal item key", document(stage={"item_maxima": {"gold": 1}})),
        ):
            with self.subTest(label), self.assertRaises(HuntingCatalogError):
                self.load(doc)

    def test_rejects_duplicate_stage_identities(self) -> None:
        doc = document()
        doc["stages"] = [doc["stages"][0], dict(doc["stages"][0])]
        with self.assertRaises(HuntingCatalogError):
            self.load(doc)



class BundledHuntingPolicyTest(unittest.TestCase):
    """The bundled policy must match the recovered client structure exactly."""

    def setUp(self) -> None:
        self.catalog = build_bundled_hunting_policy()
        self.stages = self.catalog.by_identity()

    def test_declares_every_recovered_stage(self) -> None:
        self.assertEqual(
            [(chapter, section) for chapter in (1001, 1002, 1004) for section in (1, 2, 3)]
            + [(chapter, 1) for chapter in (1200, 1201)]
            + [(3000, section) for section in (*range(1, 8), *range(11, 18))]
            # Attack of the Coin Creeps is Chapter 3002, the copy of the family
            # whose banner bundles the retained archive still carries.
            + [(3002, section) for section in (1, 2, 3)]
            + [(3003, 1), (3004, 1)],
            sorted(self.stages),
        )
        # The stack ceiling is the client's own `maxItemCount`, not a lower one
        # this server would then refuse honest inventories against.
        self.assertEqual((ITEM_SLOTS, MAX_ITEM_STACK), (self.catalog.item_slots, self.catalog.max_stack))

    def test_carries_the_recovered_entry_costs(self) -> None:
        for identity, stamina in (
            ((1001, 1), 5), ((1001, 2), 8), ((1001, 3), 10),
            ((1002, 1), 5), ((1002, 2), 8), ((1002, 3), 10),
            ((3002, 1), 10), ((3002, 2), 15), ((3002, 3), 20),
            ((1004, 1), 5), ((1004, 2), 8), ((1004, 3), 10),
        ):
            with self.subTest(identity):
                self.assertEqual(stamina, self.stages[identity].stamina)
                # No bundled stage charges Coins or an entry item; the ticket
                # contract belongs to Metal, which is deliberately absent.
                self.assertEqual((0, {}), (self.stages[identity].coins, self.stages[identity].entry_items()))

    def test_carries_the_recovered_result_ceilings(self) -> None:
        pudding = self.stages[(1001, 1)]
        self.assertEqual((0, 0, 79), (pudding.max_coins, pudding.max_exp, pudding.max_items_total))
        self.assertEqual((21, 20, 19), (pudding.item_maxima[13], pudding.item_maxima[26], pudding.item_maxima[122]))
        # Tin's first zone alone caps items 22-25 at one boss slot.
        self.assertEqual((63, 1), (self.stages[(1002, 1)].max_items_total, self.stages[(1002, 1)].item_maxima[22]))
        self.assertEqual((93, 31), (self.stages[(1002, 2)].max_items_total, self.stages[(1002, 2)].item_maxima[22]))
        self.assertEqual(
            [1500, 5000, 11000],
            [self.stages[(3002, section)].max_coins for section in (1, 2, 3)],
        )
        for section in (1, 2, 3):
            creeps = self.stages[(3002, section)]
            self.assertEqual(({}, 0), (creeps.item_maxima, creeps.max_items_total))
            self.assertEqual(74, self.stages[(1004, section)].max_items_total)
        self.assertEqual(2, self.stages[(1004, 3)].item_maxima[2])

    def test_metal_zone_carries_its_recovered_costs_and_drop_manifests(self) -> None:
        for zone, (stamina, exp_ceiling) in enumerate(
            ((5, 750_000), (8, 920_000), (10, 1_560_000), (13, 2_270_000),
             (15, 2_550_000), (18, 4_400_000), (20, 7_720_000)), 1,
        ):
            # Each zone appears at its own section and again ten sections later.
            for section in (zone, zone + 10):
                stage = self.stages[(3000, section)]
                with self.subTest(zone=zone, section=section):
                    self.assertEqual((stamina, 0, exp_ceiling), (stage.stamina, stage.coins, stage.max_exp))
                    # The ticket replaces stamina rather than adding to it.
                    self.assertEqual(({50: 1}, True), (stage.entry_items(), stage.ticket_optional))
                    # Metal settles EXP and Companions only.
                    self.assertEqual((0, {}), (stage.max_items_total, stage.item_maxima))
                    expected = {128: 1} if zone == 1 else {128: 2} if zone == 2 else {128: 3, 129: 2}
                    self.assertEqual(expected, stage.companion_maxima)
                    self.assertTrue(set(stage.companion_maxima) <= set(stage.companion_drop_levels))

    def test_the_two_roads_pay_experience_plus_one_documented_channel_each(self) -> None:
        """Training is the whole point of a species-locked Road.

        Coins and Companion drops stay refused on the client's own say-so
        (empty `dropBuddies`).  The Luck chest is refused too, but no longer on
        `allowLucky` 0, which every story chapter sets while still producing
        chests: Dragon Road is named in the record's own no-chest list, and
        Machine Road is undetermined and refused as local policy.  Each Road also
        carries the one bounded channel its community record documents: Dragon
        Road a single Steel Dragon recruit, Machine Road its Star drops.
        """
        for chapter in (1200, 1201):
            road = self.stages[(chapter, 1)]
            with self.subTest(chapter=chapter):
                self.assertEqual((15, 0, 0), (road.stamina, road.coins, road.max_coins))
                self.assertEqual(({}, {}), (road.companion_maxima, road.entry_items()))
                self.assertGreater(road.max_exp, 0)
        dragon, machine = self.stages[(1200, 1)], self.stages[(1201, 1)]
        self.assertEqual(({1090: 1}, {}, 0), (dragon.monster_recruit_maxima, dragon.item_maxima, dragon.max_items_total))
        self.assertEqual(({}, {118: 30, 119: 30, 120: 30, 121: 30}, 30), (machine.monster_recruit_maxima, machine.item_maxima, machine.max_items_total))

    def test_a_road_accepts_a_won_battles_experience_and_still_refuses_the_rest(self) -> None:
        road = self.stages[(1200, 1)]

        def result(**overrides: object) -> dict[str, object]:
            return {
                "coins": 0, "exp": 0, "items": {}, "buddies": [],
                "summons": [], "monsters": [],
            } | overrides

        self.assertTrue(hunting_settlement_within_bounds(road, result(exp=road.max_exp)))
        self.assertFalse(hunting_settlement_within_bounds(road, result(exp=road.max_exp + 1)))
        for channel, value in (
            ("coins", 1), ("items", {"50": 1}), ("buddies", [128]),
            ("summons", [1]), ("monsters", [1]),
        ):
            with self.subTest(channel):
                self.assertFalse(hunting_settlement_within_bounds(road, result(**{channel: value})))

    def test_dragon_road_accepts_one_steel_dragon_recruit_and_no_more(self) -> None:
        dragon, machine = self.stages[(1200, 1)], self.stages[(1201, 1)]

        def result(**overrides: object) -> dict[str, object]:
            return {
                "coins": 0, "exp": 0, "items": {}, "buddies": [],
                "summons": [], "monsters": [],
            } | overrides

        self.assertTrue(hunting_settlement_within_bounds(dragon, result(monsters=[1090])))
        # One per clear: the record's spawn is single, and no duplicate rule survives.
        self.assertFalse(hunting_settlement_within_bounds(dragon, result(monsters=[1090, 1090])))
        # The bound is per-stage: Machine Road declares no recruit at all.
        self.assertFalse(hunting_settlement_within_bounds(machine, result(monsters=[1090])))

    def test_machine_road_accepts_only_its_documented_star_drops(self) -> None:
        machine = self.stages[(1201, 1)]

        def result(**overrides: object) -> dict[str, object]:
            return {
                "coins": 0, "exp": 0, "items": {}, "buddies": [],
                "summons": [], "monsters": [],
            } | overrides

        self.assertTrue(hunting_settlement_within_bounds(machine, result(items={"118": 5})))
        self.assertFalse(hunting_settlement_within_bounds(machine, result(items={"50": 1})))
        self.assertFalse(hunting_settlement_within_bounds(machine, result(items={"118": 31})))

    def test_the_road_ceiling_sits_on_its_own_selectors_tier_above_it(self) -> None:
        """The ceiling is derived, not chosen: Metal's tier above level 35."""
        from liminal_gate.hunting_catalog import _METAL_EXP_CEILING

        self.assertEqual(_METAL_EXP_CEILING[3], self.stages[(1200, 1)].max_exp)

    def test_advertises_only_the_zones_the_account_has_unlocked(self) -> None:
        """The client hard-codes no thresholds; an unlisted zone does not exist.

        Deriving the lists from the same stages that authorise a start is the
        point: a card can never light up for a stage that would then refuse.
        """
        before_any = self.catalog.client_lists(0x01000000 | (3 << 6) | 1)
        self.assertEqual([], before_any["huntingHuntingList"])
        tier_one = self.catalog.client_lists(0x01000000 | (4 << 6) | 1)
        self.assertEqual(
            ["1001-1", "1002-1", "1004-1", "3002-1", "3004-1"],
            sorted(tier_one["huntingHuntingList"]),
        )
        every_tier = self.catalog.client_lists(0x01000000 | (19 << 6) | 1)
        self.assertEqual(13, len(every_tier["huntingHuntingList"]))
        for identity in every_tier["huntingHuntingList"]:
            chapter, section = (int(part) for part in identity.split("-"))
            self.assertIn((chapter, section), self.stages)

    def test_advertises_metal_zones_and_roads_on_the_metal_selector(self) -> None:
        # The key is always sent: the client's setter reads it directly, and an
        # absent key is not the same as no zones.
        self.assertEqual([], self.catalog.client_lists(0x01000000 | (3 << 6) | 1)["metalHuntingList"])
        first = self.catalog.client_lists(0x01000000 | (4 << 6) | 1)["metalHuntingList"]
        self.assertEqual(["1200-1", "1201-1", "3000-1", "3000-11"], sorted(first))
        every = self.catalog.client_lists(0x01000000 | (31 << 6) | 1)["metalHuntingList"]
        self.assertEqual(
            sorted(
                ["1200-1", "1201-1"]
                + [f"3000-{zone}" for zone in range(1, 8)]
                + [f"3000-{10 + zone}" for zone in range(1, 8)]
            ),
            sorted(every),
        )

    def test_advertises_the_default_special_quest_after_chapter_three(self) -> None:
        before = self.catalog.client_lists(0x01000000 | (3 << 6) | 1)
        self.assertEqual([], before["specialQuestList"])
        after = self.catalog.client_lists(0x01000000 | (4 << 6) | 1)
        self.assertEqual(["3003-1"], after["specialQuestList"])
        special = self.stages[(3003, 1)]
        self.assertEqual(("special", 5, 1800), (special.selector, special.stamina, special.max_coins))

    def test_advertises_the_bounded_crystal_road_after_chapter_three(self) -> None:
        before = self.catalog.client_lists(0x01000000 | (3 << 6) | 1)
        self.assertNotIn("3004-1", before["huntingHuntingList"])
        after = self.catalog.client_lists(0x01000000 | (4 << 6) | 1)
        self.assertIn("3004-1", after["huntingHuntingList"])
        crystal = self.stages[(3004, 1)]
        self.assertEqual(("crystal_road", 7, 2), (crystal.family, crystal.stamina, crystal.max_items_total))
        self.assertEqual(set(range(1, 18)) | {50, 53, 54, 55, 56}, set(crystal.item_maxima))

    def test_advertised_metal_rows_have_matching_client_event_flags(self) -> None:
        before = self.catalog.client_event_flags(
            0x01000000 | (3 << 6) | 1
        )
        self.assertEqual({}, before)
        first = self.catalog.client_event_flags(
            0x01000000 | (4 << 6) | 1
        )
        self.assertEqual(
            {
                "sp_ch_1001-1": {"name": "sp_ch_1001-1", "value": True},
                "sp_ch_1002-1": {"name": "sp_ch_1002-1", "value": True},
                "sp_ch_3002-1": {"name": "sp_ch_3002-1", "value": True},
                "sp_ch_1004-1": {"name": "sp_ch_1004-1", "value": True},
                "sp_ch_3000-1": {"name": "sp_ch_3000-1", "value": True},
                "sp_ch_3000-11": {"name": "sp_ch_3000-11", "value": True},
                "sp_ch_1200-1": {"name": "sp_ch_1200-1", "value": True},
                "sp_ch_1201-1": {"name": "sp_ch_1201-1", "value": True},
                "sp_ch_3003-1": {"name": "sp_ch_3003-1", "value": True},
                "sp_ch_3004-1": {"name": "sp_ch_3004-1", "value": True},
            },
            first,
        )

    def test_every_advertised_row_carries_its_own_section_flag(self) -> None:
        """`UpdateItems` revalidates *every* row against `CheckQuestFlag`.

        `IsQuestOpen` exempts Chapters 1000--1099 while building the list, but
        the per-frame recheck does not, so an advertised row without its flag
        is removed and re-added every frame -- the flashing Hunting selector.
        The invariant is therefore one exact flag per advertised row, with no
        chapter range excused.
        """
        for chapter in (4, 10, 19, 31):
            with self.subTest(chapter=chapter):
                progress = 0x01000000 | (chapter << 6) | 1
                lists = self.catalog.client_lists(progress)
                advertised = (
                    lists["metalHuntingList"]
                    + lists["huntingHuntingList"]
                    + lists["specialQuestList"]
                )
                flags = self.catalog.client_event_flags(progress)
                self.assertEqual(
                    sorted(f"sp_ch_{identity}" for identity in advertised),
                    sorted(flags),
                )
                # A flag must never reach beyond the rows actually advertised,
                # or a locked card becomes a card the catalog would refuse.
                self.assertTrue(all(flag["value"] for flag in flags.values()))

    def test_tier_one_hunting_rows_are_flagged_once_unlocked(self) -> None:
        """Regression for the Hunting Zone flash: 1000-series rows need flags."""
        locked = self.catalog.client_event_flags(0x01000000 | (3 << 6) | 1)
        self.assertNotIn("sp_ch_3002-1", locked)
        unlocked = self.catalog.client_event_flags(0x01000000 | (4 << 6) | 1)
        for chapter in (1001, 1002, 1004, 3002):
            self.assertIn(f"sp_ch_{chapter}-1", unlocked)

    def test_regular_and_king_metal_sections_are_both_advertised_and_startable(self) -> None:
        """The two ranges are distinct client cards, not duplicate list rows."""
        advertised = self.catalog.client_lists(0x01000000 | (31 << 6) | 1)["metalHuntingList"]
        for zone in range(1, 8):
            for section in (zone, zone + 10):
                self.assertIn((3000, section), self.stages)
                self.assertIn(f"3000-{section}", advertised)
                self.assertEqual("metal", self.stages[(3000, section)].selector)

    def test_tiers_unlock_only_after_their_policy_chapter(self) -> None:
        for section, first_allowed in ((1, 4), (2, 10), (3, 19)):
            stage = self.stages[(1001, section)]
            with self.subTest(section=section):
                self.assertFalse(stage.unlocked_at(0x01000000 | ((first_allowed - 1) << 6) | 1))
                self.assertTrue(stage.unlocked_at(0x01000000 | (first_allowed << 6) | 1))
                # The show-progress high bits must not make an earlier chapter
                # compare as later.
                self.assertFalse(stage.unlocked_at(0x03000000 | ((first_allowed - 1) << 6) | 1))

if __name__ == "__main__":
    unittest.main()
