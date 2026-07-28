from __future__ import annotations

import json
from http.client import HTTPConnection
from pathlib import Path
import tempfile
import threading
import unittest

from liminal_gate.bootstrap_server import BootstrapServer, BootstrapState, load_profile
from liminal_gate.companion_catalog import build_bundled_companion_policy, load_companion_catalog


class CompanionSaleTest(unittest.TestCase):
    def test_http_single_and_batch_sale_are_replay_safe(self) -> None:
        document = {"schema_version": 1, "provenance": "user-supplied", "coin_cap": 50, "masters": [{"companion_id": 10, "base_coins": 3}, {"companion_id": 11, "base_coins": 5}]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog_path = root / "companions.json"
            catalog_path.write_text(json.dumps(document), encoding="utf-8")
            profile = load_profile(Path(__file__).resolve().parents[1] / "profiles" / "legacy-client-bootstrap.json")
            state_path = root / "state.json"
            catalog = load_companion_catalog(catalog_path)

            def start() -> tuple[BootstrapServer, threading.Thread]:
                server = BootstrapServer(("127.0.0.1", 0), profile, BootstrapState(state_path), companion_catalog=catalog)
                thread = threading.Thread(target=server.serve_forever)
                thread.start()
                return server, thread

            def post(server: BootstrapServer, path: str, request_id: str, body: str) -> tuple[int, dict[str, object]]:
                connection = HTTPConnection(*server.server_address)
                connection.request("POST", f"{path}?otk=token&requestID={request_id}", body=body)
                response = connection.getresponse()
                result = json.loads(response.read())
                connection.close()
                return response.status, result

            server, thread = start()
            try:
                server.state.create_account("token", "account", {
                    "coins": 1,
                    "chrdata": [{"id": 3, "buddy": 1}],
                    "buddyInfo": {"list": [
                        {"iid": 1, "bid": 10, "lv": 2, "flag": 0, "chrID": 3},
                        {"iid": 2, "bid": 11, "lv": 1, "flag": 0, "chrID": 0},
                        {"iid": 3, "bid": 10, "lv": 1, "flag": 2, "chrID": 0},
                    ], "record": []},
                })
                status, first = post(server, "/gd/sell_buddy", "one", "inventoryID=1")
                self.assertEqual(200, status)
                self.assertEqual((True, 7, [2, 3], 0), (first["success"], first["coins"], [row["iid"] for row in first["buddyInfo"]["list"]], first["chrdata"][0]["buddy"]))
                self.assertEqual((status, first), post(server, "/gd/sell_buddy", "one", "inventoryID=1"))
                # Reusing a spent requestID with a different body is answered on
                # its own merits now.  This names a companion the account does
                # not own, so it is refused for that reason and leaves the
                # inventory intact for the locked and batch cases below.
                status, reused = post(server, "/gd/sell_buddy", "one", "inventoryID=99")
                self.assertEqual((200, True, 2), (status, reused["success"], reused["cmdError"]))
                status, locked = post(server, "/gd/sell_buddy", "two", "inventoryID=3")
                self.assertEqual((200, True, 2), (status, locked["success"], locked["cmdError"]))
                status, batch = post(server, "/gd/sell_buddies", "three", "sellList=[2]")
                self.assertEqual((200, True, 12, [3]), (status, batch["success"], batch["coins"], [row["iid"] for row in batch["buddyInfo"]["list"]]))
            finally:
                server.shutdown()
                thread.join()
                server.server_close()

            restarted, restarted_thread = start()
            try:
                self.assertEqual((200, first), post(restarted, "/gd/sell_buddy", "one", "inventoryID=1"))
            finally:
                restarted.shutdown()
                restarted_thread.join()
                restarted.server_close()


class BundledCompanionSaleRuntimeTest(unittest.TestCase):
    def test_bundled_values_are_paid_through_the_real_route(self) -> None:
        """The bundled masters must settle a real sale, not merely load."""
        with tempfile.TemporaryDirectory() as directory:
            profile = load_profile(Path(__file__).resolve().parents[1] / "profiles" / "legacy-client-bootstrap.json")
            state = BootstrapState(Path(directory) / "state.json")
            # Master 3's base value is 400, so a level 7 instance pays 2800.
            state.create_account("token", "account", {
                "coins": 100, "chrdata": [],
                "buddyInfo": {"list": [{"iid": 1, "bid": 3, "lv": 7, "exp": 0, "flag": 0, "chrID": 0}], "record": []},
            })
            server = BootstrapServer(("127.0.0.1", 0), profile, state, companion_catalog=build_bundled_companion_policy())
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            try:
                connection = HTTPConnection(*server.server_address)
                connection.request("POST", "/gd/sell_buddy?otk=token&requestID=bundled", body="inventoryID=1")
                response = connection.getresponse()
                payload = json.loads(response.read())
                connection.close()
            finally:
                server.shutdown(); thread.join(); server.server_close()
            self.assertEqual(200, response.status)
            self.assertTrue(payload["success"], payload)
            self.assertEqual(2900, payload["coins"])
            self.assertEqual([], payload["buddyInfo"]["list"])
