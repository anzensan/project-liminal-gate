from __future__ import annotations

import json
from http.client import HTTPConnection
from pathlib import Path
import tempfile
import threading
import unittest

from liminal_gate.achievement_catalog import load_achievement_catalog
from liminal_gate.bootstrap_server import BootstrapServer, BootstrapState, load_profile


class AchievementClaimTest(unittest.TestCase):
    def test_toml_catalog_loads_strictly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "achievements.toml"
            path.write_text(
                'schema_version = 1\nprovenance = "user-supplied"\nitem_slots = 3\nmax_free_energy = 9\nmax_coins = 99\nmax_stack = 8\n\n[[achievements]]\nachievement_id = 1\nrequired_chapter = 5\nfree_energy = 1\ncoins = 0\nitems = { "2" = 1 }\n',
                encoding="utf-8",
            )
            catalog = load_achievement_catalog(path)
            self.assertEqual((3, 5, {2: 1}), (catalog.item_slots, catalog.achievements[1].required_chapter, catalog.achievements[1].items))

    def test_http_claim_denial_collision_and_restart_replay(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog_path = root / "achievements.json"
            catalog_path.write_text(json.dumps({
                "schema_version": 1, "provenance": "user-supplied", "item_slots": 3,
                "max_free_energy": 9, "max_coins": 99, "max_stack": 8,
                "achievements": [{"achievement_id": 1, "required_chapter": 5, "free_energy": 2, "coins": 3, "items": {"2": 4}}],
            }), encoding="utf-8")
            profile = load_profile(Path(__file__).resolve().parents[1] / "profiles" / "legacy-client-bootstrap.json")
            state_path = root / "state.json"

            def start() -> tuple[BootstrapServer, threading.Thread]:
                server = BootstrapServer(("127.0.0.1", 0), profile, BootstrapState(state_path), achievement_catalog=load_achievement_catalog(catalog_path))
                thread = threading.Thread(target=server.serve_forever)
                thread.start()
                return server, thread

            def post(server: BootstrapServer, token: str, request_id: str, body: str) -> tuple[int, dict[str, object]]:
                connection = HTTPConnection(*server.server_address)
                connection.request("POST", f"/gd/achived?otk={token}&requestID={request_id}", body=body)
                response = connection.getresponse()
                payload = json.loads(response.read())
                connection.close()
                return response.status, payload

            server, thread = start()
            try:
                server.state.create_account("token", "account", {"progressCode": 6 << 6, "freeEnergy": 1, "coins": 2, "itemList": [0, 1, 0]})
                status, success = post(server, "token", "one", "id=1&lastUpdate=1")
                self.assertEqual(200, status)
                self.assertEqual({"achivementFlags", "freeEnergy", "coins", "itemList", "digest"}, set(success))
                self.assertEqual(([2], 3, 5, [0, 5, 0]), (success["achivementFlags"], success["freeEnergy"], success["coins"], success["itemList"]))
                self.assertEqual((status, success), post(server, "token", "one", "id=1&lastUpdate=1"))
                status, collision = post(server, "token", "one", "id=1&lastUpdate=0")
                self.assertEqual((409, "request_collision"), (status, collision["error"]))
                status, duplicate = post(server, "token", "two", "id=1&lastUpdate=1")
                self.assertEqual((409, "invalid_local_achievement"), (status, duplicate["error"]))
                server.state.create_account("locked", "locked-account", {"progressCode": 5 << 6, "itemList": [0, 0, 0]})
                status, locked = post(server, "locked", "locked-one", "id=1&lastUpdate=1")
                self.assertEqual((409, "invalid_local_achievement"), (status, locked["error"]))
            finally:
                server.shutdown(); thread.join(); server.server_close()

            restarted, thread = start()
            try:
                self.assertEqual((200, success), post(restarted, "token", "one", "id=1&lastUpdate=1"))
            finally:
                restarted.shutdown(); thread.join(); restarted.server_close()
