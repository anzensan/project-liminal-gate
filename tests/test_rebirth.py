from __future__ import annotations

import json
from http.client import HTTPConnection
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.parse import urlencode

from liminal_gate.bootstrap_server import BootstrapServer, BootstrapState, load_profile
from liminal_gate.rebirth_catalog import build_bundled_rebirth_policy, load_rebirth_catalog


class RebirthTest(unittest.TestCase):
    def test_http_rebirth_joker_error_and_restart_replay(self) -> None:
        document = {"schema_version": 1, "provenance": "user-supplied", "item_slots": 1, "joker_character_id": 9, "recipes": [{"recipe_id": 1, "source_character_id": 2, "destination_character_id": 3, "coins": 2, "items": {"1": 1}, "materials": [{"character_id": 7, "level": 50}, {"character_id": 8, "level": 50}]}]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); catalog_path = root / "catalog.json"; catalog_path.write_text(json.dumps(document), encoding="utf-8")
            profile = load_profile(Path(__file__).resolve().parents[1] / "profiles" / "legacy-client-bootstrap.json"); state = root / "state.json"; catalog = load_rebirth_catalog(catalog_path)
            def start() -> tuple[BootstrapServer, threading.Thread]:
                server = BootstrapServer(("127.0.0.1", 0), profile, BootstrapState(state), rebirth_catalog=catalog); thread = threading.Thread(target=server.serve_forever); thread.start(); return server, thread
            def post(server: BootstrapServer, request_id: str, body: str) -> tuple[int, dict[str, object]]:
                connection = HTTPConnection(*server.server_address); connection.request("POST", f"/gd/rebirth?otk=token&requestID={request_id}", body=body); response = connection.getresponse(); payload = json.loads(response.read()); connection.close(); return response.status, payload
            server, thread = start()
            try:
                server.state.create_account("token", "account", {"chrdata": [{"id": 2, "jobLevels": [80.0]}, {"id": 7, "jobLevels": [50.0]}, {"id": 9, "jobLevels": [1.0]}], "itemList": [1], "coins": 2})
                status, retry = post(server, "first", "rebirthID=1&useJoker=False")
                self.assertEqual((200, True, 7), (status, retry["success"], retry["cmdError"]))
                status, success = post(server, "second", "rebirthID=1&useJoker=True")
                self.assertEqual((200, True, 0, [0]), (status, success["success"], success["coins"], success["itemList"]))
                self.assertEqual([3, 7, 9], [row["id"] for row in success["chrdata"]])
            finally:
                server.shutdown(); thread.join(); server.server_close()
            restarted, restarted_thread = start()
            try:
                self.assertEqual((200, success), post(restarted, "second", "rebirthID=1&useJoker=True"))
            finally:
                restarted.shutdown(); restarted_thread.join(); restarted.server_close()


class BundledRebirthPolicyRuntimeTest(unittest.TestCase):
    def test_bundled_recipe_is_settled_through_the_real_route(self) -> None:
        """The bundled table must settle a real Rebirth, not merely load."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = load_profile(Path(__file__).resolve().parents[1] / "profiles" / "legacy-client-bootstrap.json")
            state = BootstrapState(root / "state.json")
            # Recipe 1 turns character 2 into 623 for 30000 Coins plus items
            # 10x15, 93x5, 96x1, consuming Companions 237 and 145 at level 50.
            items = [0] * 181
            for item_id, count in ((10, 20), (93, 10), (96, 5)):
                items[item_id - 1] = count
            mastered = [(2, [80, 0, 0]), (237, [50, 0, 0]), (145, [50, 0, 0])]
            state.create_account("token", "account", {
                "coins": 40000, "itemList": items,
                "chrdata": [{"id": i, "jobID": 0, "jobLevels": [float(v) for v in levels], "jobSlots": []} for i, levels in mastered],
            })
            server = BootstrapServer(("127.0.0.1", 0), profile, state, rebirth_catalog=build_bundled_rebirth_policy())
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            try:
                connection = HTTPConnection(*server.server_address)
                connection.request("POST", "/gd/rebirth?otk=token&requestID=bundled", body="rebirthID=1&useJoker=False")
                response = connection.getresponse()
                payload = json.loads(response.read())
                connection.close()
            finally:
                server.shutdown(); thread.join(); server.server_close()
            self.assertEqual(200, response.status)
            self.assertTrue(payload["success"], payload)
            self.assertEqual(10000, payload["coins"])
            self.assertIn(623, [row["id"] for row in payload["chrdata"]])
            self.assertNotIn(2, [row["id"] for row in payload["chrdata"]])
            self.assertEqual([5, 5, 4], [payload["itemList"][item_id - 1] for item_id in (10, 93, 96)])


class RebirthPartyConsistencyTest(unittest.TestCase):
    """Rebirth must not leave the party naming a character it removed."""

    def scenario(self, already_own_destination: bool) -> tuple[dict, int, dict]:
        catalog = build_bundled_rebirth_policy()
        recipe = catalog.recipes[1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = load_profile(Path(__file__).resolve().parents[1] / "profiles" / "legacy-client-bootstrap.json")
            state = BootstrapState(root / "state.json")
            items = [0] * 181
            for item_id, count in recipe.items.items():
                items[item_id - 1] = count + 5
            rows = [(recipe.source_character_id, 90)] + list(recipe.materials)
            if already_own_destination:
                rows.append((recipe.destination_character_id, 1))
            state.create_account("token", "account", {
                "coins": recipe.coins + 1000, "itemList": items, "summonList": [0] * 16,
                "progressCode": 0x01000000 | (9 << 6) | 1, "worldMapNo": 0,
                "teamMembers": [recipe.source_character_id, 0, 0, 0, 0, 0],
                "teamMembers_VS": [recipe.source_character_id] + [0] * 17,
                "chrdata": [{"id": i, "jobID": 0, "jobLevels": [float(level), 0.0, 0.0],
                             "jobSlots": [], "skillBoost": 0, "luck": 0} for i, level in rows],
                "buddyInfo": {"list": [], "record": []},
            })
            with state.lock:
                state.accounts["account"]["tutorial_phase"] = "free_roam"
                state.accounts["account"]["initial_userdata_served"] = True
                state._persist_locked()
            server = BootstrapServer(("127.0.0.1", 0), profile, state, rebirth_catalog=catalog)
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            try:
                def post(route: str, request_id: str, body: str) -> tuple[int, dict]:
                    connection = HTTPConnection(*server.server_address)
                    connection.request("POST", f"{route}?otk=token&requestID={request_id}", body=body)
                    response = connection.getresponse()
                    result = json.loads(response.read())
                    connection.close()
                    return response.status, result

                _, rebirthed = post("/gd/rebirth", "rebirth", "rebirthID=1&useJoker=False")
                userdata = state.userdata_for("token")
                # The client echoes back the party the server just left it.
                layout = urlencode([
                    ("teamMembers", json.dumps(userdata["teamMembers"])),
                    ("teamMembers_VS", json.dumps(userdata["teamMembers_VS"])),
                    ("teamBuddies_VS", "[]"), ("teamNo", "1"), ("teamNo_VS", "1"),
                    ("summonId", "1"), ("lastUpdate", "1"),
                ])
                status, _ = post("/gd/userdata", "party", layout)
            finally:
                server.shutdown(); thread.join(); server.server_close()
            return rebirthed, status, userdata

    def test_the_rebirthed_unit_keeps_its_party_slot(self) -> None:
        rebirthed, status, userdata = self.scenario(already_own_destination=False)
        self.assertFalse(rebirthed["overlapped"])
        self.assertEqual([623, 0, 0, 0, 0, 0], userdata["teamMembers"])
        self.assertEqual(623, userdata["teamMembers_VS"][0])
        # Without this the account could not save the party the server gave it.
        self.assertEqual(200, status)

    def test_an_already_owned_destination_empties_the_slot_instead(self) -> None:
        rebirthed, status, userdata = self.scenario(already_own_destination=True)
        self.assertTrue(rebirthed["overlapped"], "the destination was already owned")
        # Naming the destination twice would make the party non-unique.
        self.assertEqual([0, 0, 0, 0, 0, 0], userdata["teamMembers"])
        self.assertEqual(0, userdata["teamMembers_VS"][0])
        self.assertEqual(200, status)
