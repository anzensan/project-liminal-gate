from __future__ import annotations

import json
from http.client import HTTPConnection
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.parse import urlencode

from liminal_gate.bootstrap_server import BootstrapServer, BootstrapState, load_profile
from liminal_gate.story_progression_catalog import build_core_story_policy


PUBLIC_ROOT = Path(__file__).resolve().parents[1]


class BootstrapServerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.root = root
        profile_path = root / "profile.json"
        profile_path.write_text(json.dumps({
            "schema_version": 1,
            "routes": {
                "time": "/local/time",
                "status": "/local/status",
                "signup": "/local/signup",
                "login": "/local/login",
                "userdata": "/local/userdata",
            },
            "response_signing": {
                "algorithm": "md5-uppercase-slice",
                "salt": "user-local-test-value",
                "digest_start": 16,
                "digest_end": 32,
            },
            "account_binding": {
                "signup_response_field": "id",
                "login_query_field": "uuid",
            },
            "responses": {
                "signup": {"success": True, "id": "local-account"},
                "login": {"success": True, "message": "local"},
                "status": {"success": True, "maintenance": False},
            },
            "userdata_seed": {"coins": 0, "progressCode": 1},
        }), encoding="utf-8")
        self.state_path = root / "state.json"
        self.event_log_path = root / "events.jsonl"
        self.server = BootstrapServer(
            ("127.0.0.1", 0),
            load_profile(profile_path),
            BootstrapState(self.state_path),
            self.event_log_path,
        )
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()
        self.temporary_directory.cleanup()

    def request(self, path: str) -> tuple[int, dict[str, object]]:
        connection = HTTPConnection(*self.server.server_address)
        connection.request("GET", path)
        response = connection.getresponse()
        body = json.loads(response.read())
        connection.close()
        return response.status, body

    def test_bootstrap_sequence_persists_account_and_signs_responses(self) -> None:
        status, signup = self.request("/local/time?otk=pre-signup-token")
        self.assertEqual(200, status)
        self.assertEqual(16, len(signup["digest"]))
        status, signup = self.request("/local/signup?uuid=local-account&otk=bootstrap-token")
        self.assertEqual(200, status)
        token = "login-token"
        self.assertEqual(16, len(signup["digest"]))
        for path in ("/local/status",):
            status, response = self.request(f"{path}?otk=bootstrap-token")
            self.assertEqual(200, status)
            self.assertEqual(16, len(response["digest"]))
        status, response = self.request(f"/local/login?otk={token}&uuid=local-account")
        self.assertEqual(200, status)
        self.assertEqual(16, len(response["digest"]))
        status, response = self.request(f"/local/userdata?otk={token}")
        self.assertEqual(200, status)
        self.assertEqual(16, len(response["digest"]))
        self.assertTrue(self.state_path.is_file())
        self.assertEqual(0, json.loads(self.state_path.read_text(encoding="utf-8"))["accounts"]["local-account"]["userdata"]["coins"])

    def test_unknown_account_and_route_fail_explicitly(self) -> None:
        status, response = self.request("/local/userdata?otk=unknown")
        self.assertEqual(401, status)
        self.assertEqual("unknown_local_account", response["error"])
        status, response = self.request("/local/unknown")
        self.assertEqual(501, status)
        self.assertEqual("route_not_implemented", response["error"])
        events = [json.loads(line) for line in self.event_log_path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(
            [
                {"method": "GET", "path": "/local/userdata", "status": 401},
                {"method": "GET", "path": "/local/unknown", "status": 501},
            ],
            [{key: event[key] for key in ("method", "path", "status")} for event in events],
        )
        self.assertNotIn("otk=unknown", self.event_log_path.read_text(encoding="utf-8"))

    def test_serves_derived_local_pact_banner(self) -> None:
        banners = self.root / "public_data" / "banners"
        banners.mkdir(parents=True)
        payload = b"\x89PNG\r\n\x1a\nlocal"
        (banners / "sl_truth_01_en.png").write_bytes(payload)
        server = BootstrapServer(
            ("127.0.0.1", 0), self.server.profile, BootstrapState(self.state_path), public_data_root=self.root / "public_data"
        )
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            connection = HTTPConnection(*server.server_address)
            connection.request("GET", "/public_data/banners/sl_truth_01_en.png")
            response = connection.getresponse()
            body = response.read()
            content_type = response.getheader("Content-Type")
            connection.close()
        finally:
            server.shutdown()
            thread.join()
            server.server_close()
        self.assertEqual(200, response.status)
        self.assertEqual("image/png", content_type)
        self.assertEqual(payload, body)

    def test_account_survives_server_restart(self) -> None:
        _, signup = self.request("/local/signup?uuid=local-account&otk=signup-token")
        self.assertEqual(16, len(signup["digest"]))
        token = "restart-token"
        status, _ = self.request(f"/local/login?otk={token}&uuid=local-account")
        self.assertEqual(200, status)
        restarted = BootstrapServer(
            ("127.0.0.1", 0), self.server.profile, BootstrapState(self.state_path)
        )
        thread = threading.Thread(target=restarted.serve_forever)
        thread.start()
        try:
            connection = HTTPConnection(*restarted.server_address)
            connection.request("GET", f"/local/userdata?otk={token}")
            response = connection.getresponse()
            body = json.loads(response.read())
            connection.close()
        finally:
            restarted.shutdown()
            thread.join()
            restarted.server_close()
        self.assertEqual(200, response.status)
        self.assertEqual(0, body["coins"])
        self.assertEqual({"energyAppStore": 0, "energy": 0, "energyAndApp": 0, "freeEnergy": 0, "energyGooglePlay": 0, "coins": 0}, body["valuables"])

    def test_event_log_records_safe_form_diagnostics_for_rejected_write(self) -> None:
        self.request("/local/signup?uuid=local-account&otk=signup-token")
        self.request("/local/login?uuid=local-account&otk=login-token")
        connection = HTTPConnection(*self.server.server_address)
        connection.request(
            "POST", "/local/userdata?otk=login-token&requestID=map-write",
            body="progressCode=7&worldMapNo=0&lastUpdate=1&username=private",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response = connection.getresponse()
        self.assertEqual(501, response.status)
        response.read()
        connection.close()
        event = json.loads(self.event_log_path.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual("unsupported_userdata_write", event["error"])
        self.assertEqual(["progressCode", "worldMapNo", "lastUpdate", "username"], event["request_fields"])
        self.assertEqual({"progressCode": "7", "worldMapNo": "0", "lastUpdate": "1"}, event["request_values"])
        self.assertEqual("local-account", event["resolved_account_id"])
        self.assertEqual("initial", event["resolved_account_phase"])
        self.assertEqual("local-account", event["active_account_id"])
        self.assertEqual("initial", event["active_account_phase"])
        self.assertTrue(event["resolved_account_is_active"])
        self.assertNotIn("private", self.event_log_path.read_text(encoding="utf-8"))


class IncludedBootstrapProfileTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.state_path = root / "state.json"
        self.profile_path = PUBLIC_ROOT / "profiles" / "legacy-client-bootstrap.json"
        self.server = BootstrapServer(
            ("127.0.0.1", 0),
            load_profile(self.profile_path),
            BootstrapState(self.state_path),
        )
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()
        self.temporary_directory.cleanup()

    def request(self, path: str) -> tuple[int, dict[str, object]]:
        connection = HTTPConnection(*self.server.server_address)
        connection.request("GET", path)
        response = connection.getresponse()
        body = json.loads(response.read())
        connection.close()
        return response.status, body

    def post(self, path: str, body: str) -> tuple[int, dict[str, object]]:
        connection = HTTPConnection(*self.server.server_address)
        connection.request(
            "POST", path, body=body.encode("utf-8"), headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        response = connection.getresponse()
        payload = json.loads(response.read())
        connection.close()
        return response.status, payload

    def restart(self) -> None:
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()
        self.server = BootstrapServer(
            ("127.0.0.1", 0), load_profile(self.profile_path), BootstrapState(self.state_path)
        )
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()

    def test_profile_persists_the_declared_account_flow_and_rejects_later_routes(self) -> None:
        token = "0123456789ABCDEF"
        status, time_payload = self.request(f"/gd/get_current_time?otk={token}&digest2=client-value&requestID=request-id")
        self.assertEqual(200, status)
        self.assertTrue(time_payload["success"])
        self.assertIsInstance(time_payload["timestamp"], float)
        self.assertEqual(16, len(time_payload["digest"]))
        status, status_payload = self.request(
            f"/gd/get_server_status?platform=GooglePlay&app_version=5.57&otk={token}&digest2=client-value&requestID=request-id"
        )
        self.assertEqual(200, status)
        self.assertEqual({"success", "digest"}, set(status_payload))
        self.assertTrue(status_payload["success"])
        self.assertEqual(16, len(status_payload["digest"]))
        account_id = "0123456789ABCDEF0123456789ABCDEF"
        status, signup_payload = self.request(
            f"/gd/signup?uuid={account_id}&token=&platform=GooglePlay&app_version=5.57&otk={token}&digest2=client-value&requestID=signup-request"
        )
        self.assertEqual(200, status)
        self.assertEqual(account_id, signup_payload["id"])
        self.assertEqual(16, len(signup_payload["digest"]))
        status, duplicate_signup = self.request(
            f"/gd/signup?uuid={account_id}&token=&platform=GooglePlay&app_version=5.57&otk={token}&digest2=client-value&requestID=signup-request"
        )
        self.assertEqual(200, status)
        self.assertEqual(account_id, duplicate_signup["id"])
        login_token = "FEDCBA9876543210"
        status, login_payload = self.request(
            f"/gd/login?uuid={account_id}&platform=GooglePlay&app_version=5.57&app_version_verify=client-value&titlelogin=True&otk={login_token}&digest2=client-value&requestID=login-request"
        )
        self.assertEqual(200, status)
        self.assertEqual(account_id, login_payload["id"])
        self.assertEqual("Player", login_payload["name"])
        self.assertEqual(0.0, login_payload["weeklyChallenge"]["startDate"])
        status, multiplay = self.request(f"/gd/multiplay_enable?otk={login_token}&digest2=client-value&requestID=multiplay-enable")
        self.assertEqual(200, status)
        self.assertEqual({"success": True, "enable": False, "enablemain": False}, {key: multiplay[key] for key in ("success", "enable", "enablemain")})
        status, special_event = self.request(f"/gd/get_special_event_param?otk={login_token}&digest2=client-value&requestID=special-event")
        self.assertEqual(200, status)
        self.assertEqual({"success", "digest"}, set(special_event))
        grace_body = "kind=10&count=1&luckType=false&campaignChrID=0&eventFlag=0&lastUpdate=1"
        status, early_grace = self.post(
            f"/gd/do_slot?otk={login_token}&digest2=client-value&requestID=early-grace", grace_body
        )
        self.assertEqual(409, status)
        self.assertEqual("tutorial_state_conflict", early_grace["error"])
        self.restart()
        status, userdata_payload = self.request(f"/gd/userdata?otk={login_token}&digest2=client-value&requestID=userdata-request")
        self.assertEqual(200, status)
        self.assertEqual([], userdata_payload["chrdata"])
        self.assertEqual([], userdata_payload["teamMembers"])
        self.assertEqual(1.0, userdata_payload["lastupdate"])
        status, after_close = self.request(f"/gd/userdata_after_close?otk={login_token}&digest2=client-value&requestID=after-close")
        self.assertEqual(200, status)
        self.assertEqual({key: userdata_payload[key] for key in userdata_payload if key != "digest"}, {key: after_close[key] for key in after_close if key != "digest"})
        persisted = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual(1, len(persisted["accounts"]))
        status, grace_payload = self.post(
            f"/gd/do_slot?otk={login_token}&digest2=client-value&requestID=grace-request", grace_body
        )
        self.assertEqual(200, status)
        self.assertEqual(3, grace_payload["chrdata"][0]["id"])
        status, grace_replay = self.post(
            f"/gd/do_slot?otk={login_token}&digest2=retry-value&requestID=grace-request", grace_body
        )
        self.assertEqual(200, status)
        self.assertEqual(grace_payload["chrdata"], grace_replay["chrdata"])
        status, collision = self.post(
            f"/gd/do_slot?otk={login_token}&digest2=client-value&requestID=grace-request",
            "kind=11&count=1&luckType=false&campaignChrID=0&eventFlag=0&lastUpdate=1",
        )
        self.assertEqual(409, status)
        self.assertEqual("request_collision", collision["error"])
        self.restart()
        amisandra_body = "kind=11&count=1&luckType=false&campaignChrID=0&eventFlag=0&lastUpdate=1"
        status, amisandra_payload = self.post(
            f"/gd/do_slot?otk={login_token}&digest2=client-value&requestID=amisandra-request", amisandra_body
        )
        self.assertEqual(200, status)
        self.assertEqual(25, amisandra_payload["chrdata"][0]["id"])
        self.assertEqual(15, amisandra_payload["chrdata"][0]["levelAdded"])
        write_body = urlencode([tuple(field) for field in self.server.profile.tutorial_writes[0]["fields"]])
        status, write_payload = self.post(
            f"/gd/userdata?otk={login_token}&digest2=client-value&requestID=tutorial-write", write_body
        )
        self.assertEqual(200, status)
        self.assertEqual(1.0, write_payload["lastupdate"])
        status, write_replay = self.post(
            f"/gd/userdata?otk={login_token}&digest2=retry-value&requestID=tutorial-write", write_body
        )
        self.assertEqual(200, status)
        self.assertEqual(write_payload["lastupdate"], write_replay["lastupdate"])
        status, write_collision = self.post(
            f"/gd/userdata?otk={login_token}&digest2=client-value&requestID=tutorial-write", "progressCode=0"
        )
        self.assertEqual(409, status)
        self.assertEqual("request_collision", write_collision["error"])
        map_body = urlencode([tuple(field) for field in self.server.profile.tutorial_writes[1]["fields"]])
        status, reordered_map = self.post(
            f"/gd/userdata?otk={login_token}&requestID=reordered-map",
            "worldMapNo=0&progressCode=16777281&lastUpdate=1",
        )
        self.assertEqual(501, status)
        self.assertEqual("unsupported_userdata_write", reordered_map["error"])
        self.server.story_progression_catalog = build_core_story_policy()
        status, map_payload = self.post(
            f"/gd/userdata?otk={login_token}&digest2=client-value&requestID=map-write", map_body
        )
        self.assertEqual(200, status)
        self.assertEqual(1.0, map_payload["lastupdate"])
        self.restart()
        status, final_userdata = self.request(f"/gd/userdata?otk={login_token}&digest2=client-value&requestID=final-userdata")
        self.assertEqual(200, status)
        self.assertEqual([3, 25, 0, 0, 0, 0], final_userdata["teamMembers"])
        self.assertEqual([3, 25], [entry["id"] for entry in final_userdata["chrdata"]])
        self.assertEqual(16777281, final_userdata["progressCode"])
        status, map_replay = self.post(
            f"/gd/userdata?otk={login_token}&digest2=retry-value&requestID=map-write", map_body
        )
        self.assertEqual(200, status)
        self.assertEqual(map_payload["lastupdate"], map_replay["lastupdate"])
        start_body = self.server.profile.story_starts[0]["body"]
        status, start_payload = self.post(
            f"/gd/start_quest?otk={login_token}&digest2=client-value&requestID=chapter1-start", start_body
        )
        self.assertEqual(200, status)
        self.assertEqual({"success", "refillStartTime", "digest"}, set(start_payload))
        self.assertTrue(start_payload["success"])
        self.assertEqual(0.0, start_payload["refillStartTime"])
        status, start_collision = self.post(
            f"/gd/start_quest?otk={login_token}&requestID=chapter1-start", "stamina=0"
        )
        self.assertEqual(409, status)
        self.assertEqual("request_collision", start_collision["error"])
        self.restart()
        status, start_replay = self.post(
            f"/gd/start_quest?otk={login_token}&digest2=retry-value&requestID=chapter1-start", start_body
        )
        self.assertEqual(200, status)
        self.assertEqual(start_payload["refillStartTime"], start_replay["refillStartTime"])
        clear_fields = {
            "progressCode": "16777282",
            "worldMapNo": "0",
            "valuables": json.dumps({"coins": 30}),
            "chrdata": json.dumps([]),
            "itemList": json.dumps([]),
            "summonList": json.dumps([]),
            "battle_result": json.dumps({"chapter": 1, "section": 1, "coins": 30, "exp": 720}),
            "itmp0": "0",
            "itmp1": "0",
            "lastUpdate": "1",
        }
        clear_body = urlencode(clear_fields)
        status, clear_payload = self.post(
            f"/gd/clear_quest?otk={login_token}&digest2=client-value&requestID=chapter1-clear", clear_body
        )
        self.assertEqual(200, status)
        self.assertEqual({"success", "lastupdate", "digest"}, set(clear_payload))
        self.assertEqual(1.0, clear_payload["lastupdate"])
        status, clear_collision = self.post(
            f"/gd/clear_quest?otk={login_token}&requestID=chapter1-clear", "progressCode=0"
        )
        self.assertEqual(409, status)
        self.assertEqual("request_collision", clear_collision["error"])
        self.restart()
        status, clear_replay = self.post(
            f"/gd/clear_quest?otk={login_token}&digest2=retry-value&requestID=chapter1-clear", clear_body
        )
        self.assertEqual(200, status)
        self.assertEqual(clear_payload["lastupdate"], clear_replay["lastupdate"])
        status, repeated_clear = self.post(
            f"/gd/clear_quest?otk={login_token}&requestID=chapter1-clear-new", clear_body
        )
        self.assertEqual(409, status)
        self.assertEqual("tutorial_state_conflict", repeated_clear["error"])
        status, unknown_clear = self.post(
            f"/gd/clear_quest?otk={login_token}&requestID=unknown-clear", "progressCode=0"
        )
        self.assertEqual(501, status)
        self.assertEqual("unsupported_clear_quest", unknown_clear["error"])
        status, final_userdata = self.request(f"/gd/userdata?otk={login_token}&requestID=after-clear")
        self.assertEqual(200, status)
        self.assertEqual(16777282, final_userdata["progressCode"])
        self.assertEqual(30, final_userdata["coins"])
        knight_body = "kind=12&count=1&luckType=false&campaignChrID=0&eventFlag=0&lastUpdate=1"
        status, knight_payload = self.post(
            f"/gd/do_slot?otk={login_token}&digest2=client-value&requestID=knight-grant", knight_body
        )
        self.assertEqual(200, status)
        self.assertEqual(64, knight_payload["chrdata"][0]["id"])
        self.assertEqual(10, knight_payload["chrdata"][0]["levelAdded"])
        status, knight_collision = self.post(
            f"/gd/do_slot?otk={login_token}&requestID=knight-grant", grace_body
        )
        self.assertEqual(409, status)
        self.assertEqual("request_collision", knight_collision["error"])
        self.restart()
        status, knight_replay = self.post(
            f"/gd/do_slot?otk={login_token}&digest2=retry-value&requestID=knight-grant", knight_body
        )
        self.assertEqual(200, status)
        self.assertEqual(knight_payload["chrdata"], knight_replay["chrdata"])
        status, after_knight = self.request(f"/gd/userdata?otk={login_token}&requestID=after-knight")
        self.assertEqual(200, status)
        self.assertEqual([3, 25, 64], [entry["id"] for entry in after_knight["chrdata"]])
        knight_write_body = urlencode([
            ("chrdata", json.dumps([{"id": 64, "jobID": 0, "jobLevels": [10.0, 0.0, 0.0]}])),
            ("lastUpdate", "1"),
        ])
        status, knight_write = self.post(
            f"/gd/userdata?otk={login_token}&digest2=client-value&requestID=knight-write", knight_write_body
        )
        self.assertEqual(200, status)
        self.assertEqual(1.0, knight_write["lastupdate"])
        self.restart()
        status, knight_write_replay = self.post(
            f"/gd/userdata?otk={login_token}&digest2=retry-value&requestID=knight-write", knight_write_body
        )
        self.assertEqual(200, status)
        self.assertEqual(knight_write["lastupdate"], knight_write_replay["lastupdate"])
        status, knight_write_collision = self.post(
            f"/gd/userdata?otk={login_token}&requestID=knight-write", "chrdata=%5B%5D&lastUpdate=1"
        )
        self.assertEqual(409, status)
        self.assertEqual("request_collision", knight_write_collision["error"])
        status, repeated_knight_write = self.post(
            f"/gd/userdata?otk={login_token}&requestID=knight-write-new", knight_write_body
        )
        self.assertEqual(409, status)
        self.assertEqual("tutorial_state_conflict", repeated_knight_write["error"])
        knight_party_body = urlencode([
            ("chrdata", json.dumps([{"id": 64, "flags": 1}])),
            ("teamMembers", json.dumps([3, 25, 64, 0, 0, 0])),
            ("teamMembers_VS", json.dumps([0] * 18)),
            ("teamBuddies_VS", json.dumps([0] * 18)),
            ("teamNo", "1"),
            ("teamNo_VS", "1"),
            ("summonId", "1"),
            ("lastUpdate", "1"),
        ])
        status, knight_party = self.post(
            f"/gd/userdata?otk={login_token}&digest2=client-value&requestID=knight-party", knight_party_body
        )
        self.assertEqual(200, status)
        self.assertEqual(1.0, knight_party["lastupdate"])
        self.restart()
        status, knight_party_replay = self.post(
            f"/gd/userdata?otk={login_token}&digest2=retry-value&requestID=knight-party", knight_party_body
        )
        self.assertEqual(200, status)
        self.assertEqual(knight_party["lastupdate"], knight_party_replay["lastupdate"])
        status, after_party = self.request(f"/gd/userdata?otk={login_token}&requestID=after-party")
        self.assertEqual(200, status)
        self.assertEqual([3, 25, 64, 0, 0, 0], after_party["teamMembers"])
        chapter1_2_body = "stamina=1&coins=0&chapter=1&section=2&lastUpdate=1"
        status, chapter1_2 = self.post(
            f"/gd/start_quest?otk={login_token}&digest2=client-value&requestID=chapter1-2-start", chapter1_2_body
        )
        self.assertEqual(200, status)
        self.assertEqual(0.0, chapter1_2["refillStartTime"])
        self.restart()
        status, chapter1_2_replay = self.post(
            f"/gd/start_quest?otk={login_token}&digest2=retry-value&requestID=chapter1-2-start", chapter1_2_body
        )
        self.assertEqual(200, status)
        self.assertEqual(chapter1_2["refillStartTime"], chapter1_2_replay["refillStartTime"])
        chapter1_2_clear_body = urlencode({
            "progressCode": "16777283", "worldMapNo": "0", "valuables": json.dumps({"coins": 50}),
            "chrdata": json.dumps([]), "itemList": json.dumps([]), "summonList": json.dumps([]),
            "battle_result": json.dumps({"chapter": 1, "section": 2, "coins": 50, "exp": 1224}),
            "itmp0": "0", "itmp1": "0", "lastUpdate": "1",
        })
        status, chapter1_2_clear = self.post(
            f"/gd/clear_quest?otk={login_token}&digest2=client-value&requestID=chapter1-2-clear", chapter1_2_clear_body
        )
        self.assertEqual(200, status)
        self.assertFalse(chapter1_2_clear["sentMessage"])
        self.assertEqual([3, 25, 64, 63], [row["id"] for row in chapter1_2_clear["chrdata"]])
        self.restart()
        status, chapter1_2_clear_replay = self.post(
            f"/gd/clear_quest?otk={login_token}&digest2=retry-value&requestID=chapter1-2-clear", chapter1_2_clear_body
        )
        self.assertEqual(200, status)
        self.assertEqual(chapter1_2_clear["chrdata"], chapter1_2_clear_replay["chrdata"])
        warrior_party_body = urlencode([
            ("chrdata", json.dumps([{"id": 63, "flags": 1}])),
            ("teamMembers", json.dumps([3, 25, 64, 63, 0, 0])),
            ("teamMembers_VS", json.dumps([0] * 18)),
            ("teamBuddies_VS", json.dumps([0] * 18)),
            ("teamNo", "1"), ("teamNo_VS", "1"), ("summonId", "1"), ("lastUpdate", "1"),
        ])
        status, warrior_party = self.post(
            f"/gd/userdata?otk={login_token}&digest2=client-value&requestID=warrior-party", warrior_party_body
        )
        self.assertEqual(200, status)
        self.restart()
        status, warrior_party_replay = self.post(
            f"/gd/userdata?otk={login_token}&digest2=retry-value&requestID=warrior-party", warrior_party_body
        )
        self.assertEqual(200, status)
        self.assertEqual(warrior_party["lastupdate"], warrior_party_replay["lastupdate"])
        status, after_warrior_party = self.request(f"/gd/userdata?otk={login_token}&requestID=after-warrior-party")
        self.assertEqual(200, status)
        self.assertEqual([3, 25, 64, 63, 0, 0], after_warrior_party["teamMembers"])
        chapter1_3_body = "stamina=1&coins=0&chapter=1&section=3&lastUpdate=1"
        status, chapter1_3 = self.post(
            f"/gd/start_quest?otk={login_token}&digest2=client-value&requestID=chapter1-3-start", chapter1_3_body
        )
        self.assertEqual(200, status)
        self.assertEqual(0.0, chapter1_3["refillStartTime"])
        self.restart()
        status, chapter1_3_replay = self.post(
            f"/gd/start_quest?otk={login_token}&digest2=retry-value&requestID=chapter1-3-start", chapter1_3_body
        )
        self.assertEqual(200, status)
        self.assertEqual(chapter1_3["refillStartTime"], chapter1_3_replay["refillStartTime"])
        chapter1_3_clear_body = urlencode({
            "progressCode": "16777284", "worldMapNo": "0", "valuables": json.dumps({"coins": 90}),
            "chrdata": json.dumps([]), "itemList": json.dumps([]), "summonList": json.dumps([]),
            "battle_result": json.dumps({"chapter": 1, "section": 3, "coins": 40, "exp": 960}),
            "itmp0": "0", "itmp1": "0", "lastUpdate": "1",
        })
        status, chapter1_3_clear = self.post(
            f"/gd/clear_quest?otk={login_token}&digest2=client-value&requestID=chapter1-3-clear", chapter1_3_clear_body
        )
        self.assertEqual(200, status)
        self.assertFalse(chapter1_3_clear["sentMessage"])
        self.restart()
        status, chapter1_3_clear_replay = self.post(
            f"/gd/clear_quest?otk={login_token}&digest2=retry-value&requestID=chapter1-3-clear", chapter1_3_clear_body
        )
        self.assertEqual(200, status)
        self.assertEqual(chapter1_3_clear["lastupdate"], chapter1_3_clear_replay["lastupdate"])
        chapter1_4_body = "stamina=1&coins=0&chapter=1&section=4&lastUpdate=1"
        status, chapter1_4 = self.post(
            f"/gd/start_quest?otk={login_token}&digest2=client-value&requestID=chapter1-4-start", chapter1_4_body
        )
        self.assertEqual(200, status)
        self.assertEqual(0.0, chapter1_4["refillStartTime"])
        self.restart()
        status, chapter1_4_replay = self.post(
            f"/gd/start_quest?otk={login_token}&digest2=retry-value&requestID=chapter1-4-start", chapter1_4_body
        )
        self.assertEqual(200, status)
        self.assertEqual(chapter1_4["refillStartTime"], chapter1_4_replay["refillStartTime"])
        chapter1_4_clear_body = urlencode({
            "progressCode": "16777285", "worldMapNo": "0", "valuables": json.dumps({"coins": 140}),
            "chrdata": json.dumps([]), "itemList": json.dumps([]), "summonList": json.dumps([]),
            "battle_result": json.dumps({"chapter": 1, "section": 4, "coins": 50}),
            "itmp0": "0", "itmp1": "0", "lastUpdate": "1",
        })
        status, chapter1_4_clear = self.post(
            f"/gd/clear_quest?otk={login_token}&digest2=client-value&requestID=chapter1-4-clear", chapter1_4_clear_body
        )
        self.assertEqual(200, status)
        self.assertFalse(chapter1_4_clear["sentMessage"])
        self.restart()
        status, chapter1_4_clear_replay = self.post(
            f"/gd/clear_quest?otk={login_token}&digest2=retry-value&requestID=chapter1-4-clear", chapter1_4_clear_body
        )
        self.assertEqual(200, status)
        self.assertEqual(chapter1_4_clear["lastupdate"], chapter1_4_clear_replay["lastupdate"])
        chapter1_5_body = "stamina=1&coins=0&chapter=1&section=5&lastUpdate=1"
        status, chapter1_5 = self.post(
            f"/gd/start_quest?otk={login_token}&digest2=client-value&requestID=chapter1-5-start", chapter1_5_body
        )
        self.assertEqual(200, status)
        chapter1_5_clear_body = urlencode({
            "progressCode": "50331777", "worldMapNo": "0", "valuables": json.dumps({"coins": 218}),
            "chrdata": json.dumps([]), "itemList": json.dumps([]), "summonList": json.dumps([]),
            "battle_result": json.dumps({"chapter": 1, "section": 5, "coins": 78}),
            "itmp0": "0", "itmp1": "0", "lastUpdate": "1",
        })
        status, chapter1_5_clear = self.post(
            f"/gd/clear_quest?otk={login_token}&digest2=client-value&requestID=chapter1-5-clear", chapter1_5_clear_body
        )
        self.assertEqual(200, status)
        self.assertFalse(chapter1_5_clear["sentMessage"])
        self.restart()
        status, chapter1_5_clear_replay = self.post(
            f"/gd/clear_quest?otk={login_token}&digest2=retry-value&requestID=chapter1-5-clear", chapter1_5_clear_body
        )
        self.assertEqual(200, status)
        self.assertEqual(chapter1_5_clear["lastupdate"], chapter1_5_clear_replay["lastupdate"])
        final_map_body = "progressCode=16777345&worldMapNo=0&lastUpdate=1"
        status, final_map = self.post(
            f"/gd/userdata?otk={login_token}&digest2=client-value&requestID=final-map", final_map_body
        )
        self.assertEqual(200, status)
        self.assertEqual(1.0, final_map["lastupdate"])
        self.restart()
        status, final_map_replay = self.post(
            f"/gd/userdata?otk={login_token}&digest2=retry-value&requestID=final-map", final_map_body
        )
        self.assertEqual(200, status)
        self.assertEqual(final_map["lastupdate"], final_map_replay["lastupdate"])
        status, free_roam_userdata = self.request(f"/gd/userdata?otk={login_token}&requestID=free-roam-userdata")
        self.assertEqual(200, status)
        self.assertEqual(16777345, free_roam_userdata["progressCode"])
        post_tutorial_team_body = urlencode({
            "teamMembers": json.dumps([3, 25, 64, 63, 0, 0] * 12, separators=(",", ":")),
            "teamMembers_VS": json.dumps([0] * 18, separators=(",", ":")),
            "teamBuddies_VS": json.dumps([0] * 18, separators=(",", ":")),
            "teamNo": "1", "teamNo_VS": "1", "summonId": "1", "lastUpdate": "1",
        })
        status, team_write = self.post(
            f"/gd/userdata?otk={login_token}&digest2=client-value&requestID=post-tutorial-team",
            post_tutorial_team_body,
        )
        self.assertEqual(200, status)
        self.assertEqual(1.0, team_write["lastupdate"])
        self.restart()
        status, team_write_replay = self.post(
            f"/gd/userdata?otk={login_token}&digest2=retry-value&requestID=post-tutorial-team",
            post_tutorial_team_body,
        )
        self.assertEqual(200, status)
        self.assertEqual(team_write["lastupdate"], team_write_replay["lastupdate"])
        chapter2_1_body = "stamina=5&coins=0&chapter=2&section=1&lastUpdate=1"
        status, chapter2_1 = self.post(
            f"/gd/start_quest?otk={login_token}&digest2=client-value&requestID=chapter2-1-start", chapter2_1_body
        )
        self.assertEqual(200, status)
        self.assertEqual(0.0, chapter2_1["refillStartTime"])
        self.restart()
        status, chapter2_1_replay = self.post(
            f"/gd/start_quest?otk={login_token}&digest2=retry-value&requestID=chapter2-1-start", chapter2_1_body
        )
        self.assertEqual(200, status)
        self.assertEqual(chapter2_1["refillStartTime"], chapter2_1_replay["refillStartTime"])
        chapter2_1_clear_body = urlencode({
            "progressCode": "16777346", "worldMapNo": "0", "valuables": json.dumps({"energyAppStore": 0, "energy": 0, "energyAndApp": 0, "freeEnergy": 0, "energyGooglePlay": 0, "coins": 210}),
            "chrdata": json.dumps([]), "itemList": json.dumps([]), "summonList": json.dumps([]),
            "battle_result": json.dumps({"chapter": 2, "section": 1, "coins": 210, "exp": 3340}),
            "itmp0": "0", "itmp1": "0", "lastUpdate": "1",
        })
        status, chapter2_1_clear = self.post(
            f"/gd/clear_quest?otk={login_token}&digest2=client-value&requestID=chapter2-1-clear", chapter2_1_clear_body
        )
        self.assertEqual(200, status)
        self.assertFalse(chapter2_1_clear["sentMessage"])
        self.restart()
        status, chapter2_1_clear_replay = self.post(
            f"/gd/clear_quest?otk={login_token}&digest2=retry-value&requestID=chapter2-1-clear", chapter2_1_clear_body
        )
        self.assertEqual(200, status)
        self.assertEqual(chapter2_1_clear["lastupdate"], chapter2_1_clear_replay["lastupdate"])
        status, after_chapter2_1 = self.request(f"/gd/userdata?otk={login_token}&requestID=after-chapter2-1")
        self.assertEqual(200, status)
        self.assertEqual(16777346, after_chapter2_1["progressCode"])
        self.assertEqual(210, after_chapter2_1["coins"])
        self.assertEqual({"energyAppStore": 0, "energy": 0, "energyAndApp": 0, "freeEnergy": 0, "energyGooglePlay": 0, "coins": 210}, after_chapter2_1["valuables"])
        status, repeated_knight = self.post(
            f"/gd/do_slot?otk={login_token}&requestID=knight-grant-new", knight_body
        )
        self.assertEqual(409, status)
        self.assertEqual("tutorial_state_conflict", repeated_knight["error"])
        status, repeated_start = self.post(
            f"/gd/start_quest?otk={login_token}&requestID=chapter1-start-new", start_body
        )
        self.assertEqual(409, status)
        self.assertEqual("tutorial_state_conflict", repeated_start["error"])
        status, unknown_start = self.post(
            f"/gd/start_quest?otk={login_token}&requestID=unknown-start", "stamina=0"
        )
        self.assertEqual(501, status)
        self.assertEqual("unsupported_start_quest", unknown_start["error"])
        status, userdata_payload = self.post(
            f"/gd/userdata?otk={login_token}&requestID=unsupported-userdata", "progressCode=0"
        )
        self.assertEqual(501, status)
        self.assertEqual("unsupported_userdata_write", userdata_payload["error"])
        status, payload = self.post(f"/gd/do_slot?otk={login_token}&requestID=unsupported", "kind=0")
        self.assertEqual(501, status)
        self.assertEqual("unsupported_summon", payload["error"])

    def test_mutation_binds_rotated_token_to_active_account_durably(self) -> None:
        signup_token = "0123456789ABCDEF"
        account_id = "0123456789ABCDEF0123456789ABCDEF"
        status, _ = self.request(
            f"/gd/signup?uuid={account_id}&token=&platform=GooglePlay&app_version=5.57"
            f"&otk={signup_token}&digest2=client-value&requestID=signup-request"
        )
        self.assertEqual(200, status)
        rotated_token = "E3ACCAAA6A4BAC90"
        body = "kind=10&count=1&luckType=false&campaignChrID=0&eventFlag=0&lastUpdate=1"
        status, payload = self.post(
            f"/gd/do_slot?otk={rotated_token}&digest2=client-value&requestID=rotated-token-request", body
        )
        self.assertEqual(409, status)
        self.assertEqual("tutorial_state_conflict", payload["error"])
        self.assertEqual(account_id, self.server.state.tokens[rotated_token])
        self.restart()
        status, payload = self.post(
            f"/gd/do_slot?otk={rotated_token}&digest2=retry-value&requestID=rotated-token-request", body
        )
        self.assertEqual(409, status)
        self.assertEqual("tutorial_state_conflict", payload["error"])
        self.server.state.create_account("second-token", "second-local-account", self.server.profile.userdata_seed)
        self.assertTrue(self.server.state.bind_rotated_token(rotated_token))
        self.assertEqual("second-local-account", self.server.state.tokens[rotated_token])
        status, payload = self.post(
            "/gd/do_slot?otk=unbound-token&digest2=client-value&requestID=ambiguous-token-request", body
        )
        self.assertEqual(409, status)
        self.assertEqual("tutorial_state_conflict", payload["error"])
        self.assertEqual("second-local-account", self.server.state.tokens["unbound-token"])
        self.restart()
        status, payload = self.post(
            "/gd/do_slot?otk=unbound-token&digest2=retry-value&requestID=ambiguous-token-request", body
        )
        self.assertEqual(409, status)
        self.assertEqual("tutorial_state_conflict", payload["error"])

    def test_legacy_multi_account_state_keeps_unbound_rotated_token_unauthorized(self) -> None:
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()
        self.state_path.write_text(json.dumps({
            "accounts": {
                "first": {"userdata": {}},
                "second": {"userdata": {}},
            },
            "tokens": {},
        }), encoding="utf-8")
        state = BootstrapState(self.state_path)
        self.assertFalse(state.bind_rotated_token("unbound-token"))

    def test_user_data_binds_rotated_token_to_active_account_durably(self) -> None:
        signup_token = "0123456789ABCDEF"
        account_id = "0123456789ABCDEF0123456789ABCDEF"
        status, _ = self.request(
            f"/gd/signup?uuid={account_id}&token=&platform=GooglePlay&app_version=5.57"
            f"&otk={signup_token}&digest2=client-value&requestID=signup-request"
        )
        self.assertEqual(200, status)
        login_token = "FEDCBA9876543210"
        status, _ = self.request(
            f"/gd/login?uuid={account_id}&platform=GooglePlay&app_version=5.57"
            f"&app_version_verify=client-value&titlelogin=True&otk={login_token}"
            "&digest2=client-value&requestID=login-request"
        )
        self.assertEqual(200, status)
        rotated_token = "E3ACCAAA6A4BAC90"
        status, payload = self.request(
            f"/gd/userdata?otk={rotated_token}&digest2=client-value&requestID=rotated-userdata"
        )
        self.assertEqual(200, status)
        self.assertTrue(payload["success"])
        self.assertEqual(account_id, self.server.state.tokens[rotated_token])
        self.restart()
        status, payload = self.request(
            f"/gd/userdata?otk={rotated_token}&digest2=retry-value&requestID=rotated-userdata"
        )
        self.assertEqual(200, status)
        self.assertTrue(payload["success"])
        self.server.state.create_account("second-token", "second-local-account", self.server.profile.userdata_seed)
        status, payload = self.request(
            "/gd/userdata?otk=unbound-token&digest2=client-value&requestID=ambiguous-userdata"
        )
        self.assertEqual(200, status)
        self.assertTrue(payload["success"])
        self.assertEqual("second-local-account", self.server.state.tokens["unbound-token"])

    def test_local_news_page_and_favicon_are_not_protocol_errors(self) -> None:
        connection = HTTPConnection(*self.server.server_address)
        connection.request("GET", "/en/news/app")
        response = connection.getresponse()
        page = response.read().decode("utf-8")
        self.assertEqual(200, response.status)
        self.assertEqual("text/html; charset=utf-8", response.getheader("Content-Type"))
        self.assertIn("Project Liminal Gate", page)
        connection.close()
        connection = HTTPConnection(*self.server.server_address)
        connection.request("GET", "/favicon.ico")
        response = connection.getresponse()
        self.assertEqual(204, response.status)
        self.assertEqual(0, len(response.read()))
        connection.close()
