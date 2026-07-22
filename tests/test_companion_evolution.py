from __future__ import annotations

import json
from http.client import HTTPConnection
from pathlib import Path
import tempfile
import threading
import unittest

from liminal_gate.bootstrap_server import BootstrapServer, BootstrapState, load_profile
from liminal_gate.companion_evolution_catalog import load_companion_evolution_catalog


class CompanionEvolutionTest(unittest.TestCase):
    def test_http_evolution_transforms_in_place_and_replays_after_restart(self) -> None:
        document = {"schema_version": 1, "provenance": "user-supplied", "item_slots": 1, "recipes": [{"source_companion_id": 10, "destination_companion_id": 11, "max_level": 2, "coins": 3, "items": {"1": 1}, "duplicate_source_count": 0}]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog_path = root / "evolve.json"
            catalog_path.write_text(json.dumps(document), encoding="utf-8")
            profile = load_profile(Path(__file__).resolve().parents[1] / "profiles" / "legacy-client-bootstrap.json")
            state_path = root / "state.json"
            catalog = load_companion_evolution_catalog(catalog_path)

            def start() -> tuple[BootstrapServer, threading.Thread]:
                server = BootstrapServer(("127.0.0.1", 0), profile, BootstrapState(state_path), companion_evolution_catalog=catalog)
                thread = threading.Thread(target=server.serve_forever)
                thread.start()
                return server, thread

            def post(server: BootstrapServer, request_id: str, body: str) -> tuple[int, dict[str, object]]:
                connection = HTTPConnection(*server.server_address)
                connection.request("POST", f"/gd/buddy_evolve?otk=token&requestID={request_id}", body=body)
                response = connection.getresponse()
                result = json.loads(response.read())
                connection.close()
                return response.status, result

            server, thread = start()
            try:
                server.state.create_account("token", "account", {"coins": 3, "itemList": [1], "buddyInfo": {"list": [{"iid": 1, "bid": 10, "lv": 2, "exp": 99, "flag": 0, "chrID": 3}], "record": []}})
                status, first = post(server, "one", "baseID=1&lastUpdate=1")
                self.assertEqual(200, status)
                self.assertEqual((True, 0, [0], 1, 11, 1, 0), (first["success"], first["coins"], first["itemList"], first["buddyInfo"]["list"][0]["iid"], first["buddyInfo"]["list"][0]["bid"], first["buddyInfo"]["list"][0]["lv"], first["buddyInfo"]["list"][0]["exp"]))
                self.assertEqual((status, first), post(server, "one", "baseID=1&lastUpdate=1"))
                self.assertEqual((409, "request_collision"), (post(server, "one", "baseID=1")[0], post(server, "one", "baseID=1")[1]["error"]))
            finally:
                server.shutdown()
                thread.join()
                server.server_close()

            restarted, restarted_thread = start()
            try:
                self.assertEqual((200, first), post(restarted, "one", "baseID=1&lastUpdate=1"))
            finally:
                restarted.shutdown()
                restarted_thread.join()
                restarted.server_close()
