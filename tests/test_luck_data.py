from __future__ import annotations

import unittest

from liminal_gate.luck_data import (
    CHEST_SLOT_COUNT,
    CHEST_TIERS,
    LUCK_CAP_A_AND_BELOW,
    LUCK_CAP_S_AND_SS,
    LUCK_CAP_Z_AND_LAMBDA,
    LUCK_GAIN_MIN_STAMINA,
    LUCK_TENTHS_MAX,
    chest_probabilities,
    gains_luck,
    team_luck,
)


class LuckCapTest(unittest.TestCase):
    """The caps Mistwalker published with the stat itself."""

    def test_the_three_published_class_caps(self) -> None:
        self.assertEqual((700, 800, 1000), (
            LUCK_CAP_A_AND_BELOW, LUCK_CAP_S_AND_SS, LUCK_CAP_Z_AND_LAMBDA,
        ))
        self.assertEqual(LUCK_TENTHS_MAX, LUCK_CAP_Z_AND_LAMBDA)


class TeamLuckTest(unittest.TestCase):
    """Team Luck is a Companion-adjusted average, not a sum."""

    def test_a_plain_party_averages(self) -> None:
        self.assertEqual(500, team_luck((400, 600, 500, 500, 500, 500)))

    def test_an_empty_party_is_zero_rather_than_an_error(self) -> None:
        self.assertEqual(0, team_luck(()))

    def test_a_personal_bonus_applies_before_the_average(self) -> None:
        """Unicorn's +10 lifts one member, so the party average moves by less.

        A personal bonus is diluted by the party it is averaged over; a team
        bonus is not. That is the whole difference between the two kinds.
        """
        self.assertEqual(250, team_luck((200, 200), (100, 0)))
        self.assertEqual(300, team_luck((200, 200), (), 100))

    def test_a_personal_bonus_may_pass_a_class_cap_but_not_the_ceiling(self) -> None:
        """The record allows a boost past a character's own max, never past 100."""
        self.assertEqual(LUCK_TENTHS_MAX, team_luck((950,), (300,)))

    def test_a_team_bonus_applies_after_the_average(self) -> None:
        """Senala O's +10 raises the average itself rather than one member."""
        self.assertEqual(300, team_luck((200, 200), (), 100))

    def test_the_team_average_is_capped(self) -> None:
        self.assertEqual(LUCK_TENTHS_MAX, team_luck((1000, 1000), (), 500))


class ChestProbabilityTest(unittest.TestCase):
    """Every endpoint here is a number the record states."""

    def test_there_are_six_slots(self) -> None:
        self.assertEqual(6, CHEST_SLOT_COUNT)
        self.assertEqual(
            ["A", "B", "C", "D", "Luck 80", "Luck 100"],
            [tier.name for tier in CHEST_TIERS],
        )

    def test_a_is_guaranteed_from_forty_luck(self) -> None:
        self.assertEqual(1.0, chest_probabilities(400)["A"])
        self.assertEqual(1.0, chest_probabilities(1000)["A"])
        self.assertLess(chest_probabilities(399)["A"], 1.0)

    def test_b_is_guaranteed_from_eighty_five_luck(self) -> None:
        self.assertEqual(1.0, chest_probabilities(850)["B"])
        self.assertLess(chest_probabilities(849)["B"], 1.0)

    def test_the_hundred_luck_party_matches_the_published_row(self) -> None:
        """A, B, Luck 80 and Luck 100 always; C at 50%; D at 25%."""
        at_full = chest_probabilities(LUCK_TENTHS_MAX)
        self.assertEqual(1.0, at_full["A"])
        self.assertEqual(1.0, at_full["B"])
        self.assertEqual(1.0, at_full["Luck 80"])
        self.assertEqual(1.0, at_full["Luck 100"])
        self.assertEqual(0.5, at_full["C"])
        self.assertEqual(0.25, at_full["D"])

    def test_the_two_named_chests_are_thresholds_not_curves(self) -> None:
        """They drop always at their value and never below it."""
        self.assertEqual(0.0, chest_probabilities(799)["Luck 80"])
        self.assertEqual(1.0, chest_probabilities(800)["Luck 80"])
        self.assertEqual(0.0, chest_probabilities(999)["Luck 100"])
        self.assertEqual(1.0, chest_probabilities(1000)["Luck 100"])

    def test_luck_80_still_drops_for_a_full_luck_party(self) -> None:
        """A threshold is a floor, not a band."""
        self.assertEqual(1.0, chest_probabilities(1000)["Luck 80"])

    def test_higher_luck_never_lowers_a_chance(self) -> None:
        """The record's one qualitative claim, checked across the whole range."""
        previous = chest_probabilities(0)
        for tenths in range(0, LUCK_TENTHS_MAX + 1, 10):
            current = chest_probabilities(tenths)
            for name, chance in current.items():
                self.assertGreaterEqual(chance, previous[name], f"{name} fell at {tenths}")
            previous = current

    def test_no_chance_ever_leaves_the_unit_interval(self) -> None:
        for tenths in range(-100, LUCK_TENTHS_MAX + 200, 7):
            for name, chance in chest_probabilities(tenths).items():
                self.assertGreaterEqual(chance, 0.0, name)
                self.assertLessEqual(chance, 1.0, name)


class LuckGainTest(unittest.TestCase):
    """The developer's own stamina rule, which is easy to lose by accident."""

    def test_below_eight_stamina_never_gains(self) -> None:
        self.assertEqual(8, LUCK_GAIN_MIN_STAMINA)
        for stamina in range(0, 8):
            self.assertFalse(gains_luck(stamina), stamina)

    def test_eight_and_above_may_gain(self) -> None:
        for stamina in (8, 15, 25, 40):
            self.assertTrue(gains_luck(stamina), stamina)

    def test_a_free_stage_never_gains(self) -> None:
        """Every Daily Quest costs zero, so none of them raises Luck."""
        self.assertFalse(gains_luck(0))


if __name__ == "__main__":
    unittest.main()
