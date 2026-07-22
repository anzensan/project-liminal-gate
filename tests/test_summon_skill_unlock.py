from __future__ import annotations

import json
from http.client import HTTPConnection
from pathlib import Path
import tempfile
import threading
import unittest

from liminal_gate.bootstrap_server import BootstrapServer, BootstrapState, load_profile
from liminal_gate.summon_skill_catalog import load_summon_skill_catalog


class SummonSkillUnlockTest(unittest.TestCase):
    def test_http_unlock_preserves_checked_bit_and_replays_after_restart(self) -> None:
        document = {
            "schema_version": 1,
            "provenance": "user-supplied",
            "item_slots": 2,
            "levels": [
                {"summon_id": summon_id, "skill_level": level, "coins": 2 if summon_id == 1 and level == 1 else 0, "materials": {"1": 1} if summon_id == 1 and level == 1 else {}}
                for summon_id in range(1, 17)
                for level in range(2 if summon_id == 1 else 1)
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog_path = root / "summons.json"
            catalog_path.write_text(json.dumps(document), encoding="utf-8")
            profile = load_profile(Path(__file__).resolve().parents[1] / "profiles" / "legacy-client-bootstrap.json")
            state_path = root / "state.json"
            catalog = load_summon_skill_catalog(catalog_path)

            def start() -> tuple[BootstrapServer, threading.Thread]:
                server = BootstrapServer(("127.0.0.1", 0), profile, BootstrapState(state_path), summon_skill_catalog=catalog)
                thread = threading.Thread(target=server.serve_forever)
                thread.start()
                return server, thread

            def post(server: BootstrapServer, request_id: str, body: str) -> tuple[int, dict[str, object]]:
                connection = HTTPConnection(*server.server_address)
                connection.request("POST", f"/gd/summon_skill_unlock?otk=token&requestID={request_id}", body=body)
                response = connection.getresponse()
                result = json.loads(response.read())
                connection.close()
                return response.status, result

            server, thread = start()
            try:
                server.state.create_account("token", "account", {"summonList": [0x101] + [0] * 15, "itemList": [1, 0], "coins": 2})
                status, first = post(server, "one", "targetID=1")
                self.assertEqual(200, status)
                self.assertEqual((True, 0x102, [0, 0], 0), (first["success"], first["summonList"][0], first["itemList"], first["coins"]))
                self.assertEqual((status, first), post(server, "one", "targetID=1"))
                self.assertEqual((409, "request_collision"), (post(server, "one", "targetID=2")[0], post(server, "one", "targetID=2")[1]["error"]))
                status, unavailable = post(server, "two", "targetID=1")
                self.assertEqual((200, False, 3), (status, unavailable["success"], unavailable["errorCode"]))
            finally:
                server.shutdown()
                thread.join()
                server.server_close()

            restarted, restarted_thread = start()
            try:
                self.assertEqual((200, first), post(restarted, "one", "targetID=1"))
            finally:
                restarted.shutdown()
                restarted_thread.join()
                restarted.server_close()
