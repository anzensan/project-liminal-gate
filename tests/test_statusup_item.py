from __future__ import annotations

import json
from http.client import HTTPConnection
from pathlib import Path
import tempfile
import threading
import unittest

from liminal_gate.bootstrap_server import BootstrapServer, BootstrapState, load_profile
from liminal_gate.statusup_catalog import load_statusup_catalog


class StatusupItemTest(unittest.TestCase):
    def test_http_settlement_errors_collision_and_restart_replay(self) -> None:
        catalog_document = {
            "schema_version": 1, "provenance": "user-supplied", "item_slots": 3,
            "level_cap": 90, "skill_boost_cap": 1000,
            "items": [
                {"item_id": 1, "level": 1, "skill_boost": 0, "luck": 0, "species": None},
                {"item_id": 2, "level": 0, "skill_boost": 1, "luck": 0, "species": 8},
                {"item_id": 3, "level": 0, "skill_boost": 0, "luck": 1, "species": None},
            ],
            "characters": [
                {"character_id": 3, "species": 1, "luck_cap": 30},
                {"character_id": 91, "species": 8, "luck_cap": 1000},
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog_path = root / "statusup.json"
            catalog_path.write_text(json.dumps(catalog_document), encoding="utf-8")
            profile = load_profile(Path(__file__).resolve().parents[1] / "profiles" / "legacy-client-bootstrap.json")
            state_path = root / "state.json"
            catalog = load_statusup_catalog(catalog_path)

            def start() -> tuple[BootstrapServer, threading.Thread]:
                server = BootstrapServer(("127.0.0.1", 0), profile, BootstrapState(state_path), statusup_catalog=catalog)
                thread = threading.Thread(target=server.serve_forever)
                thread.start()
                return server, thread

            def post(server: BootstrapServer, request_id: str, body: str) -> tuple[int, dict[str, object]]:
                connection = HTTPConnection(*server.server_address)
                connection.request("POST", f"/gd/use_statusup_item?otk=token&requestID={request_id}", body=body)
                response = connection.getresponse()
                payload = json.loads(response.read())
                connection.close()
                return response.status, payload

            server, thread = start()
            try:
                server.state.create_account("token", "account", {
                    "chrdata": [
                        {"id": 3, "jobLevels": [int((111 << 12) | 89), 0.0], "skillBoost": 990, "luck": 20},
                        {"id": 91, "jobLevels": [1.0], "skillBoost": 0, "luck": 0},
                    ],
                    "itemList": [2, 2, 20],
                })
                status, level = post(server, "level", "targetChrID=3&useItemID=1&useAmount=2")
                self.assertEqual(200, status)
                self.assertEqual({"chrdata", "itemList", "resultValues", "digest"}, set(level))
                changed = next(item for item in level["chrdata"] if item["id"] == 3)
                self.assertEqual([111, 0], [int(value) >> 12 for value in changed["jobLevels"]])
                self.assertEqual([90, 0], [int(value) & 0xFFF for value in changed["jobLevels"]])
                self.assertEqual({"0": 1}, level["resultValues"]["addedLevels"])
                self.assertEqual((200, level), post(server, "level", "targetChrID=3&useItemID=1&useAmount=2"))
                status, collision = post(server, "level", "targetChrID=3&useItemID=3&useAmount=1")
                self.assertEqual((409, "request_collision"), (status, collision["error"]))
                status, wrong_species = post(server, "species", "targetChrID=3&useItemID=2&useAmount=1")
                self.assertEqual((200, False, 3), (status, wrong_species["success"], wrong_species["errorCode"]))
                status, unknown = post(server, "unknown", "targetChrID=999&useItemID=1&useAmount=1")
                self.assertEqual((200, False, 4), (status, unknown["success"], unknown["errorCode"]))
                # A semantically invalid account record must not retain the
                # speculative level update attempted before its bad scalar is
                # discovered.
                bad = {"id": 3, "jobLevels": [89], "skillBoost": "bad", "luck": 0}
                server.state.accounts["account"]["userdata"]["chrdata"] = [bad]
                server.state.accounts["account"]["userdata"]["itemList"] = [2, 0, 0]
                status, invalid_state = post(server, "bad-state", "targetChrID=3&useItemID=1&useAmount=1")
                self.assertEqual((200, False, 3), (status, invalid_state["success"], invalid_state["errorCode"]))
                self.assertEqual(([89], 2), (bad["jobLevels"], server.state.accounts["account"]["userdata"]["itemList"][0]))
                server.state.accounts["account"]["userdata"]["chrdata"] = [
                    {"id": 3, "jobLevels": [int((111 << 12) | 90), 0.0], "skillBoost": 990, "luck": 20},
                    {"id": 91, "jobLevels": [1.0], "skillBoost": 0, "luck": 0},
                ]
                server.state.accounts["account"]["userdata"]["itemList"] = [1, 2, 20]
                status, luck = post(server, "luck", "targetChrID=3&useItemID=3&useAmount=20")
                self.assertEqual((200, 1, 30), (status, luck["resultValues"]["addedLuck"], next(item for item in luck["chrdata"] if item["id"] == 3)["luck"]))
            finally:
                server.shutdown(); thread.join(); server.server_close()

            restarted, restarted_thread = start()
            try:
                self.assertEqual((200, level), post(restarted, "level", "targetChrID=3&useItemID=1&useAmount=2"))
                status, unavailable = post(restarted, "missing", "targetChrID=3&useItemID=1&useAmount=1")
                self.assertEqual((200, False, 3), (status, unavailable["success"], unavailable["errorCode"]))
            finally:
                restarted.shutdown(); restarted_thread.join(); restarted.server_close()
