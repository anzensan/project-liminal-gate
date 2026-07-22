from __future__ import annotations

import json
from http.client import HTTPConnection
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.parse import urlencode

from liminal_gate.bootstrap_server import BootstrapServer, BootstrapState, _parse_generic_story_clear, load_profile
from liminal_gate.story_catalog import load_story_catalog


PUBLIC_ROOT = Path(__file__).resolve().parents[1]


class GenericStoryServerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.state_path = self.root / "state.json"
        self.catalog_path = self.root / "story.json"
        self.catalog_path.write_text(json.dumps({
            "schema_version": 1,
            "provenance": "user-supplied",
            "stages": [{
                "chapter": 2, "section": 2, "stamina": 5, "coins": 0,
                "clear_progress_code": 16777347, "clear_coins": 30,
            }],
        }), encoding="utf-8")
        self.profile = load_profile(PUBLIC_ROOT / "profiles" / "legacy-client-bootstrap.json")
        self.catalog = load_story_catalog(self.catalog_path)
        self.start_server()
        self.token = "generic-story-token"
        self.account_id = "generic-story-account"
        self.character = {"id": 9001, "buddy": 0, "date": 0.0, "jobSlots": [0, 0, 0], "jobLevels": [1, 0, 0], "jobID": 0, "flags": 0, "skillBoost": 0}
        self.server.state.create_account(self.token, self.account_id, {"coins": 210, "worldMapNo": 0, "progressCode": 16777346, "chrdata": [self.character], "itemList": [], "summonList": []})
        with self.server.state.lock:
            account = self.server.state.accounts[self.account_id]
            account["tutorial_phase"] = "free_roam"
            account["initial_userdata_served"] = True
            self.server.state._persist_locked()

    def tearDown(self) -> None:
        self.stop_server()
        self.temporary_directory.cleanup()

    def start_server(self) -> None:
        self.server = BootstrapServer(("127.0.0.1", 0), self.profile, BootstrapState(self.state_path), story_catalog=self.catalog)
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

    def test_catalog_declared_story_start_clear_replay_collision_and_restart(self) -> None:
        start = [("stamina", "5"), ("coins", "0"), ("chapter", "2"), ("section", "2"), ("lastUpdate", "1")]
        path = f"/gd/start_quest?otk={self.token}&requestID=start-2-2"
        status, started = self.post(path, start)
        self.assertEqual(200, status)
        self.assertEqual(0.0, started["refillStartTime"])
        status, replay = self.post(path, start)
        self.assertEqual(200, status)
        self.assertEqual(started["refillStartTime"], replay["refillStartTime"])
        status, collision = self.post(path, [("stamina", "0")])
        self.assertEqual(409, status)
        self.assertEqual("request_collision", collision["error"])
        continue_path = f"/gd/continue?otk={self.token}&requestID=continue-2-2"
        status, continued = self.post(continue_path, [("cost", "1")])
        self.assertEqual(200, status)
        self.assertTrue(continued["success"])
        self.assertEqual(0, continued["energy"])
        self.assertEqual(0, continued["freeEnergy"])
        status, continue_replay = self.post(continue_path, [("cost", "1")])
        self.assertEqual(200, status)
        self.assertEqual(continued["energy"], continue_replay["energy"])
        status, continue_collision = self.post(continue_path, [("cost", "0")])
        self.assertEqual(409, status)
        self.assertEqual("request_collision", continue_collision["error"])
        self.stop_server()
        self.start_server()
        clear = [
            ("progressCode", "16777347"), ("worldMapNo", "0"),
            ("valuables", json.dumps({"energyAppStore": 0, "energy": 0, "energyAndApp": 0, "freeEnergy": 0, "energyGooglePlay": 0, "coins": 140})), ("chrdata", json.dumps([self.character])),
            ("itemList", "[]"), ("summonList", "[]"),
            ("battle_result", json.dumps({"chapter": 2, "section": 2, "coins": 30, "exp": 0, "items": {}, "buddies": [], "monsters": [], "summons": [], "luckynum": 0, "unableluckdrop": False, "boostup": [0, 0, 0, 0, 0, 0]})),
            ("itmp0", "0"), ("itmp1", "0"), ("lastUpdate", "1"),
        ]
        clear_path = f"/gd/clear_quest?otk={self.token}&requestID=clear-2-2"
        status, cleared = self.post(clear_path, clear)
        self.assertEqual(200, status)
        self.assertFalse(cleared["sentMessage"])
        self.assertEqual(140, cleared["coins"])
        status, clear_replay = self.post(clear_path, clear)
        self.assertEqual(200, status)
        self.assertEqual(cleared["coins"], clear_replay["coins"])
        persisted = json.loads(self.state_path.read_text(encoding="utf-8"))
        userdata = persisted["accounts"][self.account_id]["userdata"]
        self.assertEqual(16777347, userdata["progressCode"])
        self.assertEqual(140, userdata["coins"])
        self.assertEqual({"energyAppStore": 0, "energy": 0, "energyAndApp": 0, "freeEnergy": 0, "energyGooglePlay": 0, "coins": 140}, userdata["valuables"])
        self.assertEqual("free_roam", persisted["accounts"][self.account_id]["tutorial_phase"])

    def test_rejects_incomplete_or_malformed_client_clear_result(self) -> None:
        fields = [
            ("progressCode", "16777347"), ("worldMapNo", "0"),
            ("valuables", json.dumps({"coins": 30})), ("chrdata", json.dumps([self.character])),
            ("itemList", "[]"), ("summonList", "[]"),
            ("battle_result", json.dumps({"chapter": 2, "section": 2, "coins": 30})),
            ("itmp0", "0"), ("itmp1", "0"), ("lastUpdate", "1"),
        ]
        self.assertIsNone(_parse_generic_story_clear(urlencode(fields).encode("ascii")))
