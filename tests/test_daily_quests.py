from __future__ import annotations

import unittest

from liminal_gate.daily_quest_data import (
    DAILY_QUEST_EVENT_FLAG,
    build_bundled_daily_quest_stages,
    daily_quest_event_flags,
)
from liminal_gate.bootstrap_server import (
    _apply_hunting_character_grants,
    _daily_quest_played_today,
    _stamp_daily_quest_clear,
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

    def test_no_daily_quest_settles_experience(self) -> None:
        for stage in build_bundled_daily_quest_stages():
            with self.subTest(stage=stage.identity_label()):
                self.assertFalse(hunting_settlement_within_bounds(stage, result(exp=1)))


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
        self.assertEqual((150, 120), (userdata["chrdata"][0]["skillBoost"], userdata["chrdata"][0]["luck"]))

    def test_duplicate_gains_stop_at_the_clients_ceiling(self) -> None:
        userdata = {"chrdata": [{"id": 1018, "skillBoost": 960, "luck": 990}]}
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
            finally:
                server.shutdown(); thread.join(); server.server_close()
