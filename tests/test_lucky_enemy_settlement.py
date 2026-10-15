"""Issue 100: client-counted Lucky gains persist through both clear handlers."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

from liminal_gate.bootstrap_server import BootstrapState
from liminal_gate.daily_quest_data import build_bundled_daily_quest_stages
from liminal_gate.event_catalog import EventCatalog, EventStage
from liminal_gate.hunting_catalog import HuntingCatalog, BUNDLED_ITEM_SLOTS, BUNDLED_MAX_STACK
from liminal_gate.luck_data import character_luck_cap
from tests.support import bootstrap_profile, post, start_server, stop_server


class LuckyEnemySettlementTest(unittest.TestCase):
    NOW = 17817 * 86400.0  # Recovered daily rotation offers 6010-1.

    def setUp(self) -> None:
        clock = patch("liminal_gate.bootstrap_server.time.time", return_value=self.NOW)
        clock.start()
        self.addCleanup(clock.stop)
        chests = patch("liminal_gate.bootstrap_server.roll_luck_result", return_value=[""] * 6)
        chests.start()
        self.addCleanup(chests.stop)
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.state_path = Path(self.temporary.name) / "state.json"
        self.hunts = HuntingCatalog(build_bundled_daily_quest_stages(), BUNDLED_ITEM_SLOTS, BUNDLED_MAX_STACK)
        self.events = EventCatalog((EventStage("cryptid_forest", "sp_ch_7010", 7010, 1,
                                               1, 0, 0, ()),))
        self.start_server()
        self.addCleanup(self.stop_server)
        self.rows = [
            {"id": cid, "buddy": 0, "date": 0.0, "jobSlots": [0, 0, 0],
             "jobLevels": [1, 0, 0], "jobID": 0, "flags": 0, "skillBoost": 0,
             "luck": character_luck_cap(cid) - 1 if cid == 3 else 10}
            for cid in (1, 2, 3, 4)
        ]
        self.server.state.create_account("token", "account", {
            "coins": 0, "energy": 0, "freeEnergy": 0,
            "progressCode": 0x1000000 | (30 << 6) | 1, "worldMapNo": 0,
            "chrdata": self.rows, "teamMembers": [4, 0, 0, 0, 0, 0, 1, 2, 3, 0, 0, 0],
            "teamNo": 2, "itemList": [0] * BUNDLED_ITEM_SLOTS, "summonList": [],
        })
        account = self.server.state.accounts["account"]
        account["tutorial_phase"] = "free_roam"
        account["initial_userdata_served"] = True
        self.server.state._persist_locked()

    def start_server(self) -> None:
        self.server, self.thread = start_server(
            ("127.0.0.1", 0), bootstrap_profile(), BootstrapState(self.state_path),
            hunting_catalog=self.hunts, event_catalog=self.events, daily_quests=True,
        )

    def stop_server(self) -> None:
        stop_server(self.server, self.thread)

    def restart(self) -> None:
        self.stop_server()
        self.start_server()

    def post(self, route: str, request_id: str, body: str) -> tuple:
        return post(self.server, route, request_id, body,
                    headers={"Content-Type": "application/x-www-form-urlencoded"})

    def account(self) -> dict:
        return json.loads(self.state_path.read_text())["accounts"]["account"]

    def clear_body(self, chapter: int, lucky_num: object, *, reports_luck: bool = False) -> str:
        data = self.account()["userdata"]
        rows = copy.deepcopy(self.rows)
        if reports_luck:
            for row in rows[:3]:
                row["luck"] = min(character_luck_cap(row["id"]), row["luck"] + lucky_num)
        else:
            for row in rows:
                row.pop("luck")  # Character.ToHashTable omits Luck in 5.5.7.
        return urlencode({
            "progressCode": data["progressCode"], "worldMapNo": 0,
            "valuables": json.dumps({"coins": 0, "energy": 0, "freeEnergy": 0,
                                      "energyAppStore": 0, "energyGooglePlay": 0, "energyAndApp": 0}),
            "chrdata": json.dumps(rows), "itemList": json.dumps(data["itemList"]),
            "summonList": "[]",
            "battle_result": json.dumps({"chapter": chapter, "section": 1, "coins": 0,
                "exp": 0, "items": {}, "buddies": [], "monsters": [], "summons": [],
                "luckynum": lucky_num, "unableluckdrop": False, "boostup": [0] * 6}),
            "itmp0": 0, "itmp1": 0, "lastUpdate": 1,
        })

    def exercise(self, chapter: int, lucky_num: int, *, reports_luck: bool = False,
                 released: bool = False) -> None:
        status, started = self.post("/gd/start_quest", "start", urlencode({
            "stamina": 0 if chapter == 6010 else 1, "coins": 0,
            "chapter": chapter, "section": 1, "lastUpdate": 1,
        }))
        self.assertEqual(200, status, started)
        self.assertNotIn("luckUpTable", started, "entry must not invent enemy catches")
        before = self.account()
        for invalid in (-1, True, 1.5):
            status, _ = self.post("/gd/clear_quest", "bad", self.clear_body(chapter, invalid))
            self.assertEqual(501, status)
            self.assertEqual(before, self.account())
        body = self.clear_body(chapter, lucky_num, reports_luck=reports_luck)
        if released:
            rows = [{k: v for k, v in row.items() if k != "luck"} for row in self.rows]
            status, payload = self.post("/gd/userdata", "release", urlencode({
                "chrdata": json.dumps(rows), "lastUpdate": 1}))
            self.assertEqual(200, status, payload)
        self.restart()  # Entry (or its released record) must remain settleable.
        status, cleared = self.post("/gd/clear_quest", "clear", body)
        self.assertEqual(200, status, cleared)
        expected = {row["id"]: min(character_luck_cap(row["id"]), row["luck"] + lucky_num)
                    if row["id"] != 4 else row["luck"] for row in self.rows}
        self.assertEqual(expected, {r["id"]: r["luck"] for r in cleared["chrdata"]})
        settled = self.account()
        self.assertEqual((status, cleared), self.post("/gd/clear_quest", "clear", body))
        self.restart()
        self.assertEqual((status, cleared), self.post("/gd/clear_quest", "clear", body))
        self.assertEqual(settled, self.account())
        self.assertEqual(409, self.post("/gd/clear_quest", "second-clear", body)[0])
        self.assertEqual(settled, self.account())
        rows = [{k: v for k, v in row.items() if k != "luck"} for row in self.rows]
        self.assertEqual(200, self.post("/gd/userdata", "stale", urlencode({
            "chrdata": json.dumps(rows), "lastUpdate": 1}))[0])
        self.assertEqual(expected, {r["id"]: r["luck"] for r in self.account()["userdata"]["chrdata"]})

    def test_lucky_orbling_exact_earned_gain_survives(self) -> None:
        self.exercise(6010, 18)

    def test_the_issue_screenshot_difference_is_preserved(self) -> None:
        # Every result-row Luck is 2.1 above its Party Formation counterpart.
        self.exercise(6010, 21)

    def test_no_orbling_caught_pays_no_enemy_luck(self) -> None:
        self.exercise(6010, 0)

    def test_cryptid_forest_exact_runner_gain_survives(self) -> None:
        self.exercise(7010, 2)

    def test_released_cryptid_battle_still_settles_the_catch(self) -> None:
        self.exercise(7010, 1, released=True)

    def test_reported_luck_does_not_double_the_earned_gain(self) -> None:
        self.exercise(6010, 18, reports_luck=True)
