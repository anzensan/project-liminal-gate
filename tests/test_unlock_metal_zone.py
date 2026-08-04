from __future__ import annotations

from pathlib import Path
import tempfile
import time
import unittest

from liminal_gate.bootstrap_server import BootstrapState
from tests.support import bootstrap_profile, post, start_server, stop_server


class UnlockMetalZoneTest(unittest.TestCase):
    def test_empty_body_unlock_replay_collision_and_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = bootstrap_profile()
            state_path = root / "state.json"

            server, thread = start_server(("127.0.0.1", 0), profile, BootstrapState(state_path))
            try:
                server.state.create_account("token", "account", {"freeEnergy": 1, "energy": 3, "energyAppStore": 4, "energyGooglePlay": 5, "energyAndApp": 6})
                before = int(time.time())
                status, success = post(server, "/gd/unlock_metal_zone", "one", b"")
                self.assertEqual(200, status)
                self.assertEqual({"success", "metalZoneUnlockTime", "energy", "energyAppStore", "energyGooglePlay", "energyAndApp", "freeEnergy", "digest"}, set(success))
                self.assertTrue(success["success"])
                self.assertGreaterEqual(success["metalZoneUnlockTime"], before + 3600)
                self.assertEqual((3, 0), (success["energy"], success["freeEnergy"]))
                self.assertEqual((status, success), post(server, "/gd/unlock_metal_zone", "one", b""))
                # A body reusing a spent requestID gets exactly the answer it
                # would under a fresh one: the requestID no longer decides it.
                status, reused = post(server, "/gd/unlock_metal_zone", "one", b"unexpected")
                self.assertEqual((501, "unsupported_unlock_metal_zone"), (status, reused["error"]))
                self.assertEqual((status, reused), post(server, "/gd/unlock_metal_zone", "malformed", b"unexpected"))
            finally:
                stop_server(server, thread)

            restarted, thread = start_server(("127.0.0.1", 0), profile, BootstrapState(state_path))
            try:
                self.assertEqual((200, success), post(restarted, "/gd/unlock_metal_zone", "one", b""))
                restarted.state.create_account(
                    "poor",
                    "poor-account",
                    {},
                    client_host="127.0.0.1",
                )
                status, poor = post(restarted, "/gd/unlock_metal_zone", "poor-one", b"", "poor")
                self.assertEqual((200, True, 2), (status, poor["success"], poor["cmdError"]))
            finally:
                stop_server(restarted, thread)
