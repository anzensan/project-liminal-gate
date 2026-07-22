from __future__ import annotations

import json
from http.client import HTTPConnection
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.parse import urlencode

from liminal_gate.bootstrap_server import BootstrapServer, BootstrapState, load_profile
from liminal_gate.message_catalog import load_message_catalog


class MessageLifecycleTest(unittest.TestCase):
    def test_login_read_delete_collision_and_restart_replay(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog_path = root / "messages.toml"
            catalog_path.write_text(
                'schema_version = 1\nprovenance = "user-supplied"\nitem_slots = 3\nmax_free_energy = 9\nmax_coins = 99\nmax_stack = 8\n\n[[messages]]\nid = "local-1"\ndate = 1.0\ndays_last = 0\nmessages = { default = "Local message", ja = "Local message", en = "Local message" }\ncoins = 3\nfree_energy = 2\nitems = { "2" = 4 }\n',
                encoding="utf-8",
            )
            profile = load_profile(Path(__file__).resolve().parents[1] / "profiles" / "legacy-client-bootstrap.json")
            state_path = root / "state.json"

            def start() -> tuple[BootstrapServer, threading.Thread]:
                server = BootstrapServer(("127.0.0.1", 0), profile, BootstrapState(state_path), message_catalog=load_message_catalog(catalog_path))
                thread = threading.Thread(target=server.serve_forever)
                thread.start()
                return server, thread

            def get(server: BootstrapServer, path: str) -> tuple[int, dict[str, object]]:
                connection = HTTPConnection(*server.server_address); connection.request("GET", path); response = connection.getresponse(); payload = json.loads(response.read()); connection.close(); return response.status, payload

            def post(server: BootstrapServer, route: str, request_id: str, body: str) -> tuple[int, dict[str, object]]:
                connection = HTTPConnection(*server.server_address); connection.request("POST", f"/gd/{route}?otk=token&requestID={request_id}", body=body); response = connection.getresponse(); payload = json.loads(response.read()); connection.close(); return response.status, payload

            server, thread = start()
            try:
                server.state.create_account("signup", "account", {"chrdata": [], "buddyInfo": {"list": [], "record": []}, "summonList": [0] * 16, "itemList": [0, 1, 0], "coins": 2, "freeEnergy": 1, "energy": 7, "energyAppStore": 4, "energyGooglePlay": 5, "energyAndApp": 6}, load_message_catalog(catalog_path))
                status, login = get(server, "/gd/login?otk=token&uuid=account")
                self.assertEqual(200, status)
                message = login["messageList"][0]
                self.assertEqual({"id", "date", "read", "daysLast", "gifts", "coins", "energy", "chr", "item", "summon", "buddy", "title", "messages"}, set(message))
                self.assertEqual(("local-1", False, [{"id": 2, "num": 4}]), (message["id"], message["read"], message["item"]))
                read_body = urlencode({"idlist": json.dumps(["local-1"]), "lastUpdate": "1"})
                status, before_read = post(server, "delete_messages", "delete-before", read_body)
                self.assertEqual((409, "invalid_local_message"), (status, before_read["error"]))
                status, read = post(server, "read_messages", "read-one", read_body)
                self.assertEqual(200, status)
                self.assertEqual((True, ["local-1"], 5, 3, [0, 5, 0]), (read["result"], read["readlist"], read["coins"], read["freeEnergy"], read["itemList"]))
                self.assertTrue({"chrdata", "buddyInfo", "summonList", "achivementFlags", "energyAppStore", "energyGooglePlay", "energyAndApp"} <= set(read))
                self.assertEqual((status, read), post(server, "read_messages", "read-one", read_body))
                status, collision = post(server, "read_messages", "read-one", urlencode({"idlist": json.dumps(["local-1"])}))
                self.assertEqual((409, "request_collision"), (status, collision["error"]))
                status, deleted = post(server, "delete_messages", "delete-one", read_body)
                self.assertEqual((200, ["local-1"]), (status, deleted["deletelist"]))
            finally:
                server.shutdown(); thread.join(); server.server_close()

            restarted, thread = start()
            try:
                self.assertEqual((200, read), post(restarted, "read_messages", "read-one", read_body))
                self.assertEqual((200, deleted), post(restarted, "delete_messages", "delete-one", read_body))
            finally:
                restarted.shutdown(); thread.join(); restarted.server_close()
