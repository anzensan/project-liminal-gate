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
from liminal_gate.companion_master_data import companion_drop_level
from liminal_gate.luck_data import LUCK_TENTHS_MAX
from liminal_gate.luck_pool_catalog import LuckPoolCatalog
from liminal_gate.luck_pool_interpolation import build_luck_pools
from liminal_gate.luck_runtime import chest_coins, chest_items
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
# The route openers: play order is the section ordinal, ascending (Confirmed
# by live traffic), so Shin'en's opener is section 1 and Mutoh's is section 6.
# The client's own "battle 1" title tier -- level 80 -- is the *fourth*
# section played in each route, not the first; see world_map_special.py.
SHINEN_FIRST, MUTOH_FIRST = 1, 6


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

    def test_the_level_80_tier_is_the_fourth_battle_played_not_the_opener(self) -> None:
        # Confirmed by live traffic (a fresh account's first `start_quest` for
        # a route names its lowest section id): play order is the section
        # ordinal, ascending, not the client's own difficulty-tier numbering
        # (`Battle_Shinen_1`.._4 etc.), which runs "4, 3, 2, 1" against it. The
        # tier titled "battle 1" is level 80 and is therefore played fourth.
        for route in self.catalog.routes():
            stages = {stage.battle: stage for stage in self.catalog.stages if stage.route == route}
            self.assertEqual(80, stages[4].level)
            self.assertEqual([90, 90, 90, 90], [stages[n].level for n in (1, 2, 3, 5)])

    def test_section_ordinal_is_play_order(self) -> None:
        by_route = {
            route: [stage.section for stage in self.catalog.stages if stage.route == route]
            for route in self.catalog.routes()
        }
        self.assertEqual([1, 2, 3, 4, 5], by_route["shinen"])
        self.assertEqual([6, 7, 8, 9, 10], by_route["mutoh"])

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


class WorldMapSpecialHarness(unittest.TestCase):
    """Account, server and request helpers shared by the Chapter-1100 suites.

    Holds no tests of its own so a suite that changes how the server is
    built -- the chest suite supplies a luck-pool catalog -- inherits the
    harness without re-running every other suite's assertions against it.
    """

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

class WorldMapSpecialRuntimeTest(WorldMapSpecialHarness):
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
        # Section 1's manifest names Companion 129 (among its three); the
        # community record documents one exclusive Companion roll per clear,
        # so a single reported manifest Companion settles into the box at
        # level 1.
        self.assertEqual(200, self.start("wms-start", SHINEN_FIRST)[0])
        status, cleared = self.clear("wms-clear", SHINEN_FIRST, buddies=[129])
        self.assertEqual((200, True), (status, cleared["success"]))
        self.assertEqual("free_roam", self.phase())
        minted = cleared["buddyInfo"]["list"]
        self.assertEqual([(129, 1)], [(row["bid"], row["lv"]) for row in minted])

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
        self.assertEqual(200, self.start("second", 2)[0])
        status, _ = self.clear("second-clear", 2, buddies=[223, 66])
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
        # Battle 2 of the Shin'en route is section 2; it is locked until
        # battle 1 (section 1) has been cleared.
        self.assertEqual(409, self.start("early", 2)[0])
        self.assertEqual(200, self.start("first", SHINEN_FIRST)[0])
        self.assertEqual(200, self.clear("first-clear", SHINEN_FIRST)[0])
        self.assertEqual(2, self.frontier()["shinen"])
        self.assertEqual(200, self.start("second", 2)[0])

    def test_the_two_routes_advance_independently(self) -> None:
        self.assertEqual(200, self.start("shinen", SHINEN_FIRST)[0])
        self.assertEqual(200, self.clear("shinen-clear", SHINEN_FIRST)[0])
        self.assertEqual({"shinen": 2, "mutoh": 1}, self.frontier())
        # The Mutoh route is still at its own opener, not carried along.
        self.assertEqual(409, self.start("mutoh-early", 7)[0])
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
        self.assertEqual(200, self.start("second", 2)[0])
        self.restart()
        self.assertEqual("world_map_special_active", self.phase())
        snapshot = self.userdata()
        status, cleared = self.clear("second-clear", 2, snapshot=snapshot)
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

    def test_give_up_character_save_releases_the_active_battle_and_survives_restart(self) -> None:
        """The observed two-field Give Up save must release Chapter 1100 too."""
        self.assertEqual(200, self.start("wms-start", SHINEN_FIRST)[0])
        give_up = [("chrdata", json.dumps([self.character])), ("lastUpdate", "1")]

        status, saved = self.post("/gd/userdata", "wms-give-up", give_up)
        self.assertEqual((200, True), (status, saved["success"]))
        self.assertEqual("free_roam", self.phase())
        self.assertIsNone(self.account().get("active_world_map_special"))

        self.assertEqual((status, saved), self.post("/gd/userdata", "wms-give-up", give_up))
        self.restart()
        self.assertEqual("free_roam", self.phase())
        self.assertEqual(200, self.start("wms-reenter", SHINEN_FIRST)[0])

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


class WorldMapSpecialLuckChestTest(WorldMapSpecialHarness):
    """Chapter 1100 pays a Luck Treasure Chest like every other battle route.

    Reported by a tester on issue 77: "I just completed some special battles
    (Shin'en HM, Mutoh HM, and the 3 Dragons King Descended), and there were no
    luck-based chests at the end of the fights." The Dragon Kings were an event
    handler that had one; these two were this handler, which rolled none at all.

    Chapter 1100 is not on the record's own chestless list, and the record does
    not document its tables either, so a donated chapter fills the silence --
    which is why this server is built with interpolation on, as the shipped one
    is.
    """

    def start_server(self) -> None:
        self.server, self.thread = start_server(
            ("127.0.0.1", 0), self.profile, BootstrapState(self.state_path),
            stamina=True, luck_pool_catalog=build_luck_pools(None, interpolate=True),
        )

    def setUp(self) -> None:
        super().setUp()
        # Luck 100 is guaranteed at the ceiling, so the richest tier is certain
        # to be dealt rather than left to the roll.
        with self.server.state.lock:
            userdata = self.server.state.accounts[self.account_id]["userdata"]
            userdata["chrdata"] = [dict(self.character, luck=LUCK_TENTHS_MAX)]
            userdata["teamMembers"] = [9001, 0, 0, 0, 0, 0]
            userdata["buddyInfo"] = {"list": [], "record": []}
            userdata["nextCompanionInventoryId"] = 1
            self.server.state._persist_locked()

    def test_the_entry_deals_a_chest_and_the_clear_expects_what_it_paid(self) -> None:
        status, started = self.start("chest-start", SHINEN_FIRST)
        self.assertEqual((200, True), (status, started["success"]))
        chest = started["luckResult"]
        self.assertEqual(6, len(chest), "one slot per tier, in the client's order")
        self.assertTrue(any(slot for slot in chest), f"no chest was dealt: {chest}")
        # Kept for the clear, because the client folds it into what it reports.
        self.assertEqual(chest, self.account()["active_luck_result"])

        # The client reports its pre-clear balance plus the battle *and* the
        # chest, while the battle itself paid nothing. Before this the chest
        # half was unexpected and a won battle was refused as a wallet conflict.
        held = self.userdata()
        paid = chest_coins(chest)
        status, cleared = self.clear(
            "chest-clear", SHINEN_FIRST, coins=0,
            snapshot=dict(held, coins=held["coins"] + paid),
            roster=[dict(self.character, luck=LUCK_TENTHS_MAX)],
        )
        self.assertEqual((200, True), (status, cleared["success"]))
        self.assertEqual(held["coins"] + paid, self.userdata()["coins"])
        self.assertEqual([], self.account()["active_luck_result"])

    def test_the_chest_grants_the_forms_the_client_cannot_report(self) -> None:
        """Companions and characters have no field in the clear body at all.

        So the server grants what it authored, and the roster it answers with
        announces a granted character as new.
        """
        status, started = self.start("grant-start", SHINEN_FIRST)
        self.assertEqual(200, status)
        chest = started["luckResult"]
        companions = [int(slot[1:]) for slot in chest if slot.startswith("O")]
        characters = [int(slot[1:]) for slot in chest if slot.startswith("M")]

        held = self.userdata()
        status, cleared = self.clear(
            "grant-clear", SHINEN_FIRST, coins=0,
            snapshot=dict(held, coins=held["coins"] + chest_coins(chest)),
            roster=[dict(self.character, luck=LUCK_TENTHS_MAX)],
        )
        self.assertEqual((200, True), (status, cleared["success"]))
        owned = self.userdata()["buddyInfo"]["list"]
        for companion_id in companions:
            self.assertIn(
                companion_id, [row["bid"] for row in owned],
                "a Companion the chest named must reach the box",
            )
        roster = {row["id"] for row in self.userdata()["chrdata"]}
        announced = {row["id"] for row in cleared["chrdata"] if row.get("isNew")}
        for character_id in characters:
            self.assertIn(character_id, roster)
            self.assertIn(character_id, announced)
        # The chest's items arrive through the client's own report, which
        # `_preserved_counts` accepts because it takes the larger count.
        self.assertTrue(
            all(count >= 1 for count in chest_items(chest).values()),
            "an item slot is one copy",
        )


class WorldMapSpecialChestGrantTest(WorldMapSpecialHarness):
    """What a chest actually delivers, against a pinned pool.

    The donated pool this route rolls against does not put a Companion in every
    chest, so these use an operator catalog instead: the subject is what happens
    to a Companion the chest names, not which one the roll picks.
    """

    #: Luck 80 and Luck 100 are both certain at the ceiling. 128 is Metal
    #: Minion, which this stage's own drop manifest does *not* name -- so a
    #: Companion in the box that the battle could not have dropped came from
    #: the chest and nowhere else.
    CHEST_COMPANION = 128
    CHEST_CHARACTER = 202

    def start_server(self) -> None:
        pinned = LuckPoolCatalog({(WORLD_MAP_SPECIAL_CHAPTER, SHINEN_FIRST): {
            "Luck 80": (f"O{self.CHEST_COMPANION}",),
            "Luck 100": (f"M{self.CHEST_CHARACTER}",),
        }})
        self.server, self.thread = start_server(
            ("127.0.0.1", 0), self.profile, BootstrapState(self.state_path),
            stamina=True, luck_pool_catalog=build_luck_pools(pinned, interpolate=True),
        )

    def setUp(self) -> None:
        super().setUp()
        with self.server.state.lock:
            userdata = self.server.state.accounts[self.account_id]["userdata"]
            userdata["chrdata"] = [dict(self.character, luck=LUCK_TENTHS_MAX)]
            userdata["teamMembers"] = [9001, 0, 0, 0, 0, 0]
            userdata["buddyInfo"] = {"list": [], "record": []}
            userdata["nextCompanionInventoryId"] = 1
            self.server.state._persist_locked()

    def settle(self, tag: str, buddies: list | None = None) -> tuple[dict, dict]:
        status, started = self.start(f"{tag}-start", SHINEN_FIRST)
        self.assertEqual(200, status, started)
        chest = started["luckResult"]
        self.assertEqual(f"O{self.CHEST_COMPANION}", chest[4], chest)
        held = self.userdata()
        status, cleared = self.clear(
            f"{tag}-clear", SHINEN_FIRST, coins=0, buddies=buddies,
            snapshot=dict(held, coins=held["coins"] + chest_coins(chest)),
            roster=[dict(self.character, luck=LUCK_TENTHS_MAX)],
        )
        self.assertEqual((200, True), (status, cleared["success"]))
        return chest, cleared

    def test_a_battle_drop_and_a_chest_grant_both_survive(self) -> None:
        """The defect a tester found: "Luck chests now appear on daily quests at
        least, but rewards don't stick around."

        The battle-drop projection is built before the chest is granted, so
        assigning it over `buddyInfo` at the end of the settlement threw away
        every Companion the chest had just paid. Both must land, and the answer
        must carry the box that holds both -- `UserData.LoadBuddyInfo` replaces
        the client's box with what arrives, so reporting the pre-chest
        projection takes the chest's Companions back out of the client, and the
        next Companion write then persists their absence.
        """
        # 129 is on this stage's own `dropBuddies` manifest, so the battle may
        # report it and the two sources stay distinguishable in the box.
        _, cleared = self.settle("both", buddies=[129])
        owned = [row["bid"] for row in self.userdata()["buddyInfo"]["list"]]
        self.assertIn(129, owned, "the battle's own drop must survive")
        self.assertIn(self.CHEST_COMPANION, owned, "the chest's grant must survive")
        answered = [row["bid"] for row in cleared["buddyInfo"]["list"]]
        self.assertEqual(sorted(owned), sorted(answered), "the client is told what it owns")

    def test_a_chest_only_grant_is_still_reported_to_the_client(self) -> None:
        """No battle drop, so the old contract sent no box at all -- and the
        client went on owning nothing the chest had paid."""
        _, cleared = self.settle("report")
        self.assertIn("buddyInfo", cleared)
        answered = [row["bid"] for row in cleared["buddyInfo"]["list"]]
        self.assertEqual([self.CHEST_COMPANION], answered)

    def test_the_chest_companion_arrives_at_its_own_drop_level(self) -> None:
        """Metal Minion is a level 1 dropper; an OII Companion is a level 30
        one, which is the client's own `BuddyData.DropLevel` either way."""
        self.settle("level")
        owned = self.userdata()["buddyInfo"]["list"]
        self.assertEqual(
            [companion_drop_level(row["bid"]) for row in owned],
            [row["lv"] for row in owned],
            owned,
        )
