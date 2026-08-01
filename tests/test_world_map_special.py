"""The Chapter-1100 World Map Special routes.

Two permanent map points the client draws itself after normal Chapter 34.  The
server's only jobs are to charge the 25-stamina entry, keep the route's own
frontier, refuse to move core story progress, and refuse to invent a Companion
from the `dropBuddies` manifest.
"""
from __future__ import annotations

import json
from http.client import HTTPConnection
from pathlib import Path
import tempfile
import threading
import time
import unittest
from urllib.parse import urlencode

from liminal_gate.bootstrap_server import BootstrapServer, BootstrapState, load_profile
from liminal_gate.world_map_special import (
    UNLOCK_AFTER_CHAPTER,
    WORLD_MAP_SPECIAL_CHAPTER,
    WORLD_MAP_SPECIAL_STAMINA,
    build_bundled_world_map_special_policy,
)


PUBLIC_ROOT = Path(__file__).resolve().parents[1]


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
        self.profile = load_profile(PUBLIC_ROOT / "profiles" / "legacy-client-bootstrap.json")
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
        self.server = BootstrapServer(("127.0.0.1", 0), self.profile, BootstrapState(self.state_path))
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()

    def stop_server(self) -> None:
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()

    def restart(self) -> None:
        self.stop_server()
        self.start_server()

    def post(self, route: str, request_id: str, fields: list[tuple[str, str]]) -> tuple[int, dict]:
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
        # Preservation Energy income, as every other archive stage pays.
        self.assertEqual(4, self.userdata()["freeEnergy"])

    def test_a_clear_that_claims_core_progress_is_refused(self) -> None:
        self.assertEqual(200, self.start("wms-start", SHINEN_FIRST)[0])
        status, _ = self.clear("wms-clear", SHINEN_FIRST, progress=progress_code(36))
        self.assertEqual(409, status)
        self.assertEqual(UNLOCKED, self.userdata()["progressCode"])

    def test_a_reported_companion_drop_is_refused_not_minted(self) -> None:
        # Section 4's manifest names Companion 137, but no captured clear proves
        # the roll rule, so a client claiming it is rejected outright.
        self.assertEqual(200, self.start("wms-start", SHINEN_FIRST)[0])
        status, _ = self.clear("wms-clear", SHINEN_FIRST, buddies=[137])
        self.assertEqual(409, status)
        self.assertEqual("world_map_special_active", self.phase())

    def test_a_coin_claim_is_refused(self) -> None:
        self.assertEqual(200, self.start("wms-start", SHINEN_FIRST)[0])
        self.assertEqual(409, self.clear("wms-clear-a", SHINEN_FIRST, coins=500)[0])
        self.assertEqual(100, self.userdata()["coins"])

    def test_the_battles_own_experience_is_accepted_up_to_its_ceiling(self) -> None:
        """A won level-90 battle grants EXP; refusing it failed the clear.

        The section's own BattleData switches Coins, items, and Luck chests off,
        so those stay refused. Experience is not one of those channels -- it is
        what the battle produced -- and a zero ceiling meant 25 stamina bought a
        fight the player won and the server then rejected.
        """
        self.assertEqual(200, self.start("wms-start", SHINEN_FIRST)[0])
        self.assertEqual(200, self.clear("wms-clear", SHINEN_FIRST, exp=1000)[0])

    def test_the_roster_may_gain_levels_but_not_members(self) -> None:
        """Paying EXP must not turn the roster into a grant channel.

        Levels live in `chrdata`, so a clear that pays experience has to accept
        a changed roster -- but this chapter mints nobody, and its reported
        Companions are refused outright. A roster naming a character the account
        does not hold would be exactly the grant the Companion check denies,
        arriving through the other door.
        """
        self.assertEqual(200, self.start("wms-start", SHINEN_FIRST)[0])
        intruder = dict(self.character, id=self.character["id"] + 991)
        status, refused = self.clear(
            "wms-injected", SHINEN_FIRST, exp=1000, roster=[self.character, intruder],
        )
        self.assertEqual(409, status)
        self.assertEqual("invalid_local_world_map_special_result", refused["error"])
        self.assertEqual("world_map_special_active", self.phase())
        self.assertEqual(
            [self.character["id"]], [row["id"] for row in self.userdata()["chrdata"]],
        )

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

    def test_the_same_request_id_with_a_different_body_collides(self) -> None:
        self.assertEqual(200, self.start("shared", SHINEN_FIRST)[0])
        self.assertEqual(409, self.start("shared", MUTOH_FIRST)[0])

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

    def test_a_battle_cannot_start_while_another_is_active(self) -> None:
        self.assertEqual(200, self.start("busy", SHINEN_FIRST)[0])
        self.assertEqual(409, self.start("second", MUTOH_FIRST)[0])


if __name__ == "__main__":
    unittest.main()
