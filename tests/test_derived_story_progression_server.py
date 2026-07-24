from __future__ import annotations

import json
from http.client import HTTPConnection
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.parse import urlencode

from liminal_gate.bootstrap_server import BootstrapServer, BootstrapState, load_profile
from liminal_gate.story_progression_catalog import build_core_story_policy, load_story_progression_catalog
from liminal_gate.story_progression_importer import build_story_progression
from liminal_gate.settlement_catalog import load_settlement_catalog
from tests.test_story_progression_importer import _metadata


PUBLIC_ROOT = Path(__file__).resolve().parents[1]


class DerivedStoryProgressionServerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.state_path = self.root / "state.json"
        catalog_path = self.root / "progression.json"
        catalog_path.write_text(json.dumps(build_story_progression(_metadata())), encoding="utf-8")
        self.catalog = load_story_progression_catalog(catalog_path)
        settlement_path = self.root / "settlement.json"
        settlement_path.write_text(json.dumps({
            "schema_version": 1, "provenance": "user-supplied", "character_ids": [9001],
            "item_slots": 1, "summon_slots": 1, "max_stack": 99,
            "stages": [{"chapter": 2, "section": 5, "character_rewards": [], "item_rewards": {}, "summon_rewards": {}, "clear_coins": 7}],
        }), encoding="utf-8")
        self.settlements = load_settlement_catalog(settlement_path)
        self.profile = load_profile(PUBLIC_ROOT / "profiles" / "legacy-client-bootstrap.json")
        self.start_server()
        self.token = "derived-story-token"
        self.account_id = "derived-story-account"
        self.character = {"id": 9001, "buddy": 0, "date": 0.0, "jobSlots": [0, 0, 0], "jobLevels": [1, 0, 0], "jobID": 0, "flags": 0, "skillBoost": 0}
        self.server.state.create_account(self.token, self.account_id, {
            "coins": 0, "worldMapNo": 0, "progressCode": 0x01000085,
            "chrdata": [self.character], "itemList": [0], "summonList": [0],
            "freeEnergy": 50, "energy": 0, "energyAppStore": 0,
            "energyGooglePlay": 0, "energyAndApp": 0,
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
        self.server = BootstrapServer(
            ("127.0.0.1", 0), self.profile, BootstrapState(self.state_path),
            story_progression_catalog=self.catalog, settlement_catalog=self.settlements,
        )
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()

    def stop_server(self) -> None:
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()

    def post(self, path: str, fields: list[tuple[str, str]]) -> tuple[int, dict[str, object]]:
        connection = HTTPConnection(*self.server.server_address)
        connection.request("POST", path, body=urlencode(fields), headers={"Content-Type": "application/x-www-form-urlencoded"})
        response = connection.getresponse()
        payload = json.loads(response.read())
        connection.close()
        return response.status, payload

    def test_chapter_boundary_clear_map_reveal_retry_and_restart(self) -> None:
        start = [("stamina", "5"), ("coins", "0"), ("chapter", "2"), ("section", "5"), ("lastUpdate", "1")]
        start_path = f"/gd/start_quest?otk={self.token}&requestID=start-2-5"
        self.assertEqual(200, self.post(start_path, start)[0])
        self.stop_server()
        self.start_server()
        clear = [
            ("progressCode", str(0x030000C1)), ("worldMapNo", "0"),
            ("valuables", json.dumps({"energyAppStore": 0, "energy": 0, "energyAndApp": 0, "freeEnergy": 0, "energyGooglePlay": 0, "coins": 7})),
            ("chrdata", json.dumps([self.character])), ("itemList", "[0]"), ("summonList", "[0]"),
            ("battle_result", json.dumps({"chapter": 2, "section": 5, "coins": 7, "exp": 0, "items": {}, "buddies": [], "monsters": [], "summons": [], "luckynum": 0, "unableluckdrop": False, "boostup": [0, 0, 0, 0, 0, 0]})),
            ("itmp0", "0"), ("itmp1", "0"), ("lastUpdate", "1"),
        ]
        clear_path = f"/gd/clear_quest?otk={self.token}&requestID=clear-2-5"
        bad_clear = list(clear)
        bad_clear[6] = ("battle_result", json.dumps({"chapter": 2, "section": 5, "coins": 6, "exp": 0, "items": {}, "buddies": [], "monsters": [], "summons": [], "luckynum": 0, "unableluckdrop": False, "boostup": [0, 0, 0, 0, 0, 0]}))
        status, rejected = self.post(clear_path, bad_clear)
        self.assertEqual(409, status)
        self.assertEqual("tutorial_state_conflict", rejected["error"])
        status, cleared = self.post(clear_path, clear)
        self.assertEqual(200, status)
        self.assertEqual(7, cleared["coins"])
        self.assertEqual(200, self.post(clear_path, clear)[0])
        self.stop_server()
        self.start_server()
        reveal = [("progressCode", str(0x010000C1)), ("worldMapNo", "0"), ("lastUpdate", "1")]
        reveal_path = f"/gd/userdata?otk={self.token}&requestID=reveal-3-1"
        status, revealed = self.post(reveal_path, reveal)
        self.assertEqual(200, status)
        self.assertTrue(revealed["success"])
        self.assertEqual(200, self.post(reveal_path, reveal)[0])
        status, collision = self.post(reveal_path, [("progressCode", "0"), ("worldMapNo", "0"), ("lastUpdate", "1")])
        self.assertEqual(409, status)
        self.assertEqual("request_collision", collision["error"])
        status, started = self.post(
            f"/gd/start_quest?otk={self.token}&requestID=start-3-1",
            [("stamina", "5"), ("coins", "0"), ("chapter", "3"), ("section", "1"), ("lastUpdate", "1")],
        )
        self.assertEqual(200, status)
        self.assertTrue(started["success"])
        persisted = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual(0x010000C1, persisted["accounts"][self.account_id]["userdata"]["progressCode"])
        self.assertEqual(7, persisted["accounts"][self.account_id]["userdata"]["coins"])
        self.assertEqual(50, persisted["accounts"][self.account_id]["userdata"]["freeEnergy"])
        self.assertEqual(50, persisted["accounts"][self.account_id]["userdata"]["valuables"]["freeEnergy"])

    def test_built_in_policy_accepts_client_start_values_for_ordinary_stage(self) -> None:
        self.stop_server()
        self.server = BootstrapServer(
            ("127.0.0.1", 0), self.profile, BootstrapState(self.state_path),
            story_progression_catalog=build_core_story_policy(),
        )
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        status, payload = self.post(
            f"/gd/start_quest?otk={self.token}&requestID=policy-start-2-5",
            [("stamina", "17"), ("coins", "42"), ("chapter", "2"), ("section", "5"), ("lastUpdate", "1")],
        )
        self.assertEqual(200, status)
        self.assertTrue(payload["success"])
