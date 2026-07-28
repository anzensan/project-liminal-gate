from __future__ import annotations

import json
from http.client import HTTPConnection
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.parse import urlencode

from liminal_gate.bootstrap_server import BootstrapServer, BootstrapState, load_profile


class CompanionUserdataTest(unittest.TestCase):
    def test_http_equip_commits_both_links_atomically_and_replays_after_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            profile = load_profile(
                Path(__file__).resolve().parents[1]
                / "profiles"
                / "legacy-client-bootstrap.json"
            )

            def start() -> tuple[BootstrapServer, threading.Thread]:
                server = BootstrapServer(
                    ("127.0.0.1", 0),
                    profile,
                    BootstrapState(state_path),
                )
                thread = threading.Thread(target=server.serve_forever)
                thread.start()
                return server, thread

            def post(
                server: BootstrapServer, request_id: str, body: str,
            ) -> tuple[int, dict[str, object]]:
                connection = HTTPConnection(*server.server_address)
                connection.request(
                    "POST",
                    f"/gd/userdata?otk=token&requestID={request_id}",
                    body=body,
                )
                response = connection.getresponse()
                payload = json.loads(response.read())
                connection.close()
                return response.status, payload

            roster = [
                {"id": 3, "buddy": 1, "jobID": 0, "jobLevels": [10.0]},
                {"id": 25, "buddy": 0, "jobID": 0, "jobLevels": [10.0]},
            ]
            companion = {
                "bid": 1,
                "lv": 1,
                "date": 0.0,
                "iid": 1,
                "exp": 0,
                "flag": 0,
                "chrID": 3,
            }
            moved_roster = [{"id": 3, "buddy": 0}, {"id": 25, "buddy": 1}]

            def equip_body(companion_chr_id: int) -> str:
                moved_companion = {**companion, "chrID": companion_chr_id}
                return urlencode([
                    ("chrdata", json.dumps(moved_roster, separators=(",", ":"))),
                    ("buddyInfo", json.dumps([moved_companion], separators=(",", ":"))),
                    ("lastUpdate", "1"),
                ])

            server, thread = start()
            try:
                server.state.create_account(
                    "token",
                    "account",
                    {
                        "chrdata": roster,
                        "buddyInfo": {"list": [companion], "record": []},
                    },
                )
                with server.state.lock:
                    server.state.accounts["account"]["tutorial_phase"] = "free_roam"
                    server.state._persist_locked()

                before = server.state.userdata_for("token")
                bad_status, bad = post(server, "mismatched-equip", equip_body(3))
                self.assertEqual(
                    (501, "unsupported_companion_userdata"),
                    (bad_status, bad["error"]),
                )
                self.assertEqual(before, server.state.userdata_for("token"))

                one_sided = urlencode([
                    (
                        "buddyInfo",
                        json.dumps(
                            [{**companion, "chrID": 25}],
                            separators=(",", ":"),
                        ),
                    ),
                    ("lastUpdate", "1"),
                ])
                one_status, one = post(server, "one-sided-equip", one_sided)
                self.assertEqual(
                    (501, "unsupported_companion_userdata"),
                    (one_status, one["error"]),
                )
                self.assertEqual(before, server.state.userdata_for("token"))

                status, first = post(server, "move-equip", equip_body(25))
                self.assertEqual((200, True), (status, first["success"]))
                self.assertEqual(
                    (status, first),
                    post(server, "move-equip", equip_body(25)),
                )
                stored = server.state.userdata_for("token")
                assert stored is not None
                self.assertEqual(
                    ([0, 1], 25),
                    (
                        [row["buddy"] for row in stored["chrdata"]],
                        stored["buddyInfo"]["list"][0]["chrID"],
                    ),
                )
            finally:
                server.shutdown()
                thread.join()
                server.server_close()

            restarted, restarted_thread = start()
            try:
                self.assertEqual(
                    (200, first),
                    post(restarted, "move-equip", equip_body(25)),
                )
                stored = restarted.state.userdata_for("token")
                assert stored is not None
                self.assertEqual(
                    ([0, 1], 25),
                    (
                        [row["buddy"] for row in stored["chrdata"]],
                        stored["buddyInfo"]["list"][0]["chrID"],
                    ),
                )
            finally:
                restarted.shutdown()
                restarted_thread.join()
                restarted.server_close()

    def test_http_delta_write_persists_flag_and_replays_after_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = load_profile(Path(__file__).resolve().parents[1] / "profiles" / "legacy-client-bootstrap.json")
            state_path = root / "state.json"

            def start() -> tuple[BootstrapServer, threading.Thread]:
                server = BootstrapServer(("127.0.0.1", 0), profile, BootstrapState(state_path))
                thread = threading.Thread(target=server.serve_forever)
                thread.start()
                return server, thread

            submitted = [{"bid": 1, "lv": 1, "date": 0.0, "iid": 1, "exp": 0, "flag": 1, "chrID": 0}]
            body = urlencode({"buddyInfo": json.dumps(submitted, separators=(",", ":")), "lastUpdate": "1"})

            def post(server: BootstrapServer, request_id: str, value: str) -> tuple[int, dict[str, object]]:
                connection = HTTPConnection(*server.server_address)
                connection.request("POST", f"/gd/userdata?otk=token&requestID={request_id}", body=value)
                response = connection.getresponse()
                result = json.loads(response.read())
                connection.close()
                return response.status, result

            server, thread = start()
            try:
                server.state.create_account("token", "account", {"buddyInfo": {"list": [{"bid": 1, "lv": 1, "date": 0.0, "iid": 1, "exp": 0, "flag": 0, "chrID": 0}], "record": []}})
                status, first = post(server, "one", body)
                self.assertEqual((200, True, 1.0), (status, first["success"], first["lastupdate"]))
                self.assertEqual(1, server.state.userdata_for("token")["buddyInfo"]["list"][0]["flag"])
                self.assertEqual((status, first), post(server, "one", body))
            finally:
                server.shutdown()
                thread.join()
                server.server_close()

            restarted, restarted_thread = start()
            try:
                self.assertEqual((200, first), post(restarted, "one", body))
            finally:
                restarted.shutdown()
                restarted_thread.join()
                restarted.server_close()
