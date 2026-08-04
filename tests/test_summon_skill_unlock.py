from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from liminal_gate.bootstrap_server import BootstrapState
from liminal_gate.summon_skill_catalog import load_summon_skill_catalog
from tests.support import bootstrap_profile, post, start_server, stop_server, write_json


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
            catalog_path = write_json(root / "summons.json", document)
            profile = bootstrap_profile()
            state_path = root / "state.json"
            catalog = load_summon_skill_catalog(catalog_path)

            server, thread = start_server(("127.0.0.1", 0), profile, BootstrapState(state_path), summon_skill_catalog=catalog)
            try:
                server.state.create_account("token", "account", {"summonList": [0x101] + [0] * 15, "itemList": [1, 0], "coins": 2})
                status, first = post(server, "/gd/summon_skill_unlock", "one", "targetID=1")
                self.assertEqual(200, status)
                self.assertEqual((True, 0x102, [0, 0], 0), (first["success"], first["summonList"][0], first["itemList"], first["coins"]))
                self.assertEqual((status, first), post(server, "/gd/summon_skill_unlock", "one", "targetID=1"))
                # Reusing a spent requestID with a different body is answered on
                # its own merits: this summon has no unlock available.
                status, reused = post(server, "/gd/summon_skill_unlock", "one", "targetID=2")
                self.assertEqual((200, True, 3), (status, reused["success"], reused["cmdError"]))
                status, unavailable = post(server, "/gd/summon_skill_unlock", "two", "targetID=1")
                self.assertEqual((200, True, 3), (status, unavailable["success"], unavailable["cmdError"]))
            finally:
                stop_server(server, thread)

            restarted, restarted_thread = start_server(("127.0.0.1", 0), profile, BootstrapState(state_path), summon_skill_catalog=catalog)
            try:
                self.assertEqual((200, first), post(restarted, "/gd/summon_skill_unlock", "one", "targetID=1"))
            finally:
                stop_server(restarted, restarted_thread)
