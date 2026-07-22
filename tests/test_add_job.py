from __future__ import annotations

import json
from http.client import HTTPConnection
from pathlib import Path
import tempfile
import threading
import unittest

from liminal_gate.bootstrap_server import BootstrapServer, BootstrapState, load_profile
from liminal_gate.job_catalog import load_job_catalog


class AddJobTest(unittest.TestCase):
    def test_http_job_unlock_errors_collision_and_restart(self) -> None:
        document = {"schema_version": 1, "provenance": "user-supplied", "item_slots": 2, "unlocks": [{"character_id": 3, "job_index": 1, "coins": 2, "materials": {"1": 1}}, {"character_id": 3, "job_index": 2, "coins": 3, "materials": {"2": 1}}]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); path = root / "jobs.json"; path.write_text(json.dumps(document), encoding="utf-8")
            profile = load_profile(Path(__file__).resolve().parents[1] / "profiles" / "legacy-client-bootstrap.json")
            state = root / "state.json"; catalog = load_job_catalog(path)
            def start() -> tuple[BootstrapServer, threading.Thread]:
                server = BootstrapServer(("127.0.0.1", 0), profile, BootstrapState(state), job_catalog=catalog)
                thread = threading.Thread(target=server.serve_forever); thread.start(); return server, thread
            def post(server: BootstrapServer, request_id: str, body: str) -> tuple[int, dict[str, object]]:
                connection = HTTPConnection(*server.server_address); connection.request("POST", f"/gd/add_job?otk=token&requestID={request_id}", body=body)
                response = connection.getresponse(); result = json.loads(response.read()); connection.close(); return response.status, result
            server, thread = start()
            try:
                server.state.create_account("token", "account", {"chrdata": [{"id": 3, "jobLevels": [1.0, 0.0, 0.0]}], "itemList": [2, 2], "coins": 5})
                status, first = post(server, "one", "targetID=3&lastUpdate=1")
                self.assertEqual(200, status); self.assertEqual((True, [1.0, 1.0, 0.0], [1, 2], 3), (first["success"], first["chrdata"]["jobLevels"], first["itemList"], first["coins"]))
                self.assertEqual((status, first), post(server, "one", "targetID=3&lastUpdate=1"))
                self.assertEqual((409, "request_collision"), (post(server, "one", "targetID=3")[0], post(server, "one", "targetID=3")[1]["error"]))
                status, second = post(server, "two", "targetID=3")
                self.assertEqual((200, [1.0, 1.0, 1.0], [1, 1], 0), (status, second["chrdata"]["jobLevels"], second["itemList"], second["coins"]))
                status, none = post(server, "three", "targetID=3")
                self.assertEqual((200, True, 4), (status, none["success"], none["cmdError"]))
            finally:
                server.shutdown(); thread.join(); server.server_close()
            restarted, restarted_thread = start()
            try:
                self.assertEqual((200, first), post(restarted, "one", "targetID=3&lastUpdate=1"))
            finally:
                restarted.shutdown(); restarted_thread.join(); restarted.server_close()
