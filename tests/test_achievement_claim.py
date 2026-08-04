from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from liminal_gate.achievement_catalog import load_achievement_catalog
from liminal_gate.bootstrap_server import BootstrapState
from tests.support import bootstrap_profile, post, start_server, stop_server, write_json


class AchievementClaimTest(unittest.TestCase):
    def test_toml_catalog_loads_strictly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "achievements.toml"
            path.write_text(
                'schema_version = 1\nprovenance = "user-supplied"\nitem_slots = 3\nmax_free_energy = 9\nmax_coins = 99\nmax_stack = 8\n\n[[achievements]]\nachievement_id = 1\nrequired_chapter = 5\nfree_energy = 1\ncoins = 0\nitems = { "2" = 1 }\n',
                encoding="utf-8",
            )
            catalog = load_achievement_catalog(path)
            self.assertEqual((3, 5, {2: 1}), (catalog.item_slots, catalog.achievements[1].required_chapter, catalog.achievements[1].items))

    def test_http_claim_denial_collision_and_restart_replay(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog_path = write_json(root / "achievements.json", {
                "schema_version": 1, "provenance": "user-supplied", "item_slots": 3,
                "max_free_energy": 9, "max_coins": 99, "max_stack": 8,
                "achievements": [{"achievement_id": 1, "required_chapter": 5, "free_energy": 2, "coins": 3, "items": {"2": 4}}],
            })
            profile = bootstrap_profile()
            state_path = root / "state.json"

            server, thread = start_server(("127.0.0.1", 0), profile, BootstrapState(state_path), achievement_catalog=load_achievement_catalog(catalog_path))
            try:
                server.state.create_account("token", "account", {"progressCode": 6 << 6, "freeEnergy": 1, "coins": 2, "itemList": [0, 1, 0]})
                status, success = post(server, "/gd/achived", "one", "id=1&lastUpdate=1")
                self.assertEqual(200, status)
                self.assertEqual({"achivementFlags", "freeEnergy", "coins", "itemList", "digest"}, set(success))
                self.assertEqual(([2], 3, 5, [0, 5, 0]), (success["achivementFlags"], success["freeEnergy"], success["coins"], success["itemList"]))
                self.assertEqual((status, success), post(server, "/gd/achived", "one", "id=1&lastUpdate=1"))
                # Reusing a spent requestID with a different body is no longer
                # read as a tampered retry; this body is simply invalid.
                status, reused = post(server, "/gd/achived", "one", "id=1&lastUpdate=0")
                self.assertEqual((501, "unsupported_achievement"), (status, reused["error"]))
                status, duplicate = post(server, "/gd/achived", "two", "id=1&lastUpdate=1")
                self.assertEqual((409, "invalid_local_achievement"), (status, duplicate["error"]))
                server.state.create_account("locked", "locked-account", {"progressCode": 5 << 6, "itemList": [0, 0, 0]})
                status, locked = post(server, "/gd/achived", "locked-one", "id=1&lastUpdate=1", "locked")
                self.assertEqual((409, "invalid_local_achievement"), (status, locked["error"]))
            finally:
                stop_server(server, thread)

            restarted, thread = start_server(("127.0.0.1", 0), profile, BootstrapState(state_path), achievement_catalog=load_achievement_catalog(catalog_path))
            try:
                self.assertEqual((200, success), post(restarted, "/gd/achived", "one", "id=1&lastUpdate=1"))
            finally:
                stop_server(restarted, thread)
