from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from liminal_gate.bootstrap_server import BootstrapState
from liminal_gate.companion_draw_catalog import build_bundled_companion_draw_policy, load_companion_draw_catalog
from tests.support import bootstrap_profile, post, start_server, stop_server, write_json


class CompanionDrawTest(unittest.TestCase):
    def test_http_draw_prefers_ticket_and_replays_after_restart(self) -> None:
        document = {"schema_version": 1, "provenance": "user-supplied", "item_slots": 1, "ticket_item_id": 1, "energy_cost": 3, "max_owned": 2, "draws": [{"companion_id": 99, "weight": 1}]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog_path = write_json(root / "draw.json", document)
            profile = bootstrap_profile()
            state_path = root / "state.json"
            catalog = load_companion_draw_catalog(catalog_path)

            body = "kind=1&count=1&campaignID=0&eventFlag=0&lastUpdate=1"
            server, thread = start_server(("127.0.0.1", 0), profile, BootstrapState(state_path), companion_draw_catalog=catalog)
            try:
                server.state.create_account("token", "account", {"coins": 0, "energy": 0, "freeEnergy": 0, "itemList": [1]})
                status, first = post(server, "/gd/do_buddy_slot", "one", body)
                self.assertEqual(200, status)
                self.assertEqual((True, [0], 0, 0, [{"bid": 99, "lv": 1}], 1), (first["success"], first["itemList"], first["energy"], first["freeEnergy"], first["result"], first["buddyInfo"]["list"][0]["iid"]))
                self.assertEqual((status, first), post(server, "/gd/do_buddy_slot", "one", body))
                # Reusing a spent requestID with a different body is answered on
                # its own merits: the paid draw has no Energy to spend.
                status, reused = post(server, "/gd/do_buddy_slot", "one", "kind=21&count=1&campaignID=0&eventFlag=0&lastUpdate=1")
                self.assertEqual((200, True, 1), (status, reused["success"], reused["cmdError"]))
            finally:
                stop_server(server, thread)

            restarted, restarted_thread = start_server(("127.0.0.1", 0), profile, BootstrapState(state_path), companion_draw_catalog=catalog)
            try:
                self.assertEqual((200, first), post(restarted, "/gd/do_buddy_slot", "one", body))
            finally:
                stop_server(restarted, restarted_thread)


class BundledCompanionDrawRuntimeTest(unittest.TestCase):
    def test_bundled_pool_draws_through_the_real_route(self) -> None:
        """The bundled pool must settle a real draw, not merely load."""
        with tempfile.TemporaryDirectory() as directory:
            profile = bootstrap_profile()
            state = BootstrapState(Path(directory) / "state.json")
            catalog = build_bundled_companion_draw_policy()
            items = [0] * 181
            items[112 - 1] = 2  # Companion Tickets, spent before any Energy
            state.create_account("token", "account", {
                "coins": 0, "energy": 0, "freeEnergy": 0, "itemList": items,
                "chrdata": [], "buddyInfo": {"list": [], "record": []},
            })
            server, thread = start_server(("127.0.0.1", 0), profile, state, companion_draw_catalog=catalog)
            try:
                status, payload = post(server, "/gd/do_buddy_slot", "bundled",
                                       "kind=1&count=1&campaignID=0&eventFlag=0&lastUpdate=1")
            finally:
                stop_server(server, thread)
            self.assertEqual(200, status)
            self.assertTrue(payload["success"], payload)
            # A ticket is consumed even though the account has no Energy at all.
            self.assertEqual(1, payload["itemList"][112 - 1])
            drawn = [row["bid"] for row in payload["buddyInfo"]["list"]]
            self.assertEqual(1, len(drawn))
            self.assertIn(drawn[0], {draw.companion_id for draw in catalog.rare_draws})

    def test_fellowship_ticket_settles_the_coin_pool_in_bulk(self) -> None:
        """`UIBarSlot` posts the Companion Coin pool's ticket batch as kind 20.

        Its ten-pull control sizes the batch from the held Item 81 count, so a
        player holding three tickets sends `count=3` and must be answered with
        three Companions off the Normal pool for three tickets.
        """
        with tempfile.TemporaryDirectory() as directory:
            profile = bootstrap_profile()
            state = BootstrapState(Path(directory) / "state.json")
            catalog = build_bundled_companion_draw_policy()
            items = [0] * 181
            items[81 - 1] = 3  # Fellowship Tickets, spent before any Coins
            state.create_account("token", "account", {
                "coins": 0, "energy": 0, "freeEnergy": 0, "itemList": items,
                "chrdata": [], "buddyInfo": {"list": [], "record": []},
            })
            server, thread = start_server(("127.0.0.1", 0), profile, state, companion_draw_catalog=catalog)
            try:
                status, payload = post(server, "/gd/do_buddy_slot", "ticket",
                                       "kind=20&count=3&campaignID=0&eventFlag=0&lastUpdate=1")
                # The exhausted batch is refused with NotEnoughCoins, and the
                # refusal spends nothing.
                spent, refused = post(server, "/gd/do_buddy_slot", "spent",
                                      "kind=20&count=1&campaignID=0&eventFlag=0&lastUpdate=1")
            finally:
                stop_server(server, thread)
            self.assertEqual((200, 200), (status, spent))
            self.assertTrue(payload["success"], payload)
            self.assertEqual((0, 0), (payload["itemList"][81 - 1], payload["coins"]))
            drawn = [row["bid"] for row in payload["buddyInfo"]["list"]]
            self.assertEqual(3, len(drawn))
            self.assertLessEqual(set(drawn), {draw.companion_id for draw in catalog.normal_draws})
            self.assertEqual(2, refused["cmdError"])

    def test_coin_pool_charges_coins_when_no_ticket_is_held(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            profile = bootstrap_profile()
            state = BootstrapState(Path(directory) / "state.json")
            catalog = build_bundled_companion_draw_policy()
            state.create_account("token", "account", {
                "coins": 6000, "energy": 0, "freeEnergy": 0, "itemList": [0] * 181,
                "chrdata": [], "buddyInfo": {"list": [], "record": []},
            })
            server, thread = start_server(("127.0.0.1", 0), profile, state, companion_draw_catalog=catalog)
            try:
                status, payload = post(server, "/gd/do_buddy_slot", "coins",
                                       "kind=0&count=2&campaignID=0&eventFlag=0&lastUpdate=1")
            finally:
                stop_server(server, thread)
            self.assertEqual(200, status)
            self.assertEqual((True, 0), (payload["success"], payload["coins"]))
            self.assertEqual(2, len(payload["buddyInfo"]["list"]))

    def test_user_supplied_catalog_refuses_the_pool_it_cannot_describe(self) -> None:
        """A schema-version-1 catalog carries no Normal pool to draw from."""
        document = {"schema_version": 1, "provenance": "user-supplied", "item_slots": 181, "ticket_item_id": 112, "energy_cost": 3, "max_owned": 10, "draws": [{"companion_id": 99, "weight": 1}]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = load_companion_draw_catalog(write_json(root / "draw.json", document))
            profile = bootstrap_profile()
            state = BootstrapState(root / "state.json")
            items = [0] * 181
            items[81 - 1] = 5
            state.create_account("token", "account", {
                "coins": 999_999, "energy": 0, "freeEnergy": 0, "itemList": items,
                "chrdata": [], "buddyInfo": {"list": [], "record": []},
            })
            server, thread = start_server(("127.0.0.1", 0), profile, state, companion_draw_catalog=catalog)
            try:
                status, _ = post(server, "/gd/do_buddy_slot", "coins",
                                 "kind=20&count=1&campaignID=0&eventFlag=0&lastUpdate=1")
            finally:
                stop_server(server, thread)
            self.assertEqual(501, status)
