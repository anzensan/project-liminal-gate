from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from http.client import HTTPConnection
from pathlib import Path

from liminal_gate.bootstrap_server import BootstrapServer, BootstrapState, load_profile
from liminal_gate.exchange_catalog import active_week_index, build_bundled_exchange_policy, load_exchange_catalog


class ExchangeTest(unittest.TestCase):
 def test_nested_get_exchange_replay_and_restart(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); cat=root/'x.json'; cat.write_text(json.dumps({'schema_version':1,'provenance':'user-supplied','item_slots':3,'max_stack':9,'max_coins':99,'weekly_item':0,'end_date':'','offers':[{'offer_id':1,'target_item_id':2,'coins':0,'target_count':1,'initial_count':1,'weekly_item_count':0,'ingredients':{'1':2}}]}))
   profile=load_profile(Path(__file__).resolve().parents[1]/'profiles/legacy-client-bootstrap.json'); state=root/'s.json'
   def start():
    s=BootstrapServer(('127.0.0.1',0),profile,BootstrapState(state),exchange_catalog=load_exchange_catalog(cat)); t=threading.Thread(target=s.serve_forever); t.start(); return s,t
   def req(s,method,path,body=None):
    c=HTTPConnection(*s.server_address); c.request(method,path,body=body); r=c.getresponse(); p=json.loads(r.read()); c.close(); return r.status,p
   s,t=start()
   try:
    s.state.create_account('token','a',{'itemList':[3,0,0],'coins':0},exchange_catalog=load_exchange_catalog(cat))
    status,got=req(s,'GET','/gd/get_current_exchange?otk=token'); self.assertEqual((200,[[1,2]]),(status,got['itemList'][0]['items'][0]['items']))
    status,done=req(s,'POST','/gd/exchange?otk=token&requestID=x', 'exchangeItemID=1&amount=1&lastUpdate=1'); self.assertEqual((200,[1,1,0]),(status,done['itemList']))
    self.assertEqual((status,done),req(s,'POST','/gd/exchange?otk=token&requestID=x','exchangeItemID=1&amount=1&lastUpdate=1'))
    # Reusing a spent requestID with a different body is answered on its own
    # merits now: this asks for more than the exchange allows.
    status,reused=req(s,'POST','/gd/exchange?otk=token&requestID=x','exchangeItemID=1&amount=2'); self.assertEqual((200,True,6),(status,reused['success'],reused['cmdError']))
   finally: s.shutdown();t.join();s.server_close()
   s,t=start()
   try: self.assertEqual((200,done),req(s,'POST','/gd/exchange?otk=token&requestID=x','exchangeItemID=1&amount=1&lastUpdate=1'))
   finally: s.shutdown();t.join();s.server_close()


class BundledTradingPostTest(unittest.TestCase):
    """The bundled rotation must browse, settle, and turn over weekly."""

    def setUp(self) -> None:
        self.catalog = build_bundled_exchange_policy()
        self.profile = load_profile(Path(__file__).resolve().parents[1] / "profiles" / "legacy-client-bootstrap.json")
        self.open_offers = self.catalog.offers_open_at(active_week_index(time.time(), self.catalog.week_count()))

    def trade(self, offer, amount: int = 1):
        with tempfile.TemporaryDirectory() as directory:
            state = BootstrapState(Path(directory) / "state.json")
            items = [0] * 181
            items[181 - 1] = 20000  # Animata Core, the only cost in this rotation
            state.create_account("token", "account", {
                "coins": 0, "itemList": items, "chrdata": [],
                "buddyInfo": {"list": [], "record": []},
            })
            server = BootstrapServer(("127.0.0.1", 0), self.profile, state, exchange_catalog=self.catalog)
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            try:
                connection = HTTPConnection(*server.server_address)
                connection.request("POST", "/gd/exchange?otk=token&requestID=bundled",
                                   body=f"exchangeItemID={offer.offer_id}&amount={amount}&lastUpdate=1")
                response = connection.getresponse()
                payload = json.loads(response.read())
                connection.close()
                connection = HTTPConnection(*server.server_address)
                connection.request("GET", "/gd/get_current_exchange?otk=token")
                browse = json.loads(connection.getresponse().read())
                connection.close()
            finally:
                server.shutdown(); thread.join(); server.server_close()
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


class RotatedTokenReadTest(unittest.TestCase):
    """Authenticated reads must survive the client's three-second OTK rotation.

    The live save that exposed this had a bound host and 83 recorded tokens:
    the browse request still arrived on a value none of them matched, because
    it was minted after the last mutation, and the counter answered 401.
    """

    def setUp(self) -> None:
        self.profile = load_profile(Path(__file__).resolve().parents[1] / "profiles" / "legacy-client-bootstrap.json")
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
        self.server = BootstrapServer(("127.0.0.1", 0), self.profile, state,
                                      exchange_catalog=build_bundled_exchange_policy())
        thread = threading.Thread(target=self.server.serve_forever)
        thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(thread.join)
        self.addCleanup(self.server.shutdown)

    def get(self, path: str) -> tuple[int, dict]:
        connection = HTTPConnection(*self.server.server_address)
        connection.request("GET", path)
        response = connection.getresponse()
        payload = json.loads(response.read())
        connection.close()
        return response.status, payload

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
        self.profile = load_profile(Path(__file__).resolve().parents[1] / "profiles" / "legacy-client-bootstrap.json")
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
            server = BootstrapServer(("127.0.0.1", 0), self.profile, state, exchange_catalog=self.catalog)
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            try:
                connection = HTTPConnection(*server.server_address)
                connection.request("POST", "/gd/exchange?otk=token&requestID=refused",
                                   body=f"exchangeItemID={self.offer.offer_id}&amount=1&lastUpdate=1")
                response = connection.getresponse()
                payload = json.loads(response.read())
                connection.close()
            finally:
                server.shutdown(); thread.join(); server.server_close()
        self.assertEqual(200, response.status)
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
