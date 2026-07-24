import hashlib,json,tempfile,unittest
from pathlib import Path
from liminal_gate.event_catalog import load_event_catalog,EventCatalogError
class EventCatalogTest(unittest.TestCase):
 def test_local_event_grant_matches_catalog(self):
  with tempfile.TemporaryDirectory() as d:
   r=Path(d); c=r/'c.json'; e=r/'e.json'; c.write_text(json.dumps({'characters':[{'character_id':3}]})); e.write_text(json.dumps({'schema_version':1,'provenance':'user-supplied','character_catalog_sha256':hashlib.sha256(c.read_bytes()).hexdigest(),'stages':[{'event_id':'test','flag':'sp_test','chapter':2000,'section':1,'stamina':1,'coins':0,'clear_coins':0,'character_ids':[3]}]})); self.assertEqual((3,),load_event_catalog(e,c).stages[0].character_ids)
