from __future__ import annotations

import unittest

from liminal_gate.luck_data import (
    ALLOW_LUCKY_CHAPTERS,
    CHEST_TIERS,
    LUCK_CAP_BY_CHARACTER,
    LUCK_TENTHS_MAX,
    LUCKY_ORBLING_GAIN_TENTHS,
    LUCKY_RUNNER_CHAPTERS,
    LUCKY_RUNNER_GAIN_TENTHS,
    character_luck_cap,
)
from liminal_gate.luck_pool_catalog import LuckPoolCatalog
from liminal_gate.trading_post_data import TRADING_POST_WEEKS
from liminal_gate.luck_pool_interpolation import build_luck_pools
from liminal_gate.luck_pool_data import (
    LUCK_CHEST_POOLS,
    NO_CHEST_CHAPTERS,
    has_documented_pool,
    pool_for,
    refuses_chest,
)
from liminal_gate.luck_pool_event_data import (
    ATTRIBUTE_TYPE_ITEMS,
    BREASOUL_CHEST_POOLS,
    DAILY_QUEST_CHEST_EXTRAS,
    DAILY_QUEST_CHEST_POOLS,
    DAILY_QUEST_COMPANIONS,
    DAILY_QUEST_MONSTERS,
    EIDOLON_CHEST_POOLS,
    FIVE_EMPERORS_CHEST_POOLS,
    WEAPON_TYPE_ITEMS,
    EIDOLON_SINGLE_QUEST_REWARDS,
    EIDOLON_THIRD_QUEST_REWARDS,
    SPECIES_TYPE_ITEMS,
    STRIKES_BACK_CHEST_POOLS,
    STRIKES_BACK_EVENT_ITEM,
    STRIKES_BACK_FAMILY_REWARDS,
)
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

    def test_the_stage_whose_table_carries_no_heading_is_recorded(self) -> None:
        """Chapter 25-7's table has no heading at all, so the first scrape walked
        past it. It is the only Chapter 25 stage the record documents, and every
        cell the record fills for it resolved -- the empty Luck 100 cell is the
        record's own gap, so that tier is absent rather than invented."""
        self.assertTrue(has_documented_pool(25, 7))
        self.assertEqual(("C900", "M314", "O128", "O129"), LUCK_CHEST_POOLS[(25, 7)]["Luck 80"])
        self.assertNotIn("Luck 100", LUCK_CHEST_POOLS[(25, 7)])

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


class NoChestQuestTest(unittest.TestCase):
    """The record's own list of quests that carry no chest at all.

    A quest here is different from an undocumented one. An undocumented stage
    is a gap the record leaves and interpolation may fill; a listed one is the
    record stating an absence.
    """

    def test_the_listed_chapters_never_roll_a_chest(self) -> None:
        pools = build_luck_pools(None, interpolate=True)
        for chapter in NO_CHEST_CHAPTERS:
            with self.subTest(chapter=chapter):
                self.assertTrue(refuses_chest(chapter))
                self.assertFalse(has_documented_pool(chapter, 1))
                for tier in CHEST_TIERS:
                    self.assertEqual((), pool_for(chapter, 1, tier.name))
                    self.assertEqual((), pools.pool_for(chapter, 1, tier.name))
                self.assertEqual(
                    [""] * len(CHEST_TIERS),
                    roll_luck_result(chapter, 1, LUCK_TENTHS_MAX, "r", "d", catalog=pools),
                )

    def test_the_four_event_chapters_interpolation_had_reached(self) -> None:
        """Jade Dragon, Mobius, Captive Golem and Vengeful Heart are event
        stages, so once event starts rolled against interpolated pools they
        began paying chests the record says they never had."""
        for chapter in (2004, 2005, 2008, 2014):
            self.assertIn(chapter, NO_CHEST_CHAPTERS)

    def test_an_operator_catalog_still_overrides_the_refusal(self) -> None:
        """Naming a stage in that file is an operator deciding to go past the
        record, and this list is the record."""
        catalog = LuckPoolCatalog({(7010, 1): {"A": ("C100",)}})
        layered = build_luck_pools(catalog, interpolate=True)
        self.assertEqual(("C100",), layered.pool_for(7010, 1, "A"))
        self.assertEqual((), layered.pool_for(7010, 2, "A"))


class StrikesBackChestRecordTest(unittest.TestCase):
    """The fourteen families recovered from the record's own chest template.

    The template is the reason this half was missed twice: a Strikes Back page
    holds one invocation where a story page holds a table, so both earlier
    scrapes -- one searching the heading, one searching the table's header row
    -- read fourteen documented families as undocumented.
    """

    #: The record's three quests are sections 1--3, at the 5/10/15 stamina
    #: `_counter_descent_stamina` serves.
    SECTIONS = (1, 2, 3)

    def test_every_family_documents_its_three_quests(self) -> None:
        for chapter, *_ in STRIKES_BACK_FAMILY_REWARDS:
            for section in self.SECTIONS:
                self.assertTrue(
                    has_documented_pool(chapter, section), f"{chapter}-{section}",
                )
        self.assertEqual(
            len(STRIKES_BACK_FAMILY_REWARDS) * len(self.SECTIONS),
            len(STRIKES_BACK_CHEST_POOLS),
        )

    def test_the_named_companions_climb_the_record_ladder(self) -> None:
        """Where each Companion appears is the whole answer to Issue 76.

        Quest I pays the recruit and Metal Minion at both named tiers; quest II
        adds the second-form Companion at Luck 100; quest III moves that one
        down to Luck 80 and pays the family's own Companion, its second form
        and the guest one together at Luck 100. That last tier is the only
        place three of the four ever drop.
        """
        chapter, recruit, omicron, omicron2, other = STRIKES_BACK_FAMILY_REWARDS[6]
        self.assertEqual(8006, chapter)
        self.assertEqual((f"M{recruit}", "O128"), pool_for(chapter, 1, "Luck 100"))
        self.assertEqual(
            (f"M{recruit}", f"O{omicron2}", "O128"), pool_for(chapter, 2, "Luck 100"),
        )
        self.assertEqual(
            (f"M{recruit}", f"O{omicron2}", "O128"), pool_for(chapter, 3, "Luck 80"),
        )
        self.assertEqual(
            (f"M{recruit}", f"O{omicron}", f"O{omicron2}", f"O{other}", "O128"),
            pool_for(chapter, 3, "Luck 100"),
        )
        for tier in ("Luck 80", "Luck 100"):
            self.assertNotIn(f"O{omicron}", pool_for(chapter, 1, tier))
            self.assertNotIn(f"O{omicron}", pool_for(chapter, 2, tier))

    def test_the_event_item_tiers_pay_animata_core(self) -> None:
        """A and B pay the event item, which in this build is one item.

        The tables were written while it rotated across eight Animata items.
        Version 5.5.0 replaced all of them with Animata Core in every drop
        table, and the reviewed build is 5.5.7 -- so for the build served here
        the two tiers name item 181 and nothing else. The count the record
        states does not survive a wire form that carries one reward per slot,
        and is not invented; see the module for why.
        """
        self.assertEqual("I181", STRIKES_BACK_EVENT_ITEM)
        for chapter, *_ in STRIKES_BACK_FAMILY_REWARDS:
            for section in self.SECTIONS:
                self.assertEqual((STRIKES_BACK_EVENT_ITEM,), pool_for(chapter, section, "A"))
                self.assertEqual((STRIKES_BACK_EVENT_ITEM,), pool_for(chapter, section, "B"))
                self.assertTrue(pool_for(chapter, section, "C"))

    def test_the_event_item_is_the_one_the_trading_post_is_priced_in(self) -> None:
        """The corroboration, and it is this project's own recovery rather than
        the record: the Trading Post prices every trade in the same item these
        quests pay, which is what makes them the place it is farmed."""
        priced_in = {row[5] for week in TRADING_POST_WEEKS for row in week}
        self.assertEqual({int(STRIKES_BACK_EVENT_ITEM[1:])}, priced_in)

    def test_the_undocumented_fourth_section_is_not_given_a_table(self) -> None:
        """Chapters 8000--8007 serve a fourth 15-stamina section the record
        documents no quest for, and a section the record never covered is not
        one it covered identically to the third."""
        for chapter in range(8000, 8008):
            self.assertFalse(has_documented_pool(chapter, 4), chapter)

    def test_every_recovered_reward_is_a_well_formed_slot(self) -> None:
        for (chapter, section), tiers in STRIKES_BACK_CHEST_POOLS.items():
            for tier, pool in tiers.items():
                self.assertEqual(
                    len(pool), len(set(pool)), f"{chapter}-{section} {tier} repeats",
                )
                for reward in pool:
                    self.assertRegex(reward, r"^[CIOM][1-9][0-9]*$")

    def test_a_full_luck_party_reaches_the_family_companions(self) -> None:
        """Quest III at 100.0 Luck fills the tier those Companions live in."""
        chapter, recruit, omicron, _omicron2, _other = STRIKES_BACK_FAMILY_REWARDS[6]
        drawn = {
            roll_luck_result(chapter, 3, LUCK_TENTHS_MAX, f"r{attempt}", "d")[5]
            for attempt in range(40)
        }
        self.assertNotIn("", drawn)
        self.assertLessEqual(drawn, set(pool_for(chapter, 3, "Luck 100")))
        self.assertIn(f"O{omicron}", drawn)


class EidolonChestRecordTest(unittest.TestCase):
    """The twelve Eidolons, through the record's own Eidolon template.

    The template switches on a `stages` count, and that count is exactly the
    section this archive serves: the client's BattleData gives a three-stage
    Eidolon sections 1--3 with a battle in section 3 alone. Twelve families,
    twelve agreements.
    """

    def test_every_eidolon_documents_the_section_the_archive_serves(self) -> None:
        served = {
            (chapter, 3) for chapter, *_ in EIDOLON_THIRD_QUEST_REWARDS
        } | {(row[0], 1) for row in EIDOLON_SINGLE_QUEST_REWARDS}
        self.assertEqual(served, set(EIDOLON_CHEST_POOLS))
        self.assertEqual(12, len(EIDOLON_CHEST_POOLS))
        for chapter, section in served:
            self.assertTrue(has_documented_pool(chapter, section), (chapter, section))

    def test_the_unserved_first_and_second_quests_get_no_pool(self) -> None:
        """Their tables are on the page and no battle is behind them, so there
        is no stage for those pools to attach to."""
        for chapter, *_ in EIDOLON_THIRD_QUEST_REWARDS:
            for section in (1, 2):
                self.assertFalse(has_documented_pool(chapter, section), (chapter, section))

    def test_the_third_quest_pays_the_eidolons_own_rewards(self) -> None:
        chapter, item, companion, omicron, unique1, unique2 = EIDOLON_THIRD_QUEST_REWARDS[0]
        self.assertEqual(4100, chapter)
        self.assertEqual((unique1, unique2), pool_for(chapter, 3, "D"))
        self.assertEqual(("C1500", item, companion), pool_for(chapter, 3, "Luck 80"))
        self.assertEqual((item, unique1, unique2, omicron), pool_for(chapter, 3, "Luck 100"))

    def test_the_species_tier_drops_the_material_the_record_excludes(self) -> None:
        """"Species-type items (except Oxsecian)" is the record naming a class
        and then removing one member of it by name."""
        expected = set(SPECIES_TYPE_ITEMS) - {"I83"}
        self.assertEqual(len(SPECIES_TYPE_ITEMS) - 1, len(expected))
        for (chapter, section) in EIDOLON_CHEST_POOLS:
            for tier in ("A", "B"):
                pool = pool_for(chapter, section, tier)
                coins = [slot for slot in pool if slot.startswith("C")]
                self.assertEqual(1, len(coins), f"{chapter}-{section} {tier}")
                self.assertEqual(expected, set(pool) - set(coins), f"{chapter}-{section} {tier}")

    def test_the_unnamed_selene_rewards_are_left_out(self) -> None:
        """Selene's page carries the template's own `Companion` placeholder
        where its second Companion and its Omicron belong. Two of the five
        rewards its Luck 100 chest lists are therefore unknown, and inventing
        either would be inventing the reward the record declined to name."""
        chapter = EIDOLON_SINGLE_QUEST_REWARDS[3][0]
        self.assertEqual(4111, chapter)
        self.assertEqual(("O482", "M1239", "O483"), pool_for(chapter, 1, "Luck 100"))
        self.assertNotIn("", pool_for(chapter, 1, "Luck 80"))


class ArchiveSpecialChestRecordTest(unittest.TestCase):
    def test_the_sarah_quest_pays_the_character_its_manifest_names(self) -> None:
        """The join is confirmed from the client, not the title: the chest's
        recruit resolves to 1288, the character chapter 2018's own recovered
        manifest associates with the event."""
        self.assertTrue(has_documented_pool(2018, 1))
        self.assertEqual(("M1288", "O128", "O129"), pool_for(2018, 1, "Luck 100"))
        self.assertIn("M1288", pool_for(2018, 1, "D"))


class DailyQuestChestRecordTest(unittest.TestCase):
    """Ten of the fourteen Daily Quest stages, through their shared template."""

    def test_the_documented_quests_are_the_ten_with_a_page(self) -> None:
        """Particle Hoarder Horde and both Yamamoto Puzzle Quests have no chest
        page. The Hunt For Joker has one and is excluded anyway, by the Luck
        page's own list."""
        self.assertEqual(
            {(chapter, 1) for chapter in
             (6000, 6001, 6002, 6003, 6005, 6006, 6007, 6008, 6009, 6010)},
            set(DAILY_QUEST_CHEST_POOLS),
        )
        for chapter in (6004, 6011, 6012):
            self.assertFalse(has_documented_pool(chapter, 1), chapter)

    def test_every_quest_shares_the_template_base(self) -> None:
        materials = set(SPECIES_TYPE_ITEMS + WEAPON_TYPE_ITEMS + ATTRIBUTE_TYPE_ITEMS)
        for (chapter, section) in DAILY_QUEST_CHEST_POOLS:
            with self.subTest(chapter=chapter):
                self.assertEqual(materials, set(pool_for(chapter, section, "A")))
                self.assertEqual(materials, set(pool_for(chapter, section, "B")))
                self.assertLessEqual(
                    set(DAILY_QUEST_MONSTERS), set(pool_for(chapter, section, "C")),
                )
                self.assertLessEqual(
                    set(DAILY_QUEST_COMPANIONS), set(pool_for(chapter, section, "Luck 100")),
                )

    def test_the_one_quest_whose_additions_reach_another_tier(self) -> None:
        """Tropical Haze adds its three tickets to D as well as to Luck 80;
        every other quest adds to Luck 80 alone."""
        tickets = ("I50", "I81", "I112")
        for reward in tickets:
            self.assertIn(reward, pool_for(6007, 1, "D"))
            self.assertIn(reward, pool_for(6007, 1, "Luck 80"))
        for chapter in DAILY_QUEST_CHEST_EXTRAS:
            if chapter == 6007:
                continue
            with self.subTest(chapter=chapter):
                self.assertEqual(
                    set(DAILY_QUEST_COMPANIONS), set(pool_for(chapter, 1, "D")),
                )

    def test_the_additions_agree_with_the_recovered_enemy_records(self) -> None:
        """Independent corroboration: these sets were recovered from the
        client's own enemy records rather than from the record, and the
        record's chest table names the same four in each case."""
        self.assertLessEqual(
            {"I55", "I56", "I53", "I54"}, set(pool_for(6002, 1, "Luck 80")),
        )
        self.assertLessEqual(
            {"I26", "I27", "I28", "I29"}, set(pool_for(6005, 1, "Luck 80")),
        )
        self.assertLessEqual(
            {"I18", "I19", "I20", "I21"}, set(pool_for(6008, 1, "Luck 80")),
        )
        self.assertLessEqual(
            {"I118", "I119", "I120", "I121"}, set(pool_for(6009, 1, "Luck 80")),
        )


class SideWorldChestRecordTest(unittest.TestCase):
    """The two secondary world maps, documented per stage rather than by template."""

    def test_breasoul_covers_every_section_the_client_declares(self) -> None:
        """The page's parts come to 4, 5, 5, 5 and 1, which is exactly the
        section count of chapters 100 to 104."""
        expected = {
            (chapter, section)
            for chapter, count in ((100, 4), (101, 5), (102, 5), (103, 5), (104, 1))
            for section in range(1, count + 1)
        }
        self.assertEqual(expected, set(BREASOUL_CHEST_POOLS))
        self.assertEqual(20, len(BREASOUL_CHEST_POOLS))

    def test_the_breasoul_finale_pays_its_own_boss(self) -> None:
        self.assertIn("M1158", pool_for(104, 1, "Luck 100"))

    def test_the_five_emperors_cover_both_modes(self) -> None:
        self.assertEqual(
            {(chapter, 1) for chapter in range(110, 120)},
            set(FIVE_EMPERORS_CHEST_POOLS),
        )

    def test_the_page_order_agrees_with_the_recovered_drop_manifests(self) -> None:
        """The five normal descents name the same first-clear Companion the
        client's own `dropBuddies` gives chapters 110--114, and the five hard
        ones the same for 115--119. Asserted on the two the record spells out
        in its Luck chests as well as its reward list."""
        self.assertIn("O464", pool_for(110, 1, "Luck 80"))   # Shining Mirror, Garuda
        self.assertIn("O464", pool_for(115, 1, "C"))         # and again in hard Garuda

    def test_every_side_world_reward_is_a_well_formed_slot(self) -> None:
        for pools in (BREASOUL_CHEST_POOLS, FIVE_EMPERORS_CHEST_POOLS):
            for (chapter, section), tiers in pools.items():
                for tier, pool in tiers.items():
                    self.assertEqual(len(pool), len(set(pool)), f"{chapter}-{section} {tier}")
                    for reward in pool:
                        self.assertRegex(reward, r"^[CIOM][1-9][0-9]*$")


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


def three_squads(party_luck: dict[int, int], squads: list[list[int]], team_no: int) -> dict:
    """A save keeping several squads, fielding one of them.

    `teamMembers` is every squad flattened into one array and `teamNo` names the
    one on screen; the six-entry saves above are the single-squad case, which is
    the one shape where reading the front of the array happens to be right.
    """
    return {
        "chrdata": [{"id": cid, "luck": luck} for cid, luck in party_luck.items()],
        "teamMembers": [member for squad in squads for member in squad],
        "teamNo": team_no,
    }


class FieldedSquadTest(unittest.TestCase):
    """Every Luck decision belongs to the squad on screen.

    Three testers reported Luck that did not stick -- one of them only in the
    Metal Zones, one not at all, and one who watched a gain announced for the
    character in one party slot appear on the character in another. All three
    are this: the runtime read the first six entries of `teamMembers`, which
    name Squad 1 no matter which squad is fighting.
    """

    BENCH, FIGHTER = 1, 2
    #: Squad 1 benched, Squad 2 empty, Squad 3 on screen.
    SQUADS = [[BENCH, 0, 0, 0, 0, 0], [0] * 6, [FIGHTER, 0, 0, 0, 0, 0]]

    def save(self, bench: int, fighter: int) -> dict:
        return three_squads({self.BENCH: bench, self.FIGHTER: fighter}, self.SQUADS, 3)

    def test_the_chest_odds_read_the_squad_on_screen(self) -> None:
        """Chest tiers follow team Luck, so a benched squad decided which
        chests a battle it did not fight could pay out."""
        self.assertEqual(400, party_team_luck(self.save(bench=0, fighter=400)))

    def test_growth_is_rolled_against_the_squad_on_screen(self) -> None:
        """The benched squad is at its ceiling and the fighting one is not, so
        reading the wrong one leaves no headroom to gain into at all."""
        save = self.save(bench=character_luck_cap(self.BENCH), fighter=0)
        grew = any(
            any(roll_luck_up_table(save, 40, f"r{n}", "d")) for n in range(40)
        )
        self.assertTrue(grew, "40 battles raised nothing for the squad on screen")

    def test_a_gain_is_paid_to_the_squad_on_screen(self) -> None:
        save = self.save(bench=0, fighter=0)
        apply_luck_up_table(save, [3, 0, 0, 0, 0, 0])
        paid = {row["id"]: row["luck"] for row in save["chrdata"]}
        self.assertEqual({self.BENCH: 0, self.FIGHTER: 3}, paid)

    def test_a_squad_number_naming_no_squad_falls_back_to_the_first(self) -> None:
        """A malformed pairing is not a statement about the party; the same
        reading `active_party_members` gives every other caller."""
        save = three_squads({self.BENCH: 0, self.FIGHTER: 0}, self.SQUADS, 9)
        apply_luck_up_table(save, [3, 0, 0, 0, 0, 0])
        paid = {row["id"]: row["luck"] for row in save["chrdata"]}
        self.assertEqual({self.BENCH: 3, self.FIGHTER: 0}, paid)


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

    def test_applying_a_gain_stops_at_the_characters_own_ceiling(self) -> None:
        """The ceiling is per character, not the absolute one.

        Characters 1 and 2 are an A-and-below and an S/SS unit in the recovered
        caps, so the same table stops them in different places. Applying the
        absolute 100.0 to everyone is what let a tester's C-class Dark Tortoise
        reach 83.3 against a real cap of 70.0.
        """
        self.assertEqual((700, 800), (character_luck_cap(1), character_luck_cap(2)))
        save = userdata({1: 699, 2: 100})
        apply_luck_up_table(save, [3, 2, 0, 0, 0, 0])
        self.assertEqual(700, save["chrdata"][0]["luck"])
        self.assertEqual(102, save["chrdata"][1]["luck"])

    def test_a_character_already_at_its_cap_gains_nothing(self) -> None:
        save = userdata({1: 700})
        apply_luck_up_table(save, [3, 0, 0, 0, 0, 0])
        self.assertEqual(700, save["chrdata"][0]["luck"])

    def test_only_the_top_band_reaches_the_absolute_ceiling(self) -> None:
        top = next(
            character_id
            for character_id, cap in LUCK_CAP_BY_CHARACTER.items()
            if cap == LUCK_TENTHS_MAX
        )
        save = userdata({top: 999})
        apply_luck_up_table(save, [3, 0, 0, 0, 0, 0])
        self.assertEqual(LUCK_TENTHS_MAX, save["chrdata"][0]["luck"])

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
