"""The bundled clear-chapter achievement policy.

The client ships 99 achievement records but only eight are settleable by a
server: `unlockType == 0` (ClearChapter) with a positive `unlockValue1`, which
is a story-progress comparison the server can evaluate on its own. The other 91
are gated on client-local counters this project has not reconstructed, and are
deliberately absent rather than guessed at.

These cases pin the recovered shape so a future edit cannot quietly widen the
policy past what the master data supports.
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


class BundledAchievementPolicyTest(unittest.TestCase):
    def test_exactly_the_eight_settleable_rows(self) -> None:
        catalog = build_bundled_achievement_policy()
        self.assertEqual(8, len(catalog.achievements))
        self.assertEqual([1, 2, 3, 4, 5, 6, 7, 8], sorted(catalog.achievements))

    def test_chapters_are_the_recovered_five_step_ladder(self) -> None:
        catalog = build_bundled_achievement_policy()
        self.assertEqual(
            [5, 10, 15, 20, 25, 30, 35, 40],
            [catalog.achievements[key].required_chapter for key in sorted(catalog.achievements)],
        )

    def test_every_reward_is_the_uniform_recovered_present(self) -> None:
        # One Energy and one of item 50, identical across all eight. That
        # uniformity is the client's own, not a simplification here.
        for achievement in build_bundled_achievement_policy().achievements.values():
            with self.subTest(achievement.achievement_id):
                self.assertEqual(ACHIEVEMENT_FREE_ENERGY, achievement.free_energy)
                self.assertEqual(0, achievement.coins)
                self.assertEqual({ACHIEVEMENT_ITEM_ID: ACHIEVEMENT_ITEM_COUNT}, achievement.items)

    def test_limits_match_the_other_bundled_policies(self) -> None:
        catalog = build_bundled_achievement_policy()
        self.assertEqual(BUNDLED_ITEM_SLOTS, catalog.item_slots)
        # The Energy ceiling is the largest single grant, not an invented cap.
        self.assertEqual(ACHIEVEMENT_FREE_ENERGY, catalog.max_free_energy)
        self.assertTrue(all(1 <= item <= catalog.item_slots
                            for achievement in catalog.achievements.values()
                            for item in achievement.items))

    def test_rows_are_ordered_and_unique(self) -> None:
        ids = [row[0] for row in ACHIEVEMENT_ROWS]
        chapters = [row[1] for row in ACHIEVEMENT_ROWS]
        self.assertEqual(sorted(set(ids)), ids)
        self.assertEqual(sorted(set(chapters)), chapters)


if __name__ == "__main__":
    unittest.main()
