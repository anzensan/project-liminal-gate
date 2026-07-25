from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

from liminal_gate.bootstrap_server import BootstrapServer, BootstrapState, load_profile
from liminal_gate.exchange_catalog import build_bundled_exchange_policy, load_exchange_catalog


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
    status,reused=req(s,'POST','/gd/exchange?otk=token&requestID=x','exchangeItemID=1&amount=2'); self.assertEqual((200,False,6),(status,reused['success'],reused['errorCode']))
   finally: s.shutdown();t.join();s.server_close()
   s,t=start()
   try: self.assertEqual((200,done),req(s,'POST','/gd/exchange?otk=token&requestID=x','exchangeItemID=1&amount=1&lastUpdate=1'))
   finally: s.shutdown();t.join();s.server_close()


class BundledTradingPostTest(unittest.TestCase):
    """The bundled rotation must browse and settle both kinds of offer."""

    def setUp(self) -> None:
        self.catalog = build_bundled_exchange_policy()
        self.profile = load_profile(Path(__file__).resolve().parents[1] / "profiles" / "legacy-client-bootstrap.json")

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

    def test_every_offer_awards_exactly_one_kind_of_reward(self) -> None:
        self.assertEqual(99, len(self.catalog.offers))
        for offer_id, offer in self.catalog.offers.items():
            with self.subTest(offer_id=offer_id):
                self.assertNotEqual(bool(offer.target_item_id), bool(offer.target_buddy_id))
                self.assertTrue(offer.ingredients)
        self.assertEqual(78, sum(1 for o in self.catalog.offers.values() if o.target_buddy_id))
        self.assertEqual(21, sum(1 for o in self.catalog.offers.values() if o.target_item_id))

    def test_a_companion_offer_mints_into_the_box(self) -> None:
        offer = next(o for o in self.catalog.offers.values() if o.target_buddy_id)
        payload, browse = self.trade(offer)
        self.assertTrue(payload["success"], payload)
        owned = payload["buddyInfo"]["list"]
        self.assertEqual([(offer.target_buddy_id, 1)], [(row["bid"], row["lv"]) for row in owned])
        self.assertEqual(20000 - offer.ingredients[181], payload["itemList"][181 - 1])
        # The browse render must carry the Companion target, not a zero.
        rendered = next(row for row in browse["itemList"][0]["items"] if row["ID"] == offer.offer_id)
        self.assertEqual((0, offer.target_buddy_id), (rendered["targetItemID"], rendered["targetBuddyID"]))

    def test_an_item_offer_still_settles_into_the_inventory(self) -> None:
        offer = next(o for o in self.catalog.offers.values() if o.target_item_id)
        payload, _ = self.trade(offer)
        self.assertTrue(payload["success"], payload)
        self.assertEqual(offer.target_count, payload["itemList"][offer.target_item_id - 1])
        self.assertEqual([], payload["buddyInfo"]["list"])

    def test_stock_is_the_rotation_limit_and_exhausts(self) -> None:
        offer = next(o for o in self.catalog.offers.values() if o.target_buddy_id and o.initial_count == 1)
        payload, _ = self.trade(offer, amount=2)
        # Asking for more than the rotation stocks is refused, not clamped.
        self.assertEqual((False, 6), (payload["success"], payload["errorCode"]))
