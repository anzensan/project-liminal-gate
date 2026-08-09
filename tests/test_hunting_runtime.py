from __future__ import annotations

import copy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import urlencode

from liminal_gate.bootstrap_server import SPECIES_LIMIT_ERROR_CODE, BootstrapState
from liminal_gate.event_flag_data import music_event_flags
from liminal_gate.hunting_catalog import build_bundled_hunting_policy, load_hunting_catalog
from liminal_gate.save_validation import ITEM_SLOTS, MAX_ITEM_STACK
from liminal_gate.tuning import DEFAULT_TUNING
from tests.support import bootstrap_profile, get, post, start_server, stop_server


PROGRESS = 0x01000000 | (9 << 6) | 1
LOCKED_STAGE = (1002, 3)


class HuntingRuntimeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.state_path = self.root / "state.json"
        catalog_path = self.root / "hunting.json"
        catalog_path.write_text(json.dumps({
            "schema_version": 1, "provenance": "user-supplied",
            "item_slots": 8, "max_stack": 99,
            "stages": [
                {
                    "family": "pudding", "chapter": 1001, "section": 1,
                    "stamina": 3, "coins": 0, "entry_item_id": 0, "entry_item_count": 0,
                    "unlock_chapter": 1, "unlock_section": 1, "max_coins": 0, "max_exp": 0,
                    "max_items_total": 7, "item_maxima": {"2": 5, "3": 2},
                },
                {
                    "family": "coin_creeps", "chapter": 1003, "section": 1,
                    "stamina": 1, "coins": 0, "entry_item_id": 5, "entry_item_count": 1,
                    "unlock_chapter": 1, "unlock_section": 1, "max_coins": 1500, "max_exp": 0,
                    "max_items_total": 0, "item_maxima": {},
                },
                {
                    # A ticket-aware stage: item 5 replaces the stamina cost
                    # when one is held, and settles EXP plus Companions.
                    "family": "metal_zone", "chapter": 3000, "section": 11,
                    "stamina": 4, "coins": 0, "entry_item_id": 5, "entry_item_count": 1,
                    "ticket_optional": True, "selector": "metal",
                    "unlock_chapter": 1, "unlock_section": 1, "max_coins": 0, "max_exp": 1000,
                    "max_items_total": 0, "item_maxima": {},
                    "companion_maxima": {"11": 2}, "companion_drop_levels": {"11": 1},
                },
                {
                    # A Road: EXP plus one declared battle-recruited monster,
                    # the Dragon Road Steel Dragon shape.
                    "family": "road", "chapter": 1200, "section": 1,
                    "stamina": 2, "coins": 0, "entry_item_id": 0, "entry_item_count": 0,
                    "selector": "metal",
                    "unlock_chapter": 1, "unlock_section": 1, "max_coins": 0, "max_exp": 1000,
                    "max_items_total": 0, "item_maxima": {},
                    "monster_recruit_maxima": {"9002": 1},
                },
                {
                    "family": "money_money_time", "chapter": 3003, "section": 1,
                    "stamina": 5, "coins": 0, "entry_item_id": 0, "entry_item_count": 0,
                    "selector": "special",
                    "unlock_chapter": 1, "unlock_section": 1, "max_coins": 1800, "max_exp": 0,
                    "max_items_total": 0, "item_maxima": {},
                },
                {
                    "family": "crystal_road", "chapter": 3004, "section": 1,
                    "stamina": 7, "coins": 0, "entry_item_id": 0, "entry_item_count": 0,
                    "selector": "hunting",
                    "unlock_chapter": 1, "unlock_section": 1, "max_coins": 0, "max_exp": 0,
                    "max_items_total": 2, "item_maxima": {"1": 1, "2": 1, "5": 1, "6": 1},
                },
                {
                    # An unflagged stage above the eight-stamina gate: the
                    # shape Metal Zone zones 2--7 and the Roads have, and the
                    # one that could grow no Luck at all while the Hunting
                    # start rolled no table. Hidden, so the selector-list
                    # assertions elsewhere stay about the advertised rows.
                    "family": "road", "chapter": 1201, "section": 1,
                    "stamina": 15, "coins": 0, "entry_item_id": 0, "entry_item_count": 0,
                    "selector": "hidden",
                    "unlock_chapter": 1, "unlock_section": 1, "max_coins": 0, "max_exp": 1000,
                    "max_items_total": 0, "item_maxima": {},
                },
                {
                    "family": "tin", "chapter": LOCKED_STAGE[0], "section": LOCKED_STAGE[1],
                    "stamina": 1, "coins": 0, "entry_item_id": 0, "entry_item_count": 0,
                    "unlock_chapter": 30, "unlock_section": 1,
                    "max_coins": 0, "max_exp": 0, "max_items_total": 1, "item_maxima": {"2": 1},
                },
            ],
        }), encoding="utf-8")
        self.catalog = load_hunting_catalog(catalog_path)
        self.profile = bootstrap_profile()
        self.token, self.account_id = "hunt-token", "hunt-account"
        self.character = {
            "id": 9001, "buddy": 0, "date": 0.0, "jobSlots": [0, 0, 0],
            "jobLevels": [1, 0, 0], "jobID": 0, "flags": 0, "skillBoost": 0,
        }
        self.outcome_strict = False
        self.start_server()
        self.server.state.create_account(self.token, self.account_id, {
            "coins": 100, "energy": 40, "freeEnergy": 2, "worldMapNo": 0,
            "progressCode": PROGRESS, "chrdata": [self.character],
            "itemList": [0, 1, 0, 0, 2, 0, 0, 0], "summonList": [0, 0],
        })
        with self.server.state.lock:
            account = self.server.state.accounts[self.account_id]
            account["tutorial_phase"] = "free_roam"
            account["initial_userdata_served"] = True
            self.server.state._persist_locked()

    def tearDown(self) -> None:
        self.stop_server()
        self.temporary_directory.cleanup()

    def start_server(self) -> None:
        self.server, self.thread = start_server(
            ("127.0.0.1", 0), self.profile, BootstrapState(self.state_path),
            hunting_catalog=self.catalog, outcome_strict=self.outcome_strict,
        )

    def stop_server(self) -> None:
        stop_server(self.server, self.thread)

    def restart(self) -> None:
        self.stop_server()
        self.start_server()

    def enable_strict_outcomes(self) -> None:
        self.outcome_strict = True
        self.server.outcome_strict = True

    def post(self, route: str, request_id: str, fields: list[tuple[str, str]]) -> tuple[int, dict]:
        return post(
            self.server, route, request_id, urlencode(fields), token=self.token,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    def userdata(self) -> dict:
        return json.loads(self.state_path.read_text(encoding="utf-8"))["accounts"][self.account_id]["userdata"]

    def server_status(self, token: str) -> dict:
        status, payload = get(
            self.server,
            f"/gd/get_server_status?platform=GooglePlay&app_version=5.57&otk={token}",
        )
        self.assertEqual(200, status)
        return payload

    def login(self, token: str) -> dict:
        status, payload = get(
            self.server,
            f"/gd/login?otk={token}&uuid={self.account_id}",
        )
        self.assertEqual(200, status)
        return payload

    def account(self) -> dict:
        return json.loads(self.state_path.read_text(encoding="utf-8"))["accounts"][self.account_id]

    def phase(self) -> str:
        return self.account()["tutorial_phase"]

    def start(self, request_id: str, chapter: int, section: int, stamina: int) -> tuple[int, dict]:
        return self.post("/gd/start_quest", request_id, [
            ("stamina", str(stamina)), ("coins", "0"), ("chapter", str(chapter)),
            ("section", str(section)), ("lastUpdate", "1"),
        ])

    def start_with_ticket(
        self, request_id: str, chapter: int, section: int, stamina: int,
        item_id: int = 5, item_count: int = 1,
    ) -> tuple[int, dict]:
        """Start using the ticket-aware form the client sends for Metal Zone.

        The fixture's ticket is item 5 so it fits the fixture's eight slots; the
        real Item 50 contract is asserted against the bundled policy instead.
        """
        return self.post("/gd/start_quest", request_id, [
            ("stamina", str(stamina)), ("coins", "0"),
            ("itemID", str(item_id)), ("itemCount", str(item_count)),
            ("chapter", str(chapter)), ("section", str(section)), ("lastUpdate", "1"),
        ])

    def clear(self, request_id: str, chapter: int, section: int, *, coins: int = 0,
              items: dict | None = None, item_list: list | None = None, exp: int = 0,
              buddies: list | None = None, monsters: list | None = None,
              summons: list | None = None, summon_list: list | None = None,
              snapshot: dict | None = None) -> tuple[int, dict]:
        # A real retry resends the body it sent the first time.  Rebuilding it
        # from live userdata would instead echo the Energy the first clear
        # granted, producing a different body and so a cache miss rather than
        # the replay the caller is asserting; pass `snapshot` to pin it.
        userdata = self.userdata() if snapshot is None else snapshot
        return self.post("/gd/clear_quest", request_id, [
            ("progressCode", str(userdata["progressCode"])), ("worldMapNo", "0"),
            ("valuables", json.dumps({
                "energyAppStore": 0, "energy": userdata["energy"], "energyAndApp": 0,
                "freeEnergy": userdata["freeEnergy"], "energyGooglePlay": 0,
                "coins": userdata["coins"] + coins,
            })),
            ("chrdata", json.dumps([self.character])),
            ("itemList", json.dumps(userdata["itemList"] if item_list is None else item_list)),
            ("summonList", json.dumps(userdata["summonList"] if summon_list is None else summon_list)),
            ("battle_result", json.dumps({
                "chapter": chapter, "section": section, "coins": coins, "exp": exp,
                "items": items or {}, "buddies": buddies or [], "monsters": monsters or [],
                "summons": summons or [],
                "luckynum": 0, "unableluckdrop": False, "boostup": [0, 0, 0, 0, 0, 0],
            })),
            ("itmp0", "0"), ("itmp1", "0"), ("lastUpdate", "1"),
        ])

    def form_party(self) -> None:
        """Put the fixture's one character in the party.

        `roll_luck_up_table` reads `teamMembers`, and an account with no party
        cannot gain Luck at all, so every Luck test below needs this first.
        """
        with self.server.state.lock:
            account = self.server.state.accounts[self.account_id]
            account["userdata"]["teamMembers"] = [9001, 0, 0, 0, 0, 0]
            self.server.state._persist_locked()

    def luck(self) -> int:
        return next(
            int(row.get("luck", 0)) for row in self.userdata()["chrdata"]
            if row["id"] == 9001
        )

    def battle(self, tag: str, chapter: int, section: int, stamina: int) -> int:
        """Run one whole battle and return the Luck it added, in tenths.

        The clear reports `self.character`, which carries no `luck` member --
        the confirmed shape of a real client clear, and the reason a
        server-authored gain has to survive the roster merge to exist at all.
        """
        before = self.luck()
        status, started = self.start(tag, chapter, section, stamina)
        self.assertEqual((200, True), (status, started["success"]), started)
        status, cleared = self.clear(f"{tag}-clear", chapter, section)
        self.assertEqual(200, status, cleared)
        return self.luck() - before

    def test_a_costly_hunting_stage_grows_luck(self) -> None:
        """The family gap: a fifteen-stamina Road is past Mistwalker's own gate,
        and grew nothing while only the story handler rolled a table."""
        self.form_party()
        gained = sum(self.battle(f"road{n}", 1201, 1, 15) for n in range(24))
        self.assertGreater(gained, 0, "24 battles at 15 stamina raised no Luck")

    def test_a_cheap_unflagged_hunting_stage_never_grows_luck(self) -> None:
        """`LUCK_GAIN_MIN_STAMINA` is confirmed and stays enforced here."""
        self.form_party()
        for n in range(24):
            self.assertEqual(
                0, self.battle(f"pud{n}", 1001, 1, 3),
                f"a three-stamina stage raised Luck on battle {n}",
            )

    def test_a_flagged_stage_grows_luck_below_the_stamina_gate(self) -> None:
        """Crystal Road is `allowLucky` and costs seven, so only the
        Lucky-enemy source can reach it. Its gain is the record's +0.3."""
        self.form_party()
        gains = [self.battle(f"cr{n}", 3004, 1, 7) for n in range(24)]
        self.assertTrue(any(gains), "a flagged stage never granted Luck")
        self.assertLessEqual(set(gains), {0, 3}, f"unexpected gains {gains}")

    def test_a_luck_gain_is_durable_across_restart(self) -> None:
        self.form_party()
        for n in range(24):
            self.battle(f"dur{n}", 3004, 1, 7)
        earned = self.luck()
        self.assertGreater(earned, 0)
        self.restart()
        self.assertEqual(earned, self.luck())

    def test_a_start_retry_replays_its_luck_table_rather_than_re_rolling(self) -> None:
        """A re-roll on retry would be a Luck duplicator, as it would be a
        chest duplicator; and the clear must pay the entry's table once."""
        self.form_party()
        status, first = self.start("retry", 3004, 1, 7)
        self.assertEqual((200, True), (status, first["success"]))
        self.assertEqual(first, self.start("retry", 3004, 1, 7)[1])
        before = self.luck()
        self.clear("retry-clear", 3004, 1)
        once = self.luck() - before
        self.assertEqual(sum(first.get("luckUpTable", [0])[:1]), once)
        # Replaying the clear must not pay it twice.
        self.clear("retry-clear", 3004, 1)
        self.assertEqual(before + once, self.luck())

    def test_stage_charges_stamina_settles_within_bounds_and_survives_restart(self) -> None:
        status, started = self.start("hunt-start", 1001, 1, 3)
        self.assertEqual((200, True), (status, started["success"]))
        # Entry debits the stamina meter, not the Energy wallet.
        self.assertEqual((2, 40), (self.userdata()["freeEnergy"], self.userdata()["energy"]))
        self.assertEqual("hunting_active", self.phase())

        self.restart()
        snapshot = copy.deepcopy(self.userdata())
        status, cleared = self.clear("hunt-clear", 1001, 1, items={"2": 4}, item_list=[0, 5, 0, 0, 2, 0, 0, 0], snapshot=snapshot)
        self.assertEqual(200, status, cleared)
        self.assertEqual([0, 5, 0, 0, 2, 0, 0, 0], self.userdata()["itemList"])
        self.assertEqual("free_roam", self.phase())
        # Settling a Hunting stage never moves story progress.
        self.assertEqual(PROGRESS, self.userdata()["progressCode"])

        self.assertEqual((status, cleared), self.clear("hunt-clear", 1001, 1, items={"2": 4}, item_list=[0, 5, 0, 0, 2, 0, 0, 0], snapshot=snapshot))
        self.restart()
        self.assertEqual([0, 5, 0, 0, 2, 0, 0, 0], self.userdata()["itemList"])

    def test_prelogin_status_uses_single_migrated_account_progress(self) -> None:
        with self.server.state.lock:
            self.server.state.tokens.clear()
            self.server.state.client_hosts.clear()
            self.server.state._persist_locked()
        constants = self.server_status("rotated-before-login")["constants"]
        self.assertEqual(
            ["1001-1", "1003-1", "1200-1", "3000-11", "3004-1"],
            sorted(
                constants["huntingHuntingList"]
                + constants["metalHuntingList"]
            ),
        )
        self.assertEqual(["3003-1"], constants["specialQuestList"])

    def test_prelogin_status_uses_known_host_but_not_an_unrelated_host(self) -> None:
        with self.server.state.lock:
            self.server.state.tokens.clear()
            self.server.state.client_hosts = {"127.0.0.1": self.account_id}
            self.server.state._persist_locked()
        constants = self.server_status("rotated-after-login")["constants"]
        self.assertEqual(["1001-1", "1003-1", "3004-1"], sorted(constants["huntingHuntingList"]))
        self.assertEqual(["1200-1", "3000-11"], sorted(constants["metalHuntingList"]))
        self.assertEqual(["3003-1"], constants["specialQuestList"])

    def test_a_new_address_still_sees_the_world_when_one_account_exists(self) -> None:
        """A router lease must not empty every selector the client draws.

        Status is fetched *before* login, so on the first launch from a new
        address nothing resolves; the client then builds its menus from empty
        Tower, Eidolon, Strikes Back, Metal, and Hunting lists and looks like a
        server that supports none of them. The login that follows re-binds the
        host, but the menus are already drawn.
        """
        with self.server.state.lock:
            self.server.state.tokens.clear()
            self.server.state.client_hosts = {"127.0.0.1": self.account_id}
            self.server.state._persist_locked()
        self.assertEqual(
            PROGRESS,
            self.server.state.progress_for_status("unbound", "192.0.2.10"),
        )

    def test_a_second_account_stops_an_unrelated_address_resolving(self) -> None:
        """The guard that matters: with two players, neither leaks to a stranger."""
        with self.server.state.lock:
            self.server.state.tokens.clear()
            self.server.state.client_hosts = {"127.0.0.1": self.account_id}
            self.server.state.accounts["second-account"] = {
                "userdata": {"progressCode": PROGRESS}, "tutorial_phase": "free_roam",
            }
            self.server.state._persist_locked()
        self.assertIsNone(
            self.server.state.progress_for_status("unbound", "192.0.2.10")
        )
        # The bound host keeps resolving to its own account, not the newcomer.
        self.assertEqual(
            PROGRESS,
            self.server.state.progress_for_status("unbound", "127.0.0.1"),
        )

    def test_login_pairs_every_advertised_row_with_its_required_flag(self) -> None:
        """Including the 1000-series Hunting rows.

        `UISpecialSelect.IsQuestOpen` excuses Chapters 1000--1099 from the flag
        while the list is built, but `UpdateItems` revalidates every drawn row
        against `CheckQuestFlag` with no such exemption. An unflagged row is
        therefore removed and rebuilt every frame, which is the flashing
        Hunting Zone selector reported in issue 20.
        """
        login = self.login("login-token")
        # Total on purpose, so an unexpected flag fails here rather than
        # reaching a client. The music flags ride every login and carry no
        # stage of their own.
        self.assertEqual(
            music_event_flags() | {
                "sp_ch_1001-1": {
                    "name": "sp_ch_1001-1",
                    "value": True,
                },
                "sp_ch_1003-1": {
                    "name": "sp_ch_1003-1",
                    "value": True,
                },
                "sp_ch_1200-1": {
                    "name": "sp_ch_1200-1",
                    "value": True,
                },
                "sp_ch_3000-11": {
                    "name": "sp_ch_3000-11",
                    "value": True,
                },
                "sp_ch_3003-1": {
                    "name": "sp_ch_3003-1",
                    "value": True,
                },
                "sp_ch_3004-1": {
                    "name": "sp_ch_3004-1",
                    "value": True,
                },
            },
            login["eventFlags"],
        )

    def test_special_quest_settles_and_replays_after_restart(self) -> None:
        self.enable_strict_outcomes()
        status, started = self.start("special-start", 3003, 1, 5)
        self.assertEqual((200, True), (status, started["success"]))
        # Entry debits the client stamina meter, not the Energy wallet.
        self.assertEqual((2, 40), (self.userdata()["freeEnergy"], self.userdata()["energy"]))

        self.restart()
        snapshot = copy.deepcopy(self.userdata())
        status, refused = self.clear("special-over", 3003, 1, coins=1801, snapshot=snapshot)
        self.assertEqual((409, "invalid_local_hunting_result"), (status, refused["error"]))
        self.assertEqual(snapshot, self.userdata())
        self.assertEqual("hunting_active", self.phase())

        # Issue 25 captured this exact final-client result. The old 1,500
        # ceiling rejected it durably and left every later stage blocked.
        self.restart()
        status, cleared = self.clear("special-clear", 3003, 1, coins=1800, snapshot=snapshot)
        self.assertEqual((200, True), (status, cleared["success"]))
        self.assertEqual(1900, self.userdata()["coins"])
        self.assertEqual("free_roam", self.phase())
        self.assertEqual(
            (status, cleared),
            self.clear("special-clear", 3003, 1, coins=1800, snapshot=snapshot),
        )
        self.restart()
        self.assertEqual((1900, "free_roam"), (self.userdata()["coins"], self.phase()))
        self.assertEqual(
            (status, cleared),
            self.clear("special-clear", 3003, 1, coins=1800, snapshot=snapshot),
        )
        self.assertEqual(1900, self.userdata()["coins"])

    def test_crystal_road_settles_only_the_two_documented_item_channels(self) -> None:
        self.enable_strict_outcomes()
        status, started = self.start("crystal-start", 3004, 1, 7)
        self.assertEqual((200, True), (status, started["success"]))
        self.restart()
        snapshot = copy.deepcopy(self.userdata())
        # The fixture treats Item 1 as a material and Item 5 as the Metal
        # Ticket channel.  Two different declared items are the hard maximum.
        status, cleared = self.clear(
            "crystal-clear", 3004, 1, items={"1": 1, "5": 1},
            item_list=[1, 1, 0, 0, 3, 0, 0, 0], snapshot=snapshot,
        )
        self.assertEqual((200, True), (status, cleared["success"]))
        self.assertEqual([1, 1, 0, 0, 3, 0, 0, 0], self.userdata()["itemList"])
        status, started = self.start("crystal-overflow-start", 3004, 1, 7)
        self.assertEqual((200, True), (status, started["success"]))
        self.assertEqual(
            409,
            self.clear(
                "crystal-overflow", 3004, 1, items={"1": 1, "2": 1, "5": 1},
                item_list=[2, 2, 0, 0, 4, 0, 0, 0],
            )[0],
        )

    def test_a_road_recruit_settles_once_and_a_duplicate_changes_nothing(self) -> None:
        self.enable_strict_outcomes()
        status, started = self.start("road-start", 1200, 1, 2)
        self.assertEqual((200, True), (status, started["success"]))
        snapshot = copy.deepcopy(self.userdata())
        status, cleared = self.clear("road-clear", 1200, 1, exp=500, monsters=[9002], snapshot=snapshot)
        self.assertEqual((200, True), (status, cleared["success"]))
        roster_ids = {row["id"] for row in self.userdata()["chrdata"]}
        self.assertIn(9002, roster_ids)
        self.assertEqual("free_roam", self.phase())

        # A second recruit of the same monster settles but grants nothing new:
        # no duplicate rule survives, so none is invented.
        status, started = self.start("road-again", 1200, 1, 2)
        self.assertEqual((200, True), (status, started["success"]))
        before = copy.deepcopy(self.userdata()["chrdata"])
        status, cleared = self.clear("road-clear-again", 1200, 1, monsters=[9002])
        self.assertEqual((200, True), (status, cleared["success"]))
        self.assertEqual(before, self.userdata()["chrdata"])

        # An undeclared monster, or a second copy at once, is refused outright.
        status, started = self.start("road-third", 1200, 1, 2)
        self.assertEqual((200, True), (status, started["success"]))
        for label, claim in (("undeclared", [9003]), ("two-at-once", [9002, 9002])):
            with self.subTest(label):
                status, refused = self.clear(f"road-{label}", 1200, 1, monsters=claim)
                self.assertEqual((409, "invalid_local_hunting_result"), (status, refused["error"]))

    def test_entry_item_is_consumed_and_a_missing_one_refuses_entry(self) -> None:
        self.assertEqual(2, self.userdata()["itemList"][4])
        for index, request_id in enumerate(("ticket-one", "ticket-two")):
            status, started = self.start(request_id, 1003, 1, 1)
            self.assertEqual((200, True), (status, started["success"]), request_id)
            self.assertEqual(1 - index, self.userdata()["itemList"][4])
            status, cleared = self.clear(f"clear-{request_id}", 1003, 1, coins=1500)
            self.assertEqual(200, status, cleared)

        # The third entry has no ticket left, and must not charge or start.
        before = self.userdata()
        status, refused = self.start("ticket-three", 1003, 1, 1)
        self.assertEqual((200, True, 2), (status, refused["success"], refused["cmdError"]))
        self.assertEqual((before["itemList"], before["energy"], "free_roam"), (self.userdata()["itemList"], self.userdata()["energy"], self.phase()))

    def test_a_result_outside_the_declared_bounds_is_refused_without_mutation(self) -> None:
        # Catalog maxima are an explicit audit mode. Normal preservation play
        # trusts a structurally consistent result from the active battle.
        self.enable_strict_outcomes()
        for label, kwargs in (
            ("coins", {"coins": 1}),                      # Pudding declares none
            ("exp", {"exp": 1}),                          # nor any EXP
            ("unlisted-item", {"items": {"7": 1}, "item_list": [0, 1, 0, 0, 2, 0, 1, 0]}),
            ("over-maximum", {"items": {"3": 3}, "item_list": [0, 1, 3, 0, 2, 0, 0, 0]}),
            ("companions", {"buddies": [11]}),            # unbounded without its own catalog
        ):
            with self.subTest(label):
                status, started = self.start(f"start-{label}", 1001, 1, 3)
                self.assertEqual((200, True), (status, started["success"]), f"{label} start")
                before = self.userdata()
                status, refused = self.clear(f"clear-{label}", 1001, 1, **kwargs)
                self.assertEqual(409, status, f"{label}: {refused}")
                self.assertEqual("invalid_local_hunting_result", refused["error"])
                self.assertEqual(before, self.userdata(), f"{label} mutated the save")
                # The stage stays active, so the player may retry it honestly.
                self.assertEqual("hunting_active", self.phase())
                self.assertEqual(200, self.clear(f"settle-{label}", 1001, 1)[0])

    def test_default_trusts_the_pixel_crystal_road_result_and_replays_after_restart(self) -> None:
        """Issue 20's Pixel report outranks the catalog's zero placeholders."""
        self.assertEqual(200, self.start("crystal-pixel-start", 3004, 1, 7)[0])
        snapshot = copy.deepcopy(self.userdata())
        status, cleared = self.clear(
            "crystal-pixel-clear", 3004, 1,
            coins=280, exp=5625, snapshot=snapshot,
        )
        self.assertEqual((200, True), (status, cleared["success"]))
        self.assertEqual((380, "free_roam"), (self.userdata()["coins"], self.phase()))

        self.restart()
        self.assertEqual(
            (status, cleared),
            self.clear(
                "crystal-pixel-clear", 3004, 1,
                coins=280, exp=5625, snapshot=snapshot,
            ),
        )
        self.assertEqual((380, "free_roam"), (self.userdata()["coins"], self.phase()))

    def test_a_reported_summon_is_settled_from_the_client_report(self) -> None:
        """The client owns what its own battle dropped; refusing only wedged it.

        A refused clear leaves the battle active, so the earlier refusal lost
        the Summon *and* blocked every other stage until the quest was replayed.
        """
        self.assertEqual(200, self.start("summon-start", 1001, 1, 3)[0])
        held = self.userdata()["summonList"]
        gained = [count + 1 if slot == 0 else count for slot, count in enumerate(held)]
        status, cleared = self.clear(
            "summon-clear", 1001, 1, summons=[1], summon_list=gained,
        )
        self.assertEqual((200, True), (status, cleared["success"]))
        self.assertEqual(gained, self.userdata()["summonList"])
        self.assertEqual("free_roam", self.phase())

    def test_a_stale_summon_count_never_deletes_a_held_one(self) -> None:
        """`_preserved_counts` governs the Summon array as it does `itemList`."""
        self.assertEqual(200, self.start("stale-summon-start", 1001, 1, 3)[0])
        held = self.userdata()["summonList"]
        self.assertEqual(200, self.clear(
            "stale-summon-clear", 1001, 1, summon_list=[0] * len(held),
        )[0])
        self.assertEqual(held, self.userdata()["summonList"])

    def test_a_locked_stage_is_refused_and_a_second_battle_releases_the_first(self) -> None:
        status, locked = self.start("locked", *LOCKED_STAGE, 1)
        self.assertEqual((409, "hunting_stage_locked"), (status, locked["error"]))
        self.assertEqual("free_roam", self.phase())

        self.assertEqual(200, self.start("first", 1001, 1, 3)[0])
        # A different stage is the player having left the first one. Refusing
        # instead stranded the account: nothing the client sends on the way out
        # of a lost battle releases the stage.
        self.assertEqual(200, self.start("second", 1003, 1, 1)[0])
        self.assertEqual({"chapter": 1003, "section": 1}, self.account()["active_hunt"])
        # A story stage out of progression order is still refused, and by its
        # own gate: `expected_clear_progress` rejects 2-1 for this account
        # before any battle state is consulted. This clause used to sit under a
        # comment claiming it proved a hunt could not be displaced, which it
        # never did -- both refusals answered `tutorial_state_conflict`.
        status, story = self.post("/gd/start_quest", "story", [
            ("stamina", "5"), ("coins", "0"), ("chapter", "2"), ("section", "1"), ("lastUpdate", "1"),
        ])
        self.assertEqual((409, "tutorial_state_conflict"), (status, story["error"]))
        self.assertEqual({"chapter": 1003, "section": 1}, self.account()["active_hunt"])

    def test_declining_the_resume_prompt_abandons_a_hunt_rather_than_stranding_it(self) -> None:
        """The client's party save after a declined resume must free the account."""
        self.assertEqual(200, self.start("abandoned", 1001, 1, 3)[0])
        self.assertEqual("hunting_active", self.phase())
        status, saved = self.post("/gd/userdata", "abandon", [
            ("teamMembers", json.dumps([9001, 0, 0, 0, 0, 0])), ("teamMembers_VS", json.dumps([0] * 18)),
            ("teamBuddies_VS", json.dumps([0] * 18)), ("teamNo", "1"), ("teamNo_VS", "1"),
            ("summonId", "1"), ("lastUpdate", "1"),
        ])
        self.assertEqual((200, True), (status, saved["success"]))
        self.assertEqual("free_roam", self.phase())
        self.assertEqual(200, self.start("after-abandon", 1001, 1, 3)[0])

    def buddy_info(self) -> dict:
        return self.userdata().get("buddyInfo", {"list": [], "record": []})

    def test_a_held_ticket_is_spent_instead_of_stamina(self) -> None:
        before = self.userdata()
        status, started = self.start_with_ticket("metal-ticket", 3000, 11, 4)
        self.assertEqual((200, True), (status, started["success"]))
        # The ticket went, the wallet did not.
        self.assertEqual(1, self.userdata()["itemList"][4])
        self.assertEqual(
            (before["energy"], before["freeEnergy"]),
            (self.userdata()["energy"], self.userdata()["freeEnergy"]),
        )

    def test_holding_no_ticket_charges_stamina_rather_than_refusing(self) -> None:
        """A ticket is an alternative to stamina, so its absence is not an error."""
        with self.server.state.lock:
            self.server.state.accounts[self.account_id]["userdata"]["itemList"] = [0, 1, 0, 0, 0, 0, 0, 0]
            self.server.state._persist_locked()
        status, started = self.start_with_ticket("metal-stamina", 3000, 11, 4)
        self.assertEqual((200, True), (status, started["success"]))
        # Entry debits the stamina meter, so the Energy wallet is untouched.
        self.assertEqual((2, 40), (self.userdata()["freeEnergy"], self.userdata()["energy"]))
        self.assertEqual([0, 1, 0, 0, 0, 0, 0, 0], self.userdata()["itemList"])
        # Stamina fallback did not consume a ticket, so a clear cannot claim
        # that the client is merely repeating a pre-entry ticket balance.
        before = self.userdata()
        status, refused = self.clear(
            "metal-stamina-clear", 3000, 11,
            item_list=[0, 1, 0, 0, 1, 0, 0, 0],
        )
        self.assertEqual((409, "invalid_local_hunting_result"), (status, refused["error"]))
        self.assertEqual(before, self.userdata())
        self.assertEqual(200, self.clear("metal-stamina-settle", 3000, 11)[0])

    def test_ticket_clear_preserves_the_committed_spend_and_replays_after_restart(self) -> None:
        """The final client repeats its pre-entry ticket count at Metal clear."""
        pre_entry = list(self.userdata()["itemList"])
        self.assertEqual(2, pre_entry[4])
        self.assertEqual(200, self.start_with_ticket("metal-stale-ticket-start", 3000, 11, 4)[0])
        self.assertEqual(1, self.userdata()["itemList"][4])
        with self.server.state.lock:
            self.assertIs(
                True,
                self.server.state.accounts[self.account_id]["active_hunt_ticket_spent"],
            )

        self.restart()
        snapshot = copy.deepcopy(self.userdata())
        status, cleared = self.clear(
            "metal-stale-ticket-clear", 3000, 11,
            exp=1000, buddies=[11], item_list=pre_entry, snapshot=snapshot,
        )
        self.assertEqual(200, status, cleared)
        self.assertEqual(1, self.userdata()["itemList"][4])
        self.assertEqual([11], [row["bid"] for row in self.buddy_info()["list"]])

        # The exact retry remains a replay, including after another restart,
        # and therefore cannot restore the ticket or duplicate the Companion.
        self.assertEqual(
            (status, cleared),
            self.clear(
                "metal-stale-ticket-clear", 3000, 11,
                exp=1000, buddies=[11], item_list=pre_entry, snapshot=snapshot,
            ),
        )
        self.restart()
        self.assertEqual(
            (status, cleared),
            self.clear(
                "metal-stale-ticket-clear", 3000, 11,
                exp=1000, buddies=[11], item_list=pre_entry, snapshot=snapshot,
            ),
        )
        self.assertEqual(1, self.userdata()["itemList"][4])
        self.assertEqual([11], [row["bid"] for row in self.buddy_info()["list"]])

        status, collision = self.clear(
            "metal-stale-ticket-clear", 3000, 11,
            exp=1000, buddies=[11], item_list=self.userdata()["itemList"],
        )
        # Replay keys include the body. A changed body cannot inherit the
        # cached success and instead reaches the now-free-roam phase guard.
        self.assertEqual(
            (409, "tutorial_state_conflict"),
            (status, collision["error"]),
        )

    def test_a_pre_fix_active_ticket_clear_can_recover_once_without_minting(self) -> None:
        """A live active battle predating the spend marker remains settleable."""
        pre_entry = list(self.userdata()["itemList"])
        self.assertEqual(200, self.start_with_ticket("legacy-metal-start", 3000, 11, 4)[0])
        with self.server.state.lock:
            del self.server.state.accounts[self.account_id]["active_hunt_ticket_spent"]
            self.server.state._persist_locked()
        self.restart()
        self.assertIsNone(
            self.server.state.accounts[self.account_id]["active_hunt_ticket_spent"],
        )

        status, cleared = self.clear(
            "legacy-metal-clear", 3000, 11,
            exp=1000, buddies=[11], item_list=pre_entry,
        )
        self.assertEqual(200, status, cleared)
        self.assertEqual(1, self.userdata()["itemList"][4])
        self.assertEqual([11], [row["bid"] for row in self.buddy_info()["list"]])
        self.assertIsNone(
            self.server.state.accounts[self.account_id]["active_hunt_ticket_spent"],
        )

    def test_a_ticket_stage_settles_bounded_companions_into_the_box(self) -> None:
        self.assertEqual([], self.buddy_info()["list"])
        self.assertEqual(200, self.start_with_ticket("metal-start", 3000, 11, 4)[0])
        status, cleared = self.clear("metal-clear", 3000, 11, exp=1000, buddies=[11, 11])
        self.assertEqual(200, status, cleared)
        granted = self.buddy_info()["list"]
        self.assertEqual([11, 11], [row["bid"] for row in granted])
        self.assertEqual([1, 1], [row["lv"] for row in granted])
        # Inventory ids must be unique and must advance the account's counter.
        self.assertEqual(2, len({row["iid"] for row in granted}))
        self.assertEqual(3, self.userdata()["nextCompanionInventoryId"])
        self.assertEqual(granted, cleared["buddyInfo"]["list"])
        self.assertEqual("free_roam", self.phase())

    def test_a_companion_claim_beyond_the_manifest_is_refused(self) -> None:
        self.enable_strict_outcomes()
        for label, kwargs in (
            ("too-many", {"buddies": [11, 11, 11], "exp": 0}),   # manifest allows two
            ("undeclared", {"buddies": [12], "exp": 0}),         # not in the manifest
            ("over-exp", {"buddies": [], "exp": 1001}),          # ceiling is 1000
        ):
            with self.subTest(label):
                self.assertEqual(200, self.start_with_ticket(f"start-{label}", 3000, 11, 4)[0])
                before = self.userdata()
                status, refused = self.clear(f"clear-{label}", 3000, 11, **kwargs)
                self.assertEqual(409, status, refused)
                self.assertEqual("invalid_local_hunting_result", refused["error"])
                self.assertEqual(before, self.userdata(), f"{label} mutated the save")
                self.assertEqual(200, self.clear(f"settle-{label}", 3000, 11)[0])

    def test_each_stage_accepts_only_the_entry_form_the_client_sends_for_it(self) -> None:
        # Metal Zone is the only family that puts the entry pair on the wire.
        status, without = self.start("metal-plain", 3000, 11, 4)
        self.assertEqual((501, "unsupported_hunting_start"), (status, without["error"]))
        status, wrong_item = self.start_with_ticket("metal-wrong", 3000, 11, 4, item_id=6)
        self.assertEqual((501, "unsupported_hunting_start"), (status, wrong_item["error"]))
        status, extra = self.start_with_ticket("pudding-ticket", 1001, 1, 3, item_id=0, item_count=0)
        self.assertEqual(501, status, extra)

    def test_hunting_is_unavailable_without_a_catalog(self) -> None:
        self.stop_server()
        self.catalog = None
        self.server, self.thread = start_server(("127.0.0.1", 0), self.profile, BootstrapState(self.state_path))
        status, refused = self.start("no-catalog", 1001, 1, 3)
        self.assertEqual(501, status, refused)


class BundledHuntingStackCeilingTest(unittest.TestCase):
    """A haul that carries a slot past 999 settles, at the client's ceiling.

    Reported against Puppet Show 20-39 with 47 item chests: the clear was
    refused, the refusal reached the client as an unsigned 409, and the item
    screen looped Network Errors that only a force-close escaped
    ([#57](https://github.com/anzensan/project-liminal-gate/issues/57)).
    """

    PROGRESS = 0x01000000 | (20 << 6) | 1
    #: The ceiling this server used to project against, which the client was
    #: never told and never enforced.
    WITHDRAWN_CEILING = 999
    CHARACTER = {
        "id": 9001, "buddy": 0, "date": 0.0, "jobSlots": [0, 0, 0],
        "jobLevels": [1, 0, 0], "jobID": 0, "flags": 0, "skillBoost": 0,
    }

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.state_path = Path(self.temporary_directory.name) / "state.json"
        state = BootstrapState(self.state_path)
        # One slot within a single Puppet Show haul of the old 999 ceiling.
        items = [0] * ITEM_SLOTS
        items[0] = self.WITHDRAWN_CEILING - 39
        state.create_account("token", "account", {
            "coins": 100, "energy": 40, "freeEnergy": 2, "worldMapNo": 0,
            "progressCode": self.PROGRESS, "chrdata": [self.CHARACTER],
            "itemList": items, "summonList": [0, 0],
        })
        with state.lock:
            account = state.accounts["account"]
            account["tutorial_phase"] = "free_roam"
            account["initial_userdata_served"] = True
            state._persist_locked()
        self.server, self.thread = start_server(
            ("127.0.0.1", 0), bootstrap_profile(), state,
            hunting_catalog=build_bundled_hunting_policy(),
        )
        self.addCleanup(self.temporary_directory.cleanup)
        self.addCleanup(stop_server, self.server, self.thread)

    def userdata(self) -> dict:
        return json.loads(self.state_path.read_text(encoding="utf-8"))["accounts"]["account"]["userdata"]

    def post(self, route: str, request_id: str, fields: list[tuple[str, str]]) -> tuple[int, dict]:
        return post(self.server, route, request_id, urlencode(fields), token="token",
                    headers={"Content-Type": "application/x-www-form-urlencoded"})

    def test_a_haul_that_crosses_the_old_ceiling_settles(self) -> None:
        status, started = self.post("/gd/start_quest", "start", [
            ("stamina", "8"), ("coins", "0"), ("chapter", "1004"),
            ("section", "2"), ("lastUpdate", "1"),
        ])
        self.assertEqual((200, True), (status, started["success"]))
        userdata = self.userdata()
        chests, held = 47, userdata["itemList"][0]
        # What the client reports: its own inventory plus the drops, capped
        # where the client caps it rather than where this server used to.
        submitted = list(userdata["itemList"])
        submitted[0] = min(MAX_ITEM_STACK, held + chests)
        self.assertGreater(submitted[0], self.WITHDRAWN_CEILING,
                           "the case only bites past the old ceiling")
        status, cleared = self.post("/gd/clear_quest", "clear", [
            ("progressCode", str(userdata["progressCode"])), ("worldMapNo", "0"),
            ("valuables", json.dumps({
                "energyAppStore": 0, "energy": userdata["energy"], "energyAndApp": 0,
                "freeEnergy": userdata["freeEnergy"], "energyGooglePlay": 0,
                "coins": userdata["coins"],
            })),
            ("chrdata", json.dumps([self.CHARACTER])),
            ("itemList", json.dumps(submitted)),
            ("summonList", json.dumps(userdata["summonList"])),
            ("battle_result", json.dumps({
                "chapter": 1004, "section": 2, "coins": 0, "exp": 0,
                "items": {"1": chests}, "buddies": [], "monsters": [], "summons": [],
                "luckynum": 0, "unableluckdrop": False, "boostup": [0] * 6,
            })),
            ("itmp0", "0"), ("itmp1", "0"), ("lastUpdate", "1"),
        ])
        self.assertEqual(200, status, cleared)
        self.assertTrue(cleared["success"], cleared)
        self.assertEqual(held + chests, self.userdata()["itemList"][0])
        self.assertEqual("free_roam", json.loads(
            self.state_path.read_text(encoding="utf-8"))["accounts"]["account"]["tutorial_phase"])


class BundledMetalZoneFullBoxTest(unittest.TestCase):
    """A Metal Zone clear settles with a full Companion box, keeping what fits.

    Reported against All Hail The King 30-39
    ([#58](https://github.com/anzensan/project-liminal-gate/issues/58)): the
    screen after the Metal Minions dropped looped Network Errors. A box with no
    room refused the whole won battle, and because a refusal leaves the battle
    open every retry was refused identically.
    """

    PROGRESS = 0x01000000 | (25 << 6) | 1
    CHAPTER, SECTION, STAMINA = 3000, 13, 10   # assumedLevel 30, the client's Lv 30-39
    CHARACTER = {
        "id": 9001, "buddy": 0, "date": 0.0, "jobSlots": [0, 0, 0],
        "jobLevels": [1, 0, 0], "jobID": 0, "flags": 0, "skillBoost": 0,
    }

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.state_path = Path(self.temporary_directory.name) / "state.json"
        state = BootstrapState(self.state_path)
        self.capacity = build_bundled_hunting_policy().max_companions
        box = [{"bid": 128, "lv": 1, "date": 0.0, "iid": iid, "exp": 0, "flag": 0, "chrID": 0}
               for iid in range(1, self.capacity)]   # one free slot, three will drop
        state.create_account("token", "account", {
            "coins": 100, "energy": 40, "freeEnergy": 2, "worldMapNo": 0,
            "progressCode": self.PROGRESS, "chrdata": [self.CHARACTER],
            "itemList": [0] * ITEM_SLOTS, "summonList": [0, 0],
            "buddyInfo": {"list": box, "record": []},
            "nextCompanionInventoryId": self.capacity,
        })
        with state.lock:
            account = state.accounts["account"]
            account["tutorial_phase"] = "free_roam"
            account["initial_userdata_served"] = True
            state._persist_locked()
        self.server, self.thread = start_server(
            ("127.0.0.1", 0), bootstrap_profile(), state,
            hunting_catalog=build_bundled_hunting_policy(),
        )
        self.addCleanup(self.temporary_directory.cleanup)
        self.addCleanup(stop_server, self.server, self.thread)

    def account(self) -> dict:
        return json.loads(self.state_path.read_text(encoding="utf-8"))["accounts"]["account"]

    def post(self, route: str, request_id: str, fields: list[tuple[str, str]]) -> tuple[int, dict]:
        return post(self.server, route, request_id, urlencode(fields), token="token",
                    headers={"Content-Type": "application/x-www-form-urlencoded"})

    def clear(self, request_id: str, buddies: list[int]) -> tuple[int, dict]:
        userdata = self.account()["userdata"]
        return self.post("/gd/clear_quest", request_id, [
            ("progressCode", str(userdata["progressCode"])), ("worldMapNo", "0"),
            ("valuables", json.dumps({
                "energyAppStore": 0, "energy": userdata["energy"], "energyAndApp": 0,
                "freeEnergy": userdata["freeEnergy"], "energyGooglePlay": 0,
                "coins": userdata["coins"],
            })),
            ("chrdata", json.dumps([self.CHARACTER])),
            ("itemList", json.dumps(userdata["itemList"])),
            ("summonList", json.dumps(userdata["summonList"])),
            ("battle_result", json.dumps({
                "chapter": self.CHAPTER, "section": self.SECTION, "coins": 0, "exp": 250_000,
                "items": {}, "buddies": buddies, "monsters": [], "summons": [],
                "luckynum": 0, "unableluckdrop": False, "boostup": [0] * 6,
            })),
            ("itmp0", "0"), ("itmp1", "0"), ("lastUpdate", "1"),
        ])

    def start(self, request_id: str) -> tuple[int, dict]:
        return self.post("/gd/start_quest", request_id, [
            ("stamina", str(self.STAMINA)), ("coins", "0"), ("itemID", "50"), ("itemCount", "1"),
            ("chapter", str(self.CHAPTER)), ("section", str(self.SECTION)), ("lastUpdate", "1"),
        ])

    def test_an_overflowing_drop_settles_and_fills_the_box(self) -> None:
        status, started = self.start("start")
        self.assertEqual((200, True), (status, started["success"]))
        status, cleared = self.clear("clear", [128, 128, 129])
        self.assertEqual(200, status, cleared)
        self.assertEqual(self.capacity, len(cleared["buddyInfo"]["list"]))
        self.assertEqual("free_roam", self.account()["tutorial_phase"])

    def test_a_box_with_no_room_still_settles_the_battle(self) -> None:
        with self.server.state.lock:
            userdata = self.server.state.accounts["account"]["userdata"]
            userdata["buddyInfo"]["list"].append({
                "bid": 128, "lv": 1, "date": 0.0, "iid": self.capacity,
                "exp": 0, "flag": 0, "chrID": 0,
            })
            userdata["nextCompanionInventoryId"] = self.capacity + 1
            self.server.state._persist_locked()
        self.assertEqual(200, self.start("start")[0])
        status, cleared = self.clear("clear", [128, 129])
        self.assertEqual(200, status, cleared)
        self.assertEqual(self.capacity, len(cleared["buddyInfo"]["list"]))
        self.assertEqual("free_roam", self.account()["tutorial_phase"])

    def test_a_companion_the_stage_cannot_author_is_still_refused(self) -> None:
        """A full box does not turn an undeclared drop into an accepted one."""
        self.assertEqual(200, self.start("start")[0])
        status, refused = self.clear("clear", [130])
        self.assertEqual((409, "invalid_local_hunting_result"), (status, refused["error"]))


class RoadSpeciesLimitTest(unittest.TestCase):
    """Dragon and Machine Road admit only the species they declare.

    `BattleData.Section.species` is 128 on 1200-1 and 256 on 1201-1 -- `1 <<
    Dragon` and `1 << Machine` -- and they are the only two sections in the
    game that declare it. The client owns `StartQuestErrorCode.SpeciesLimit`
    but its local start gate never walks the party, so until now any party
    could farm either Road's EXP.
    """

    PROGRESS = 0x01000000 | (9 << 6) | 1
    DRAGON, MACHINE, HUMAN = 82, 91, 1
    #: Outside the recovered species table entirely, as a monster ID is.
    UNDESCRIBED = 999999

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.state_path = Path(self.temporary_directory.name) / "state.json"
        self.addCleanup(self.temporary_directory.cleanup)

    def start(self, chapter: int, party: list[int], request_id: str = "road", tuning=None) -> tuple[int, dict]:
        state = BootstrapState(self.state_path, tuning)
        state.create_account("token", "account", {
            "coins": 100, "energy": 100, "freeEnergy": 2, "worldMapNo": 0,
            "progressCode": self.PROGRESS,
            "chrdata": [{
                "id": self.DRAGON, "buddy": 0, "date": 0.0, "jobSlots": [0, 0, 0],
                "jobLevels": [1, 0, 0], "jobID": 0, "flags": 0, "skillBoost": 0,
            }],
            "itemList": [0] * ITEM_SLOTS, "summonList": [0, 0], "teamMembers": party,
        })
        with state.lock:
            account = state.accounts["account"]
            account["tutorial_phase"] = "free_roam"
            account["initial_userdata_served"] = True
            state._persist_locked()
        server, thread = start_server(
            ("127.0.0.1", 0), bootstrap_profile(), state,
            hunting_catalog=build_bundled_hunting_policy(),
        )
        try:
            return post(
                server, "/gd/start_quest", request_id,
                urlencode([
                    ("stamina", "15"), ("coins", "0"), ("chapter", str(chapter)),
                    ("section", "1"), ("lastUpdate", "1"),
                ]),
                token="token", headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        finally:
            stop_server(server, thread)

    def test_a_party_of_the_wrong_species_is_refused_in_the_clients_own_shape(self) -> None:
        # A refusal, not a transport error: 200 carrying the client's own
        # SpeciesLimit code on `cmdError`, so the game shows its dialog and the
        # screen returns rather than looping a Network Error.
        for chapter, party in ((1200, [self.HUMAN, 0, 0, 0, 0, 0]), (1201, [self.DRAGON, 0, 0, 0, 0, 0])):
            with self.subTest(chapter=chapter):
                status, payload = self.start(chapter, party)
                self.assertEqual(200, status, payload)
                # An endpoint refusal rides `cmdError` on an accepted success;
                # `errorCode` is the transport's own namespace and would show a
                # bare server error instead. See docs/server-protocol.md.
                self.assertEqual(
                    (True, SPECIES_LIMIT_ERROR_CODE),
                    (payload["success"], payload["cmdError"]),
                )

    def test_a_refused_entry_charges_nothing(self) -> None:
        """The gate runs before the debit, so a refusal costs no stamina."""
        self.start(1200, [self.HUMAN, 0, 0, 0, 0, 0])
        account = json.loads(self.state_path.read_text(encoding="utf-8"))["accounts"]["account"]
        self.assertEqual(100, account["userdata"]["energy"])
        self.assertEqual("free_roam", account["tutorial_phase"])
        self.assertIsNone(account.get("active_hunt"))

    def test_the_declared_species_still_enters(self) -> None:
        for chapter, member in ((1200, self.DRAGON), (1201, self.MACHINE)):
            with self.subTest(chapter=chapter):
                status, payload = self.start(chapter, [member, 0, 0, 0, 0, 0])
                self.assertEqual((200, True), (status, payload["success"]))

    def test_one_wrong_member_is_enough_to_refuse(self) -> None:
        status, payload = self.start(1200, [self.DRAGON, self.HUMAN, 0, 0, 0, 0])
        self.assertEqual(SPECIES_LIMIT_ERROR_CODE, payload["cmdError"])

    def test_a_character_the_table_cannot_describe_is_not_refused(self) -> None:
        """The gate restores a declared limit; it does not invent one."""
        status, payload = self.start(1200, [self.DRAGON, self.UNDESCRIBED, 0, 0, 0, 0])
        self.assertEqual((200, True), (status, payload["success"]))

    def test_an_operator_can_decline_the_limit(self) -> None:
        """Enforcing a recovered limit is still a choice about one's own archive.

        Dragon Road spent a long time serving as this game's general-purpose EXP
        route on servers that never asserted its species lock, and an operator
        restoring that deliberately is doing something different from one who
        never knew the limit existed. Off by request only: the default above
        refuses the same party.
        """
        relaxed = replace(DEFAULT_TUNING, gates=replace(DEFAULT_TUNING.gates, species_limits=False))
        status, payload = self.start(1200, [self.HUMAN, 0, 0, 0, 0, 0], tuning=relaxed)
        self.assertEqual((200, True), (status, payload["success"]))
        self.assertNotIn("cmdError", payload)

    def test_every_other_zone_admits_anyone(self) -> None:
        """The Roads are the only stages that declare a species at all."""
        catalog = build_bundled_hunting_policy()
        locked = {
            stage.identity_label() for stage in catalog.stages if stage.species_mask
        }
        self.assertEqual({"1200-1", "1201-1"}, locked)
        for stage in catalog.stages:
            if not stage.species_mask:
                self.assertTrue(stage.admits_species(1), stage.identity_label())
                self.assertFalse(
                    catalog.over_species_limit(stage, [self.HUMAN, 0, 0, 0, 0, 0]),
                    stage.identity_label(),
                )


if __name__ == "__main__":
    unittest.main()
