"""The pre-battle Power-Up Item slot: its gate, its wire form, and its spend.

The slot is gated entirely on the `helpItemEnabled` constant -- the client
consults nothing the account owns -- so the constant and the `helpItemID` field
that becomes reachable once it is true are tested together here.
"""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import urlencode

from liminal_gate.bootstrap_parsers import _parse_generic_story_start, _parse_hunting_start
from liminal_gate.bootstrap_server import BootstrapState, help_item_debit
from liminal_gate.hunting_catalog import load_hunting_catalog
from liminal_gate.save_validation import HELP_ITEM_IDS, ITEM_SLOTS
from liminal_gate.server_constants import build_server_constants
from liminal_gate.story_catalog import load_story_catalog
from liminal_gate.world_map_special import build_bundled_world_map_special_policy
from tests.support import bootstrap_profile, request, start_server, stop_server


def inventory(**held: int) -> list[int]:
    """A full-shape inventory holding the named one-based item ids."""
    items = [0] * ITEM_SLOTS
    for item_id, count in held.items():
        items[int(item_id.removeprefix("item_")) - 1] = count
    return items


class HelpItemConstantTest(unittest.TestCase):
    def test_constants_open_the_power_up_slot(self) -> None:
        # `UITeamPopup.<Setup>` caches `IsHelpItemEnabled()`, which returns false
        # unless this key is true; an absent key hid the row for every account.
        self.assertIs(True, build_server_constants()["helpItemEnabled"])

    def test_the_accepted_ids_are_the_client_s_own_help_item_kind(self) -> None:
        # Rows 52-55 and 165/166/171/179 of `ItemSet.itemSet` carry
        # `ItemData.kind == ItemKind.HelpItem`, and item ids are one-based.
        self.assertEqual((53, 54, 55, 56, 166, 167, 172, 180), HELP_ITEM_IDS)


class HelpItemWireFormTest(unittest.TestCase):
    def test_ordinary_start_parses_with_and_without_the_field(self) -> None:
        without = _parse_generic_story_start(b"stamina=5&coins=0&chapter=8&section=1&lastUpdate=1")
        self.assertEqual(0, without["helpItemID"])
        with_item = _parse_generic_story_start(
            b"stamina=5&coins=0&helpItemID=54&chapter=8&section=1&lastUpdate=1"
        )
        self.assertEqual(54, with_item["helpItemID"])

    def test_ticket_start_parses_with_and_without_the_field(self) -> None:
        without = _parse_hunting_start(
            b"stamina=5&coins=0&itemID=50&itemCount=1&chapter=3000&section=1&lastUpdate=1"
        )
        self.assertEqual((0, 1), (without["helpItemID"], without["ticket_form"]))
        with_item = _parse_hunting_start(
            b"stamina=5&coins=0&itemID=50&itemCount=1&helpItemID=180&chapter=3000&section=1&lastUpdate=1"
        )
        self.assertEqual((180, 1), (with_item["helpItemID"], with_item["ticket_form"]))

    def test_position_is_part_of_the_contract(self) -> None:
        # The client emits the field in exactly one place in each form.
        self.assertIsNone(_parse_generic_story_start(
            b"stamina=5&coins=0&chapter=8&helpItemID=54&section=1&lastUpdate=1"
        ))
        self.assertIsNone(_parse_hunting_start(
            b"stamina=5&coins=0&helpItemID=180&itemID=50&itemCount=1&chapter=3000&section=1&lastUpdate=1"
        ))

    def test_a_declared_zero_is_not_a_form_the_client_sends(self) -> None:
        # It omits the field rather than sending zero.
        self.assertIsNone(_parse_generic_story_start(
            b"stamina=5&coins=0&helpItemID=0&chapter=8&section=1&lastUpdate=1"
        ))


class HelpItemDebitTest(unittest.TestCase):
    def test_no_choice_spends_nothing_and_reports_no_inventory(self) -> None:
        self.assertEqual(("ok", None), help_item_debit({"itemList": inventory()}, 0))

    def test_every_help_item_id_is_spendable(self) -> None:
        for item_id in HELP_ITEM_IDS:
            userdata = {"itemList": inventory(**{f"item_{item_id}": 3})}
            result, projected = help_item_debit(userdata, item_id)
            with self.subTest(item=item_id):
                self.assertEqual("ok", result)
                self.assertEqual(2, projected[item_id - 1])
                # Nothing is written until the caller commits the entry.
                self.assertEqual(3, userdata["itemList"][item_id - 1])

    def test_an_unheld_power_up_is_a_soft_refusal(self) -> None:
        self.assertEqual(("unavailable", None), help_item_debit({"itemList": inventory()}, 54))

    def test_an_id_the_slot_cannot_offer_is_a_wire_form_refusal(self) -> None:
        # 50 is the Metal Ticket and 161 is Level Candy: neither is HelpItem kind.
        userdata = {"itemList": inventory(item_50=5, item_161=5)}
        self.assertEqual(("unsupported", None), help_item_debit(userdata, 50))
        self.assertEqual(("unsupported", None), help_item_debit(userdata, 161))

    def test_an_id_past_a_narrower_inventory_is_refused_not_indexed_for(self) -> None:
        # The Hunting catalogs declare their own width.
        self.assertEqual(("unsupported", None), help_item_debit({"itemList": [0] * 8}, 180, 8))


class HelpItemStartTest(unittest.TestCase):
    """The spend as the client drives it, over the real start route."""

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.catalog_path = self.root / "story.json"
        self.catalog_path.write_text(json.dumps({
            "schema_version": 1,
            "provenance": "user-supplied",
            "stages": [{
                "chapter": 2, "section": 2, "stamina": 5, "coins": 0,
                "clear_progress_code": 16777347, "clear_coins": 30,
            }],
        }), encoding="utf-8")
        self.token = "help-item-token"
        self.account_id = "help-item-account"
        self.server, self.thread = start_server(
            ("127.0.0.1", 0), bootstrap_profile(), BootstrapState(self.root / "state.json"),
            story_catalog=load_story_catalog(self.catalog_path),
            world_map_special_catalog=build_bundled_world_map_special_policy(),
            stamina=False,
        )
        self.server.state.create_account(self.token, self.account_id, {
            "coins": 210, "worldMapNo": 0, "progressCode": 16777346,
            "chrdata": [], "itemList": inventory(item_54=2), "summonList": [],
        })
        with self.server.state.lock:
            account = self.server.state.accounts[self.account_id]
            account["tutorial_phase"] = "free_roam"
            account["initial_userdata_served"] = True
            self.server.state._persist_locked()

    def tearDown(self) -> None:
        stop_server(self.server, self.thread)
        self.temporary_directory.cleanup()

    def start(self, request_id: str, fields: list[tuple[str, str]]) -> tuple[int, dict[str, object]]:
        return request(
            self.server, "POST", f"/gd/start_quest?otk={self.token}&requestID={request_id}",
            urlencode(fields), headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    def held(self, item_id: int) -> int:
        return self.server.state.accounts[self.account_id]["userdata"]["itemList"][item_id - 1]

    def fields(self, help_item: int | None = None) -> list[tuple[str, str]]:
        chosen = [] if help_item is None else [("helpItemID", str(help_item))]
        return [
            ("stamina", "5"), ("coins", "0"), *chosen,
            ("chapter", "2"), ("section", "2"), ("lastUpdate", "1"),
        ]

    def test_a_chosen_power_up_is_debited_and_reported_back(self) -> None:
        status, started = self.start("start-with-disarmer", self.fields(54))
        self.assertEqual(200, status)
        self.assertTrue(started["success"])
        # The client overwrites its whole inventory from this list, so the one
        # it carries into the clear is the one the server just committed.
        self.assertEqual(1, started["itemList"][53])
        self.assertEqual(1, self.held(54))

    def test_a_replay_does_not_debit_twice(self) -> None:
        fields = self.fields(54)
        self.start("start-replayed", fields)
        status, replay = self.start("start-replayed", fields)
        self.assertEqual(200, status)
        self.assertEqual(1, replay["itemList"][53])
        self.assertEqual(1, self.held(54))

    def test_an_ordinary_start_reports_no_inventory_at_all(self) -> None:
        status, started = self.start("start-plain", self.fields())
        self.assertEqual(200, status)
        self.assertNotIn("itemList", started)
        self.assertEqual(2, self.held(54))

    def test_a_power_up_the_account_does_not_hold_refuses_softly(self) -> None:
        # The client greys these out, so reaching here means it asked for
        # something it was not offering; it must see its own refusal.
        # `_endpoint_refusal_envelope` hoists the code onto `cmdError`, which is
        # the field that reaches the client's own callback.
        status, started = self.start("start-unheld", self.fields(55))
        self.assertEqual((200, True, 2), (status, started["success"], started["cmdError"]))
        self.assertNotIn("itemList", started)
        self.assertEqual(2, self.held(54))
        self.assertEqual("free_roam", self.server.state.accounts[self.account_id]["tutorial_phase"])

    def test_an_id_outside_the_help_item_kind_is_refused_as_a_wire_form(self) -> None:
        status, refused = self.start("start-bad-id", self.fields(161))
        self.assertEqual(501, status)
        self.assertEqual("unsupported_start_quest", refused["error"])
        self.assertEqual(2, self.held(54))

    def test_a_world_map_special_refuses_a_power_up_outright(self) -> None:
        # `IsHelpItemEnabled` refuses on `InWMSpecial`, so the slot is hidden
        # there and no start from it can name one.
        fields = [
            ("stamina", "25"), ("coins", "0"), ("helpItemID", "54"),
            ("chapter", "1100"), ("section", "1"), ("lastUpdate", "1"),
        ]
        status, refused = self.start("start-wm-special", fields)
        self.assertEqual(501, status)
        self.assertEqual("unsupported_start_quest", refused["error"])
        self.assertEqual(2, self.held(54))


class HelpItemHuntingStartTest(unittest.TestCase):
    """The other wire form: a Huntland entry that also spends a ticket."""

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        catalog_path = self.root / "hunting.json"
        catalog_path.write_text(json.dumps({
            "schema_version": 1, "provenance": "user-supplied",
            "item_slots": ITEM_SLOTS, "max_stack": 999,
            "stages": [{
                # Metal Zone: item 50 stands in for the stamina cost.
                "family": "metal_zone", "chapter": 3000, "section": 11,
                "stamina": 4, "coins": 0, "entry_item_id": 50, "entry_item_count": 1,
                "ticket_optional": True, "selector": "metal",
                "unlock_chapter": 1, "unlock_section": 1,
                "max_coins": 0, "max_exp": 1000, "max_items_total": 0, "item_maxima": {},
            }],
        }), encoding="utf-8")
        self.token, self.account_id = "hunt-help-token", "hunt-help-account"
        self.server, self.thread = start_server(
            ("127.0.0.1", 0), bootstrap_profile(), BootstrapState(self.root / "state.json"),
            hunting_catalog=load_hunting_catalog(catalog_path),
        )
        self.server.state.create_account(self.token, self.account_id, {
            "coins": 100, "energy": 40, "freeEnergy": 2, "worldMapNo": 0,
            "progressCode": 0x01000000 | (9 << 6) | 1, "chrdata": [],
            "itemList": inventory(item_50=2, item_56=1), "summonList": [0, 0],
        })
        with self.server.state.lock:
            account = self.server.state.accounts[self.account_id]
            account["tutorial_phase"] = "free_roam"
            account["initial_userdata_served"] = True
            self.server.state._persist_locked()

    def tearDown(self) -> None:
        stop_server(self.server, self.thread)
        self.temporary_directory.cleanup()

    def test_the_ticket_and_the_power_up_are_both_debited(self) -> None:
        fields = [
            ("stamina", "4"), ("coins", "0"), ("itemID", "50"), ("itemCount", "1"),
            ("helpItemID", "56"), ("chapter", "3000"), ("section", "11"), ("lastUpdate", "1"),
        ]
        status, started = request(
            self.server, "POST", f"/gd/start_quest?otk={self.token}&requestID=hunt-help",
            urlencode(fields), headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        self.assertEqual(200, status)
        self.assertTrue(started["success"])
        # One Coin Boost and one Metal Ticket, in the same reported inventory.
        self.assertEqual(0, started["itemList"][55])
        self.assertEqual(1, started["itemList"][49])
        held = self.server.state.accounts[self.account_id]["userdata"]["itemList"]
        self.assertEqual((0, 1), (held[55], held[49]))


if __name__ == "__main__":
    unittest.main()
