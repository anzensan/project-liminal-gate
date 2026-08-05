from __future__ import annotations

import unittest

from liminal_gate.luck_data import (
    ALLOW_LUCKY_CHAPTERS,
    LUCK_TENTHS_MAX,
    LUCKY_ORBLING_GAIN_TENTHS,
    LUCKY_RUNNER_CHAPTERS,
    LUCKY_RUNNER_GAIN_TENTHS,
)
from liminal_gate.luck_pool_data import LUCK_CHEST_POOLS, has_documented_pool
from liminal_gate.luck_runtime import (
    apply_luck_up_table,
    chest_coins,
    chest_companions,
    chest_items,
    party_team_luck,
    roll_luck_result,
    roll_luck_up_table,
    roll_lucky_enemy_gain,
)

#: 6010 Lucky Orbling: a flagged chapter whose Lucky enemy is an Orbling.
ORBLING_CHAPTER = 6010
#: 7010 Cryptid Forest: the flagged chapter whose Lucky enemy is a Runner.
RUNNER_CHAPTER = 7010


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


class LuckyEnemySourceTest(unittest.TestCase):
    """The `allowLucky` source, which the stamina gate deliberately does not
    govern -- three of the five flagged chapters cost less than eight stamina
    or nothing at all."""

    def test_a_free_flagged_stage_still_grows_luck(self) -> None:
        """Lucky Orbling is free, and granting Luck is the whole point of it."""
        grew = any(
            any(roll_luck_up_table(
                userdata({1: 0, 2: 0}), 0, f"r{n}", "d", lucky_chapter=ORBLING_CHAPTER,
            ))
            for n in range(40)
        )
        self.assertTrue(grew, "40 battles on a free flagged stage raised no Luck")

    def test_the_gain_is_the_record_s_three_tenths(self) -> None:
        seen = {
            gain
            for n in range(60)
            for gain in roll_luck_up_table(
                userdata({1: 0, 2: 0}), 0, f"r{n}", "d", lucky_chapter=ORBLING_CHAPTER,
            )
        }
        self.assertLessEqual(seen, {0, LUCKY_ORBLING_GAIN_TENTHS})

    def test_a_pincer_grants_the_whole_party_at_once(self) -> None:
        """The record describes the gain as reaching every party member, so it
        is one draw for the battle rather than six independent ones."""
        for n in range(40):
            table = roll_luck_up_table(
                userdata({1: 0, 2: 0, 3: 0}), 0, f"r{n}", "d", lucky_chapter=ORBLING_CHAPTER,
            )
            occupied = table[:3]
            self.assertEqual(1, len(set(occupied)), f"party split on battle {n}: {table}")

    def test_an_empty_party_slot_stays_zero(self) -> None:
        for n in range(20):
            table = roll_luck_up_table(
                userdata({1: 0}, [1, 0, 0, 0, 0, 0]), 0, f"r{n}", "d", lucky_chapter=ORBLING_CHAPTER,
            )
            self.assertEqual([0] * 5, table[1:], f"an empty slot gained on battle {n}")

    def test_the_flag_never_shifts_an_existing_battle_end_roll(self) -> None:
        """The Lucky draw comes off its own stream precisely so that adding it
        cannot change what a stage that already granted Luck grants."""
        for n in range(40):
            plain = roll_luck_up_table(userdata({1: 0, 2: 0}), 40, f"r{n}", "d")
            flagged = roll_luck_up_table(
                userdata({1: 0, 2: 0}), 40, f"r{n}", "d", lucky_chapter=ORBLING_CHAPTER,
            )
            lucky = roll_lucky_enemy_gain(ORBLING_CHAPTER, f"r{n}", "d")
            self.assertEqual(
                [value + lucky for value in plain[:2]], flagged[:2],
                f"the battle-end roll moved on battle {n}",
            )

    def test_the_flag_is_replay_stable(self) -> None:
        first = roll_luck_up_table(userdata({1: 0}), 0, "r", "d", lucky_chapter=ORBLING_CHAPTER)
        self.assertEqual(
            first, roll_luck_up_table(userdata({1: 0}), 0, "r", "d", lucky_chapter=ORBLING_CHAPTER),
        )

    def test_a_capped_character_gains_nothing_from_a_pincer_either(self) -> None:
        for n in range(30):
            table = roll_luck_up_table(
                userdata({1: LUCK_TENTHS_MAX}), 0, f"r{n}", "d", lucky_chapter=ORBLING_CHAPTER,
            )
            self.assertEqual(0, table[0], f"gained past the ceiling on battle {n}")

    def test_the_five_flagged_chapters_are_the_recovered_ones(self) -> None:
        self.assertEqual({2006, 3003, 3004, 6010, 7010}, set(ALLOW_LUCKY_CHAPTERS))

    def test_an_unflagged_chapter_offers_no_lucky_source(self) -> None:
        """Passing the chapter rather than a flag means the membership test is
        the runtime's, so a chapter outside the five must still grant nothing."""
        for n in range(20):
            self.assertEqual(
                [0] * 6,
                roll_luck_up_table(
                    userdata({1: 0, 2: 0}), 0, f"r{n}", "d", lucky_chapter=1001,
                ),
                f"an unflagged chapter granted Luck on battle {n}",
            )


class LuckyRunnerZoneTest(unittest.TestCase):
    """Cryptid Forest, 7010, is the one flagged chapter the record documents
    enemy by enemy, and the enemy it documents is a Lucky Runner: one always
    spawns, a second spawns with a 30% chance, and a pincer from any direction
    grants 0.1 to the whole party. It had been granting the Orbling's 0.3 on a
    coin flip -- the wrong species, the wrong magnitude, and the wrong shape."""

    def test_the_runner_zone_never_grants_the_orbling_s_three_tenths(self) -> None:
        seen = {roll_lucky_enemy_gain(RUNNER_CHAPTER, f"r{n}", "d") for n in range(200)}
        self.assertNotIn(
            LUCKY_ORBLING_GAIN_TENTHS, seen,
            "Cryptid Forest still pays an Orbling's Luck",
        )

    def test_a_runner_always_spawns_so_every_battle_grants(self) -> None:
        """The guaranteed spawn is the record's, not a roll: a run that grants
        nothing would be the defect in the other direction."""
        for n in range(60):
            self.assertGreaterEqual(
                roll_lucky_enemy_gain(RUNNER_CHAPTER, f"r{n}", "d"),
                LUCKY_RUNNER_GAIN_TENTHS,
                f"no Lucky Runner granted on battle {n}",
            )

    def test_the_gain_is_one_or_two_runners_worth(self) -> None:
        seen = {roll_lucky_enemy_gain(RUNNER_CHAPTER, f"r{n}", "d") for n in range(200)}
        self.assertEqual(
            {LUCKY_RUNNER_GAIN_TENTHS, 2 * LUCKY_RUNNER_GAIN_TENTHS}, seen,
        )

    def test_the_second_runner_is_the_exception_rather_than_the_rule(self) -> None:
        """A 30% second spawn: seeded, so this is a fixed count rather than a
        sampling assertion, and it pins the rate against drifting to a coin
        flip or to a guarantee."""
        trials = 400
        doubles = sum(
            roll_lucky_enemy_gain(RUNNER_CHAPTER, f"r{n}", "d")
            == 2 * LUCKY_RUNNER_GAIN_TENTHS
            for n in range(trials)
        )
        self.assertLess(doubles, trials // 2, "a second Runner spawned too often")
        self.assertGreater(doubles, trials // 10, "a second Runner never spawned")

    def test_the_runner_zone_reaches_the_party_through_the_table(self) -> None:
        """7010 costs one stamina, far below the battle-end gate, so the whole
        gain has to arrive through the Lucky-enemy source."""
        for n in range(30):
            table = roll_luck_up_table(
                userdata({1: 0, 2: 0}), 1, f"r{n}", "d", lucky_chapter=RUNNER_CHAPTER,
            )
            self.assertIn(
                table[0], (LUCKY_RUNNER_GAIN_TENTHS, 2 * LUCKY_RUNNER_GAIN_TENTHS),
                f"battle {n} paid {table[0]} tenths",
            )
            self.assertEqual(table[0], table[1], f"party split on battle {n}")

    def test_the_orbling_chapters_are_untouched_by_the_runner_rule(self) -> None:
        """The correction is scoped to the chapter the record names. The other
        four keep the Orbling policy, and their stream must not have moved."""
        for n in range(60):
            self.assertIn(
                roll_lucky_enemy_gain(ORBLING_CHAPTER, f"r{n}", "d"),
                (0, LUCKY_ORBLING_GAIN_TENTHS),
            )

    def test_cryptid_forest_is_the_only_runner_chapter(self) -> None:
        self.assertEqual({7010}, set(LUCKY_RUNNER_CHAPTERS))
        self.assertLessEqual(LUCKY_RUNNER_CHAPTERS, ALLOW_LUCKY_CHAPTERS)


if __name__ == "__main__":
    unittest.main()
