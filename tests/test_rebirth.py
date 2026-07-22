from __future__ import annotations

import json
from http.client import HTTPConnection
from pathlib import Path
import tempfile
import threading
import unittest

from liminal_gate.bootstrap_server import BootstrapServer, BootstrapState, load_profile
from liminal_gate.rebirth_catalog import load_rebirth_catalog


class RebirthTest(unittest.TestCase):
    def test_http_rebirth_joker_error_and_restart_replay(self) -> None:
        document = {"schema_version": 1, "provenance": "user-supplied", "item_slots": 1, "joker_character_id": 9, "recipes": [{"recipe_id": 1, "source_character_id": 2, "destination_character_id": 3, "coins": 2, "items": {"1": 1}, "materials": [{"character_id": 7, "level": 50}, {"character_id": 8, "level": 50}]}]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); catalog_path = root / "catalog.json"; catalog_path.write_text(json.dumps(document), encoding="utf-8")
            profile = load_profile(Path(__file__).resolve().parents[1] / "profiles" / "legacy-client-bootstrap.json"); state = root / "state.json"; catalog = load_rebirth_catalog(catalog_path)
            def start() -> tuple[BootstrapServer, threading.Thread]:
                server = BootstrapServer(("127.0.0.1", 0), profile, BootstrapState(state), rebirth_catalog=catalog); thread = threading.Thread(target=server.serve_forever); thread.start(); return server, thread
            def post(server: BootstrapServer, request_id: str, body: str) -> tuple[int, dict[str, object]]:
                connection = HTTPConnection(*server.server_address); connection.request("POST", f"/gd/rebirth?otk=token&requestID={request_id}", body=body); response = connection.getresponse(); payload = json.loads(response.read()); connection.close(); return response.status, payload
            server, thread = start()
            try:
                server.state.create_account("token", "account", {"chrdata": [{"id": 2, "jobLevels": [80.0]}, {"id": 7, "jobLevels": [50.0]}, {"id": 9, "jobLevels": [1.0]}], "itemList": [1], "coins": 2})
                status, retry = post(server, "first", "rebirthID=1&useJoker=False")
                self.assertEqual((200, False, 7), (status, retry["success"], retry["errorCode"]))
                status, success = post(server, "second", "rebirthID=1&useJoker=True")
                self.assertEqual((200, True, 0, [0]), (status, success["success"], success["coins"], success["itemList"]))
                self.assertEqual([3, 7, 9], [row["id"] for row in success["chrdata"]])
            finally:
                server.shutdown(); thread.join(); server.server_close()
            restarted, restarted_thread = start()
            try:
                self.assertEqual((200, success), post(restarted, "second", "rebirthID=1&useJoker=True"))
            finally:
                restarted.shutdown(); restarted_thread.join(); restarted.server_close()
