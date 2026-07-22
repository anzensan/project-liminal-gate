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
