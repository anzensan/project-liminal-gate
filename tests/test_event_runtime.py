import json
from http.client import HTTPConnection
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.parse import urlencode

from liminal_gate.bootstrap_server import BootstrapServer, BootstrapState, load_profile
from liminal_gate.event_catalog import EventCatalog, EventStage


def character(character_id: int) -> dict[str, object]:
    return {"id": character_id, "buddy": 0, "date": 0.0, "jobSlots": [0, 0, 0], "jobLevels": [1, 0, 0], "jobID": 0, "flags": 0, "skillBoost": 0}


class EventRuntimeTest(unittest.TestCase):
    def test_event_start_is_accepted_over_real_http_transport(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"; token = "token"; state = BootstrapState(path)
            state.create_account(token, "account", {"coins": 0, "progressCode": 77, "worldMapNo": 0, "chrdata": [character(3)], "itemList": [], "summonList": []})
            state.accounts["account"]["tutorial_phase"] = "free_roam"; state._persist_locked()
            catalog = EventCatalog((EventStage("test", "sp_test", 2000, 1, 15, 0, 0, (25,)),))
            profile = load_profile(Path(__file__).resolve().parents[1] / "profiles" / "legacy-client-bootstrap.json")
            server = BootstrapServer(("127.0.0.1", 0), profile, state, event_catalog=catalog)
            thread = threading.Thread(target=server.serve_forever); thread.start()
            try:
                connection = HTTPConnection(*server.server_address)
                body = b"stamina=15&coins=0&chapter=2000&section=1&lastUpdate=1"
                connection.request("POST", f"/gd/start_quest?otk={token}&requestID=event-start", body=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
                response = connection.getresponse(); payload = json.loads(response.read()); connection.close()
            finally:
                server.shutdown(); thread.join(); server.server_close()
            self.assertEqual(200, response.status)
            self.assertTrue(payload["success"])
            self.assertEqual(0.0, payload["refillStartTime"])

    def test_event_clear_grants_character_once_and_replays_after_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"; token = "token"; state = BootstrapState(path)
            state.create_account(token, "account", {"coins": 0, "progressCode": 77, "worldMapNo": 0, "chrdata": [character(3)], "itemList": [], "summonList": []})
            state.accounts["account"]["tutorial_phase"] = "free_roam"; state._persist_locked()
            catalog = EventCatalog((EventStage("test", "sp_test", 2000, 1, 1, 0, 0, (25,)),))
            start = b"stamina=1&coins=0&chapter=2000&section=1&lastUpdate=1"
            self.assertEqual("success", state.apply_generic_story_start(token, "start", start, catalog)[0])
            clear = urlencode({"progressCode": 77, "worldMapNo": 0, "valuables": json.dumps({"energyAppStore":0,"energy":0,"energyAndApp":0,"freeEnergy":0,"energyGooglePlay":0,"coins":0}), "chrdata": json.dumps([character(3)]), "itemList":"[]", "summonList":"[]", "battle_result":json.dumps({"coins":0,"buddies":[],"items":{},"exp":0,"section":1,"monsters":[],"summons":[],"luckynum":0,"chapter":2000,"unableluckdrop":False,"boostup":[0]*6}), "itmp0":0,"itmp1":0,"lastUpdate":1}).encode()
            self.assertEqual("success", state.apply_generic_story_clear(token, "clear", clear, catalog)[0])
            restarted = BootstrapState(path)
            replay = restarted.apply_generic_story_clear(token, "clear", clear, catalog)
            self.assertEqual("replay", replay[0]); self.assertEqual([3, 25], [row["id"] for row in restarted.accounts["account"]["userdata"]["chrdata"]])
