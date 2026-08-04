from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from liminal_gate.bootstrap_server import BootstrapState
from liminal_gate.companion_strengthen_catalog import build_bundled_companion_strengthen_policy, load_companion_strengthen_catalog
from tests.support import bootstrap_profile, post, start_server, stop_server, write_json


class CompanionStrengthenTest(unittest.TestCase):
    def test_http_strengthen_consumes_material_and_replays_after_restart(self) -> None:
        document = {"schema_version": 1, "provenance": "user-supplied", "same_companion_multiplier": 2, "byebye_companion_id": None, "byebye_multiplier_percent": 150, "bonus_weights": [{"percent": 0, "weight": 1}], "masters": [{"companion_id": 10, "base_exp": 1, "max_level": 2, "exp_max": 100, "exp_coeff": 1, "same_bonus_bias": 1}, {"companion_id": 11, "base_exp": 100, "max_level": 2, "exp_max": 100, "exp_coeff": 1, "same_bonus_bias": 1}]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog_path = write_json(root / "strengthen.json", document)
            profile = bootstrap_profile()
            state_path = root / "state.json"
            catalog = load_companion_strengthen_catalog(catalog_path)

            server, thread = start_server(("127.0.0.1", 0), profile, BootstrapState(state_path), companion_strengthen_catalog=catalog)
            try:
                server.state.create_account("token", "account", {"coins": 100, "chrdata": [{"id": 3, "buddy": 2}], "buddyInfo": {"list": [{"iid": 1, "bid": 10, "lv": 1, "exp": 0, "flag": 0}, {"iid": 2, "bid": 11, "lv": 1, "exp": 0, "flag": 0, "chrID": 3}], "record": []}})
                status, first = post(server, "/gd/buddy_strengthen", "one", "baseID=1&matList=[2]")
                self.assertEqual(200, status)
                self.assertEqual((True, 50, 100, 0, 0, [1], 0), (first["success"], first["coins"], first["totalEXP"], first["additionalEXP"], first["expBonus"], [row["iid"] for row in first["buddyInfo"]["list"]], first["chrdata"][0]["buddy"]))
                self.assertEqual(2, first["buddyInfo"]["list"][0]["lv"])
                self.assertEqual((status, first), post(server, "/gd/buddy_strengthen", "one", "baseID=1&matList=[2]"))
                # Reusing a spent requestID with a different body is no longer
                # read as a tampered retry; feeding a companion to itself is
                # rejected on its own merits.
                self.assertEqual((501, "unsupported_companion_strengthen"), (post(server, "/gd/buddy_strengthen", "one", "baseID=1&matList=[1]")[0], post(server, "/gd/buddy_strengthen", "one", "baseID=1&matList=[1]")[1]["error"]))
                server.state.create_account("other", "other-account", {"coins": 100, "buddyInfo": {"list": [{"iid": 4, "bid": 10, "lv": 1, "exp": 0, "flag": 0}, {"iid": 5, "bid": 11, "lv": 1, "exp": 0, "flag": 2}], "record": []}})
                # Production signup/login identifies which LAN client owns this
                # account before a rotated token can mutate it.
                server.state.bind_login_token("other", "other-account", "127.0.0.1")
                status, favorite = post(server, "/gd/buddy_strengthen", "favorite", "baseID=4&matList=[5]", "other")
                self.assertEqual((200, True, 6), (status, favorite["success"], favorite["cmdError"]))
                self.assertEqual([4, 5], [row["iid"] for row in server.state.userdata_for("other")["buddyInfo"]["list"]])
            finally:
                stop_server(server, thread)

            restarted, restarted_thread = start_server(("127.0.0.1", 0), profile, BootstrapState(state_path), companion_strengthen_catalog=catalog)
            try:
                # The same emulator last logged into other-account above.
                # Logging back in restores ownership before this account's
                # durable replay is requested.
                restarted.state.bind_login_token("token", "account", "127.0.0.1")
                self.assertEqual((200, first), post(restarted, "/gd/buddy_strengthen", "one", "baseID=1&matList=[2]"))
            finally:
                stop_server(restarted, restarted_thread)


class BundledCompanionStrengthenRuntimeTest(unittest.TestCase):
    def test_bundled_progression_is_applied_through_the_real_route(self) -> None:
        """The bundled masters must settle a real strengthen, not merely load."""
        with tempfile.TemporaryDirectory() as directory:
            profile = bootstrap_profile()
            state = BootstrapState(Path(directory) / "state.json")
            catalog = build_bundled_companion_strengthen_policy()
            # Master 1's base EXP is 671 with a same-Companion bias of 1, so a
            # level 5 material of the same master is worth 5 * 671 * 2.
            state.create_account("token", "account", {
                "coins": 100000, "chrdata": [],
                "buddyInfo": {"list": [
                    {"iid": 1, "bid": 1, "lv": 1, "exp": 0, "flag": 0, "chrID": 0},
                    {"iid": 2, "bid": 1, "lv": 5, "exp": 0, "flag": 0, "chrID": 0},
                ], "record": []},
            })
            server, thread = start_server(("127.0.0.1", 0), profile, state, companion_strengthen_catalog=catalog)
            try:
                status, payload = post(server, "/gd/buddy_strengthen", "bundled",
                                       "baseID=1&matList=[2]&lastUpdate=1")
            finally:
                stop_server(server, thread)
            self.assertEqual(200, status)
            self.assertEqual(6710, payload["totalEXP"])
            self.assertIn(payload["expBonus"], {percent for percent, _ in catalog.bonus_weights})
