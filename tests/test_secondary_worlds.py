from __future__ import annotations

import unittest

from liminal_gate.hunting_catalog import (
    BUNDLED_ITEM_SLOTS,
    BUNDLED_MAX_STACK,
    HuntingCatalog,
    hunting_settlement_within_bounds,
)
from liminal_gate.secondary_world_data import (
    BREASOUL_EVENT_FLAG,
    BREASOUL_UNLOCK,
    FIVE_EMPERORS_EVENT_FLAGS,
    FIVE_EMPERORS_UNLOCK,
    build_bundled_breasoul_stages,
    build_bundled_five_emperors_stages,
    secondary_world_event_flags,
)


def result(items=None, coins=0, exp=0, buddies=(), summons=(), monsters=()):
    return {
        "items": items or {}, "coins": coins, "exp": exp,
        "buddies": list(buddies), "summons": list(summons), "monsters": list(monsters),
    }


def progress(chapter: int, section: int) -> int:
    """Pack a chapter/section the way the client's progressCode does."""
    return (chapter << 6) | section


class BreasoulTest(unittest.TestCase):
    def test_twenty_sections_across_five_chapters(self) -> None:
        """BattleData gives 100 four sections, 104 one, and five each between."""
        stages = build_bundled_breasoul_stages()
        self.assertEqual(20, len(stages))
        counts = {chapter: 0 for chapter in range(100, 105)}
        for stage in stages:
            counts[stage.chapter] += 1
        self.assertEqual({100: 4, 101: 5, 102: 5, 103: 5, 104: 1}, counts)

    def test_every_section_costs_fifteen_stamina_and_no_coins(self) -> None:
        for stage in build_bundled_breasoul_stages():
            with self.subTest(stage=stage.identity_label()):
                self.assertEqual(15, stage.stamina)
                self.assertEqual(0, stage.coins)
                self.assertEqual("hidden", stage.selector)

    def test_no_section_settles_a_companion(self) -> None:
        """Every one of the twenty declares an empty dropBuddies."""
        for stage in build_bundled_breasoul_stages():
            with self.subTest(stage=stage.identity_label()):
                self.assertEqual({}, stage.companion_maxima)

    def test_experience_is_paid_but_coins_and_items_are_not(self) -> None:
        catalog = HuntingCatalog(build_bundled_breasoul_stages(), BUNDLED_ITEM_SLOTS, BUNDLED_MAX_STACK)
        stage = catalog.by_identity()[(100, 1)]
        self.assertTrue(hunting_settlement_within_bounds(stage, result(exp=1_000)))
        self.assertFalse(hunting_settlement_within_bounds(stage, result(coins=1)))
        self.assertFalse(hunting_settlement_within_bounds(stage, result(items={1: 1})))

    def test_an_absurd_experience_claim_is_refused(self) -> None:
        catalog = HuntingCatalog(build_bundled_breasoul_stages(), BUNDLED_ITEM_SLOTS, BUNDLED_MAX_STACK)
        stage = catalog.by_identity()[(100, 1)]
        self.assertFalse(hunting_settlement_within_bounds(stage, result(exp=99_000_000)))


class FiveEmperorsTest(unittest.TestCase):
    def test_ten_descents_one_per_chapter(self) -> None:
        stages = build_bundled_five_emperors_stages()
        self.assertEqual(10, len(stages))
        self.assertEqual(
            [(chapter, 1) for chapter in range(110, 120)],
            sorted((s.chapter, s.section) for s in stages),
        )

    def test_five_normal_at_fifteen_and_five_hard_at_twenty(self) -> None:
        stamina = [s.stamina for s in sorted(build_bundled_five_emperors_stages(), key=lambda s: s.chapter)]
        self.assertEqual([15] * 5 + [20] * 5, stamina)

    def test_no_descent_charges_coins(self) -> None:
        for stage in build_bundled_five_emperors_stages():
            with self.subTest(stage=stage.identity_label()):
                self.assertEqual(0, stage.coins)

    def test_each_descent_names_one_or_two_candidates(self) -> None:
        for stage in build_bundled_five_emperors_stages():
            with self.subTest(stage=stage.identity_label()):
                self.assertIn(len(stage.companion_maxima), (1, 2))
                self.assertTrue(all(count == 1 for count in stage.companion_maxima.values()))

    def test_a_dropped_companion_arrives_at_level_one(self) -> None:
        for stage in build_bundled_five_emperors_stages():
            with self.subTest(stage=stage.identity_label()):
                self.assertTrue(all(level == 1 for level in stage.companion_drop_levels.values()))

    def test_one_manifest_companion_settles_and_a_second_does_not(self) -> None:
        """The record's rule for this manifest shape is a single exclusive roll."""
        catalog = HuntingCatalog(build_bundled_five_emperors_stages(), BUNDLED_ITEM_SLOTS, BUNDLED_MAX_STACK)
        stage = catalog.by_identity()[(115, 1)]
        first, second = sorted(stage.companion_maxima)
        self.assertTrue(hunting_settlement_within_bounds(stage, result(buddies=[first])))
        self.assertFalse(hunting_settlement_within_bounds(stage, result(buddies=[first, second])))

    def test_a_companion_the_manifest_does_not_name_is_refused(self) -> None:
        catalog = HuntingCatalog(build_bundled_five_emperors_stages(), BUNDLED_ITEM_SLOTS, BUNDLED_MAX_STACK)
        stage = catalog.by_identity()[(110, 1)]
        self.assertFalse(hunting_settlement_within_bounds(stage, result(buddies=[999])))


class SecondaryWorldGateTest(unittest.TestCase):
    """Both maps are permanent once open, which is archive policy."""

    def test_neither_map_opens_before_its_section(self) -> None:
        self.assertEqual({}, secondary_world_event_flags(19, 9))

    def test_the_five_emperors_open_first(self) -> None:
        flags = secondary_world_event_flags(*FIVE_EMPERORS_UNLOCK)
        self.assertEqual(set(FIVE_EMPERORS_EVENT_FLAGS), set(flags))
        self.assertNotIn(BREASOUL_EVENT_FLAG, flags)

    def test_breasoul_opens_at_its_own_section_and_both_stay_open(self) -> None:
        flags = secondary_world_event_flags(*BREASOUL_UNLOCK)
        self.assertIn(BREASOUL_EVENT_FLAG, flags)
        for name in FIVE_EMPERORS_EVENT_FLAGS:
            self.assertIn(name, flags)

    def test_the_map_needs_both_five_emperors_flags(self) -> None:
        """The expanded coordinate branch checks the second one."""
        self.assertEqual(2, len(FIVE_EMPERORS_EVENT_FLAGS))
        self.assertTrue(all(secondary_world_event_flags(30, 1)[n]["value"] for n in FIVE_EMPERORS_EVENT_FLAGS))

    def test_stages_are_locked_until_their_story_section(self) -> None:
        emperor = build_bundled_five_emperors_stages()[0]
        self.assertFalse(emperor.unlocked_at(progress(19, 9)))
        self.assertTrue(emperor.unlocked_at(progress(*FIVE_EMPERORS_UNLOCK)))
        breasoul = build_bundled_breasoul_stages()[0]
        self.assertFalse(breasoul.unlocked_at(progress(25, 9)))
        self.assertTrue(breasoul.unlocked_at(progress(*BREASOUL_UNLOCK)))


if __name__ == "__main__":
    unittest.main()
