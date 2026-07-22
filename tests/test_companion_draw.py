from __future__ import annotations

import json
from http.client import HTTPConnection
from pathlib import Path
import tempfile
import threading
import unittest

from liminal_gate.bootstrap_server import BootstrapServer, BootstrapState, load_profile
from liminal_gate.companion_draw_catalog import load_companion_draw_catalog


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
                self.assertEqual((409, "request_collision"), (post(server, "one", "kind=21&count=1&campaignID=0&eventFlag=0&lastUpdate=1")[0], post(server, "one", "kind=21&count=1&campaignID=0&eventFlag=0&lastUpdate=1")[1]["error"]))
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
