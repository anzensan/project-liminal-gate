from __future__ import annotations

import json
from http.client import HTTPConnection
from pathlib import Path
import tempfile
import threading
import unittest

from liminal_gate.bootstrap_server import BootstrapServer, BootstrapState, load_profile
from liminal_gate.companion_draw_catalog import build_bundled_companion_draw_policy, load_companion_draw_catalog


class CompanionDrawTest(unittest.TestCase):
    def test_http_draw_prefers_ticket_and_replays_after_restart(self) -> None:
        document = {"schema_version": 1, "provenance": "user-supplied", "item_slots": 1, "ticket_item_id": 1, "energy_cost": 3, "max_owned": 2, "draws": [{"companion_id": 99, "weight": 1}]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog_path = root / "draw.json"
            catalog_path.write_text(json.dumps(document), encoding="utf-8")
            profile = load_profile(Path(__file__).resolve().parents[1] / "profiles" / "legacy-client-bootstrap.json")
            state_path = root / "state.json"
            catalog = load_companion_draw_catalog(catalog_path)

            def start() -> tuple[BootstrapServer, threading.Thread]:
                server = BootstrapServer(("127.0.0.1", 0), profile, BootstrapState(state_path), companion_draw_catalog=catalog)
                thread = threading.Thread(target=server.serve_forever)
                thread.start()
                return server, thread

            def post(server: BootstrapServer, request_id: str, body: str) -> tuple[int, dict[str, object]]:
                connection = HTTPConnection(*server.server_address)
                connection.request("POST", f"/gd/do_buddy_slot?otk=token&requestID={request_id}", body=body)
                response = connection.getresponse()
                result = json.loads(response.read())
                connection.close()
                return response.status, result

            body = "kind=1&count=1&campaignID=0&eventFlag=0&lastUpdate=1"
            server, thread = start()
            try:
                server.state.create_account("token", "account", {"coins": 0, "energy": 0, "freeEnergy": 0, "itemList": [1]})
                status, first = post(server, "one", body)
                self.assertEqual(200, status)
                self.assertEqual((True, [0], 0, 0, [{"bid": 99, "lv": 1}], 1), (first["success"], first["itemList"], first["energy"], first["freeEnergy"], first["result"], first["buddyInfo"]["list"][0]["iid"]))
                self.assertEqual((status, first), post(server, "one", body))
                # Reusing a spent requestID with a different body is answered on
                # its own merits: the paid draw has no Energy to spend.
                status, reused = post(server, "one", "kind=21&count=1&campaignID=0&eventFlag=0&lastUpdate=1")
                self.assertEqual((200, False, 1), (status, reused["success"], reused["errorCode"]))
            finally:
                server.shutdown()
                thread.join()
                server.server_close()

            restarted, restarted_thread = start()
            try:
                self.assertEqual((200, first), post(restarted, "one", body))
            finally:
                restarted.shutdown()
                restarted_thread.join()
                restarted.server_close()


class BundledCompanionDrawRuntimeTest(unittest.TestCase):
    def test_bundled_pool_draws_through_the_real_route(self) -> None:
        """The bundled pool must settle a real draw, not merely load."""
        with tempfile.TemporaryDirectory() as directory:
            profile = load_profile(Path(__file__).resolve().parents[1] / "profiles" / "legacy-client-bootstrap.json")
            state = BootstrapState(Path(directory) / "state.json")
            catalog = build_bundled_companion_draw_policy()
            items = [0] * 181
            items[112 - 1] = 2  # Companion Tickets, spent before any Energy
            state.create_account("token", "account", {
                "coins": 0, "energy": 0, "freeEnergy": 0, "itemList": items,
                "chrdata": [], "buddyInfo": {"list": [], "record": []},
            })
            server = BootstrapServer(("127.0.0.1", 0), profile, state, companion_draw_catalog=catalog)
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            try:
                connection = HTTPConnection(*server.server_address)
                connection.request("POST", "/gd/do_buddy_slot?otk=token&requestID=bundled",
                                   body="kind=1&count=1&campaignID=0&eventFlag=0&lastUpdate=1")
                response = connection.getresponse()
                payload = json.loads(response.read())
                connection.close()
            finally:
                server.shutdown(); thread.join(); server.server_close()
            self.assertEqual(200, response.status)
            self.assertTrue(payload["success"], payload)
            # A ticket is consumed even though the account has no Energy at all.
            self.assertEqual(1, payload["itemList"][112 - 1])
            drawn = [row["bid"] for row in payload["buddyInfo"]["list"]]
            self.assertEqual(1, len(drawn))
            self.assertIn(drawn[0], {draw.companion_id for draw in catalog.draws})
