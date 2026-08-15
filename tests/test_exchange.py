from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path

from liminal_gate.bootstrap_server import BootstrapState
from liminal_gate.exchange_catalog import active_week_index, build_bundled_exchange_policy, load_exchange_catalog
from tests.support import bootstrap_profile, get, post, request, start_server, stop_server


class ExchangeTest(unittest.TestCase):
 def test_nested_get_exchange_replay_and_restart(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); cat=root/'x.json'; cat.write_text(json.dumps({'schema_version':1,'provenance':'user-supplied','item_slots':3,'max_stack':9,'max_coins':99,'weekly_item':0,'end_date':'','offers':[{'offer_id':1,'target_item_id':2,'coins':0,'target_count':1,'initial_count':1,'weekly_item_count':0,'ingredients':{'1':2}}]}))
   profile=bootstrap_profile(); state=root/'s.json'
   def start():
    return start_server(('127.0.0.1',0),profile,BootstrapState(state),exchange_catalog=load_exchange_catalog(cat))
   def req(s,method,path,body=None):
    return request(s,method,path,body)
   s,t=start()
   try:
    s.state.create_account('token','a',{'itemList':[3,0,0],'coins':0},exchange_catalog=load_exchange_catalog(cat))
    status,got=req(s,'GET','/gd/get_current_exchange?otk=token'); self.assertEqual((200,[[1,2]]),(status,got['itemList'][0]['items'][0]['items']))
    status,done=req(s,'POST','/gd/exchange?otk=token&requestID=x', 'exchangeItemID=1&amount=1&lastUpdate=1'); self.assertEqual((200,[1,1,0]),(status,done['itemList']))
    self.assertEqual((status,done),req(s,'POST','/gd/exchange?otk=token&requestID=x','exchangeItemID=1&amount=1&lastUpdate=1'))
    # Reusing a spent requestID with a different body is answered on its own
    # merits now: this asks for more than the exchange allows.
    status,reused=req(s,'POST','/gd/exchange?otk=token&requestID=x','exchangeItemID=1&amount=2'); self.assertEqual((200,True,6),(status,reused['success'],reused['cmdError']))
   finally: stop_server(s,t)
   s,t=start()
   try: self.assertEqual((200,done),req(s,'POST','/gd/exchange?otk=token&requestID=x','exchangeItemID=1&amount=1&lastUpdate=1'))
   finally: stop_server(s,t)


class BundledTradingPostTest(unittest.TestCase):
    """The bundled rotation must browse, settle, and turn over weekly."""

    def setUp(self) -> None:
        self.catalog = build_bundled_exchange_policy()
        self.profile = bootstrap_profile()
        self.open_offers = self.catalog.offers_open_at(active_week_index(time.time(), self.catalog.week_count()))

    def trade(self, offer, amount: int = 1, holdings: list[int] | None = None):
        with tempfile.TemporaryDirectory() as directory:
            state = BootstrapState(Path(directory) / "state.json")
            items = [0] * 181 if holdings is None else list(holdings)
            if holdings is None:
                items[181 - 1] = 20000  # Animata Core, the only cost in this rotation
            state.create_account("token", "account", {
                "coins": 0, "itemList": items, "chrdata": [],
                "buddyInfo": {"list": [], "record": []},
            })
            server, thread = start_server(("127.0.0.1", 0), self.profile, state, exchange_catalog=self.catalog)
            try:
                _, payload = post(server, "/gd/exchange", "bundled",
                                  f"exchangeItemID={offer.offer_id}&amount={amount}&lastUpdate=1")
                _, browse = get(server, "/gd/get_current_exchange?otk=token")
            finally:
                stop_server(server, thread)
            return payload, browse

    def test_the_rotation_is_eight_weeks_of_single_reward_offers(self) -> None:
        self.assertEqual(126, len(self.catalog.offers))
        self.assertEqual(8, self.catalog.week_count())
        for offer_id, offer in self.catalog.offers.items():
            with self.subTest(offer_id=offer_id):
                self.assertNotEqual(bool(offer.target_item_id), bool(offer.target_buddy_id))
                self.assertTrue(offer.ingredients)
        self.assertEqual(92, sum(1 for o in self.catalog.offers.values() if o.target_buddy_id))
        self.assertEqual(34, sum(1 for o in self.catalog.offers.values() if o.target_item_id))

    def test_each_week_opens_its_own_offers_and_the_cycle_repeats(self) -> None:
        weeks = [frozenset(self.catalog.offers_open_at(index)) for index in range(8)]
        self.assertEqual(8, len(set(weeks)), "each week must open a distinct set")
        self.assertEqual(set(self.catalog.offers), set().union(*weeks))
        # Week 8 is week 0 again: the rotation cycles rather than ending.
        self.assertEqual(weeks[0], frozenset(self.catalog.offers_open_at(8)))
        # It turns over weekly, on the same weekday each time, anchored to the
        # community-dated phase: week 0 opened with version 5.5.0 (its Friday
        # boundary was 2018-10-05) and reopened on Friday 2018-11-30 when the
        # wiki's live edit trail recorded "Rotation finished".
        friday = 1_538_697_600  # 2018-10-05 00:00 UTC
        self.assertEqual(0, active_week_index(friday, 8))
        self.assertEqual(0, active_week_index(friday + 604799, 8))
        self.assertEqual(1, active_week_index(friday + 604800, 8))
        self.assertEqual(0, active_week_index(friday + 604800 * 8, 8))
        # 2018-11-30 00:00 UTC is exactly eight weeks on: week 0 again.
        self.assertEqual(0, active_week_index(1_543_536_000, 8))

    def test_a_companion_offer_mints_into_the_box(self) -> None:
        offer = next(o for o in self.open_offers.values() if o.target_buddy_id)
        payload, browse = self.trade(offer)
        self.assertTrue(payload["success"], payload)
        owned = payload["buddyInfo"]["list"]
        self.assertEqual([(offer.target_buddy_id, 1)], [(row["bid"], row["lv"]) for row in owned])
        self.assertEqual(20000 - offer.ingredients[181], payload["itemList"][181 - 1])
        rendered = next(row for row in browse["itemList"][0]["items"] if row["ID"] == offer.offer_id)
        self.assertEqual((0, offer.target_buddy_id), (rendered["targetItemID"], rendered["targetBuddyID"]))

    def test_an_item_offer_still_settles_into_the_inventory(self) -> None:
        offer = next(o for o in self.open_offers.values() if o.target_item_id)
        payload, _ = self.trade(offer)
        self.assertTrue(payload["success"], payload)
        self.assertEqual(offer.target_count, payload["itemList"][offer.target_item_id - 1])
        self.assertEqual([], payload["buddyInfo"]["list"])

    def test_only_this_week_is_browsable_and_tradable(self) -> None:
        closed = next(o for o in self.catalog.offers.values() if o.offer_id not in self.open_offers)
        payload, browse = self.trade(closed)
        # Trading it is refused the same way any unknown offer is: the client
        # can only have asked for something that is not on the counter.
        self.assertEqual("invalid_local_exchange", payload["error"])
        listed = {row["ID"] for row in browse["itemList"][0]["items"]}
        self.assertEqual(set(self.open_offers), listed)
        self.assertNotIn(closed.offer_id, listed)

    def test_stock_is_the_rotation_limit_and_exhausts(self) -> None:
        offer = next(o for o in self.open_offers.values() if o.initial_count == 1)
        payload, _ = self.trade(offer, amount=2)
        self.assertEqual((True, 6), (payload["success"], payload["cmdError"]))

    def test_a_cost_spends_animata_core_first_and_then_the_older_items(self) -> None:
        """The nine Animata items are one purse, in the client's own order.

        A player who ran the Core down and still holds thousands of the retired
        Animata items was refused with "Not enough items." at a counter showing
        the retired ones right beside the Core, because only the Core was ever
        charged. `UIExchange.ExchangeItemIDs` lists all nine with the Core
        first, and the rotation record says the older items "will be used after
        Animata Core".
        """
        offer = next(o for o in self.open_offers.values()
                     if o.target_item_id and o.ingredients.get(181))
        cost = offer.ingredients[181]
        holdings = [0] * 181
        # Exactly one Core short of the price, with the remainder in Eggs.
        holdings[181 - 1] = cost - 1
        holdings[124 - 1] = 500
        payload, _ = self.trade(offer, holdings=holdings)
        # An accepted trade carries no `cmdError` at all; only a refusal does.
        self.assertEqual((True, 0), (payload["success"], payload.get("cmdError", 0)), payload)
        self.assertEqual(0, payload["itemList"][181 - 1], "Core is spent first")
        self.assertEqual(499, payload["itemList"][124 - 1], "the shortfall comes from Eggs")
        self.assertEqual(offer.target_count, payload["itemList"][offer.target_item_id - 1])

    def test_a_cost_no_animata_can_cover_is_still_refused(self) -> None:
        """Pooling widens what can pay, never what a holding is worth."""
        offer = next(o for o in self.open_offers.values()
                     if o.target_item_id and o.ingredients.get(181))
        cost = offer.ingredients[181]
        holdings = [0] * 181
        # One short across the whole purse, spread over two of the nine.
        holdings[181 - 1] = cost - 2
        holdings[131 - 1] = 1
        payload, _ = self.trade(offer, holdings=holdings)
        self.assertEqual((True, 3), (payload["success"], payload["cmdError"]))

    def test_an_operator_catalog_is_charged_only_what_it_names(self) -> None:
        """Pooling is the recovered rotation's, not a rule for every catalog."""
        catalog = build_bundled_exchange_policy()
        self.assertEqual((181, 124, 125, 126, 127, 128, 129, 130, 131), catalog.currency_order)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "offers.json"
            path.write_text(json.dumps({
                "schema_version": 1, "provenance": "user-supplied", "item_slots": 3,
                "max_stack": 99, "max_coins": 99, "weekly_item": 0, "end_date": "",
                "offers": [{"offer_id": 1, "target_item_id": 3, "coins": 0,
                            "target_count": 1, "initial_count": 1,
                            "weekly_item_count": 0, "ingredients": {"1": 2}}],
            }))
            authored = load_exchange_catalog(path)
        self.assertEqual((), authored.currency_order)
        offer = authored.offers[1]
        # Holding the other item instead pays nothing towards this cost.
        self.assertIsNone(authored.payment_plan(offer, 1, [1, 50, 0]))
        self.assertEqual({1: 2}, authored.payment_plan(offer, 1, [2, 50, 0]))


class RotatedTokenReadTest(unittest.TestCase):
    """Authenticated reads must survive the client's three-second OTK rotation.

    The live save that exposed this had a bound host and 83 recorded tokens:
    the browse request still arrived on a value none of them matched, because
    it was minted after the last mutation, and the counter answered 401.
    """

    def setUp(self) -> None:
        self.profile = bootstrap_profile()
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        state = BootstrapState(Path(self.directory.name) / "state.json")
        items = [0] * 181
        items[181 - 1] = 20000
        # The host is recorded exactly as signup/login records it, so the
        # ownership branch — not the legacy no-host fallback — is what answers.
        state.create_account("login-token", "account", {
            "coins": 0, "itemList": items, "chrdata": [],
            "buddyInfo": {"list": [], "record": []},
        }, exchange_catalog=build_bundled_exchange_policy(), client_host="127.0.0.1")
        self.server, thread = start_server(("127.0.0.1", 0), self.profile, state,
                                           exchange_catalog=build_bundled_exchange_policy())
        self.addCleanup(stop_server, self.server, thread)

    def get(self, path: str) -> tuple[int, dict]:
        return get(self.server, path)

    def test_the_trading_post_opens_on_a_token_no_mutation_bound(self) -> None:
        status, payload = self.get("/gd/get_current_exchange?otk=ROTATED0000000A")
        self.assertEqual(200, status, payload)
        self.assertTrue(payload["success"])
        self.assertTrue(payload["itemList"][0]["items"])

    def test_a_resume_read_survives_the_same_rotation(self) -> None:
        status, payload = self.get("/gd/userdata_after_close?otk=ROTATED0000000B")
        self.assertEqual(200, status, payload)
        self.assertTrue(payload["success"])

    def test_an_unidentified_host_is_still_refused(self) -> None:
        # Binding by host must not become "any token opens the counter": the
        # household guard is the whole reason the raw lookup was there.
        self.server.state.client_hosts["10.0.0.9"] = "other-account"
        status, payload = self.get("/gd/get_current_exchange?otk=ROTATED0000000C")
        self.assertEqual(200, status, payload)
        del self.server.state.client_hosts["127.0.0.1"]
        status, payload = self.get("/gd/get_current_exchange?otk=ROTATED0000000D")
        self.assertEqual((401, "unknown_account"), (status, payload["error"]))


class RefusalEnvelopeTest(unittest.TestCase):
    """A refused trade must reach the counter, not the common error dialog.

    `errorCode` is the transport namespace (1, 90, 100-115) and is only read
    when `success` is false — a path that shows the shared dialog and never
    invokes the endpoint callback. A route's own code rides `cmdError` on an
    accepted success. See `reports/response_verifier.md` in the research repo.
    """

    def setUp(self) -> None:
        self.catalog = build_bundled_exchange_policy()
        self.profile = bootstrap_profile()
        self.offer = next(iter(self.catalog.offers_open_at(
            active_week_index(time.time(), self.catalog.week_count())).values()))

    def test_a_trade_you_cannot_afford_rides_cmdError(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = BootstrapState(Path(directory) / "state.json")
            # One short of the price: the refusal is correct, only its
            # delivery was not.
            items = [0] * 181
            items[181 - 1] = self.offer.ingredients[181] - 1
            state.create_account("token", "account", {
                "coins": 0, "itemList": items, "chrdata": [],
                "buddyInfo": {"list": [], "record": []},
            })
            server, thread = start_server(("127.0.0.1", 0), self.profile, state, exchange_catalog=self.catalog)
            try:
                status, payload = post(server, "/gd/exchange", "refused",
                                       f"exchangeItemID={self.offer.offer_id}&amount=1&lastUpdate=1")
            finally:
                stop_server(server, thread)
        self.assertEqual(200, status)
        # NotEnoughItems, on the field the endpoint callback actually reads.
        self.assertEqual((True, 3), (payload["success"], payload["cmdError"]))
        self.assertNotIn("errorCode", payload)
        # Nothing was spent, and the guarded refresh fields stay absent so the
        # client keeps the state it already has.
        self.assertNotIn("itemList", payload)
        self.assertNotIn("buddyInfo", payload)

    def test_the_counter_names_the_currency_it_charges(self) -> None:
        # `UIExchange.UpdateOwnCount` counts how many of `weeklyItem` you hold
        # and files every other exchange currency under a "(+n)" remainder.
        # Sending 0 named no item, so the header read "0 (+n)" at a counter
        # that only ever charges Animata Cores.
        self.assertEqual(181, self.catalog.weekly_item)
        self.assertEqual({181}, {item for o in self.catalog.offers.values() for item in o.ingredients})
