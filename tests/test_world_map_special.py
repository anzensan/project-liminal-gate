"""The Chapter-1100 World Map Special routes.

Two permanent map points the client draws itself after normal Chapter 34.  The
server's jobs are to charge the 25-stamina entry, keep the route's own
frontier, refuse to move core story progress, and settle at most one reported
Companion per clear from the stage's own `dropBuddies` manifest -- the bounded
acceptance the community record supports.
"""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import time
import unittest
from urllib.parse import urlencode

from liminal_gate.bootstrap_server import BootstrapState
from liminal_gate.world_map_special import (
    UNLOCK_AFTER_CHAPTER,
    WORLD_MAP_SPECIAL_CHAPTER,
    WORLD_MAP_SPECIAL_STAMINA,
    build_bundled_world_map_special_policy,
)
from tests.support import bootstrap_profile, post, start_server, stop_server


def progress_code(chapter: int, section: int = 1) -> int:
    return 0x01000000 | (chapter << 6) | section


# Chapter 35 Section 1 is the earliest progress the native map gate admits.
UNLOCKED = progress_code(UNLOCK_AFTER_CHAPTER + 1)
LOCKED = progress_code(UNLOCK_AFTER_CHAPTER)
# The route openers: Shin'en battle 1 is section 4, Mutoh battle 1 is section 9.
SHINEN_FIRST, MUTOH_FIRST = 4, 9


class WorldMapSpecialCatalogTest(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = build_bundled_world_map_special_policy()

    def test_ten_recovered_identities_at_the_recovered_cost(self) -> None:
        identities = sorted(self.catalog.by_identity())
        self.assertEqual([(WORLD_MAP_SPECIAL_CHAPTER, section) for section in range(1, 11)], identities)
        self.assertTrue(all(
            stage.stamina == WORLD_MAP_SPECIAL_STAMINA and stage.coins == 0
            for stage in self.catalog.stages
        ))

    def test_two_routes_of_five_battles_each(self) -> None:
        self.assertEqual(("shinen", "mutoh"), self.catalog.routes())
        for route in self.catalog.routes():
            battles = sorted(stage.battle for stage in self.catalog.stages if stage.route == route)
            self.assertEqual([1, 2, 3, 4, 5], battles)
            self.assertEqual(5, self.catalog.final_battle(route))

    def test_each_routes_opener_is_the_level_80_section(self) -> None:
        # The evidence for reading the title's battle number as play order: in
        # both routes independently, the section titled "battle 1" is the only
        # one of five whose assumed level is 80 rather than 90.
        for route in self.catalog.routes():
            stages = {stage.battle: stage for stage in self.catalog.stages if stage.route == route}
            self.assertEqual(80, stages[1].level)
            self.assertEqual([90, 90, 90, 90], [stages[n].level for n in (2, 3, 4, 5)])

    def test_section_ordinal_is_storage_order_not_play_order(self) -> None:
        by_route = {
            route: [stage.section for stage in self.catalog.stages if stage.route == route]
            for route in self.catalog.routes()
        }
        self.assertEqual([4, 3, 2, 1, 5], by_route["shinen"])
        self.assertEqual([9, 8, 7, 6, 10], by_route["mutoh"])

    def test_companion_candidates_are_retained_exactly(self) -> None:
        by_section = {stage.section: stage.companion_candidates for stage in self.catalog.stages}
        self.assertEqual(((129, 1), (267, 1), (140, 1)), by_section[1])
        self.assertEqual(((137, 1),), by_section[4])
        self.assertEqual((), by_section[5])
        self.assertEqual(((111, 1),), by_section[9])
        self.assertEqual((), by_section[10])

    def test_the_gate_is_the_native_chapter_34_map_gate(self) -> None:
        self.assertFalse(self.catalog.unlocked_at(UNLOCK_AFTER_CHAPTER))
        self.assertTrue(self.catalog.unlocked_at(UNLOCK_AFTER_CHAPTER + 1))


class WorldMapSpecialRuntimeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.state_path = self.root / "state.json"
        self.profile = bootstrap_profile()
        self.token, self.account_id = "wms-token", "wms-account"
        self.character = {
            "id": 9001, "buddy": 0, "date": 0.0, "jobSlots": [0, 0, 0],
            "jobLevels": [1, 0, 0], "jobID": 0, "flags": 0, "skillBoost": 0,
        }
        self.start_server()
        self.create_account(UNLOCKED)

    def tearDown(self) -> None:
        self.stop_server()
        self.temporary_directory.cleanup()

    def create_account(self, progress: int) -> None:
        self.server.state.create_account(self.token, self.account_id, {
            "coins": 100, "energy": 40, "freeEnergy": 2, "worldMapNo": 0,
            "progressCode": progress, "chrdata": [self.character],
            "itemList": [0, 0, 0, 0], "summonList": [0, 0],
            # A meter that filled long ago, so a 25-stamina entry is affordable.
            "refillStartTime": 0.0,
        })
        with self.server.state.lock:
            account = self.server.state.accounts[self.account_id]
            account["tutorial_phase"] = "free_roam"
            account["initial_userdata_served"] = True
            self.server.state._persist_locked()

    def start_server(self) -> None:
        self.server, self.thread = start_server(
            ("127.0.0.1", 0), self.profile, BootstrapState(self.state_path), stamina=True,
        )

    def stop_server(self) -> None:
        stop_server(self.server, self.thread)

    def restart(self) -> None:
        self.stop_server()
        self.start_server()

    def post(self, route: str, request_id: str, fields: list[tuple[str, str]]) -> tuple[int, dict]:
        return post(
            self.server, route, request_id, urlencode(fields), token=self.token,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    def account(self) -> dict:
        return json.loads(self.state_path.read_text(encoding="utf-8"))["accounts"][self.account_id]

    def userdata(self) -> dict:
        return self.account()["userdata"]

    def phase(self) -> str:
        return self.account()["tutorial_phase"]

    def frontier(self) -> dict:
        return self.account().get("world_map_special_progress", {})

    def start(self, request_id: str, section: int, stamina: int = WORLD_MAP_SPECIAL_STAMINA) -> tuple[int, dict]:
        return self.post("/gd/start_quest", request_id, [
            ("stamina", str(stamina)), ("coins", "0"),
            ("chapter", str(WORLD_MAP_SPECIAL_CHAPTER)), ("section", str(section)),
            ("lastUpdate", "1"),
        ])

    def clear(
        self, request_id: str, section: int, *, coins: int = 0, exp: int = 0,
        buddies: list | None = None, progress: int | None = None,
        snapshot: dict | None = None, roster: list | None = None,
    ) -> tuple[int, dict]:
        userdata = self.userdata() if snapshot is None else snapshot
        return self.post("/gd/clear_quest", request_id, [
            ("progressCode", str(userdata["progressCode"] if progress is None else progress)),
            ("worldMapNo", "0"),
            ("valuables", json.dumps({
                "energyAppStore": 0, "energy": userdata["energy"], "energyAndApp": 0,
                "freeEnergy": userdata["freeEnergy"], "energyGooglePlay": 0,
                "coins": userdata["coins"] + coins,
            })),
            ("chrdata", json.dumps([self.character] if roster is None else roster)),
            ("itemList", json.dumps(userdata["itemList"])),
            ("summonList", json.dumps(userdata["summonList"])),
            ("battle_result", json.dumps({
                "chapter": WORLD_MAP_SPECIAL_CHAPTER, "section": section,
                "coins": coins, "exp": exp, "items": {}, "buddies": buddies or [],
                "monsters": [], "summons": [], "luckynum": 0,
                "unableluckdrop": False, "boostup": [0, 0, 0, 0, 0, 0],
            })),
            ("itmp0", "0"), ("itmp1", "0"), ("lastUpdate", "1"),
        ])

    def test_entry_charges_the_meter_and_clear_leaves_core_progress_alone(self) -> None:
        before = self.userdata()["progressCode"]
        status, started = self.start("wms-start", SHINEN_FIRST)
        self.assertEqual((200, True), (status, started["success"]))
        self.assertEqual("world_map_special_active", self.phase())
        # 25 stamina is debited from the meter, never from the Energy wallet.
        self.assertLess(started["refillStartTime"], time.time())
        self.assertEqual((2, 40), (self.userdata()["freeEnergy"], self.userdata()["energy"]))

        status, cleared = self.clear("wms-clear", SHINEN_FIRST)
        self.assertEqual((200, True), (status, cleared["success"]))
        self.assertEqual(before, self.userdata()["progressCode"])
        self.assertEqual("free_roam", self.phase())
        # A repeatable Road pays no preservation Energy; see `archive_economy`.
        self.assertEqual(2, self.userdata()["freeEnergy"])

    def test_a_chapter_1100_battle_grows_luck(self) -> None:
        """25 stamina is well past Mistwalker's eight-stamina gate, and this
        handler rolled no table at all until the Luck family gap was closed.

        Chapter 1100's own `allowLucky` is 0, so the only source here is the
        battle-end gain.
        """
        with self.server.state.lock:
            account = self.server.state.accounts[self.account_id]
            account["userdata"]["teamMembers"] = [9001, 0, 0, 0, 0, 0]
            self.server.state._persist_locked()

        def luck() -> int:
            return next(
                int(row.get("luck", 0)) for row in self.userdata()["chrdata"]
                if row["id"] == 9001
            )

        for attempt in range(24):
            with self.server.state.lock:
                # Refill the meter, so 24 entries at 25 stamina stay affordable.
                self.server.state.accounts[self.account_id]["userdata"]["refillStartTime"] = 0.0
                self.server.state._persist_locked()
            self.assertEqual(200, self.start(f"luck-start-{attempt}", SHINEN_FIRST)[0])
            self.assertEqual(200, self.clear(f"luck-clear-{attempt}", SHINEN_FIRST)[0])
        self.assertGreater(luck(), 0, "24 battles at 25 stamina raised no Luck")
        earned = luck()
        self.restart()
        self.assertEqual(earned, luck())

    def test_a_clear_that_claims_core_progress_is_refused(self) -> None:
        self.assertEqual(200, self.start("wms-start", SHINEN_FIRST)[0])
        status, _ = self.clear("wms-clear", SHINEN_FIRST, progress=progress_code(36))
        self.assertEqual(409, status)
        self.assertEqual(UNLOCKED, self.userdata()["progressCode"])

    def test_a_manifest_companion_is_accepted_and_minted_at_level_one(self) -> None:
        # Section 4's manifest names Companion 137; the community record
        # documents one exclusive Companion roll per clear, so a single
        # reported manifest Companion settles into the box at level 1.
        self.assertEqual(200, self.start("wms-start", SHINEN_FIRST)[0])
        status, cleared = self.clear("wms-clear", SHINEN_FIRST, buddies=[137])
        self.assertEqual((200, True), (status, cleared["success"]))
        self.assertEqual("free_roam", self.phase())
        minted = cleared["buddyInfo"]["list"]
        self.assertEqual([(137, 1)], [(row["bid"], row["lv"]) for row in minted])

    def test_a_companion_outside_the_manifest_is_refused(self) -> None:
        # Companion 128 is a Metal Zone drop, not a Chapter-1100 candidate.
        self.assertEqual(200, self.start("wms-start", SHINEN_FIRST)[0])
        status, _ = self.clear("wms-clear", SHINEN_FIRST, buddies=[128])
        self.assertEqual(409, status)
        self.assertEqual("world_map_special_active", self.phase())

    def test_two_manifest_companions_at_once_are_refused(self) -> None:
        # The record describes a single exclusive roll: two claims at once are
        # outside the bound even when both IDs are in the manifest.
        self.assertEqual(200, self.start("first", SHINEN_FIRST)[0])
        self.assertEqual(200, self.clear("first-clear", SHINEN_FIRST)[0])
        self.assertEqual(200, self.start("second", 3)[0])
        status, _ = self.clear("second-clear", 3, buddies=[223, 66])
        self.assertEqual(409, status)
        self.assertEqual("world_map_special_active", self.phase())

    def test_a_reported_coin_drop_is_settled(self) -> None:
        """The battle's own Coins land, the way Hunting's do.

        This was refused while the chapter's rewards were unrecovered. The
        client is the only party that ever knew what its battle paid, and a
        refusal did not withhold the Coins so much as wedge the account: it
        leaves the battle active until the same quest is replayed.
        """
        self.assertEqual(200, self.start("wms-start", SHINEN_FIRST)[0])
        self.assertEqual(200, self.clear("wms-clear-a", SHINEN_FIRST, coins=500)[0])
        self.assertEqual(600, self.userdata()["coins"])
        self.assertEqual("free_roam", self.phase())

    def test_the_battles_own_experience_is_accepted_up_to_its_ceiling(self) -> None:
        """A won level-90 battle grants EXP; refusing it failed the clear.

        Experience is what the battle produced, and a zero ceiling meant 25
        stamina bought a fight the player won and the server then rejected.
        The ceiling is still enforced, and is the one bound this clear keeps
        over the channels the client reports.
        """
        self.assertEqual(200, self.start("wms-start", SHINEN_FIRST)[0])
        self.assertEqual(200, self.clear("wms-clear", SHINEN_FIRST, exp=1000)[0])

    def test_the_roster_may_gain_both_levels_and_members(self) -> None:
        """The roster is how a recruited monster reaches the account.

        Levels live in `chrdata`, so a clear that pays experience has to accept
        a changed roster, and a recruit arrives through that same array.  The
        membership check that used to refuse one refused the other with it,
        which is why this chapter could never settle the recruit its own battle
        rolled.  `_preserved_roster` is authoritative for every character the
        submission names and still restores any the client omitted.
        """
        self.assertEqual(200, self.start("wms-start", SHINEN_FIRST)[0])
        recruit = dict(self.character, id=self.character["id"] + 991)
        self.assertEqual(200, self.clear(
            "wms-recruit", SHINEN_FIRST, exp=1000, roster=[self.character, recruit],
        )[0])
        self.assertEqual("free_roam", self.phase())
        self.assertEqual(
            [self.character["id"], recruit["id"]],
            [row["id"] for row in self.userdata()["chrdata"]],
        )

        self.assertEqual(200, self.start("wms-start-2", SHINEN_FIRST)[0])
        levelled = dict(self.character, jobLevels=[9, 0, 0])
        self.assertEqual(
            200, self.clear("wms-levelled", SHINEN_FIRST, exp=1000, roster=[levelled])[0],
        )
        self.assertEqual([9, 0, 0], self.userdata()["chrdata"][0]["jobLevels"])

    def test_an_experience_claim_beyond_the_ceiling_is_still_refused(self) -> None:
        from liminal_gate.world_map_special import WORLD_MAP_SPECIAL_EXP_CEILING

        self.assertEqual(200, self.start("wms-start", SHINEN_FIRST)[0])
        self.assertEqual(
            409,
            self.clear("wms-over", SHINEN_FIRST, exp=WORLD_MAP_SPECIAL_EXP_CEILING + 1)[0],
        )
        self.assertEqual("world_map_special_active", self.phase())

    def test_the_route_advances_one_battle_at_a_time(self) -> None:
        # Battle 2 of the Shin'en route is section 3; it is locked until
        # battle 1 (section 4) has been cleared.
        self.assertEqual(409, self.start("early", 3)[0])
        self.assertEqual(200, self.start("first", SHINEN_FIRST)[0])
        self.assertEqual(200, self.clear("first-clear", SHINEN_FIRST)[0])
        self.assertEqual(2, self.frontier()["shinen"])
        self.assertEqual(200, self.start("second", 3)[0])

    def test_the_two_routes_advance_independently(self) -> None:
        self.assertEqual(200, self.start("shinen", SHINEN_FIRST)[0])
        self.assertEqual(200, self.clear("shinen-clear", SHINEN_FIRST)[0])
        self.assertEqual({"shinen": 2, "mutoh": 1}, self.frontier())
        # The Mutoh route is still at its own opener, not carried along.
        self.assertEqual(409, self.start("mutoh-early", 8)[0])
        self.assertEqual(200, self.start("mutoh", MUTOH_FIRST)[0])

    def test_a_cleared_battle_stays_repeatable(self) -> None:
        self.assertEqual(200, self.start("first", SHINEN_FIRST)[0])
        self.assertEqual(200, self.clear("first-clear", SHINEN_FIRST)[0])
        self.assertEqual(200, self.start("again", SHINEN_FIRST)[0])
        self.assertEqual(200, self.clear("again-clear", SHINEN_FIRST)[0])
        # Replaying an earlier battle must not push the frontier backwards.
        self.assertEqual(2, self.frontier()["shinen"])

    def test_the_frontier_and_active_battle_survive_a_restart(self) -> None:
        self.assertEqual(200, self.start("first", SHINEN_FIRST)[0])
        self.assertEqual(200, self.clear("first-clear", SHINEN_FIRST)[0])
        self.assertEqual(200, self.start("second", 3)[0])
        self.restart()
        self.assertEqual("world_map_special_active", self.phase())
        snapshot = self.userdata()
        status, cleared = self.clear("second-clear", 3, snapshot=snapshot)
        self.assertEqual((200, True), (status, cleared["success"]))
        self.assertEqual(3, self.frontier()["shinen"])
        self.restart()
        self.assertEqual(3, self.frontier()["shinen"])

    def test_a_retry_under_a_new_request_id_does_not_charge_twice(self) -> None:
        status, first = self.start("retry-one", SHINEN_FIRST)
        self.assertEqual(200, status)
        status, second = self.start("retry-two", SHINEN_FIRST)
        self.assertEqual((200, first["refillStartTime"]), (status, second["refillStartTime"]))

    def test_a_spent_request_id_with_a_different_body_is_judged_on_its_merits(self) -> None:
        """The replay key carries the body, so this is not a collision at all.

        It used to answer 409, but by way of the one-active-battle refusal
        rather than anything about the request id. Now that a start for a
        different stage releases the battle still open, what this proves is the
        keying: a fresh body under a spent id is a new request, not a replay of
        the first stage's answer.
        """
        self.assertEqual(200, self.start("shared", SHINEN_FIRST)[0])
        self.assertEqual(200, self.start("shared", MUTOH_FIRST)[0])
        self.assertEqual(
            {"chapter": WORLD_MAP_SPECIAL_CHAPTER, "section": MUTOH_FIRST},
            self.account()["active_world_map_special"],
        )

    def test_entry_is_refused_before_the_native_chapter_34_gate(self) -> None:
        self.stop_server()
        self.state_path.unlink()
        self.start_server()
        self.create_account(LOCKED)
        self.assertEqual(409, self.start("too-early", SHINEN_FIRST)[0])
        self.assertEqual("free_roam", self.phase())

    def test_a_declared_cost_other_than_the_recovered_one_is_rejected(self) -> None:
        status, _ = self.start("cheap", SHINEN_FIRST, stamina=1)
        self.assertEqual(501, status)

    def test_an_exhausted_meter_refuses_the_entry(self) -> None:
        with self.server.state.lock:
            account = self.server.state.accounts[self.account_id]
            account["userdata"]["refillStartTime"] = time.time()
            self.server.state._persist_locked()
        status, refused = self.start("broke", SHINEN_FIRST)
        self.assertEqual((200, True, 1), (status, refused["success"], refused["cmdError"]))
        self.assertEqual("free_roam", self.phase())

    def test_starting_a_different_battle_releases_the_one_left_open(self) -> None:
        """The client runs one battle, so this is the player having left it.

        Refusing instead is what left an account unable to start anything after
        an ordinary game over: nothing the client sends on the way out of a lost
        battle released the stage, and a Daily Quest could not be re-entered to
        release it either, because the day is spent at accepted start.
        """
        self.assertEqual(200, self.start("busy", SHINEN_FIRST)[0])
        self.assertEqual(200, self.start("second", MUTOH_FIRST)[0])
        self.assertEqual("world_map_special_active", self.phase())
        self.assertEqual(
            {"chapter": WORLD_MAP_SPECIAL_CHAPTER, "section": MUTOH_FIRST},
            self.account()["active_world_map_special"],
        )


if __name__ == "__main__":
    unittest.main()
