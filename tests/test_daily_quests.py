from __future__ import annotations

from http.client import HTTPConnection
import json
from pathlib import Path
import tempfile
import threading
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
    BootstrapServer,
    BootstrapState,
    _apply_hunting_character_grants,
    _daily_quest_played_today,
    _stamp_daily_quest_clear,
    daily_quest_login_fields,
    load_profile,
)
from liminal_gate.hunting_catalog import HuntingCatalog, BUNDLED_ITEM_SLOTS, BUNDLED_MAX_STACK, hunting_settlement_within_bounds


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
        # 10% Skill Boost and 1 Luck, both in the client's tenths.
        self.assertEqual((100, 10), (stage.duplicate_grant_skill_boost, stage.duplicate_grant_luck))
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
        _apply_hunting_character_grants(userdata, self.stage())
        self.assertEqual(1, len(userdata["chrdata"]))
        row = userdata["chrdata"][0]
        self.assertEqual((1018, True, 0), (row["id"], row["isNew"], row["skillBoost"]))

    def test_a_duplicate_raises_skill_boost_and_luck_instead(self) -> None:
        userdata = {"chrdata": [{"id": 1018, "skillBoost": 50, "luck": 20}]}
        _apply_hunting_character_grants(userdata, self.stage())
        self.assertEqual(1, len(userdata["chrdata"]), "a duplicate must not add a second row")
        self.assertEqual((150, 30), (userdata["chrdata"][0]["skillBoost"], userdata["chrdata"][0]["luck"]))

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
        import json
        import tempfile
        import threading
        from http.client import HTTPConnection
        from pathlib import Path

        from liminal_gate.bootstrap_server import BootstrapServer, BootstrapState, load_profile

        catalog = HuntingCatalog(build_bundled_daily_quest_stages(), BUNDLED_ITEM_SLOTS, BUNDLED_MAX_STACK)
        with tempfile.TemporaryDirectory() as directory:
            profile = load_profile(Path(__file__).resolve().parents[1] / "profiles" / "legacy-client-bootstrap.json")
            server = BootstrapServer(
                ("127.0.0.1", 0), profile, BootstrapState(Path(directory) / "state.json"),
                hunting_catalog=catalog, daily_quests=True,
            )
            thread = threading.Thread(target=server.serve_forever); thread.start()

            def get(path: str) -> tuple[int, dict]:
                connection = HTTPConnection(*server.server_address)
                connection.request("GET", path)
                response = connection.getresponse()
                payload = json.loads(response.read()); connection.close()
                return response.status, payload

            try:
                self.assertEqual(200, get("/gd/signup?uuid=acct&otk=sig&requestID=s1")[0])
                status, payload = get("/gd/login?uuid=acct&otk=tok&requestID=l1")
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
                server.shutdown(); thread.join(); server.server_close()

    def test_the_category_stays_off_unless_asked_for(self) -> None:
        import json
        import tempfile
        import threading
        from http.client import HTTPConnection
        from pathlib import Path

        from liminal_gate.bootstrap_server import BootstrapServer, BootstrapState, load_profile

        with tempfile.TemporaryDirectory() as directory:
            profile = load_profile(Path(__file__).resolve().parents[1] / "profiles" / "legacy-client-bootstrap.json")
            server = BootstrapServer(("127.0.0.1", 0), profile, BootstrapState(Path(directory) / "state.json"))
            thread = threading.Thread(target=server.serve_forever); thread.start()

            def get(path: str) -> tuple[int, dict]:
                connection = HTTPConnection(*server.server_address)
                connection.request("GET", path)
                response = connection.getresponse()
                payload = json.loads(response.read()); connection.close()
                return response.status, payload

            try:
                get("/gd/signup?uuid=acct&otk=sig&requestID=s1")
                _, payload = get("/gd/login?uuid=acct&otk=tok&requestID=l1")
                self.assertNotIn(DAILY_QUEST_EVENT_FLAG, payload.get("eventFlags", {}))
                # Naming today's quests to a client whose category is off would
                # advertise a menu it must not open.
                self.assertNotIn("dailyQuest1", payload)
                self.assertNotIn("lastDailyQuestPlayTime1", payload)
            finally:
                server.shutdown(); thread.join(); server.server_close()


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
        profile = load_profile(Path(__file__).resolve().parents[1] / "profiles" / "legacy-client-bootstrap.json")
        catalog = HuntingCatalog(build_bundled_daily_quest_stages(), BUNDLED_ITEM_SLOTS, BUNDLED_MAX_STACK)
        self.server = BootstrapServer(
            ("127.0.0.1", 0), profile, BootstrapState(self.state_path),
            hunting_catalog=catalog, daily_quests=True,
        )
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
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
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()

    def post(self, route: str, request_id: str, fields: list) -> tuple:
        connection = HTTPConnection(*self.server.server_address)
        connection.request(
            "POST", f"{route}?otk={self.token}&requestID={request_id}",
            body=urlencode(fields), headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response = connection.getresponse()
        payload = json.loads(response.read())
        connection.close()
        return response.status, payload

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

    def test_a_companion_the_manifest_does_not_name_is_still_refused(self) -> None:
        """The bound moved to what the client's own data allows, not away."""
        self.assertEqual(200, self.start("undeclared-start")[0])
        before = self.userdata()
        status, refused = self.clear("undeclared-clear", buddies=[140])
        self.assertEqual((409, "invalid_local_hunting_result"), (status, refused["error"]))
        self.assertEqual(before, self.userdata(), "a refused clear must not mutate the save")
        # And the honest clear still settles afterwards, which is the recovery
        # path a wedged account takes: replay the same stage and finish it.
        self.assertEqual(200, self.clear("recover", buddies=[self.GLASSY_MINION])[0])
        self.assertEqual("free_roam", self.account()["tutorial_phase"])
