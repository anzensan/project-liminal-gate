from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from liminal_gate.bootstrap_server import BootstrapState
from liminal_gate.companion_catalog import build_bundled_companion_policy, load_companion_catalog
from tests.support import bootstrap_profile, post, running_server, start_server, stop_server, write_json


class CompanionSaleTest(unittest.TestCase):
    def test_http_single_and_batch_sale_are_replay_safe(self) -> None:
        document = {"schema_version": 1, "provenance": "user-supplied", "coin_cap": 50, "masters": [{"companion_id": 10, "base_coins": 3}, {"companion_id": 11, "base_coins": 5}]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog_path = write_json(root / "companions.json", document)
            profile = bootstrap_profile()
            state_path = root / "state.json"
            catalog = load_companion_catalog(catalog_path)

            server, thread = start_server(("127.0.0.1", 0), profile, BootstrapState(state_path), companion_catalog=catalog)
            try:
                server.state.create_account("token", "account", {
                    "coins": 1,
                    "chrdata": [{"id": 3, "buddy": 1}],
                    "buddyInfo": {"list": [
                        {"iid": 1, "bid": 10, "lv": 2, "flag": 0, "chrID": 3},
                        {"iid": 2, "bid": 11, "lv": 1, "flag": 0, "chrID": 0},
                        {"iid": 3, "bid": 10, "lv": 1, "flag": 2, "chrID": 0},
                    ], "record": []},
                })
                # The client's shared mutation POST helper appends lastUpdate
                # to every body, so this is the form every real sale arrives
                # in; test_trailing_lastupdate_field_is_accepted below pins the
                # regression that once refused it.
                status, first = post(server, "/gd/sell_buddy", "one", "inventoryID=1&lastUpdate=1")
                self.assertEqual(200, status)
                self.assertEqual((True, 7, [2, 3], 0), (first["success"], first["coins"], [row["iid"] for row in first["buddyInfo"]["list"]], first["chrdata"][0]["buddy"]))
                self.assertEqual((status, first), post(server, "/gd/sell_buddy", "one", "inventoryID=1&lastUpdate=1"))
                # Reusing a spent requestID with a different body is answered on
                # its own merits now.  This names a companion the account does
                # not own, so it is refused for that reason and leaves the
                # inventory intact for the locked and batch cases below.
                status, reused = post(server, "/gd/sell_buddy", "one", "inventoryID=99&lastUpdate=1")
                self.assertEqual((200, True, 2), (status, reused["success"], reused["cmdError"]))
                status, locked = post(server, "/gd/sell_buddy", "two", "inventoryID=3&lastUpdate=1")
                self.assertEqual((200, True, 2), (status, locked["success"], locked["cmdError"]))
                status, batch = post(server, "/gd/sell_buddies", "three", "sellList=[2]&lastUpdate=1")
                self.assertEqual((200, True, 12, [3]), (status, batch["success"], batch["coins"], [row["iid"] for row in batch["buddyInfo"]["list"]]))
            finally:
                stop_server(server, thread)

            restarted, restarted_thread = start_server(("127.0.0.1", 0), profile, BootstrapState(state_path), companion_catalog=catalog)
            try:
                self.assertEqual((200, first), post(restarted, "/gd/sell_buddy", "one", "inventoryID=1&lastUpdate=1"))
            finally:
                stop_server(restarted, restarted_thread)

    def test_trailing_lastupdate_field_is_accepted(self) -> None:
        """A real sell request was refused as unsupported_companion_sale.

        The client sends `sellList`/`inventoryID` with a trailing `lastUpdate`
        on every call, the same as every other mutation. The parser demanded
        the sale field alone, so every real sale -- one companion or a batch --
        was refused with a 501 the client shows as a Network Error (issue #40).
        The earlier coverage only ever posted the bare field, which is why the
        gap survived.
        """
        document = {"schema_version": 1, "provenance": "user-supplied", "coin_cap": 50, "masters": [{"companion_id": 10, "base_coins": 3}]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = load_companion_catalog(write_json(root / "companions.json", document))
            with running_server(("127.0.0.1", 0), bootstrap_profile(), BootstrapState(root / "state.json"), companion_catalog=catalog) as server:
                server.state.create_account("token", "account", {
                    "coins": 0, "chrdata": [],
                    "buddyInfo": {"list": [
                        {"iid": 1, "bid": 10, "lv": 1, "flag": 0, "chrID": 0},
                        {"iid": 2, "bid": 10, "lv": 1, "flag": 0, "chrID": 0},
                    ], "record": []},
                })
                status, payload = post(server, "/gd/sell_buddies", "all", "sellList=[1,2]&lastUpdate=1")
            self.assertEqual(200, status)
            self.assertTrue(payload["success"], payload)
            self.assertEqual(6, payload["coins"])
            self.assertEqual([], payload["buddyInfo"]["list"])


class BundledCompanionSaleRuntimeTest(unittest.TestCase):
    def test_bundled_values_are_paid_through_the_real_route(self) -> None:
        """The bundled masters must settle a real sale, not merely load."""
        with tempfile.TemporaryDirectory() as directory:
            profile = bootstrap_profile()
            state = BootstrapState(Path(directory) / "state.json")
            # Master 3's base value is 400, so a level 7 instance pays 2800.
            state.create_account("token", "account", {
                "coins": 100, "chrdata": [],
                "buddyInfo": {"list": [{"iid": 1, "bid": 3, "lv": 7, "exp": 0, "flag": 0, "chrID": 0}], "record": []},
            })
            server, thread = start_server(("127.0.0.1", 0), profile, state, companion_catalog=build_bundled_companion_policy())
            try:
                status, payload = post(server, "/gd/sell_buddy", "bundled", "inventoryID=1&lastUpdate=1")
            finally:
                stop_server(server, thread)
            self.assertEqual(200, status)
            self.assertTrue(payload["success"], payload)
            self.assertEqual(2900, payload["coins"])
            self.assertEqual([], payload["buddyInfo"]["list"])
