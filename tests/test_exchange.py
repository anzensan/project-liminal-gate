from __future__ import annotations
import json
from http.client import HTTPConnection
from pathlib import Path
import tempfile, threading, unittest
from liminal_gate.bootstrap_server import BootstrapServer, BootstrapState, load_profile
from liminal_gate.exchange_catalog import load_exchange_catalog

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
    status,collision=req(s,'POST','/gd/exchange?otk=token&requestID=x','exchangeItemID=1&amount=2'); self.assertEqual((409,'request_collision'),(status,collision['error']))
   finally: s.shutdown();t.join();s.server_close()
   s,t=start()
   try: self.assertEqual((200,done),req(s,'POST','/gd/exchange?otk=token&requestID=x','exchangeItemID=1&amount=1&lastUpdate=1'))
   finally: s.shutdown();t.join();s.server_close()
