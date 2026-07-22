from __future__ import annotations

import json
from http.client import HTTPConnection
from pathlib import Path
import tempfile
import threading
import unittest

from liminal_gate.bootstrap_server import BootstrapServer, BootstrapState, load_profile


class ChangeUnameTest(unittest.TestCase):
    def test_http_replay_collision_and_cooldown(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = load_profile(Path(__file__).resolve().parents[1] / "profiles" / "legacy-client-bootstrap.json")
            server = BootstrapServer(("127.0.0.1", 0), profile, BootstrapState(root / "state.json"))
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            try:
                server.state.create_account("token", "account", {"coins": 0})
                def post(request_id: str, body: str) -> tuple[int, dict[str, object]]:
                    connection = HTTPConnection(*server.server_address)
                    connection.request("POST", f"/gd/change_uname?otk=token&requestID={request_id}", body=body)
                    response = connection.getresponse()
                    payload = json.loads(response.read())
                    connection.close()
                    return response.status, payload
                status, first = post("one", "name=Alice")
                self.assertEqual(200, status)
                self.assertEqual("Alice", first["name"])
                self.assertEqual((status, first), post("one", "name=Alice"))
                status, collision = post("one", "name=Bob")
                self.assertEqual((409, "request_collision"), (status, collision["error"]))
                status, blocked = post("two", "name=Bob")
                self.assertEqual((200, 1), (status, blocked["errorCode"]))
            finally:
                server.shutdown(); thread.join(); server.server_close()
