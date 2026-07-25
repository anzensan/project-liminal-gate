from __future__ import annotations

import json
from http.client import HTTPConnection
from pathlib import Path
import tempfile
import threading
import unittest

from liminal_gate.bootstrap_server import BootstrapServer, BootstrapState, load_profile
from liminal_gate.companion_evolution_catalog import build_bundled_companion_evolution_policy, load_companion_evolution_catalog


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
                # Reusing a spent requestID with a different body is answered on
                # its own merits: this companion has no evolution available.
                status, reused = post(server, "one", "baseID=1")
                self.assertEqual((200, False, 3), (status, reused["success"], reused["errorCode"]))
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


class BundledCompanionEvolutionRuntimeTest(unittest.TestCase):
    def test_bundled_recipe_is_settled_through_the_real_route(self) -> None:
        """The bundled recipes must settle a real evolution, not merely load."""
        with tempfile.TemporaryDirectory() as directory:
            profile = load_profile(Path(__file__).resolve().parents[1] / "profiles" / "legacy-client-bootstrap.json")
            state = BootstrapState(Path(directory) / "state.json")
            # Master 1 evolves into 2 at level 30 for 10000 Coins plus items
            # 17x15, 20x5, and 24x5.
            items = [0] * 181
            for item_id, count in ((17, 20), (20, 10), (24, 10)):
                items[item_id - 1] = count
            state.create_account("token", "account", {
                "coins": 15000, "itemList": items, "chrdata": [],
                "buddyInfo": {"list": [{"iid": 1, "bid": 1, "lv": 30, "exp": 0, "flag": 0, "chrID": 0}], "record": []},
            })
            server = BootstrapServer(("127.0.0.1", 0), profile, state,
                                     companion_evolution_catalog=build_bundled_companion_evolution_policy())
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            try:
                connection = HTTPConnection(*server.server_address)
                connection.request("POST", "/gd/buddy_evolve?otk=token&requestID=bundled", body="baseID=1&lastUpdate=1")
                response = connection.getresponse()
                payload = json.loads(response.read())
                connection.close()
            finally:
                server.shutdown(); thread.join(); server.server_close()
            self.assertEqual(200, response.status)
            self.assertTrue(payload["success"], payload)
            self.assertEqual(5000, payload["coins"])
            self.assertEqual([2], [row["bid"] for row in payload["buddyInfo"]["list"]])
            self.assertEqual([5, 5, 5], [payload["itemList"][item_id - 1] for item_id in (17, 20, 24)])
