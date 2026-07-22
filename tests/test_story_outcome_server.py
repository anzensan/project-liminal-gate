from __future__ import annotations

import json
from http.client import HTTPConnection
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.parse import urlencode

from liminal_gate.bootstrap_server import BootstrapServer, BootstrapState, load_profile
from liminal_gate.clear_state_catalog import load_clear_state_catalog
from liminal_gate.story_catalog import load_story_catalog
from liminal_gate.story_outcome_catalog import load_story_outcome_catalog


class StoryOutcomeServerTest(unittest.TestCase):
    def test_persists_catalog_bounded_client_reported_outcome(self) -> None:
        character = {"id": 9001, "buddy": 0, "date": 0.0, "jobSlots": [0, 0, 0], "jobLevels": [1, 0, 0], "jobID": 0, "flags": 0, "skillBoost": 0}
        recruited = {**character, "id": 9002}
        story_document = {"schema_version": 1, "provenance": "user-supplied", "stages": [{"chapter": 2, "section": 2, "stamina": 5, "coins": 0, "clear_progress_code": 10, "clear_coins": 30}]}
        outcome_document = {"schema_version": 1, "provenance": "user-supplied", "character_ids": [9001, 9002], "item_slots": 1, "max_stack": 99, "max_companions": 3, "companion_masters": [{"companion_id": 8001, "drop_level": 2}], "stages": [{"chapter": 2, "section": 2, "item_maxima": {"1": 1}, "character_maxima": {"9001": 1, "9002": 1}, "companion_maxima": {"8001": 1}}]}
        clear_state_document = {"schema_version": 1, "provenance": "user-supplied", "team_slots": 6, "max_skill_boost": 9, "max_skill_boost_per_battle": 2, "characters": [{"character_id": 9001, "duplicate_skill_boost": 3, "jobs": [{"maximum_experience": 10, "level_thresholds": [0, 5, 10]}, {"maximum_experience": 0, "level_thresholds": [0]}, {"maximum_experience": 0, "level_thresholds": [0]}]}, {"character_id": 9002, "duplicate_skill_boost": 0, "jobs": [{"maximum_experience": 10, "level_thresholds": [0, 5, 10]}, {"maximum_experience": 0, "level_thresholds": [0]}, {"maximum_experience": 0, "level_thresholds": [0]}]}]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); story_path, outcome_path, clear_state_path, state_path = root / "story.json", root / "outcome.json", root / "clear-state.json", root / "state.json"
            story_path.write_text(json.dumps(story_document), encoding="utf-8"); outcome_path.write_text(json.dumps(outcome_document), encoding="utf-8"); clear_state_path.write_text(json.dumps(clear_state_document), encoding="utf-8")
            profile = load_profile(Path(__file__).resolve().parents[1] / "profiles" / "legacy-client-bootstrap.json")
            story, outcomes, clear_state = load_story_catalog(story_path), load_story_outcome_catalog(outcome_path), load_clear_state_catalog(clear_state_path)
            def start() -> tuple[BootstrapServer, threading.Thread]:
                server = BootstrapServer(("127.0.0.1", 0), profile, BootstrapState(state_path), story_catalog=story, story_outcome_catalog=outcomes, clear_state_catalog=clear_state)
                thread = threading.Thread(target=server.serve_forever); thread.start(); return server, thread
            def post(server: BootstrapServer, path: str, fields: list[tuple[str, str]]) -> tuple[int, dict[str, object]]:
                connection = HTTPConnection(*server.server_address); connection.request("POST", path, body=urlencode(fields)); response = connection.getresponse(); payload = json.loads(response.read()); connection.close(); return response.status, payload
            server, thread = start()
            try:
                server.state.create_account("token", "account", {"coins": 0, "worldMapNo": 0, "progressCode": 9, "chrdata": [character], "teamMembers": [9001, 0, 0, 0, 0, 0], "itemList": [0], "summonList": [], "buddyInfo": {"list": [], "record": []}})
                with server.state.lock:
                    server.state.accounts["account"]["tutorial_phase"] = "free_roam"; server.state._persist_locked()
                self.assertEqual(200, post(server, "/gd/start_quest?otk=token&requestID=start", [("stamina", "5"), ("coins", "0"), ("chapter", "2"), ("section", "2"), ("lastUpdate", "1")])[0])
                advanced = {**character, "jobLevels": [(8 << 12) | 2, 0, 0], "skillBoost": 4}
                clear = [("progressCode", "10"), ("worldMapNo", "0"), ("valuables", json.dumps({"energyAppStore": 0, "energy": 0, "energyAndApp": 0, "freeEnergy": 0, "energyGooglePlay": 0, "coins": 30})), ("chrdata", json.dumps([advanced, recruited])), ("itemList", "[1]"), ("summonList", "[]"), ("battle_result", json.dumps({"chapter": 2, "section": 2, "coins": 30, "exp": 8, "items": {"1": 1}, "buddies": [8001], "monsters": [9001, 9002], "summons": [], "luckynum": 0, "unableluckdrop": False, "boostup": [1, 0, 0, 0, 0, 0]})), ("itmp0", "0"), ("itmp1", "0"), ("lastUpdate", "1")]
                forged_recruit = {**recruited, "flags": 1}
                forged = list(clear); forged[3] = ("chrdata", json.dumps([advanced, forged_recruit]))
                self.assertEqual((409, "invalid_local_clear_state"), (post(server, "/gd/clear_quest?otk=token&requestID=forged", forged)[0], post(server, "/gd/clear_quest?otk=token&requestID=forged", forged)[1]["error"]))
                rejected = list(clear); rejected[4] = ("itemList", "[2]"); rejected[6] = ("battle_result", json.dumps({"chapter": 2, "section": 2, "coins": 30, "exp": 8, "items": {"1": 2}, "buddies": [8001], "monsters": [9001, 9002], "summons": [], "luckynum": 0, "unableluckdrop": False, "boostup": [1, 0, 0, 0, 0, 0]}))
                self.assertEqual((409, "invalid_local_outcome"), (post(server, "/gd/clear_quest?otk=token&requestID=rejected", rejected)[0], post(server, "/gd/clear_quest?otk=token&requestID=rejected", rejected)[1]["error"]))
                status, payload = post(server, "/gd/clear_quest?otk=token&requestID=clear", clear)
                self.assertEqual(200, status); self.assertEqual((1, 2), (payload["itemList"][0], payload["buddyInfo"]["list"][0]["lv"]))
            finally:
                server.shutdown(); thread.join(); server.server_close()
            restarted, restarted_thread = start()
            try:
                status, replay = post(restarted, "/gd/clear_quest?otk=token&requestID=clear", clear)
                self.assertEqual((200, payload), (status, replay))
            finally:
                restarted.shutdown(); restarted_thread.join(); restarted.server_close()
