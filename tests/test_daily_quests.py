from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from urllib.parse import urlencode

from liminal_gate.daily_quest_data import (
    DAILY_QUEST_EPOCH_DAY,
    DAILY_QUEST_EVENT_FLAG,
    DAILY_QUEST_ROTATION,
    build_bundled_daily_quest_stages,
    daily_quest_event_flags,
    daily_quest_rotation,
)
from liminal_gate.bootstrap_server import (
    BootstrapState,
    _announced_roster,
    _apply_hunting_character_grants,
    _daily_quest_played_today,
    _stamp_daily_quest_clear,
    daily_quest_login_fields,
)
from liminal_gate.archive_economy import (
    DAILY_QUEST_FREE_ENERGY,
    ENERGY_BEARING_KINDS,
    MAX_FREE_ENERGY,
    award_daily_quest_energy,
    award_stage_energy,
)
from liminal_gate.server_constants import build_server_constants
from liminal_gate.bootstrap_parsers import _valid_generic_character_record
from liminal_gate.hunting_catalog import HuntingCatalog, BUNDLED_ITEM_SLOTS, BUNDLED_MAX_STACK, hunting_settlement_within_bounds
from tests.support import bootstrap_profile, get, post, start_server, stop_server


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

    def test_the_hunt_for_joker_grants_joker_lambda(self) -> None:
        """Joker Λ is character 1018: a character grant, not an item or Companion."""
        stage = next(s for s in build_bundled_daily_quest_stages() if (s.chapter, s.section) == (6012, 1))
        self.assertEqual((1018,), stage.character_grants)
        # 10% Skill Boost and 10 Luck, both in the client's tenths, which is
        # what the client's own recruit message announces to the player.
        self.assertEqual((100, 100), (stage.duplicate_grant_skill_boost, stage.duplicate_grant_luck))
        self.assertEqual({}, stage.companion_maxima)

    def test_only_the_joker_quest_grants_a_character(self) -> None:
        for stage in build_bundled_daily_quest_stages():
            if stage.family != "the_hunt_for_joker":
                with self.subTest(stage=stage.identity_label()):
                    self.assertEqual((), stage.character_grants)

    def test_every_daily_quest_pays_out_once_per_day(self) -> None:
        for stage in build_bundled_daily_quest_stages():
            with self.subTest(stage=stage.identity_label()):
                self.assertTrue(stage.once_per_utc_day)


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

    def test_a_daily_quest_settles_ordinary_battle_experience(self) -> None:
        """A Daily Quest is an ordinary battle and pays ordinary EXP.

        Refusing all of it was the bug: Metal Runner Rampage pays nothing but
        EXP, and its recovered spawns reach 306,000 on their own.
        """
        for stage in build_bundled_daily_quest_stages():
            with self.subTest(stage=stage.identity_label()):
                self.assertTrue(hunting_settlement_within_bounds(stage, result(exp=306_000)))

    def test_an_absurd_experience_claim_is_still_refused(self) -> None:
        for stage in build_bundled_daily_quest_stages():
            with self.subTest(stage=stage.identity_label()):
                self.assertFalse(hunting_settlement_within_bounds(stage, result(exp=7_720_001)))

    def test_each_puzzle_quest_settles_the_companion_its_manifest_names(self) -> None:
        """The two `dropBuddies` codes, 68353 and 35841, decoded and honoured.

        Declaring neither is what refused an honest Puzzle Quest clear and left
        the account's battle active; see issue 29.
        """
        self.assertTrue(hunting_settlement_within_bounds(self.stage(6011, 1), result(buddies=[267])))
        self.assertTrue(hunting_settlement_within_bounds(self.stage(6011, 2), result(buddies=[140])))

    def test_a_puzzle_quest_refuses_the_other_ones_companion(self) -> None:
        """Each manifest names one candidate, and only that one."""
        self.assertFalse(hunting_settlement_within_bounds(self.stage(6011, 1), result(buddies=[140])))
        self.assertFalse(hunting_settlement_within_bounds(self.stage(6011, 2), result(buddies=[267])))

    def test_a_puzzle_quest_settles_at_most_one_companion(self) -> None:
        """`code & 0xFF` is 1 on both manifests, so a second copy is a claim."""
        self.assertFalse(hunting_settlement_within_bounds(self.stage(6011, 1), result(buddies=[267, 267])))

    def test_a_dropped_companion_arrives_at_level_one(self) -> None:
        for identity, companion in (((6011, 1), 267), ((6011, 2), 140)):
            with self.subTest(stage=identity):
                self.assertEqual({companion: 1}, self.stage(*identity).companion_drop_levels)

    def test_the_other_twelve_quests_refuse_every_companion(self) -> None:
        """Their own `dropBuddies` manifests are empty, so the refusal stands."""
        for stage in build_bundled_daily_quest_stages():
            if (stage.chapter, stage.section) in {(6011, 1), (6011, 2)}:
                continue
            with self.subTest(stage=stage.identity_label()):
                self.assertEqual({}, stage.companion_maxima)
                self.assertFalse(hunting_settlement_within_bounds(stage, result(buddies=[267])))

    def test_a_puzzle_quest_settles_every_tier_it_pays(self) -> None:
        """Weapons, Tears and Particles: bounding only the first tier refused
        the other two, which a real clear reports."""
        self.assertTrue(hunting_settlement_within_bounds(
            self.stage(6011, 1), result({9: 12, 18: 6, 22: 4}),
        ))
        # The second Puzzle Quest widens tier one and swaps Particles for Ores.
        self.assertTrue(hunting_settlement_within_bounds(
            self.stage(6011, 2), result({13: 8, 22: 4, 26: 2}),
        ))

    def test_a_puzzle_quest_still_refuses_more_than_its_waves_could_hold(self) -> None:
        self.assertFalse(hunting_settlement_within_bounds(self.stage(6011, 1), result({9: 94})))
        self.assertFalse(hunting_settlement_within_bounds(self.stage(6011, 2), result({13: 82})))

    def test_the_ore_and_tear_families_settle_where_they_drop(self) -> None:
        """Rarity Rumble's Ore and Tearjerker Time's Tears and rings."""
        self.assertTrue(hunting_settlement_within_bounds(self.stage(6005, 1), result({26: 1, 81: 1})))
        self.assertTrue(hunting_settlement_within_bounds(self.stage(6008, 1), result({18: 2, 46: 1})))


class DailyQuestGrantTest(unittest.TestCase):
    """The two helpers the clear path uses, exercised directly."""

    def stage(self):
        return next(s for s in build_bundled_daily_quest_stages() if s.family == "the_hunt_for_joker")

    def test_a_first_clear_adds_joker_lambda_to_the_roster(self) -> None:
        userdata = {"chrdata": []}
        announced = _apply_hunting_character_grants(userdata, self.stage())
        self.assertEqual(1, len(userdata["chrdata"]))
        row = userdata["chrdata"][0]
        self.assertEqual((1018, 0), (row["id"], row["skillBoost"]))
        # The grant is announced on the response, not stored on the row: the
        # durable roster holds only the shape every settlement check accepts.
        self.assertEqual({1018: 1}, announced)
        self.assertTrue(_valid_generic_character_record(row))
        self.assertEqual(
            {"isNew": True, "levelAdded": 1},
            {key: _announced_roster(userdata["chrdata"], announced)[0][key]
             for key in ("isNew", "levelAdded")},
        )

    def test_a_duplicate_raises_skill_boost_and_luck_instead(self) -> None:
        userdata = {"chrdata": [{"id": 1018, "skillBoost": 50, "luck": 20}]}
        _apply_hunting_character_grants(userdata, self.stage())
        self.assertEqual(1, len(userdata["chrdata"]), "a duplicate must not add a second row")
        self.assertEqual((150, 120), (userdata["chrdata"][0]["skillBoost"], userdata["chrdata"][0]["luck"]))

    def test_duplicate_gains_stop_at_the_clients_ceiling(self) -> None:
        userdata = {"chrdata": [{"id": 1018, "skillBoost": 960, "luck": 995}]}
        _apply_hunting_character_grants(userdata, self.stage())
        self.assertEqual((1000, 1000), (userdata["chrdata"][0]["skillBoost"], userdata["chrdata"][0]["luck"]))

    def test_a_clear_is_remembered_for_the_rest_of_the_utc_day(self) -> None:
        account: dict = {}
        stage = self.stage()
        noon = 1_754_000_000.0
        self.assertFalse(_daily_quest_played_today(account, stage, noon))
        _stamp_daily_quest_clear(account, stage, noon)
        self.assertTrue(_daily_quest_played_today(account, stage, noon))
        self.assertTrue(_daily_quest_played_today(account, stage, noon + 3600))

    def test_the_limit_lifts_at_the_next_utc_midnight(self) -> None:
        account: dict = {}
        stage = self.stage()
        day = 1_754_000_000.0
        _stamp_daily_quest_clear(account, stage, day)
        self.assertFalse(_daily_quest_played_today(account, stage, day + 86_400))

    def test_one_quest_being_played_does_not_lock_another(self) -> None:
        account: dict = {}
        stages = {s.family: s for s in build_bundled_daily_quest_stages()}
        now = 1_754_000_000.0
        _stamp_daily_quest_clear(account, stages["the_hunt_for_joker"], now)
        self.assertFalse(_daily_quest_played_today(account, stages["sweet_temptation"], now))


class DailyQuestEnergyTest(unittest.TestCase):
    """The reward the client draws and the server has to back with a balance.

    `DailyQuestManager.EnergyGetChapter` is 6006 and the result screen takes
    its amount from `EnergyBonusByDailyQuest`. Nothing in the client mints it,
    so a server that grants none shows an Energy line with no amount and moves
    no wallet -- the reported symptom.
    """

    def account(self, free_energy: int = 0) -> dict:
        return {"userdata": {"freeEnergy": free_energy}}

    def test_the_advertised_constant_and_the_grant_are_one_number(self) -> None:
        """A screen that promises what the wallet does not pay is the bug."""
        self.assertEqual(
            DAILY_QUEST_FREE_ENERGY,
            build_server_constants()["EnergyBonusByDailyQuest"],
        )

    def test_a_clear_pays_the_advertised_energy(self) -> None:
        account = self.account(4)
        self.assertEqual(
            DAILY_QUEST_FREE_ENERGY,
            award_daily_quest_energy(account, "6006-1", 20_000),
        )
        self.assertEqual(4 + DAILY_QUEST_FREE_ENERGY, account["userdata"]["freeEnergy"])

    def test_every_daily_quest_pays_not_only_the_energy_one(self) -> None:
        """Local policy, wider than the client's own rule. 6006 is the only
        chapter the client designates; the operator asked for all fourteen."""
        account = self.account()
        for stage in build_bundled_daily_quest_stages():
            with self.subTest(stage=stage.identity_label()):
                self.assertEqual(
                    DAILY_QUEST_FREE_ENERGY,
                    award_daily_quest_energy(account, stage.identity_label(), 20_000),
                )

    def test_a_second_clear_the_same_day_pays_nothing(self) -> None:
        """Keyed by quest and day, not by request id, so a replay cannot farm."""
        account = self.account()
        award_daily_quest_energy(account, "6006-1", 20_000)
        self.assertEqual(0, award_daily_quest_energy(account, "6006-1", 20_000))
        self.assertEqual(DAILY_QUEST_FREE_ENERGY, account["userdata"]["freeEnergy"])

    def test_the_next_utc_day_pays_again(self) -> None:
        account = self.account()
        award_daily_quest_energy(account, "6006-1", 20_000)
        self.assertEqual(
            DAILY_QUEST_FREE_ENERGY,
            award_daily_quest_energy(account, "6006-1", 20_001),
        )

    def test_a_full_wallet_mints_nothing_rather_than_overflowing(self) -> None:
        account = self.account(MAX_FREE_ENERGY)
        self.assertEqual(0, award_daily_quest_energy(account, "6006-1", 20_000))
        self.assertEqual(MAX_FREE_ENERGY, account["userdata"]["freeEnergy"])

    def test_a_save_written_before_this_existed_still_grants(self) -> None:
        """The account document gains a key; it never required one."""
        account = self.account()
        self.assertNotIn("daily_quest_energy_granted", account)
        self.assertEqual(
            DAILY_QUEST_FREE_ENERGY,
            award_daily_quest_energy(account, "6010-1", 20_000),
        )
        self.assertEqual({"6010-1": 20_000}, account["daily_quest_energy_granted"])

    def test_the_replayable_zones_still_pay_nothing(self) -> None:
        """Daily Quests are the exception; Metal Zone and Hunting are not.

        What bounds a Daily Quest is the calendar, not the stage. Hunting
        repeats without limit, so the anti-farm rule it was written for stands.
        """
        self.assertEqual(frozenset({"story", "event"}), ENERGY_BEARING_KINDS)
        for kind in ("hunting", "metal", "special"):
            with self.subTest(kind=kind):
                account = self.account()
                self.assertEqual(0, award_stage_energy(account, kind, 1001, 1))
                self.assertEqual(0, account["userdata"]["freeEnergy"])


class DailyQuestRotationTest(unittest.TestCase):
    """Which two quests a day offers is the server's answer to give."""

    def test_the_rotation_is_the_recovered_asset(self) -> None:
        """41 entries over exactly the fourteen stages, as questOrder has it.

        `liminal_gate.daily_quest_importer` run against a matching APK must
        reproduce this tuple; that is what makes the bundled copy checkable.
        """
        self.assertEqual(41, len(DAILY_QUEST_ROTATION))
        named = {tuple(int(part) for part in entry.split("-")) for entry in DAILY_QUEST_ROTATION}
        self.assertEqual(set(ROTATION_STAGES), named)

    def test_the_epoch_day_anchors_the_published_schedule(self) -> None:
        """2018-10-10 UTC is index nine, the record's first published day."""
        self.assertEqual((DAILY_QUEST_ROTATION[9], DAILY_QUEST_ROTATION[10]),
                         daily_quest_rotation(DAILY_QUEST_EPOCH_DAY))

    def test_the_ring_advances_by_two_a_day_and_wraps(self) -> None:
        """Two quests a day means the 41-entry ring realigns every 41 days."""
        for offset in range(0, 41):
            day = DAILY_QUEST_EPOCH_DAY + offset
            first, second = daily_quest_rotation(day)
            self.assertEqual(DAILY_QUEST_ROTATION[(9 + 2 * offset) % 41], first)
            self.assertEqual(DAILY_QUEST_ROTATION[(10 + 2 * offset) % 41], second)
        # 41 is odd, so two-a-day only returns to the same pair after 41 days.
        self.assertEqual(daily_quest_rotation(DAILY_QUEST_EPOCH_DAY),
                         daily_quest_rotation(DAILY_QUEST_EPOCH_DAY + 41))

    def test_a_day_before_the_epoch_still_resolves(self) -> None:
        """An operator's clock set behind the anchor must not crash the login."""
        first, second = daily_quest_rotation(DAILY_QUEST_EPOCH_DAY - 1)
        self.assertIn(first, DAILY_QUEST_ROTATION)
        self.assertIn(second, DAILY_QUEST_ROTATION)


class DailyQuestPlayTimeTest(unittest.TestCase):
    """The client greys an entry out from the play times login carries."""

    def test_an_unplayed_day_offers_both_quests_at_zero(self) -> None:
        now = 1_754_000_000.0
        fields = daily_quest_login_fields({}, now)
        self.assertEqual("", fields["dailyQuest"])
        self.assertEqual(daily_quest_rotation(int(now // 86_400)),
                         (fields["dailyQuest1"], fields["dailyQuest2"]))
        self.assertEqual(0.0, fields["lastDailyQuestPlayTime1"])
        self.assertEqual(0.0, fields["lastDailyQuestPlayTime2"])

    def test_playing_one_slot_greys_only_that_slot(self) -> None:
        now = 1_754_000_000.0
        account: dict = {}
        played = daily_quest_rotation(int(now // 86_400))[0]
        stage = next(s for s in build_bundled_daily_quest_stages() if s.identity_label() == played)
        _stamp_daily_quest_clear(account, stage, now)
        fields = daily_quest_login_fields(account, now)
        self.assertEqual(now, fields["lastDailyQuestPlayTime1"])
        self.assertEqual(0.0, fields["lastDailyQuestPlayTime2"])

    def test_yesterdays_stamp_does_not_grey_todays_quest(self) -> None:
        """A stale timestamp left in place is how a quest never resets."""
        yesterday = 1_754_000_000.0
        account: dict = {}
        for stage in build_bundled_daily_quest_stages():
            _stamp_daily_quest_clear(account, stage, yesterday)
        fields = daily_quest_login_fields(account, yesterday + 86_400)
        self.assertEqual(0.0, fields["lastDailyQuestPlayTime1"])
        self.assertEqual(0.0, fields["lastDailyQuestPlayTime2"])

    def test_a_save_without_play_times_still_greys_out(self) -> None:
        """Saves written before play times were recorded know only the day."""
        now = 1_754_000_000.0
        played = daily_quest_rotation(int(now // 86_400))[0]
        account = {"daily_quest_clears": {played: int(now // 86_400)}}
        self.assertGreater(daily_quest_login_fields(account, now)["lastDailyQuestPlayTime1"], 0.0)


class DailyQuestLoginTest(unittest.TestCase):
    """The category is useless unless the client is told it is on."""

    def test_login_advertises_the_category_and_every_stage(self) -> None:
        catalog = HuntingCatalog(build_bundled_daily_quest_stages(), BUNDLED_ITEM_SLOTS, BUNDLED_MAX_STACK)
        with tempfile.TemporaryDirectory() as directory:
            server, thread = start_server(
                ("127.0.0.1", 0), bootstrap_profile(), BootstrapState(Path(directory) / "state.json"),
                hunting_catalog=catalog, daily_quests=True,
            )
            try:
                self.assertEqual(200, get(server, "/gd/signup?uuid=acct&otk=sig&requestID=s1")[0])
                status, payload = get(server, "/gd/login?uuid=acct&otk=tok&requestID=l1")
                self.assertEqual(200, status)
                flags = payload["eventFlags"]
                self.assertTrue(flags[DAILY_QUEST_EVENT_FLAG]["value"])
                for chapter, section in ROTATION_STAGES:
                    self.assertIn(f"sp_ch_{chapter}-{section}", flags)
                # The flags alone drew the menu and greyed every entry out.
                # DailyQuestManager fills todaysQuest1/2 from these, and
                # IsDailyQuestPlayable1/2 refuse an empty string, so omitting
                # them makes the whole category unreachable.
                self.assertIn(payload["dailyQuest1"], DAILY_QUEST_ROTATION)
                self.assertIn(payload["dailyQuest2"], DAILY_QUEST_ROTATION)
                self.assertEqual("", payload["dailyQuest"])
                self.assertEqual(0.0, payload["lastDailyQuestPlayTime"])
                self.assertEqual(0.0, payload["lastDailyQuestPlayTime1"])
                self.assertEqual(0.0, payload["lastDailyQuestPlayTime2"])
                # UserData.lastLoginTime gates a slot opening at all, so a zero
                # here disables the Huntland button whatever else is sent.
                self.assertGreater(payload["lastLogin"], 0.0)
            finally:
                stop_server(server, thread)

    def test_the_category_stays_off_unless_asked_for(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            server, thread = start_server(("127.0.0.1", 0), bootstrap_profile(), BootstrapState(Path(directory) / "state.json"))
            try:
                get(server, "/gd/signup?uuid=acct&otk=sig&requestID=s1")
                _, payload = get(server, "/gd/login?uuid=acct&otk=tok&requestID=l1")
                self.assertNotIn(DAILY_QUEST_EVENT_FLAG, payload.get("eventFlags", {}))
                # Naming today's quests to a client whose category is off would
                # advertise a menu it must not open.
                self.assertNotIn("dailyQuest1", payload)
                self.assertNotIn("lastDailyQuestPlayTime1", payload)
            finally:
                stop_server(server, thread)


class PuzzleQuestCompanionRuntimeTest(unittest.TestCase):
    """The refusal issue 29 reported, over real HTTP, start to finish.

    A tester cleared Yamamoto's Puzzle Quest, the client reported the Companion
    its own `dropBuddies` manifest allows, and the settlement refused it with
    `409 invalid_local_hunting_result`. The clear never released the account, so
    the battle stayed active across a force-close and every later stage start
    was refused too -- which is why the report reads as a corrupted install
    rather than as one lost reward.

    The clock is pinned to a UTC day whose rotation offers 6011-1, so the test
    does not depend on the day it runs.
    """

    #: UTC day 17817, whose two quests are 6010-1 and 6011-1.
    NOW = 17817 * 86400.0
    GLASSY_MINION = 267

    def setUp(self) -> None:
        patcher = mock.patch("liminal_gate.bootstrap_server.time.time", return_value=self.NOW)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.state_path = Path(self.temporary_directory.name) / "state.json"
        self.token, self.account_id = "daily-token", "daily-account"
        self.character = {
            "id": 9001, "buddy": 0, "date": 0.0, "jobSlots": [0, 0, 0],
            "jobLevels": [1, 0, 0], "jobID": 0, "flags": 0, "skillBoost": 0,
        }
        profile = bootstrap_profile()
        catalog = HuntingCatalog(build_bundled_daily_quest_stages(), BUNDLED_ITEM_SLOTS, BUNDLED_MAX_STACK)
        self.server, self.thread = start_server(
            ("127.0.0.1", 0), profile, BootstrapState(self.state_path),
            hunting_catalog=catalog, daily_quests=True,
        )
        self.addCleanup(self.stop_server)
        self.server.state.create_account(self.token, self.account_id, {
            "coins": 100, "energy": 40, "freeEnergy": 2, "worldMapNo": 0,
            "progressCode": (1 << 24) | (3 << 6) | 1, "chrdata": [self.character],
            "itemList": [0] * BUNDLED_ITEM_SLOTS, "summonList": [0, 0],
        })
        with self.server.state.lock:
            account = self.server.state.accounts[self.account_id]
            account["tutorial_phase"] = "free_roam"
            account["initial_userdata_served"] = True
            self.server.state._persist_locked()

    def stop_server(self) -> None:
        stop_server(self.server, self.thread)

    def post(self, route: str, request_id: str, fields: list) -> tuple:
        return post(
            self.server, route, request_id, urlencode(fields), token=self.token,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    def account(self) -> dict:
        return json.loads(self.state_path.read_text(encoding="utf-8"))["accounts"][self.account_id]

    def userdata(self) -> dict:
        return self.account()["userdata"]

    def start(self, request_id: str) -> tuple:
        return self.post("/gd/start_quest", request_id, [
            ("stamina", "0"), ("coins", "0"), ("chapter", "6011"),
            ("section", "1"), ("lastUpdate", "1"),
        ])

    def clear(self, request_id: str, *, buddies=(), items=None, item_list=None) -> tuple:
        userdata = self.userdata()
        return self.post("/gd/clear_quest", request_id, [
            ("progressCode", str(userdata["progressCode"])), ("worldMapNo", "0"),
            ("valuables", json.dumps({
                "energyAppStore": 0, "energy": userdata["energy"], "energyAndApp": 0,
                "freeEnergy": userdata["freeEnergy"], "energyGooglePlay": 0,
                "coins": userdata["coins"],
            })),
            ("chrdata", json.dumps([self.character])),
            ("itemList", json.dumps(userdata["itemList"] if item_list is None else item_list)),
            ("summonList", json.dumps(userdata["summonList"])),
            ("battle_result", json.dumps({
                "chapter": 6011, "section": 1, "coins": 0, "exp": 0,
                "items": items or {}, "buddies": list(buddies), "monsters": [], "summons": [],
                "luckynum": 0, "unableluckdrop": False, "boostup": [0, 0, 0, 0, 0, 0],
            })),
            ("itmp0", "0"), ("itmp1", "0"), ("lastUpdate", "1"),
        ])

    def test_the_reported_companion_settles_and_releases_the_account(self) -> None:
        status, started = self.start("dq-start")
        self.assertEqual((200, True), (status, started["success"]))
        self.assertEqual("hunting_active", self.account()["tutorial_phase"])

        status, cleared = self.clear("dq-clear", buddies=[self.GLASSY_MINION])
        self.assertEqual(200, status, cleared)
        granted = self.userdata()["buddyInfo"]["list"]
        self.assertEqual([self.GLASSY_MINION], [row["bid"] for row in granted])
        self.assertEqual([1], [row["lv"] for row in granted])
        self.assertEqual(granted, cleared["buddyInfo"]["list"])
        # The whole severity of the report was here: a refused clear left this
        # `hunting_active`, and every unrelated stage start then failed too.
        self.assertEqual("free_roam", self.account()["tutorial_phase"])
        self.assertIsNone(self.account()["active_hunt"])

    def test_the_puzzle_reward_tiers_settle_alongside_the_companion(self) -> None:
        """Weapons, Tears and Particles in one clear, with the drop."""
        self.assertEqual(200, self.start("tiers-start")[0])
        projected = [0] * BUNDLED_ITEM_SLOTS
        for item_id, count in ((9, 3), (18, 2), (22, 1)):
            projected[item_id - 1] = count
        status, cleared = self.clear(
            "tiers-clear", buddies=[self.GLASSY_MINION],
            items={"9": 3, "18": 2, "22": 1}, item_list=projected,
        )
        self.assertEqual(200, status, cleared)
        self.assertEqual(projected, self.userdata()["itemList"])
        self.assertEqual("free_roam", self.account()["tutorial_phase"])

    def test_the_reported_incidental_item_settles_and_releases_the_account(self) -> None:
        """PR 28's device clear included an item outside this quest's chest.

        The normal preservation policy trusts that client-reported battle
        outcome. Inventory reconciliation still requires the submitted slot
        delta to say exactly the same thing as ``battle_result.items``.
        """
        self.assertEqual(200, self.start("incidental-start")[0])
        projected = [0] * BUNDLED_ITEM_SLOTS
        projected[0] = 1  # Item 1 is outside Yamamoto 6011-1's themed chest.

        status, cleared = self.clear(
            "incidental-clear", items={"1": 1}, item_list=projected,
        )

        self.assertEqual(200, status, cleared)
        self.assertEqual(projected, self.userdata()["itemList"])
        self.assertEqual("free_roam", self.account()["tutorial_phase"])

    def test_an_unreported_incidental_slot_change_is_refused_without_mutation(self) -> None:
        """Trust covers the requested reward, not unrelated inventory writes."""
        self.assertEqual(200, self.start("unreported-start")[0])
        before = self.userdata()
        submitted = list(before["itemList"])
        submitted[0] = 1
        submitted[49] = 999

        status, refused = self.clear(
            "unreported-clear", items={"1": 1}, item_list=submitted,
        )

        self.assertEqual((409, "invalid_local_hunting_items"), (status, refused["error"]))
        self.assertEqual(before, self.userdata())
        self.assertEqual("hunting_active", self.account()["tutorial_phase"])

    def test_a_clear_pays_the_energy_the_result_screen_promises(self) -> None:
        """The reported bug, over real HTTP: the reward line had nothing behind it.

        The balance has to arrive in three places at once, because the client
        reads two of them and the durable save is the third. The nested
        `valuables` copy is the one that was easy to miss: it is built before
        the grant, and left stale it shows the player the balance they had
        before the reward they just watched drop.
        """
        before = self.userdata()["freeEnergy"]
        self.assertEqual(200, self.start("energy-start")[0])
        status, cleared = self.clear("energy-clear")
        self.assertEqual(200, status, cleared)

        expected = before + DAILY_QUEST_FREE_ENERGY
        self.assertEqual(expected, self.userdata()["freeEnergy"])
        self.assertEqual(expected, cleared["freeEnergy"])
        self.assertEqual(expected, self.userdata()["valuables"]["freeEnergy"])
        # Paid Energy is never written by this server, so a local grant can
        # never be mistaken for a purchase the account did not make.
        self.assertEqual(
            self.userdata()["energy"], self.userdata()["valuables"]["energy"],
        )

    def test_the_day_gate_is_what_stops_a_second_payment(self) -> None:
        """There is no second clear to farm: the day is spent at start.

        The account is released to `free_roam` by the first clear, so a repeat
        clear has no active battle to settle, and a repeat *start* is refused by
        the once-per-UTC-day gate with the client's own soft refusal rather than
        an error. The day key inside the grant is a second lock on the same
        door; `DailyQuestEnergyTest` exercises it directly.
        """
        self.assertEqual(200, self.start("gate-start")[0])
        self.assertEqual(200, self.clear("gate-clear")[0])
        paid_once = self.userdata()["freeEnergy"]

        # The refusal reaches the client on `cmdError`, so it draws its own
        # "already played today" rather than a Network Error.
        status, refused = self.start("gate-start-again")
        self.assertEqual(200, status)
        self.assertEqual(1, refused["cmdError"])
        self.assertEqual(paid_once, self.userdata()["freeEnergy"])

    def test_a_companion_the_manifest_does_not_name_is_still_refused(self) -> None:
        """Unknown Companion ids still cannot be authored without level data."""
        self.assertEqual(200, self.start("undeclared-start")[0])
        before = self.userdata()
        status, refused = self.clear("undeclared-clear", buddies=[140])
        self.assertEqual((409, "invalid_local_hunting_companions"), (status, refused["error"]))
        self.assertEqual(before, self.userdata(), "a refused clear must not mutate the save")
        # And the honest clear still settles afterwards, which is the recovery
        # path a wedged account takes: replay the same stage and finish it.
        self.assertEqual(200, self.clear("recover", buddies=[self.GLASSY_MINION])[0])
        self.assertEqual("free_roam", self.account()["tutorial_phase"])


class JokerDuplicateRuntimeTest(unittest.TestCase):
    """The +20% Skill Boost a tester read where the client announced +10%.

    The client raises a duplicate's Skill Boost itself and reports the raised
    figure -- `Character.ToHashTable` (ARM64 `0xD0A318`) serializes
    `skillBoost` -- so granting the stage's increment *after* the clear merged
    that row paid it twice. Luck cannot double the same way, because the same
    serializer omits `luck`; it is checked here so the two halves of one
    duplicate stay described by one test.

    The clock is pinned to UTC day 17819, whose rotation offers 6012-1.
    """

    NOW = 17819 * 86400.0
    JOKER = 1018

    def setUp(self) -> None:
        patcher = mock.patch("liminal_gate.bootstrap_server.time.time", return_value=self.NOW)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.state_path = Path(self.temporary_directory.name) / "state.json"
        self.token, self.account_id = "joker-token", "joker-account"
        self.character = {
            "id": self.JOKER, "buddy": 0, "date": 0.0, "jobSlots": [0, 0, 0],
            "jobLevels": [1, 0, 0], "jobID": 0, "flags": 0, "skillBoost": 0,
            "luck": 0,
        }
        catalog = HuntingCatalog(build_bundled_daily_quest_stages(), BUNDLED_ITEM_SLOTS, BUNDLED_MAX_STACK)
        self.server, self.thread = start_server(
            ("127.0.0.1", 0), bootstrap_profile(), BootstrapState(self.state_path),
            hunting_catalog=catalog, daily_quests=True,
        )
        self.addCleanup(lambda: stop_server(self.server, self.thread))
        self.server.state.create_account(self.token, self.account_id, {
            "coins": 100, "energy": 40, "freeEnergy": 2, "worldMapNo": 0,
            "progressCode": (1 << 24) | (3 << 6) | 1,
            "chrdata": [dict(self.character)], "teamMembers": [self.JOKER, 0, 0, 0, 0, 0],
            "itemList": [0] * BUNDLED_ITEM_SLOTS, "summonList": [0, 0],
        })
        with self.server.state.lock:
            account = self.server.state.accounts[self.account_id]
            account["tutorial_phase"] = "free_roam"
            account["initial_userdata_served"] = True
            self.server.state._persist_locked()

    def userdata(self) -> dict:
        return json.loads(self.state_path.read_text(encoding="utf-8"))["accounts"][self.account_id]["userdata"]

    def send(self, route: str, request_id: str, fields: list) -> tuple:
        return post(
            self.server, route, request_id, urlencode(fields), token=self.token,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    def clear(self, request_id: str, reported: dict) -> tuple:
        userdata = self.userdata()
        return self.send("/gd/clear_quest", request_id, [
            ("progressCode", str(userdata["progressCode"])), ("worldMapNo", "0"),
            ("valuables", json.dumps({
                "energyAppStore": 0, "energy": userdata["energy"], "energyAndApp": 0,
                "freeEnergy": userdata["freeEnergy"], "energyGooglePlay": 0,
                "coins": userdata["coins"],
            })),
            ("chrdata", json.dumps([reported])),
            ("itemList", json.dumps(userdata["itemList"])),
            ("summonList", json.dumps(userdata["summonList"])),
            ("battle_result", json.dumps({
                "chapter": 6012, "section": 1, "coins": 0, "exp": 0, "items": {},
                "buddies": [], "monsters": [], "summons": [],
                "luckynum": 0, "unableluckdrop": False, "boostup": [0, 0, 0, 0, 0, 0],
            })),
            ("itmp0", "0"), ("itmp1", "0"), ("lastUpdate", "1"),
        ])

    def start(self, request_id: str) -> tuple:
        return self.send("/gd/start_quest", request_id, [
            ("stamina", "0"), ("coins", "0"), ("chapter", "6012"),
            ("section", "1"), ("lastUpdate", "1"),
        ])

    def test_a_duplicate_is_paid_once_when_the_client_reports_it(self) -> None:
        self.assertEqual(200, self.start("joker-start")[0])
        # What the client posts: no `luck` member, and `skillBoost` already
        # carrying the increment it announced on the result screen.
        reported = {key: value for key, value in self.character.items() if key != "luck"}
        status, _ = self.clear("joker-clear", reported | {"skillBoost": 100})
        self.assertEqual(200, status)
        row = self.userdata()["chrdata"][0]
        self.assertEqual((100, 100), (row["skillBoost"], row["luck"]))

    def test_a_duplicate_is_paid_in_full_when_the_client_does_not(self) -> None:
        """The grant is the server's either way; the client only agrees with it."""
        self.assertEqual(200, self.start("silent-start")[0])
        reported = {key: value for key, value in self.character.items() if key != "luck"}
        status, _ = self.clear("silent-clear", reported)
        self.assertEqual(200, status)
        row = self.userdata()["chrdata"][0]
        self.assertEqual((100, 100), (row["skillBoost"], row["luck"]))


class DailyQuestGameOverContinueTest(unittest.TestCase):
    """The Network Error a tester hit retrying Rarity Rumble after a game over.

    The client offers Continue when a Daily Quest ends in a game over, and posts
    `/gd/continue` for it. The server accepted Continue only in the generic-story
    phase, so a Hunting battle -- which every Daily Quest is -- answered
    `continue_unavailable` at 409, and the client showed a transport failure
    with no way past it. Four identical 409s sit in the server's own event log.

    The account was left worse than the one error: the day is spent at accepted
    start, so the client greys out the one stage whose re-entry would have
    released the battle, and until a start for a different stage counted as
    abandonment every other quest answered 409 too.

    The clock is pinned to UTC day 17819, whose rotation offers 6005-1.
    """

    #: UTC day 17819, whose two quests are 6005-1 and 6012-1.
    NOW = 17819 * 86400.0
    CONTINUE_COINS = 100

    def setUp(self) -> None:
        patcher = mock.patch("liminal_gate.bootstrap_server.time.time", return_value=self.NOW)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.state_path = Path(self.temporary_directory.name) / "state.json"
        self.token, self.account_id = "rumble-token", "rumble-account"
        self.character = {
            "id": 9001, "buddy": 0, "date": 0.0, "jobSlots": [0, 0, 0],
            "jobLevels": [1, 0, 0], "jobID": 0, "flags": 0, "skillBoost": 0,
        }
        profile = bootstrap_profile()
        catalog = HuntingCatalog(build_bundled_daily_quest_stages(), BUNDLED_ITEM_SLOTS, BUNDLED_MAX_STACK)
        self.server, self.thread = start_server(
            ("127.0.0.1", 0), profile, BootstrapState(self.state_path),
            hunting_catalog=catalog, daily_quests=True,
        )
        self.addCleanup(self.stop_server)
        self.server.state.create_account(self.token, self.account_id, {
            "coins": 14_722, "energy": 0, "freeEnergy": 19, "worldMapNo": 0,
            "progressCode": (1 << 24) | (3 << 6) | 1, "chrdata": [self.character],
            "itemList": [0] * BUNDLED_ITEM_SLOTS, "summonList": [0, 0],
        })
        with self.server.state.lock:
            account = self.server.state.accounts[self.account_id]
            account["tutorial_phase"] = "free_roam"
            account["initial_userdata_served"] = True
            self.server.state._persist_locked()

    def stop_server(self) -> None:
        stop_server(self.server, self.thread)

    def post(self, route: str, request_id: str, fields: list) -> tuple:
        return post(
            self.server, route, request_id, urlencode(fields), token=self.token,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    def account(self) -> dict:
        return json.loads(self.state_path.read_text(encoding="utf-8"))["accounts"][self.account_id]

    def userdata(self) -> dict:
        return self.account()["userdata"]

    def start(self, request_id: str, chapter: int = 6005, section: int = 1) -> tuple:
        return self.post("/gd/start_quest", request_id, [
            ("stamina", "0"), ("coins", "0"), ("chapter", str(chapter)),
            ("section", str(section)), ("lastUpdate", "1"),
        ])

    def resume(self, request_id: str) -> tuple:
        return self.post("/gd/continue", request_id, [("cost", "1")])

    def test_a_game_over_in_a_daily_quest_can_be_continued(self) -> None:
        self.assertEqual(200, self.start("rumble-start")[0])
        coins = self.userdata()["coins"]

        status, continued = self.resume("rumble-continue")

        self.assertEqual(200, status, continued)
        self.assertTrue(continued["success"])
        self.assertEqual(coins - self.CONTINUE_COINS, self.userdata()["coins"])
        # The battle is still the one being played, so the clear that follows
        # settles it the way an uninterrupted run would.
        self.assertEqual("hunting_active", self.account()["tutorial_phase"])
        self.assertEqual({"chapter": 6005, "section": 1}, self.account()["active_hunt"])

    def test_the_clients_four_retries_charge_for_one_continue(self) -> None:
        """What the tester's client actually sent, once the answer is not 409."""
        self.assertEqual(200, self.start("rumble-start")[0])
        coins = self.userdata()["coins"]
        for attempt in range(4):
            status, continued = self.resume("rumble-continue")
            self.assertEqual((200, True), (status, continued["success"]), attempt)
        self.assertEqual(coins - self.CONTINUE_COINS, self.userdata()["coins"])

    def test_a_continue_with_no_battle_open_refuses_softly_rather_than_erroring(self) -> None:
        """A refusal the client can show beats a transport error it cannot.

        The refusal rides `cmdError` on an accepted success, which is the field
        the endpoint's own callback reads; `_endpoint_refusal_envelope` puts it
        there. A 409 reached no callback at all -- it showed the transport
        error dialog, which is the Network Error the tester saw.
        """
        status, refused = self.resume("idle-continue")
        self.assertEqual((200, 1), (status, refused["cmdError"]))
        self.assertEqual("free_roam", self.account()["tutorial_phase"])

    def test_a_continue_beyond_the_players_coins_refuses_softly(self) -> None:
        self.assertEqual(200, self.start("broke-start")[0])
        with self.server.state.lock:
            self.server.state.accounts[self.account_id]["userdata"]["coins"] = self.CONTINUE_COINS - 1
            self.server.state._persist_locked()
        status, refused = self.resume("broke-continue")
        self.assertEqual((200, 1), (status, refused["cmdError"]))
        self.assertEqual(self.CONTINUE_COINS - 1, self.userdata()["coins"])

    def test_walking_away_from_the_game_over_does_not_strand_the_account(self) -> None:
        """The other half: a player who declines Continue and plays something else.

        Nothing the client sends on the way out of a lost battle releases the
        stage, and this one cannot be re-entered to release it -- the day was
        spent at accepted start. Starting the day's other quest is the proof
        the player left.
        """
        self.assertEqual(200, self.start("rumble-start")[0])
        self.assertEqual("hunting_active", self.account()["tutorial_phase"])

        status, other = self.start("other-start", chapter=6012, section=1)

        self.assertEqual(200, status, other)
        self.assertEqual({"chapter": 6012, "section": 1}, self.account()["active_hunt"])

    def test_the_spent_day_still_stands_after_the_battle_is_released(self) -> None:
        """Releasing an abandoned battle must not hand back the attempt.

        The day is consumed at accepted start, which is recovered behaviour;
        the abandonment policy is local and has no business overturning it.
        """
        self.assertEqual(200, self.start("rumble-start")[0])
        self.assertEqual(200, self.start("other-start", chapter=6012, section=1)[0])
        self.assertEqual(17819, self.account()["daily_quest_clears"]["6005-1"])
        status, again = self.start("rumble-again")
        self.assertEqual((200, 1), (status, again["cmdError"]))

    def clear(
        self, request_id: str, *, coins: int | None = None, items: dict | None = None,
        chapter: int = 6005, section: int = 1,
    ) -> tuple:
        """Settle the quest, reporting the wallet the way the client does.

        `coins` is what the client believes it holds. Left unset it is the
        server's own total, which is what an uninterrupted run reports.
        """
        userdata = self.userdata()
        item_list = list(userdata["itemList"])
        for item_id, count in (items or {}).items():
            item_list[int(item_id) - 1] += count
        return self.post("/gd/clear_quest", request_id, [
            ("progressCode", str(userdata["progressCode"])), ("worldMapNo", "0"),
            ("valuables", json.dumps({
                "energyAppStore": 0, "energy": userdata["energy"], "energyAndApp": 0,
                "freeEnergy": userdata["freeEnergy"], "energyGooglePlay": 0,
                "coins": userdata["coins"] if coins is None else coins,
            })),
            ("chrdata", json.dumps([self.character])),
            ("itemList", json.dumps(item_list)),
            ("summonList", json.dumps(userdata["summonList"])),
            ("battle_result", json.dumps({
                "chapter": chapter, "section": section, "coins": 0, "exp": 0,
                "items": items or {}, "buddies": [], "monsters": [], "summons": [],
                "luckynum": 0, "unableluckdrop": False, "boostup": [0, 0, 0, 0, 0, 0],
            })),
            ("itmp0", "0"), ("itmp1", "0"), ("lastUpdate", "1"),
        ])

    def test_a_continued_quest_still_settles_on_the_result_screen(self) -> None:
        """The second Network Error the same tester hit, one screen later.

        Continue debits coins the client never takes off its own wallet -- it
        cannot, because the coin cost is local policy and what the client thinks
        it spent is the `client_cost` unit the answer reports back as Energy.
        The clear therefore reported the pre-Continue total, the settlement
        compared it against the server's, and refused with
        `tutorial_state_conflict` on the result screen, with the run already
        played and the Ore already rolled.
        """
        self.assertEqual(200, self.start("rumble-start")[0])
        before = self.userdata()["coins"]
        self.assertEqual(200, self.resume("rumble-continue")[0])

        # One Ore, which is Rarity Rumble's guaranteed drop, and the wallet the
        # client actually reported in the tester's own log: the pre-Continue one.
        status, cleared = self.clear("rumble-clear", coins=before, items={"26": 1})

        self.assertEqual(200, status, cleared)
        # The Continue is still paid for: the settlement commits the server's
        # total, and the answer carries it back so the client resynchronizes.
        self.assertEqual(before - self.CONTINUE_COINS, self.userdata()["coins"])
        self.assertEqual(before - self.CONTINUE_COINS, cleared["coins"])
        self.assertEqual(1, self.userdata()["itemList"][25])
        self.assertEqual("free_roam", self.account()["tutorial_phase"])

    def test_an_uncontinued_quest_still_has_to_report_the_real_wallet(self) -> None:
        """The widening is this battle's Continues and nothing else."""
        self.assertEqual(200, self.start("plain-start")[0])
        before = self.userdata()["coins"]
        status, refused = self.clear("plain-clear", coins=before + self.CONTINUE_COINS)
        self.assertEqual((409, "hunting_clear_wallet_conflict"), (status, refused["error"]))

    def test_a_continue_outlives_the_battle_it_was_spent_in(self) -> None:
        """Issue 64: leaving a continued battle must not forget what it charged.

        The client cannot deduct a Continue's coin cost, so the wallet it
        reports stays that much above the server's until a settlement hands it
        an authoritative one. Starting something else reconciles nothing --
        the Coins are still gone here and still present there -- so zeroing the
        record made the *next* clear refuse by exactly the orphaned amount, on
        every retry, until a relaunch resynchronised the wallet. A tester's
        event log caught it as three Continues at 100 Coins each: one spent in
        a Metal Zone run that was abandoned for another, and two in the run
        that followed, whose clear reported a wallet 100 above the widest total
        the server would accept.
        """
        self.assertEqual(200, self.start("first-start")[0])
        before = self.userdata()["coins"]
        self.assertEqual(200, self.resume("first-continue")[0])
        self.assertEqual(200, self.start("second-start", chapter=6012, section=1)[0])
        # The debt outlives the battle it was spent in.
        self.assertEqual(self.CONTINUE_COINS, self.account()["active_battle_continue_coins"])

        # The client reports the wallet it actually holds: the pre-Continue one.
        status, cleared = self.clear("second-clear", chapter=6012, coins=before)

        self.assertEqual(200, status, cleared)
        # The Continue is still paid for, and the answer carries the total back
        # so the client resynchronizes.
        self.assertEqual(before - self.CONTINUE_COINS, self.userdata()["coins"])
        self.assertEqual(before - self.CONTINUE_COINS, cleared["coins"])
        # Settled, so nothing is owed into the quest after this one.
        self.assertEqual(0, self.account()["active_battle_continue_coins"])
