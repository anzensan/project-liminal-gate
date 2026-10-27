"""Community-recorded Battle Champs pools, with existing one-item wire policy."""

import unittest

from liminal_gate.luck_data import CHEST_TIERS, LUCK_TENTHS_MAX
from liminal_gate.luck_pool_catalog import LuckPoolCatalog
from liminal_gate.luck_pool_data import pool_for
from liminal_gate.luck_pool_interpolation import build_luck_pools
from liminal_gate.luck_runtime import roll_luck_result


class BattleChampsChestTest(unittest.TestCase):
    def test_every_tier_matches_its_quest_and_family(self):
        for chapter in range(8008, 8012):
            for section in (1, 2):
                with self.subTest(chapter=chapter, section=section):
                    if section == 1:
                        extras = {
                            8008: ("I138",), 8009: ("I139",),
                            8010: (), 8011: ("I138", "I139"),
                        }[chapter]
                        expected = {
                            "A": ("C50", "I181"), "B": ("C50", "I181"),
                            "C": ("C100", "I181"), "D": ("I181", *extras),
                            "Luck 80": ("O128", *extras), "Luck 100": ("M918", "O128"),
                        }
                    else:
                        extras = {
                            8008: ("I138", "I143"), 8009: ("M947", "I139"),
                            8010: (), 8011: ("M947", "I138", "I139", "I143"),
                        }[chapter]
                        expected = {
                            "A": ("C50", "I181"), "B": ("C50", "I181"),
                            "C": ("C100", "C150", "I181", *extras),
                            "D": ("C300", "I181", *extras),
                            "Luck 80": ("O128", "O129", *extras),
                            "Luck 100": ("M918", "O128", "O129", "O347"),
                        }
                        if chapter == 8011:
                            expected["Luck 80"] = ("O128", "O129", "M947", "C100", "I138", "I139", "I143")
                    for tier, rewards in expected.items():
                        self.assertEqual(rewards, pool_for(chapter, section, tier))
                        # Default donation must yield to this event's record.
                        self.assertEqual(rewards, build_luck_pools().pool_for(chapter, section, tier))

    def test_rolls_use_only_the_event_pools_with_and_without_donation(self):
        for chapter in range(8008, 8012):
            for section in (1, 2):
                for resolver in (None, build_luck_pools()):
                    for attempt in range(16):
                        slots = roll_luck_result(chapter, section, LUCK_TENTHS_MAX, attempt, catalog=resolver)
                        self.assertEqual(6, len(slots))
                        for tier, reward in zip(CHEST_TIERS, slots):
                            if reward:
                                self.assertIn(reward, pool_for(chapter, section, tier.name))
                        self.assertTrue(all(slots[i] for i in (0, 1, 4, 5)))

    def test_explicit_operator_pool_still_replaces_the_whole_stage(self):
        resolver = build_luck_pools(LuckPoolCatalog({(8008, 2): {"A": ("C1",)}}))
        self.assertEqual(("C1",), resolver.pool_for(8008, 2, "A"))
        self.assertEqual((), resolver.pool_for(8008, 2, "Luck 100"))
        self.assertEqual(("M918", "O128"), resolver.pool_for(8008, 1, "Luck 100"))
