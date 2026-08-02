from __future__ import annotations

import unittest

from liminal_gate.luck_data import LUCK_TENTHS_MAX
from liminal_gate.luck_pool_data import LUCK_CHEST_POOLS, has_documented_pool
from liminal_gate.luck_runtime import (
    apply_luck_up_table,
    chest_coins,
    chest_companions,
    chest_items,
    party_team_luck,
    roll_luck_result,
    roll_luck_up_table,
)


def userdata(party_luck: dict[int, int], team: list[int] | None = None) -> dict:
    return {
        "chrdata": [{"id": cid, "luck": luck} for cid, luck in party_luck.items()],
        "teamMembers": team if team is not None else list(party_luck),
    }


class ChestRollTest(unittest.TestCase):
    def test_a_retry_never_re_rolls_the_chest(self) -> None:
        """A re-roll on retry would be a reward duplicator, not a nicety."""
        first = roll_luck_result(1, 1, LUCK_TENTHS_MAX, "req-1", "digest")
        again = roll_luck_result(1, 1, LUCK_TENTHS_MAX, "req-1", "digest")
        self.assertEqual(first, again)

    def test_a_different_battle_rolls_differently(self) -> None:
        rolls = {
            tuple(roll_luck_result(1, 1, LUCK_TENTHS_MAX, f"req-{n}", "d"))
            for n in range(12)
        }
        self.assertGreater(len(rolls), 1, "every battle produced an identical chest")

    def test_an_undocumented_stage_yields_six_empty_slots(self) -> None:
        """Most of the game has no recorded pool, and gets no invented one."""
        self.assertFalse(has_documented_pool(99, 9))
        self.assertEqual([""] * 6, roll_luck_result(99, 9, LUCK_TENTHS_MAX, "r", "d"))

    def test_a_full_luck_party_always_opens_the_two_named_chests(self) -> None:
        """Luck 80 and Luck 100 are guaranteed at 100.0, so a stage documenting
        both must fill both slots on every roll."""
        stage = next(
            key for key, tiers in LUCK_CHEST_POOLS.items()
            if tiers.get("Luck 80") and tiers.get("Luck 100")
        )
        for attempt in range(20):
            slots = roll_luck_result(*stage, LUCK_TENTHS_MAX, f"r{attempt}", "d")
            self.assertNotEqual("", slots[4], f"Luck 80 empty on attempt {attempt}")
            self.assertNotEqual("", slots[5], f"Luck 100 empty on attempt {attempt}")

    def test_a_zero_luck_party_never_opens_the_named_chests(self) -> None:
        stage = next(iter(LUCK_CHEST_POOLS))
        for attempt in range(20):
            slots = roll_luck_result(*stage, 0, f"r{attempt}", "d")
            self.assertEqual("", slots[4])
            self.assertEqual("", slots[5])

    def test_every_roll_returns_exactly_six_slots(self) -> None:
        for tenths in (0, 400, 850, LUCK_TENTHS_MAX):
            self.assertEqual(6, len(roll_luck_result(1, 1, tenths, "r", "d")))


class ChestWireTest(unittest.TestCase):
    """The client's own encoding: C coins, I item, O Companion."""

    def test_coins_items_and_companions_are_read_apart(self) -> None:
        slots = ["C50", "I11", "O128", "", "I11", "C1500"]
        self.assertEqual(1550, chest_coins(slots))
        self.assertEqual({11: 2}, chest_items(slots))
        self.assertEqual((128,), chest_companions(slots))

    def test_empty_slots_contribute_nothing(self) -> None:
        self.assertEqual(0, chest_coins([""] * 6))
        self.assertEqual({}, chest_items([""] * 6))


class TeamLuckReadTest(unittest.TestCase):
    def test_the_party_average_comes_off_the_save(self) -> None:
        self.assertEqual(300, party_team_luck(userdata({1: 200, 2: 400})))

    def test_an_empty_slot_does_not_dilute_the_average(self) -> None:
        """A zero in teamMembers is an empty slot, not a zero-Luck member."""
        self.assertEqual(300, party_team_luck(userdata({1: 200, 2: 400}, [1, 2, 0, 0, 0, 0])))

    def test_a_save_without_a_party_is_zero(self) -> None:
        self.assertEqual(0, party_team_luck({}))


class LuckGrowthTest(unittest.TestCase):
    def test_below_eight_stamina_nothing_grows(self) -> None:
        """Mistwalker's own rule, and it makes every Daily Quest ineligible."""
        for stamina in (0, 5, 7):
            self.assertEqual(
                [0] * 6, roll_luck_up_table(userdata({1: 0, 2: 0}), stamina, "r", "d"),
            )

    def test_a_costly_stage_eventually_grows_someone(self) -> None:
        grew = any(
            any(roll_luck_up_table(userdata({1: 0, 2: 0}), 40, f"r{n}", "d"))
            for n in range(40)
        )
        self.assertTrue(grew, "40 stamina never raised anyone's Luck in 40 battles")

    def test_growth_is_replay_stable(self) -> None:
        first = roll_luck_up_table(userdata({1: 0, 2: 0}), 40, "r", "d")
        self.assertEqual(first, roll_luck_up_table(userdata({1: 0, 2: 0}), 40, "r", "d"))

    def test_a_capped_character_gains_nothing_further(self) -> None:
        for attempt in range(30):
            table = roll_luck_up_table(
                userdata({1: LUCK_TENTHS_MAX}), 40, f"r{attempt}", "d",
            )
            self.assertEqual(0, table[0], f"gained past the ceiling on attempt {attempt}")

    def test_applying_a_gain_stops_at_the_ceiling(self) -> None:
        save = userdata({1: 999, 2: 100})
        apply_luck_up_table(save, [3, 2, 0, 0, 0, 0])
        self.assertEqual(LUCK_TENTHS_MAX, save["chrdata"][0]["luck"])
        self.assertEqual(102, save["chrdata"][1]["luck"])

    def test_applying_an_empty_table_changes_nothing(self) -> None:
        save = userdata({1: 500})
        apply_luck_up_table(save, [0] * 6)
        self.assertEqual(500, save["chrdata"][0]["luck"])


if __name__ == "__main__":
    unittest.main()
