from __future__ import annotations

import json
from http.client import HTTPConnection
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.parse import urlencode

from liminal_gate.bootstrap_server import BootstrapServer, BootstrapState, _parse_generic_story_clear, _preserved_progress, load_profile
from liminal_gate.story_catalog import load_story_catalog


PUBLIC_ROOT = Path(__file__).resolve().parents[1]


class GenericStoryServerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.state_path = self.root / "state.json"
        self.catalog_path = self.root / "story.json"
        self.catalog_path.write_text(json.dumps({
            "schema_version": 1,
            "provenance": "user-supplied",
            "stages": [{
                "chapter": 2, "section": 2, "stamina": 5, "coins": 0,
                "clear_progress_code": 16777347, "clear_coins": 30,
            }],
        }), encoding="utf-8")
        self.profile = load_profile(PUBLIC_ROOT / "profiles" / "legacy-client-bootstrap.json")
        self.catalog = load_story_catalog(self.catalog_path)
        self.start_server()
        self.token = "generic-story-token"
        self.account_id = "generic-story-account"
        self.character = {"id": 9001, "buddy": 0, "date": 0.0, "jobSlots": [0, 0, 0], "jobLevels": [1, 0, 0], "jobID": 0, "flags": 0, "skillBoost": 0}
        self.server.state.create_account(self.token, self.account_id, {"coins": 210, "worldMapNo": 0, "progressCode": 16777346, "chrdata": [self.character], "itemList": [], "summonList": []})
        with self.server.state.lock:
            account = self.server.state.accounts[self.account_id]
            account["tutorial_phase"] = "free_roam"
            account["initial_userdata_served"] = True
            self.server.state._persist_locked()

    def tearDown(self) -> None:
        self.stop_server()
        self.temporary_directory.cleanup()

    def start_server(self) -> None:
        self.server = BootstrapServer(("127.0.0.1", 0), self.profile, BootstrapState(self.state_path), story_catalog=self.catalog)
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()

    def stop_server(self) -> None:
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()

    def post(self, path: str, fields: list[tuple[str, str]]) -> tuple[int, dict[str, object]]:
        connection = HTTPConnection(*self.server.server_address)
        connection.request("POST", path, body=urlencode(fields), headers={"Content-Type": "application/x-www-form-urlencoded"})
        response = connection.getresponse()
        payload = json.loads(response.read())
        connection.close()
        return response.status, payload

    def test_catalog_declared_story_start_clear_replay_collision_and_restart(self) -> None:
        start = [("stamina", "5"), ("coins", "0"), ("chapter", "2"), ("section", "2"), ("lastUpdate", "1")]
        path = f"/gd/start_quest?otk={self.token}&requestID=start-2-2"
        status, started = self.post(path, start)
        self.assertEqual(200, status)
        # Entry debits the stamina meter, so the fill origin moves off zero.
        self.assertGreater(started["refillStartTime"], 0.0)
        status, replay = self.post(path, start)
        self.assertEqual(200, status)
        self.assertEqual(started["refillStartTime"], replay["refillStartTime"])
        status, collision = self.post(path, [("stamina", "0")])
        # Reusing a spent requestID with a different body is no longer read
        # as a tampered retry; it is answered on its own merits.
        self.assertEqual(501, status)
        self.assertEqual("unsupported_start_quest", collision["error"])
        continue_path = f"/gd/continue?otk={self.token}&requestID=continue-2-2"
        status, continued = self.post(continue_path, [("cost", "1")])
        self.assertEqual(200, status)
        self.assertTrue(continued["success"])
        self.assertEqual(0, continued["energy"])
        self.assertEqual(0, continued["freeEnergy"])
        status, continue_replay = self.post(continue_path, [("cost", "1")])
        self.assertEqual(200, status)
        self.assertEqual(continued["energy"], continue_replay["energy"])
        status, continue_collision = self.post(continue_path, [("cost", "0")])
        # Reusing a spent requestID with a different body is no longer read
        # as a tampered retry; it is answered on its own merits.
        self.assertEqual(501, status)
        self.assertEqual("unsupported_continue", continue_collision["error"])
        self.stop_server()
        self.start_server()
        clear = [
            ("progressCode", "16777347"), ("worldMapNo", "0"),
            ("valuables", json.dumps({"energyAppStore": 0, "energy": 0, "energyAndApp": 0, "freeEnergy": 0, "energyGooglePlay": 0, "coins": 140})), ("chrdata", json.dumps([self.character])),
            ("itemList", "[]"), ("summonList", "[]"),
            ("battle_result", json.dumps({"chapter": 2, "section": 2, "coins": 30, "exp": 0, "items": {}, "buddies": [], "monsters": [], "summons": [], "luckynum": 0, "unableluckdrop": False, "boostup": [0, 0, 0, 0, 0, 0]})),
            ("itmp0", "0"), ("itmp1", "0"), ("lastUpdate", "1"),
        ]
        clear_path = f"/gd/clear_quest?otk={self.token}&requestID=clear-2-2"
        status, cleared = self.post(clear_path, clear)
        self.assertEqual(200, status)
        self.assertFalse(cleared["sentMessage"])
        self.assertEqual(140, cleared["coins"])
        status, clear_replay = self.post(clear_path, clear)
        self.assertEqual(200, status)
        self.assertEqual(cleared["coins"], clear_replay["coins"])
        persisted = json.loads(self.state_path.read_text(encoding="utf-8"))
        userdata = persisted["accounts"][self.account_id]["userdata"]
        self.assertEqual(16777347, userdata["progressCode"])
        self.assertEqual(140, userdata["coins"])
        # `freeEnergy` carries the preservation stage award; see `archive_economy`.
        self.assertEqual({"energyAppStore": 0, "energy": 0, "energyAndApp": 0, "freeEnergy": 2, "energyGooglePlay": 0, "coins": 140}, userdata["valuables"])
        self.assertEqual("free_roam", persisted["accounts"][self.account_id]["tutorial_phase"])

    def test_clear_keeps_a_grant_the_client_had_not_read_back(self) -> None:
        """A stale client roster at clear time must not delete a server grant.

        This is the configuration the guided tester actually launches: a story
        catalog with no settlement, clear-state, or outcome catalog, so nothing
        else requires the submitted roster to cover the durable one.  A Pact
        draw whose response never reached the client, an event character, or an
        achievement reward is present on the server and absent from the next
        clear's payload, and a wholesale replace would silently drop it.
        """
        granted = {"id": 9002, "buddy": 0, "date": 0.0, "jobSlots": [0, 0, 0], "jobLevels": [7, 0, 0], "jobID": 0, "flags": 0, "skillBoost": 2}
        with self.server.state.lock:
            userdata = self.server.state.accounts[self.account_id]["userdata"]
            userdata["chrdata"] = [self.character, granted]
            userdata["itemList"] = [0, 0, 5]
            userdata["summonList"] = [0, 4]
            self.server.state._persist_locked()

        start = [("stamina", "5"), ("coins", "0"), ("chapter", "2"), ("section", "2"), ("lastUpdate", "1")]
        status, _ = self.post(f"/gd/start_quest?otk={self.token}&requestID=start-grant", start)
        self.assertEqual(200, status)

        # The client reports only the character it knows about, its own battle
        # drop in slot 1, and a base for slots 3/2 that predates the grants.
        clear = [
            ("progressCode", "16777347"), ("worldMapNo", "0"),
            ("valuables", json.dumps({"energyAppStore": 0, "energy": 0, "energyAndApp": 0, "freeEnergy": 0, "energyGooglePlay": 0, "coins": 240})),
            ("chrdata", json.dumps([self.character])),
            ("itemList", json.dumps([1, 0, 0])), ("summonList", json.dumps([0, 0])),
            ("battle_result", json.dumps({"chapter": 2, "section": 2, "coins": 30, "exp": 0, "items": {}, "buddies": [], "monsters": [], "summons": [], "luckynum": 0, "unableluckdrop": False, "boostup": [0, 0, 0, 0, 0, 0]})),
            ("itmp0", "0"), ("itmp1", "0"), ("lastUpdate", "1"),
        ]
        status, cleared = self.post(f"/gd/clear_quest?otk={self.token}&requestID=clear-grant", clear)
        self.assertEqual(200, status)
        # The response carries the merged roster, so the client learns about the
        # character it was missing instead of re-submitting without it forever.
        self.assertEqual([9001, 9002], sorted(row["id"] for row in cleared["chrdata"]))

        self.stop_server()
        self.start_server()
        persisted = json.loads(self.state_path.read_text(encoding="utf-8"))
        userdata = persisted["accounts"][self.account_id]["userdata"]
        self.assertEqual([9001, 9002], sorted(row["id"] for row in userdata["chrdata"]))
        surviving = next(row for row in userdata["chrdata"] if row["id"] == 9002)
        self.assertEqual([7, 0, 0], surviving["jobLevels"])
        self.assertEqual(2, surviving["skillBoost"])
        # The battle's own drop is kept alongside the grants the client missed.
        self.assertEqual([1, 0, 5], userdata["itemList"])
        self.assertEqual([0, 4], userdata["summonList"])

    def test_clear_does_not_roll_back_progression_the_client_is_stale_about(self) -> None:
        """Preserving a whole character is not enough on its own.

        A client can know about a character and still be stale about it: the
        Pact duplicate that raised its level and skill boost arrived while the
        client was showing an older row.  Job experience and skill boost only
        accumulate, so the client's lower values are stale, not a spend.
        """
        boosted = dict(self.character, jobLevels=[(500 << 12) | 10, 0, 0], skillBoost=3)
        with self.server.state.lock:
            self.server.state.accounts[self.account_id]["userdata"]["chrdata"] = [boosted]
            self.server.state._persist_locked()

        start = [("stamina", "5"), ("coins", "0"), ("chapter", "2"), ("section", "2"), ("lastUpdate", "1")]
        self.assertEqual(200, self.post(f"/gd/start_quest?otk={self.token}&requestID=start-stale", start)[0])
        clear = [
            ("progressCode", "16777347"), ("worldMapNo", "0"),
            ("valuables", json.dumps({"energyAppStore": 0, "energy": 0, "energyAndApp": 0, "freeEnergy": 0, "energyGooglePlay": 0, "coins": 240})),
            # The client reports the character at its pre-Pact level and boost.
            ("chrdata", json.dumps([self.character])),
            ("itemList", "[]"), ("summonList", "[]"),
            ("battle_result", json.dumps({"chapter": 2, "section": 2, "coins": 30, "exp": 0, "items": {}, "buddies": [], "monsters": [], "summons": [], "luckynum": 0, "unableluckdrop": False, "boostup": [0, 0, 0, 0, 0, 0]})),
            ("itmp0", "0"), ("itmp1", "0"), ("lastUpdate", "1"),
        ]
        status, _ = self.post(f"/gd/clear_quest?otk={self.token}&requestID=clear-stale", clear)
        self.assertEqual(200, status)

        self.stop_server()
        self.start_server()
        row = json.loads(self.state_path.read_text(encoding="utf-8"))["accounts"][self.account_id]["userdata"]["chrdata"][0]
        self.assertEqual([(500 << 12) | 10, 0, 0], row["jobLevels"])
        self.assertEqual(3, row["skillBoost"])
        # A player choice still moves in whichever direction the client reports.
        self.assertEqual(self.character["jobID"], row["jobID"])

    def test_clear_preserves_omitted_luck_then_commits_one_authored_gain(self) -> None:
        """The final client omits optional Luck from a valid clear roster.

        Preserve the durable value before applying the start response's
        server-authored gain. Replay and restart must not apply that gain twice.
        """
        with self.server.state.lock:
            account = self.server.state.accounts[self.account_id]
            account["userdata"]["chrdata"] = [dict(self.character, luck=50)]
            account["userdata"]["teamMembers"] = [9001, 0, 0, 0, 0, 0]
            self.server.state._persist_locked()

        start = [("stamina", "5"), ("coins", "0"), ("chapter", "2"), ("section", "2"), ("lastUpdate", "1")]
        self.assertEqual(200, self.post(f"/gd/start_quest?otk={self.token}&requestID=start-luck", start)[0])
        with self.server.state.lock:
            self.server.state.accounts[self.account_id]["active_luck_up"] = [2, 0, 0, 0, 0, 0]
            self.server.state._persist_locked()

        clear = [
            ("progressCode", "16777347"), ("worldMapNo", "0"),
            ("valuables", json.dumps({"energyAppStore": 0, "energy": 0, "energyAndApp": 0, "freeEnergy": 0, "energyGooglePlay": 0, "coins": 240})),
            # Exact final-client behavior: the optional Luck member is absent.
            ("chrdata", json.dumps([self.character])),
            ("itemList", "[]"), ("summonList", "[]"),
            ("battle_result", json.dumps({"chapter": 2, "section": 2, "coins": 30, "exp": 0, "items": {}, "buddies": [], "monsters": [], "summons": [], "luckynum": 0, "unableluckdrop": False, "boostup": [0, 0, 0, 0, 0, 0]})),
            ("itmp0", "0"), ("itmp1", "0"), ("lastUpdate", "1"),
        ]
        path = f"/gd/clear_quest?otk={self.token}&requestID=clear-luck"
        status, cleared = self.post(path, clear)
        self.assertEqual((200, 52), (status, cleared["chrdata"][0]["luck"]))
        self.assertEqual((status, cleared), self.post(path, clear))

        self.stop_server()
        self.start_server()
        row = json.loads(self.state_path.read_text(encoding="utf-8"))["accounts"][self.account_id]["userdata"]["chrdata"][0]
        self.assertEqual(52, row["luck"])

    def test_clear_cannot_replace_durable_luck_with_explicit_zero(self) -> None:
        self.assertEqual(
            50,
            _preserved_progress(
                dict(self.character, luck=50), dict(self.character, luck=0),
            )["luck"],
        )

    def test_rejects_incomplete_or_malformed_client_clear_result(self) -> None:
        fields = [
            ("progressCode", "16777347"), ("worldMapNo", "0"),
            ("valuables", json.dumps({"coins": 30})), ("chrdata", json.dumps([self.character])),
            ("itemList", "[]"), ("summonList", "[]"),
            ("battle_result", json.dumps({"chapter": 2, "section": 2, "coins": 30})),
            ("itmp0", "0"), ("itmp1", "0"), ("lastUpdate", "1"),
        ]
        self.assertIsNone(_parse_generic_story_clear(urlencode(fields).encode("ascii")))
