from __future__ import annotations

import json
from http.client import HTTPConnection
from pathlib import Path
import tempfile
import threading
import time
import unittest

from liminal_gate.bootstrap_server import BootstrapServer, BootstrapState, load_profile


class UnlockMetalZoneTest(unittest.TestCase):
    def test_empty_body_unlock_replay_collision_and_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = load_profile(Path(__file__).resolve().parents[1] / "profiles" / "legacy-client-bootstrap.json")
            state_path = root / "state.json"

            def start() -> tuple[BootstrapServer, threading.Thread]:
                server = BootstrapServer(("127.0.0.1", 0), profile, BootstrapState(state_path))
                thread = threading.Thread(target=server.serve_forever)
                thread.start()
                return server, thread

            def post(server: BootstrapServer, request_id: str, body: bytes) -> tuple[int, dict[str, object]]:
                connection = HTTPConnection(*server.server_address)
                connection.request("POST", f"/gd/unlock_metal_zone?otk=token&requestID={request_id}", body=body)
                response = connection.getresponse()
                payload = json.loads(response.read())
                connection.close()
                return response.status, payload

            server, thread = start()
            try:
                server.state.create_account("token", "account", {"freeEnergy": 1, "energy": 3, "energyAppStore": 4, "energyGooglePlay": 5, "energyAndApp": 6})
                before = int(time.time())
                status, success = post(server, "one", b"")
                self.assertEqual(200, status)
                self.assertEqual({"success", "metalZoneUnlockTime", "energy", "energyAppStore", "energyGooglePlay", "energyAndApp", "freeEnergy", "digest"}, set(success))
                self.assertTrue(success["success"])
                self.assertGreaterEqual(success["metalZoneUnlockTime"], before + 3600)
                self.assertEqual((3, 0), (success["energy"], success["freeEnergy"]))
                self.assertEqual((status, success), post(server, "one", b""))
                # A body reusing a spent requestID gets exactly the answer it
                # would under a fresh one: the requestID no longer decides it.
                status, reused = post(server, "one", b"unexpected")
                self.assertEqual((501, "unsupported_unlock_metal_zone"), (status, reused["error"]))
                self.assertEqual((status, reused), post(server, "malformed", b"unexpected"))
            finally:
                server.shutdown(); thread.join(); server.server_close()

            restarted, thread = start()
            try:
                self.assertEqual((200, success), post(restarted, "one", b""))
                restarted.state.create_account(
                    "poor",
                    "poor-account",
                    {},
                    client_host="127.0.0.1",
                )
                connection = HTTPConnection(*restarted.server_address)
                connection.request("POST", "/gd/unlock_metal_zone?otk=poor&requestID=poor-one", body=b"")
                response = connection.getresponse()
                poor = json.loads(response.read())
                connection.close()
                self.assertEqual((200, True, 2), (response.status, poor["success"], poor["cmdError"]))
            finally:
                restarted.shutdown(); thread.join(); restarted.server_close()
