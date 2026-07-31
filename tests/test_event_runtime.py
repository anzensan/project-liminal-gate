import json
from http.client import HTTPConnection
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.parse import urlencode

from liminal_gate.bootstrap_server import BootstrapServer, BootstrapState, load_profile
from liminal_gate.event_catalog import (
    EventCatalog,
    EventStage,
    build_bundled_counter_descent_policy,
)
from liminal_gate.hunting_catalog import build_bundled_hunting_policy


def character(character_id: int) -> dict[str, object]:
    return {"id": character_id, "buddy": 0, "date": 0.0, "jobSlots": [0, 0, 0], "jobLevels": [1, 0, 0], "jobID": 0, "flags": 0, "skillBoost": 0}


class EventRuntimeTest(unittest.TestCase):
    def test_event_start_is_accepted_over_real_http_transport(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"; token = "token"; state = BootstrapState(path)
            state.create_account(token, "account", {"coins": 0, "energy": 100, "freeEnergy": 0, "progressCode": 16777473, "worldMapNo": 0, "chrdata": [character(3)], "itemList": [], "summonList": []})
            state.accounts["account"]["tutorial_phase"] = "free_roam"; state._persist_locked()
            catalog = EventCatalog((EventStage("test", "sp_test", 2000, 1, 15, 0, 0, (25,)),))
            profile = load_profile(Path(__file__).resolve().parents[1] / "profiles" / "legacy-client-bootstrap.json")
            server = BootstrapServer(
                ("127.0.0.1", 0),
                profile,
                state,
                event_catalog=catalog,
                hunting_catalog=build_bundled_hunting_policy(),
            )
            thread = threading.Thread(target=server.serve_forever); thread.start()
            try:
                connection = HTTPConnection(*server.server_address)
                connection.request("GET", f"/gd/get_server_status?otk={token}")
                status_response = connection.getresponse()
                status_payload = json.loads(status_response.read())
                connection.close()
                connection = HTTPConnection(*server.server_address)
                body = b"stamina=15&coins=0&chapter=2000&section=1&lastUpdate=1"
                connection.request("POST", f"/gd/start_quest?otk={token}&requestID=event-start", body=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
                response = connection.getresponse(); payload = json.loads(response.read()); connection.close()
                connection = HTTPConnection(*server.server_address)
                collision_body = b"stamina=14&coins=0&chapter=2000&section=1&lastUpdate=1"
                connection.request("POST", f"/gd/start_quest?otk={token}&requestID=event-start", body=collision_body, headers={"Content-Type": "application/x-www-form-urlencoded"})
                collision = connection.getresponse(); collision_payload = json.loads(collision.read()); connection.close()
                connection = HTTPConnection(*server.server_address)
                connection.request("POST", f"/gd/start_quest?otk={token}&requestID=event-reenter", body=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
                reenter = connection.getresponse(); reenter_payload = json.loads(reenter.read()); connection.close()
            finally:
                server.shutdown(); thread.join(); server.server_close()
            self.assertEqual(200, response.status)
            self.assertTrue(payload["success"])
            # Replay is body scoped: the same request ID with a different,
            # invalid entry is evaluated and refused on its own merits.
            self.assertEqual(
                (501, "unsupported_start_quest"),
                (collision.status, collision_payload["error"]),
            )
            # Entry debits the stamina meter, so the fill origin moves off zero.
            self.assertGreater(payload["refillStartTime"], 0.0)
            # Entry moved the stamina meter, so the Energy wallet is intact.
            self.assertEqual(
                100,
                server.state.accounts["account"]["userdata"]["energy"],
            )
            self.assertEqual(200, reenter.status)
            self.assertEqual(payload, reenter_payload)
            self.assertEqual(200, status_response.status)
            self.assertEqual(
                ["2000-1", "3003-1"],
                status_payload["constants"]["specialQuestList"],
            )

    def test_event_clear_grants_character_over_real_http_transport(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"; token = "token"; state = BootstrapState(path)
            state.create_account(token, "account", {"coins": 0, "energy": 100, "freeEnergy": 0, "progressCode": 16777346, "worldMapNo": 0, "chrdata": [character(3)], "itemList": [], "summonList": []})
            state.accounts["account"]["tutorial_phase"] = "free_roam"; state._persist_locked()
            catalog = EventCatalog((EventStage("test", "sp_test", 2000, 1, 15, 0, 0, (25,)),))
            profile = load_profile(Path(__file__).resolve().parents[1] / "profiles" / "legacy-client-bootstrap.json")
            server = BootstrapServer(("127.0.0.1", 0), profile, state, event_catalog=catalog)
            thread = threading.Thread(target=server.serve_forever); thread.start()
            start = b"stamina=15&coins=0&chapter=2000&section=1&lastUpdate=1"
            clear = urlencode({"progressCode": 16777346, "worldMapNo": 0, "valuables": json.dumps({"energyAppStore": 0, "energy": 0, "energyAndApp": 0, "freeEnergy": 0, "energyGooglePlay": 0, "coins": 0}), "chrdata": json.dumps([character(3)]), "itemList": "[]", "summonList": "[]", "battle_result": json.dumps({"coins": 0, "buddies": [], "items": {}, "exp": 0, "section": 1, "monsters": [], "summons": [], "luckynum": 0, "chapter": 2000, "unableluckdrop": False, "boostup": [0] * 6}), "itmp0": 0, "itmp1": 0, "lastUpdate": 1}).encode()
            try:
                connection = HTTPConnection(*server.server_address)
                connection.request("POST", f"/gd/start_quest?otk={token}&requestID=event-start", body=start, headers={"Content-Type": "application/x-www-form-urlencoded"})
                self.assertEqual(200, connection.getresponse().status); connection.close()
                connection = HTTPConnection(*server.server_address)
                connection.request("POST", f"/gd/clear_quest?otk={token}&requestID=event-clear", body=clear, headers={"Content-Type": "application/x-www-form-urlencoded"})
                response = connection.getresponse(); payload = json.loads(response.read()); connection.close()
                connection = HTTPConnection(*server.server_address)
                connection.request("GET", f"/gd/userdata?otk={token}")
                userdata_response = connection.getresponse(); userdata = json.loads(userdata_response.read()); connection.close()
            finally:
                server.shutdown(); thread.join(); server.server_close()
            self.assertEqual(200, response.status)
            self.assertEqual([3, 25], [row["id"] for row in payload["chrdata"]])
            self.assertEqual(200, userdata_response.status)
            granted = next(row for row in userdata["chrdata"] if row["id"] == 25)
            self.assertEqual([1.0], granted["jobLevels"])

    def test_party_save_after_interrupted_event_returns_account_to_free_roam(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"; token = "token"; state = BootstrapState(path)
            state.create_account(token, "account", {"coins": 0, "energy": 100, "freeEnergy": 0, "progressCode": 77, "worldMapNo": 0, "chrdata": [character(3)], "itemList": [], "summonList": []})
            state.accounts["account"]["tutorial_phase"] = "free_roam"; state._persist_locked()
            catalog = EventCatalog((EventStage("test", "sp_test", 2000, 1, 15, 0, 0, (25,)),))
            profile = load_profile(Path(__file__).resolve().parents[1] / "profiles" / "legacy-client-bootstrap.json")
            server = BootstrapServer(("127.0.0.1", 0), profile, state, event_catalog=catalog)
            thread = threading.Thread(target=server.serve_forever); thread.start()
            start = b"stamina=15&coins=0&chapter=2000&section=1&lastUpdate=1"
            party = urlencode({
                "chrdata": json.dumps([character(3)]), "teamMembers": json.dumps([3, 0, 0, 0, 0, 0]),
                "teamMembers_VS": json.dumps([0] * 18), "teamBuddies_VS": json.dumps([0] * 18),
                "teamNo": "1", "teamNo_VS": "1", "summonId": "1", "lastUpdate": "1",
            }).encode()
            try:
                connection = HTTPConnection(*server.server_address)
                connection.request("POST", f"/gd/start_quest?otk={token}&requestID=event-start", body=start, headers={"Content-Type": "application/x-www-form-urlencoded"})
                self.assertEqual(200, connection.getresponse().status); connection.close()
                connection = HTTPConnection(*server.server_address)
                connection.request("POST", f"/gd/userdata?otk={token}&requestID=decline-resume", body=party, headers={"Content-Type": "application/x-www-form-urlencoded"})
                response = connection.getresponse(); payload = json.loads(response.read()); connection.close()
            finally:
                server.shutdown(); thread.join(); server.server_close()
            self.assertEqual(200, response.status)
            self.assertTrue(payload["success"])
            self.assertEqual("free_roam", state.accounts["account"]["tutorial_phase"])
            self.assertIsNone(state.accounts["account"]["active_generic_story"])

    def test_event_clear_grants_character_once_and_replays_after_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"; token = "token"; state = BootstrapState(path)
            state.create_account(token, "account", {"coins": 0, "energy": 100, "freeEnergy": 0, "progressCode": 77, "worldMapNo": 0, "chrdata": [character(3)], "itemList": [], "summonList": []})
            state.accounts["account"]["tutorial_phase"] = "free_roam"; state._persist_locked()
            catalog = EventCatalog((EventStage("test", "sp_test", 2000, 1, 1, 0, 0, (25,)),))
            start = b"stamina=1&coins=0&chapter=2000&section=1&lastUpdate=1"
            self.assertEqual("success", state.apply_generic_story_start(token, "start", start, catalog)[0])
            clear = urlencode({"progressCode": 77, "worldMapNo": 0, "valuables": json.dumps({"energyAppStore":0,"energy":0,"energyAndApp":0,"freeEnergy":0,"energyGooglePlay":0,"coins":0}), "chrdata": json.dumps([character(3)]), "itemList":"[]", "summonList":"[]", "battle_result":json.dumps({"coins":0,"buddies":[],"items":{},"exp":0,"section":1,"monsters":[],"summons":[],"luckynum":0,"chapter":2000,"unableluckdrop":False,"boostup":[0]*6}), "itmp0":0,"itmp1":0,"lastUpdate":1}).encode()
            self.assertEqual("success", state.apply_generic_story_clear(token, "clear", clear, catalog)[0])
            state.close()
            restarted = BootstrapState(path)
            try:
                replay = restarted.apply_generic_story_clear(token, "clear", clear, catalog)
                self.assertEqual("replay", replay[0]); self.assertEqual([3, 25], [row["id"] for row in restarted.accounts["account"]["userdata"]["chrdata"]])
            finally:
                restarted.close()


class CounterDescentRuntimeTest(unittest.TestCase):
    """The standard Strikes Back slice uses the real HTTP and durable path."""

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.state_path = Path(self.temporary_directory.name) / "state.json"
        self.profile = load_profile(
            Path(__file__).resolve().parents[1]
            / "profiles"
            / "legacy-client-bootstrap.json"
        )
        self.catalog = build_bundled_counter_descent_policy()
        self.token, self.account_id = "descent-token", "descent-account"
        state = BootstrapState(self.state_path)
        state.create_account(
            self.token,
            self.account_id,
            {
                "coins": 0,
                "energy": 20,
                "freeEnergy": 2,
                "progressCode": 0x01000000 | (7 << 6) | 1,
                "worldMapNo": 0,
                "chrdata": [character(3)],
                "itemList": [0, 0],
                "summonList": [0, 0],
            },
        )
        state.accounts[self.account_id]["tutorial_phase"] = "free_roam"
        state._persist_locked()
        state.close()
        self.start_server()

    def tearDown(self) -> None:
        self.stop_server()
        self.temporary_directory.cleanup()

    def start_server(self) -> None:
        self.server = BootstrapServer(
            ("127.0.0.1", 0),
            self.profile,
            BootstrapState(self.state_path),
            event_catalog=self.catalog,
        )
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()

    def stop_server(self) -> None:
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()

    def restart(self) -> None:
        self.stop_server()
        self.start_server()

    def get(self, path: str) -> tuple[int, dict]:
        connection = HTTPConnection(*self.server.server_address)
        connection.request("GET", path)
        response = connection.getresponse()
        payload = json.loads(response.read())
        connection.close()
        return response.status, payload

    def post(self, path: str, body: bytes) -> tuple[int, dict]:
        connection = HTTPConnection(*self.server.server_address)
        connection.request(
            "POST",
            path,
            body=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response = connection.getresponse()
        payload = json.loads(response.read())
        connection.close()
        return response.status, payload

    def account(self) -> dict:
        return json.loads(self.state_path.read_text(encoding="utf-8"))[
            "accounts"
        ][self.account_id]

    def clear_body(self, *, experience: int = 0) -> bytes:
        userdata = self.account()["userdata"]
        return urlencode({
            "progressCode": userdata["progressCode"],
            "worldMapNo": userdata["worldMapNo"],
            "valuables": json.dumps({
                "energyAppStore": 0,
                "energy": userdata["energy"],
                "energyAndApp": 0,
                "freeEnergy": userdata["freeEnergy"],
                "energyGooglePlay": 0,
                "coins": userdata["coins"],
            }),
            "chrdata": json.dumps(userdata["chrdata"]),
            "itemList": json.dumps(userdata["itemList"]),
            "summonList": json.dumps(userdata["summonList"]),
            "battle_result": json.dumps({
                "coins": 0,
                "buddies": [],
                "items": {},
                "exp": experience,
                "section": 5,
                "monsters": [],
                "summons": [],
                "luckynum": 0,
                "chapter": 8000,
                "unableluckdrop": False,
                "boostup": [0] * 6,
            }),
            "itmp0": 0,
            "itmp1": 0,
            "lastUpdate": 1,
        }).encode()

    def test_visibility_charge_zero_base_clear_and_restart_replay(self) -> None:
        status, server_status = self.get(
            f"/gd/get_server_status?otk={self.token}&requestID=status"
        )
        self.assertEqual(200, status)
        constants = server_status["constants"]
        self.assertEqual(["8000-1", "8001-1"], constants["descentHuntingList"])
        self.assertEqual(["3003-1"], constants["specialQuestList"])
        status, login = self.get(
            f"/gd/login?otk={self.token}&uuid={self.account_id}&requestID=login"
        )
        self.assertEqual(200, status)
        self.assertEqual(
            ["sp_ch_8000", "sp_ch_8001"],
            sorted(login["eventFlags"]),
        )

        locked = b"stamina=5&coins=0&chapter=8002&section=1&lastUpdate=1"
        status, refused = self.post(
            f"/gd/start_quest?otk={self.token}&requestID=locked",
            locked,
        )
        self.assertEqual((409, "event_stage_locked"), (status, refused["error"]))
        wrong = b"stamina=5&coins=0&chapter=8000&section=5&lastUpdate=1"
        self.assertEqual(
            501,
            self.post(
                f"/gd/start_quest?otk={self.token}&requestID=wrong",
                wrong,
            )[0],
        )

        start = b"stamina=15&coins=0&chapter=8000&section=5&lastUpdate=1"
        status, started = self.post(
            f"/gd/start_quest?otk={self.token}&requestID=start",
            start,
        )
        self.assertEqual((200, True), (status, started["success"]))
        # Entry debits the stamina meter, never the Energy wallet.
        self.assertEqual((20, 2), (
            self.account()["userdata"]["energy"],
            self.account()["userdata"]["freeEnergy"],
        ))
        self.assertGreater(self.account()["userdata"]["refillStartTime"], 0.0)
        # A different request id for the same active stage is an accepted retry,
        # but it cannot debit the entry a second time.
        self.assertEqual(
            200,
            self.post(
                f"/gd/start_quest?otk={self.token}&requestID=start-again",
                start,
            )[0],
        )
        self.assertEqual(20, self.account()["userdata"]["energy"])

        self.restart()
        status, refused = self.post(
            f"/gd/clear_quest?otk={self.token}&requestID=bad-clear",
            self.clear_body(experience=1),
        )
        self.assertEqual(
            (409, "invalid_local_event_result"),
            (status, refused["error"]),
        )
        self.assertEqual("generic_story_active", self.account()["tutorial_phase"])

        clear = self.clear_body()
        status, cleared = self.post(
            f"/gd/clear_quest?otk={self.token}&requestID=clear",
            clear,
        )
        self.assertEqual(200, status, cleared)
        self.assertEqual("free_roam", self.account()["tutorial_phase"])
        self.assertEqual(0x01000000 | (7 << 6) | 1, self.account()["userdata"]["progressCode"])
        self.restart()
        self.assertEqual(
            (status, cleared),
            self.post(
                f"/gd/clear_quest?otk={self.token}&requestID=clear",
                clear,
            ),
        )
