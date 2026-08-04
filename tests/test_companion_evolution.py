from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from liminal_gate.bootstrap_server import BootstrapState
from liminal_gate.companion_evolution_catalog import build_bundled_companion_evolution_policy, load_companion_evolution_catalog
from tests.support import bootstrap_profile, post, start_server, stop_server, write_json


class CompanionEvolutionTest(unittest.TestCase):
    def test_http_evolution_transforms_in_place_and_replays_after_restart(self) -> None:
        document = {"schema_version": 1, "provenance": "user-supplied", "item_slots": 1, "recipes": [{"source_companion_id": 10, "destination_companion_id": 11, "max_level": 2, "coins": 3, "items": {"1": 1}, "duplicate_source_count": 0}]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog_path = write_json(root / "evolve.json", document)
            profile = bootstrap_profile()
            state_path = root / "state.json"
            catalog = load_companion_evolution_catalog(catalog_path)

            server, thread = start_server(("127.0.0.1", 0), profile, BootstrapState(state_path), companion_evolution_catalog=catalog)
            try:
                server.state.create_account("token", "account", {"coins": 3, "itemList": [1], "buddyInfo": {"list": [{"iid": 1, "bid": 10, "lv": 2, "exp": 99, "flag": 0, "chrID": 3}], "record": []}})
                status, first = post(server, "/gd/buddy_evolve", "one", "baseID=1&lastUpdate=1")
                self.assertEqual(200, status)
                self.assertEqual((True, 0, [0], 1, 11, 1, 0), (first["success"], first["coins"], first["itemList"], first["buddyInfo"]["list"][0]["iid"], first["buddyInfo"]["list"][0]["bid"], first["buddyInfo"]["list"][0]["lv"], first["buddyInfo"]["list"][0]["exp"]))
                self.assertEqual((status, first), post(server, "/gd/buddy_evolve", "one", "baseID=1&lastUpdate=1"))
                # Reusing a spent requestID with a different body is answered on
                # its own merits: this companion has no evolution available.
                status, reused = post(server, "/gd/buddy_evolve", "one", "baseID=1")
                self.assertEqual((200, True, 3), (status, reused["success"], reused["cmdError"]))
            finally:
                stop_server(server, thread)

            restarted, restarted_thread = start_server(("127.0.0.1", 0), profile, BootstrapState(state_path), companion_evolution_catalog=catalog)
            try:
                self.assertEqual((200, first), post(restarted, "/gd/buddy_evolve", "one", "baseID=1&lastUpdate=1"))
            finally:
                stop_server(restarted, restarted_thread)


class BundledCompanionEvolutionRuntimeTest(unittest.TestCase):
    def test_bundled_recipe_is_settled_through_the_real_route(self) -> None:
        """The bundled recipes must settle a real evolution, not merely load."""
        with tempfile.TemporaryDirectory() as directory:
            profile = bootstrap_profile()
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
            server, thread = start_server(("127.0.0.1", 0), profile, state,
                                          companion_evolution_catalog=build_bundled_companion_evolution_policy())
            try:
                status, payload = post(server, "/gd/buddy_evolve", "bundled", "baseID=1&lastUpdate=1")
            finally:
                stop_server(server, thread)
            self.assertEqual(200, status)
            self.assertTrue(payload["success"], payload)
            self.assertEqual(5000, payload["coins"])
            self.assertEqual([2], [row["bid"] for row in payload["buddyInfo"]["list"]])
            self.assertEqual([5, 5, 5], [payload["itemList"][item_id - 1] for item_id in (17, 20, 24)])
