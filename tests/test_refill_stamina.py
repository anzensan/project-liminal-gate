from __future__ import annotations

import json
from http.client import HTTPConnection
from pathlib import Path
import tempfile
import threading
import unittest

from liminal_gate.bootstrap_server import BootstrapServer, BootstrapState, load_profile


class RefillStaminaTest(unittest.TestCase):
    def test_http_success_errors_collision_and_restart_replay(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = load_profile(Path(__file__).resolve().parents[1] / "profiles" / "legacy-client-bootstrap.json")
            state_path = root / "state.json"
            server = BootstrapServer(("127.0.0.1", 0), profile, BootstrapState(state_path))
            thread = threading.Thread(target=server.serve_forever)
            thread.start()

            def post(active_server: BootstrapServer, request_id: str, body: str) -> tuple[int, dict[str, object]]:
                connection = HTTPConnection(*active_server.server_address)
                connection.request("POST", f"/gd/refill_stamina?otk=token&requestID={request_id}", body=body)
                response = connection.getresponse()
                payload = json.loads(response.read())
                connection.close()
                return response.status, payload

            try:
                server.state.create_account("token", "account", {
                    "refillStartTime": 1.0,
                    "freeEnergy": 1,
                    "energy": 3,
                    "energyAppStore": 4,
                    "energyGooglePlay": 5,
                    "energyAndApp": 6,
                    "bonusStamina": 7,
                })
                status, success = post(server, "one", "cost=1")
                self.assertEqual(200, status)
                self.assertEqual({
                    "success", "refillStartTime", "energy", "energyAppStore", "energyGooglePlay",
                    "energyAndApp", "freeEnergy", "bonusStamina", "digest",
                }, set(success))
                self.assertEqual((True, 0.0, 3, 0, 7), (
                    success["success"], success["refillStartTime"], success["energy"],
                    success["freeEnergy"], success["bonusStamina"],
                ))
                self.assertEqual((status, success), post(server, "one", "cost=1"))
                status, collision = post(server, "one", "cost=2")
                self.assertEqual((409, "request_collision"), (status, collision["error"]))
                status, full = post(server, "two", "cost=1")
                self.assertEqual((200, False, 1), (status, full["success"], full["errorCode"]))
            finally:
                server.shutdown(); thread.join(); server.server_close()

            restarted = BootstrapServer(("127.0.0.1", 0), profile, BootstrapState(state_path))
            restarted_thread = threading.Thread(target=restarted.serve_forever)
            restarted_thread.start()
            try:
                self.assertEqual((200, success), post(restarted, "one", "cost=1"))
                self.assertEqual((200, full), post(restarted, "two", "cost=1"))
                restarted.state.create_account("poor", "poor-account", {"refillStartTime": 1.0})
                connection = HTTPConnection(*restarted.server_address)
                connection.request("POST", "/gd/refill_stamina?otk=poor&requestID=poor-one", body="cost=1")
                response = connection.getresponse()
                poor = json.loads(response.read())
                connection.close()
                self.assertEqual((200, False, 2), (response.status, poor["success"], poor["errorCode"]))
            finally:
                restarted.shutdown(); restarted_thread.join(); restarted.server_close()
