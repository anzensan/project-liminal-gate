from __future__ import annotations

import unittest

from liminal_gate.daily_quest_data import (
    DAILY_QUEST_EVENT_FLAG,
    build_bundled_daily_quest_stages,
    daily_quest_event_flags,
)
from liminal_gate.hunting_catalog import HuntingCatalog, BUNDLED_ITEM_SLOTS, BUNDLED_MAX_STACK, hunting_settlement_within_bounds


def result(items=None, coins=0, exp=0, buddies=(), summons=(), monsters=()):
    """The client-reported battle result shape the bounds check reads."""
    return {
        "items": items or {}, "coins": coins, "exp": exp,
        "buddies": list(buddies), "summons": list(summons), "monsters": list(monsters),
    }


ROTATION_STAGES = (
    (6000, 1), (6001, 1), (6002, 1), (6003, 1), (6004, 1), (6005, 1), (6006, 1),
    (6007, 1), (6008, 1), (6009, 1), (6010, 1), (6011, 1), (6011, 2), (6012, 1),
)


class DailyQuestDataTest(unittest.TestCase):
    def test_the_stage_set_matches_the_recovered_rotation(self) -> None:
        """These are the fourteen stages DailyQuestData.questOrder names."""
        stages = build_bundled_daily_quest_stages()
        self.assertEqual(ROTATION_STAGES, tuple(sorted((s.chapter, s.section) for s in stages)))

    def test_every_stage_is_free_and_unadvertised(self) -> None:
        """The client lists Daily Quests itself, and all fourteen cost nothing."""
        for stage in build_bundled_daily_quest_stages():
            with self.subTest(stage=stage.identity_label()):
                self.assertEqual(0, stage.stamina)
                self.assertEqual(0, stage.entry_item_id)
                self.assertEqual("hidden", stage.selector)
                # Progress packs chapter into bits 6+, so 65 is Chapter 1-1.
                self.assertTrue(stage.unlocked_at(65), "Daily Quests carry no recovered story gate")

    def test_sweet_temptation_is_the_energy_quest(self) -> None:
        """6006 is EnergyGetChapter, and item 80 is EnergyItemId."""
        stage = next(s for s in build_bundled_daily_quest_stages() if (s.chapter, s.section) == (6006, 1))
        self.assertEqual("sweet_temptation", stage.family)
        self.assertEqual(1, stage.item_maxima[80])

    def test_yamamoto_occupies_the_only_two_section_chapter(self) -> None:
        stages = {(s.chapter, s.section): s.family for s in build_bundled_daily_quest_stages()}
        self.assertEqual("yamamotos_puzzle_quest", stages[(6011, 1)])
        self.assertEqual("yamamotos_puzzle_quest_ii", stages[(6011, 2)])

    def test_flags_cover_the_category_and_every_stage(self) -> None:
        flags = daily_quest_event_flags()
        self.assertTrue(flags[DAILY_QUEST_EVENT_FLAG]["value"])
        for chapter, section in ROTATION_STAGES:
            self.assertIn(f"sp_ch_{chapter}-{section}", flags)

    def test_the_hunt_for_joker_awards_nothing_rather_than_an_invented_grant(self) -> None:
        """Joker Λ is character 1018, which bounded item settlement cannot express."""
        stage = next(s for s in build_bundled_daily_quest_stages() if (s.chapter, s.section) == (6012, 1))
        self.assertEqual({}, stage.companion_maxima)
        self.assertEqual(0, stage.max_coins)


class DailyQuestSettlementTest(unittest.TestCase):
    def catalog(self) -> HuntingCatalog:
        return HuntingCatalog(build_bundled_daily_quest_stages(), BUNDLED_ITEM_SLOTS, BUNDLED_MAX_STACK)

    def stage(self, chapter: int, section: int):
        return self.catalog().by_identity()[(chapter, section)]

    def test_a_documented_reward_settles(self) -> None:
        """Sweet Temptation's single Energy is inside its bound."""
        stage = self.stage(6006, 1)
        self.assertTrue(hunting_settlement_within_bounds(stage, result({80: 1})))

    def test_an_absurd_claim_is_refused(self) -> None:
        """The ceilings exist to refuse this, not to reproduce a drop rate."""
        stage = self.stage(6006, 1)
        self.assertFalse(hunting_settlement_within_bounds(stage, result({80: 99})))

    def test_an_unlisted_item_is_refused(self) -> None:
        stage = self.stage(6006, 1)
        self.assertFalse(hunting_settlement_within_bounds(stage, result({1: 1})))

    def test_tropical_haze_settles_its_tickets(self) -> None:
        stage = self.stage(6007, 1)
        self.assertTrue(hunting_settlement_within_bounds(stage, result({50: 1, 81: 1, 112: 1})))

    def test_hedgehog_hullabaloo_is_the_only_coin_quest(self) -> None:
        self.assertTrue(hunting_settlement_within_bounds(self.stage(6003, 1), result(coins=15_000)))
        self.assertFalse(hunting_settlement_within_bounds(self.stage(6003, 1), result(coins=15_001)))
        self.assertFalse(hunting_settlement_within_bounds(self.stage(6006, 1), result(coins=1)))

    def test_no_daily_quest_settles_experience(self) -> None:
        for stage in build_bundled_daily_quest_stages():
            with self.subTest(stage=stage.identity_label()):
                self.assertFalse(hunting_settlement_within_bounds(stage, result(exp=1)))
