from __future__ import annotations

from pathlib import Path
import tempfile
import time
import unittest

from liminal_gate.bootstrap_server import BootstrapState
from tests.support import bootstrap_profile, post, start_server, stop_server


class RefillStaminaTest(unittest.TestCase):
    def test_http_success_errors_collision_and_restart_replay(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = bootstrap_profile()
            state_path = root / "state.json"
            server, thread = start_server(
                ("127.0.0.1", 0), profile, BootstrapState(state_path), stamina=True,
            )

            try:
                # An origin at "now" is a meter that has refilled nothing yet,
                # which is the only state a refill is for.  A fixed early origin
                # would instead read as a bar that filled to its maximum years
                # ago; see `stamina_meter.current_stamina`.
                server.state.create_account("token", "account", {
                    "refillStartTime": time.time(),
                    "freeEnergy": 1,
                    "energy": 3,
                    "energyAppStore": 4,
                    "energyGooglePlay": 5,
                    "energyAndApp": 6,
                    "bonusStamina": 7,
                })
                status, success = post(server, "/gd/refill_stamina", "one", "cost=1")
                self.assertEqual(200, status)
                self.assertEqual({
                    "success", "refillStartTime", "energy", "energyAppStore", "energyGooglePlay",
                    "energyAndApp", "freeEnergy", "bonusStamina", "digest",
                }, set(success))
                self.assertEqual((True, 0.0, 3, 0, 7), (
                    success["success"], success["refillStartTime"], success["energy"],
                    success["freeEnergy"], success["bonusStamina"],
                ))
                self.assertEqual((status, success), post(server, "/gd/refill_stamina", "one", "cost=1"))
                # Reusing a spent requestID with a different body is no longer
                # read as a tampered retry; this cost is simply unsupported.
                status, reused = post(server, "/gd/refill_stamina", "one", "cost=2")
                self.assertEqual((501, "unsupported_refill_stamina"), (status, reused["error"]))
                status, full = post(server, "/gd/refill_stamina", "two", "cost=1")
                self.assertEqual((200, True, 1), (status, full["success"], full["cmdError"]))
            finally:
                stop_server(server, thread)

            restarted, restarted_thread = start_server(
                ("127.0.0.1", 0), profile, BootstrapState(state_path), stamina=True,
            )
            try:
                self.assertEqual((200, success), post(restarted, "/gd/refill_stamina", "one", "cost=1"))
                self.assertEqual((200, full), post(restarted, "/gd/refill_stamina", "two", "cost=1"))
                restarted.state.create_account(
                    "poor",
                    "poor-account",
                    {"refillStartTime": time.time()},
                    client_host="127.0.0.1",
                )
                status, poor = post(restarted, "/gd/refill_stamina", "poor-one", "cost=1", "poor")
                self.assertEqual((200, True, 2), (status, poor["success"], poor["cmdError"]))
            finally:
                stop_server(restarted, restarted_thread)
