from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from liminal_gate.bootstrap_server import BootstrapState
from tests.support import bootstrap_profile, post, running_server


class ChangeUnameTest(unittest.TestCase):
    def test_http_replay_collision_and_cooldown(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = bootstrap_profile()
            with running_server(("127.0.0.1", 0), profile, BootstrapState(root / "state.json")) as server:
                server.state.create_account("token", "account", {"coins": 0})
                status, first = post(server, "/gd/change_uname", "one", "name=Alice")
                self.assertEqual(200, status)
                self.assertEqual("Alice", first["name"])
                self.assertEqual((status, first), post(server, "/gd/change_uname", "one", "name=Alice"))
                # A different body reusing a spent requestID gets exactly the
                # answer it would under a fresh one -- here a second rename,
                # refused by the cooldown -- rather than a collision.
                status, reused = post(server, "/gd/change_uname", "one", "name=Bob")
                self.assertEqual((200, 1), (status, reused["cmdError"]))
                self.assertEqual((status, reused), post(server, "/gd/change_uname", "two", "name=Bob"))
