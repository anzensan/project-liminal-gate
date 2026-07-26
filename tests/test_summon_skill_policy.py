"""The bundled Battle Summon skill-unlock policy.

Before this policy existed the route was unreachable without an operator
catalog, which is why the behavioural differential could not compare it at all.

The costs are the recovered `SummonData` -> `ChrJobParams` join. Nothing here
concerns how a Summon is acquired; that remains unrecovered and out of scope.
"""
from __future__ import annotations

import unittest

from liminal_gate.summon_skill_catalog import (
    BUNDLED_ITEM_SLOTS,
    build_bundled_summon_skill_policy,
)
from liminal_gate.summon_skill_data import SUMMON_SKILL_ROWS


class BundledSummonSkillPolicyTest(unittest.TestCase):
    def test_every_summon_is_present(self) -> None:
        catalog = build_bundled_summon_skill_policy()
        self.assertEqual(set(range(1, 17)), set(catalog.level_counts))
        self.assertEqual(44, len(catalog.levels))

    def test_levels_are_consecutive_from_zero(self) -> None:
        # The loader's own invariant for operator catalogs; the bundled policy
        # has to satisfy it too or the two paths would disagree.
        catalog = build_bundled_summon_skill_policy()
        for summon_id, count in catalog.level_counts.items():
            with self.subTest(summon_id):
                self.assertEqual(
                    list(range(count)),
                    sorted(level for sid, level in catalog.levels if sid == summon_id),
                )

    def test_two_summons_ship_with_only_their_base_skill(self) -> None:
        catalog = build_bundled_summon_skill_policy()
        self.assertEqual(1, catalog.level_counts[1])
        self.assertEqual(1, catalog.level_counts[2])
        self.assertTrue(all(catalog.level_counts[sid] == 3 for sid in range(3, 17)))

    def test_level_zero_is_always_free(self) -> None:
        # Level 0 is the skill the Summon ships with, so it costs nothing.
        catalog = build_bundled_summon_skill_policy()
        for summon_id in range(1, 17):
            with self.subTest(summon_id):
                base = catalog.levels[(summon_id, 0)]
                self.assertEqual(0, base.coins)
                self.assertEqual({}, base.materials)

    def test_paid_tiers_cost_materials_and_no_coins(self) -> None:
        catalog = build_bundled_summon_skill_policy()
        paid = [level for (_, skill_level), level in catalog.levels.items() if skill_level > 0]
        self.assertEqual(28, len(paid))
        for level in paid:
            with self.subTest((level.summon_id, level.skill_level)):
                self.assertEqual(0, level.coins)
                self.assertTrue(level.materials)
                for item_id, count in level.materials.items():
                    self.assertTrue(1 <= item_id <= BUNDLED_ITEM_SLOTS)
                    self.assertGreater(count, 0)

    def test_rows_are_ordered_and_unique(self) -> None:
        identities = [(row[0], row[1]) for row in SUMMON_SKILL_ROWS]
        self.assertEqual(sorted(identities), identities)
        self.assertEqual(len(set(identities)), len(identities))


if __name__ == "__main__":
    unittest.main()
