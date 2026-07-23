from __future__ import annotations

import json
from http.client import HTTPConnection
from pathlib import Path
import tempfile
import threading
import unittest

from liminal_gate.bootstrap_server import BootstrapServer, BootstrapState, load_profile
from liminal_gate.pact_draw_catalog import build_bundled_pact_policy, load_pact_draw_catalog


class PactDrawTest(unittest.TestCase):
    def test_http_pact_draw_replays_and_persists(self) -> None:
        catalog_document = {
            "schema_version": 1, "provenance": "user-supplied", "coin_cost": 10,
            "new_level": 1, "max_level": 9, "max_skill_boost": 100,
            "draws": [{"character_id": 9001, "weight": 1, "duplicate_level_added": 2, "duplicate_skill_boost": 5}],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog_path, state_path = root / "pact.json", root / "state.json"
            catalog_path.write_text(json.dumps(catalog_document), encoding="utf-8")
            profile = load_profile(Path(__file__).resolve().parents[1] / "profiles" / "legacy-client-bootstrap.json")
            catalog = load_pact_draw_catalog(catalog_path)

            def start() -> tuple[BootstrapServer, threading.Thread]:
                server = BootstrapServer(("127.0.0.1", 0), profile, BootstrapState(state_path), pact_draw_catalog=catalog)
                thread = threading.Thread(target=server.serve_forever); thread.start()
                return server, thread

            def post(server: BootstrapServer, request_id: str) -> tuple[int, dict[str, object]]:
                connection = HTTPConnection(*server.server_address)
                connection.request("POST", f"/gd/do_slot?otk=token&requestID={request_id}", body="kind=0&count=1&luckType=false&campaignChrID=0&eventFlag=0&lastUpdate=1")
                response = connection.getresponse(); payload = json.loads(response.read()); connection.close()
                return response.status, payload

            server, thread = start()
            try:
                server.state.create_account("token", "account", {"coins": 20, "energy": 0, "freeEnergy": 0, "chrdata": []})
                status, first = post(server, "one")
                self.assertEqual(200, status)
                self.assertEqual((True, 10, [{"id": 9001, "jobID": 0, "jobLevels": [1], "jobSlots": [], "isNew": True, "levelAdded": 1, "skillBoost": 0}]), (first["success"], first["coins"], first["chrdata"]))
                self.assertEqual((status, first), post(server, "one"))
                _, duplicate = post(server, "two")
                self.assertEqual((0, False, 2, 5), (duplicate["coins"], duplicate["chrdata"][0]["isNew"], duplicate["chrdata"][0]["levelAdded"], duplicate["chrdata"][0]["boostUp"]))
            finally:
                server.shutdown(); thread.join(); server.server_close()
            restarted, restarted_thread = start()
            try:
                self.assertEqual((200, first), post(restarted, "one"))
            finally:
                restarted.shutdown(); restarted_thread.join(); restarted.server_close()

    def test_http_bundled_truth_pact_spends_starter_energy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = root / "state.json"
            profile = load_profile(Path(__file__).resolve().parents[1] / "profiles" / "legacy-client-bootstrap.json")
            server = BootstrapServer(("127.0.0.1", 0), profile, BootstrapState(state_path), pact_draw_catalog=build_bundled_pact_policy())
            thread = threading.Thread(target=server.serve_forever); thread.start()
            try:
                server.state.create_account("token", "account", {"coins": 0, "energy": 0, "freeEnergy": 5, "chrdata": []})
                connection = HTTPConnection(*server.server_address)
                connection.request("POST", "/gd/do_slot?otk=token&requestID=truth-one", body="kind=1&count=1&luckType=false&campaignChrID=0&eventFlag=0&lastUpdate=1")
                response = connection.getresponse(); payload = json.loads(response.read()); connection.close()
                self.assertEqual(200, response.status)
                self.assertTrue(payload["success"])
                self.assertEqual(0, payload["freeEnergy"])
                self.assertEqual(1, len(payload["chrdata"]))
                self.assertIn(payload["chrdata"][0]["id"], {draw.character_id for draw in build_bundled_pact_policy().truth_draws})
            finally:
                server.shutdown(); thread.join(); server.server_close()
