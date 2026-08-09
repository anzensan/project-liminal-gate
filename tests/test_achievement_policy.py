"""The bundled achievement policy: all 98 of the client's own records.

The client ships 99 achievement records and evaluates every one of them against
its own state. Only nine are `unlockType == 0` (ClearChapter), the one condition
a server can check for itself; the rest turn on client-local counters -- levels,
jobs, species, gathered EXP, and the retired Co-op and VS tallies -- that this
server never observes.

This policy used to carry eight rows and refuse the rest, which made the other
ninety unclaimable and, with no `achive-*` flag sent, invisible as well. Both
halves are fixed: every record is listed and every record is claimable, with the
eight story conditions kept because they cost nothing to honour.

These cases pin the recovered shape so a future edit cannot quietly narrow the
policy back, or widen a reward past what the master data actually declares.
"""
from __future__ import annotations

import unittest

from liminal_gate.achievement_catalog import (
    BUNDLED_ITEM_SLOTS,
    build_bundled_achievement_policy,
)
from liminal_gate.achievement_data import (
    ACHIEVEMENT_FREE_ENERGY,
    ACHIEVEMENT_ITEM_COUNT,
    ACHIEVEMENT_ITEM_ID,
    ACHIEVEMENT_ROWS,
)
from liminal_gate.event_flag_data import ACHIEVEMENT_EVENT_FLAGS, achievement_event_flags


class BundledAchievementPolicyTest(unittest.TestCase):
    def test_every_record_the_client_carries_is_claimable(self) -> None:
        """98 of the 99: the empty-keyed placeholder grants nothing."""
        catalog = build_bundled_achievement_policy()
        self.assertEqual(98, len(catalog.achievements))

    def test_the_clear_chapter_ladder_survives_unchanged(self) -> None:
        """The eight story rows keep the one condition a server can check."""
        catalog = build_bundled_achievement_policy()
        gated = sorted(
            achievement.required_chapter
            for achievement in catalog.achievements.values()
            if achievement.required_chapter
        )
        self.assertEqual([5, 10, 15, 20, 25, 30, 35, 40], gated)
        # The eight this project carried by hand are still exactly themselves.
        for identifier, chapter in enumerate([5, 10, 15, 20, 25, 30, 35, 40], start=1):
            with self.subTest(identifier):
                achievement = catalog.achievements[identifier]
                self.assertEqual(chapter, achievement.required_chapter)
                self.assertEqual(ACHIEVEMENT_FREE_ENERGY, achievement.free_energy)
                self.assertEqual({ACHIEVEMENT_ITEM_ID: ACHIEVEMENT_ITEM_COUNT}, achievement.items)

    def test_everything_else_is_free_to_claim(self) -> None:
        """A zero chapter is what makes a claim free.

        The gate refuses when the account's chapter is at or below
        `required_chapter`, so zero passes for any real account. That is the
        whole mechanism -- there is no separate "free" flag to get wrong.
        """
        catalog = build_bundled_achievement_policy()
        free = [a for a in catalog.achievements.values() if not a.required_chapter]
        self.assertEqual(90, len(free))

    def test_no_reward_exceeds_what_the_master_declares(self) -> None:
        catalog = build_bundled_achievement_policy()
        for achievement in catalog.achievements.values():
            with self.subTest(achievement.achievement_id):
                # Two Energy is the largest present in the recovered table, and
                # no record pays Coins at all.
                self.assertLessEqual(achievement.free_energy, 2)
                self.assertEqual(0, achievement.coins)
                self.assertTrue(all(1 <= item <= catalog.item_slots for item in achievement.items))
                self.assertTrue(all(count > 0 for count in achievement.items.values()))

    def test_limits_match_the_other_bundled_policies(self) -> None:
        catalog = build_bundled_achievement_policy()
        self.assertEqual(BUNDLED_ITEM_SLOTS, catalog.item_slots)
        # The ceiling is the save's own Energy bound now that a claim can pay
        # two: capping at one grant would have silently clamped the second.
        self.assertGreaterEqual(catalog.max_free_energy, 2)

    def test_rows_are_ordered_and_unique(self) -> None:
        ids = [row[0] for row in ACHIEVEMENT_ROWS]
        self.assertEqual(sorted(set(ids)), ids)

    def test_both_visibility_flags_are_sent(self) -> None:
        """Listing them is the other half; a claimable achievement nothing
        shows is exactly as unreachable as an unclaimable one."""
        self.assertEqual(("achive-1", "achive-hide"), ACHIEVEMENT_EVENT_FLAGS)
        flags = achievement_event_flags()
        self.assertEqual({"achive-1", "achive-hide"}, set(flags))
        self.assertTrue(all(entry["value"] is True for entry in flags.values()))


if __name__ == "__main__":
    unittest.main()
