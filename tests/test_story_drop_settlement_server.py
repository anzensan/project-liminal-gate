"""Drive a real story clear against a catalog the drop generator produced.

The unit tests either side of this one check the extraction and the join.  This
one checks the point of the exercise: that a catalog composed from recovered
drop data actually lets the running server mint the Companion the client rolled,
and still refuses a roll above the recovered ceiling.
"""

from __future__ import annotations

import json
from http.client import HTTPConnection
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.parse import urlencode

from liminal_gate.bootstrap_server import BootstrapServer, BootstrapState, load_profile
from liminal_gate.hunting_catalog import BUNDLED_ITEM_SLOTS
from liminal_gate.story_catalog import load_story_catalog
from liminal_gate.story_outcome_catalog import load_story_outcome_catalog
from liminal_gate.story_outcome_generator import DEFAULT_COMPANION_DROP_LEVEL, build_catalog, write_catalog


BOMBORG, ELECTROTICK = 95, 92
COMPANION = 111
CHARACTER = 9001
CLEAR_COINS = 30


class StoryDropSettlementServerTest(unittest.TestCase):
    def _generated_catalog(self) -> dict[str, object]:
        """Compose the catalog exactly as the command-line generator does."""
        encounters = {
            "schema_version": 1, "provenance": "user-derived",
            "source": {"abi": "arm64", "apk_sha256": "a" * 64},
            "stages": [{
                "chapter": 2, "section": 2, "resolved": True, "exact": True,
                "spawns": [
                    {"symbol": "CH2_BMAKER", "enemy_id": BOMBORG, "exact": True, "count": 2},
                    {"symbol": "CH2_L_TICK", "enemy_id": ELECTROTICK, "exact": True, "count": 4},
                ],
            }],
        }
        battledata = {"chapters": [{"chapterNo": 2, "sections": [
            {"dropBuddies": []},
            # The section allowlist alone would cap this stage at one copy; the
            # native map finds two enemies able to drop it.
            {"dropBuddies": [{"code": (COMPANION << 8) | 1}]},
        ]}]}
        enemy_data = {"data": [
            {"ID": BOMBORG, "DropBuddyID": COMPANION, "DropBuddyRatio": 20.0},
            {"ID": ELECTROTICK, "DropBuddyID": COMPANION, "DropBuddyRatio": 0.0},
        ]}
        characters = {"characters": [{"character_id": CHARACTER}]}
        catalog, _report, _notes = build_catalog(encounters, battledata, enemy_data, characters)
        return catalog

    def _clear_fields(self, buddies: list[int]) -> list[tuple[str, str]]:
        character = {"id": CHARACTER, "buddy": 0, "date": 0.0, "jobSlots": [0, 0, 0], "jobLevels": [1, 0, 0], "jobID": 0, "flags": 0, "skillBoost": 0}
        return [
            ("progressCode", "10"), ("worldMapNo", "0"),
            ("valuables", json.dumps({"energyAppStore": 0, "energy": 0, "energyAndApp": 0, "freeEnergy": 0, "energyGooglePlay": 0, "coins": CLEAR_COINS})),
            ("chrdata", json.dumps([character])), ("itemList", json.dumps([0] * BUNDLED_ITEM_SLOTS)), ("summonList", "[]"),
            ("battle_result", json.dumps({
                "chapter": 2, "section": 2, "coins": CLEAR_COINS, "exp": 8, "items": {},
                "buddies": buddies, "monsters": [], "summons": [],
                "luckynum": 0, "unableluckdrop": False, "boostup": [0, 0, 0, 0, 0, 0],
            })),
            ("itmp0", "0"), ("itmp1", "0"), ("lastUpdate", "1"),
        ]

    def test_a_generated_ceiling_mints_the_rolled_companion_and_caps_it(self) -> None:
        story_document = {"schema_version": 1, "provenance": "user-supplied", "stages": [
            {"chapter": 2, "section": 2, "stamina": 5, "coins": 0, "clear_progress_code": 10, "clear_coins": CLEAR_COINS},
        ]}
        character = {"id": CHARACTER, "buddy": 0, "date": 0.0, "jobSlots": [0, 0, 0], "jobLevels": [1, 0, 0], "jobID": 0, "flags": 0, "skillBoost": 0}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            story_path, outcome_path, state_path = root / "story.json", root / "outcome.json", root / "state.json"
            story_path.write_text(json.dumps(story_document), encoding="utf-8")
            write_catalog(outcome_path, self._generated_catalog())
            outcomes = load_story_outcome_catalog(outcome_path)
            # The union, not either source alone: the section list allows one.
            self.assertEqual({COMPANION: 2}, outcomes.rules[(2, 2)].companion_maxima)
            profile = load_profile(Path(__file__).resolve().parents[1] / "profiles" / "legacy-client-bootstrap.json")
            story = load_story_catalog(story_path)

            def start() -> tuple[BootstrapServer, threading.Thread]:
                server = BootstrapServer(("127.0.0.1", 0), profile, BootstrapState(state_path), story_catalog=story, story_outcome_catalog=outcomes)
                thread = threading.Thread(target=server.serve_forever)
                thread.start()
                return server, thread

            def post(server: BootstrapServer, path: str, fields: list[tuple[str, str]]) -> tuple[int, dict[str, object]]:
                connection = HTTPConnection(*server.server_address)
                connection.request("POST", path, body=urlencode(fields))
                response = connection.getresponse()
                payload = json.loads(response.read())
                connection.close()
                return response.status, payload

            server, thread = start()
            try:
                server.state.create_account("token", "account", {
                    "coins": 0, "worldMapNo": 0, "progressCode": 9, "chrdata": [character],
                    "teamMembers": [CHARACTER, 0, 0, 0, 0, 0], "itemList": [0] * BUNDLED_ITEM_SLOTS,
                    "summonList": [], "buddyInfo": {"list": [], "record": []},
                })
                with server.state.lock:
                    server.state.accounts["account"]["tutorial_phase"] = "free_roam"
                    server.state._persist_locked()
                self.assertEqual(200, post(server, "/gd/start_quest?otk=token&requestID=start", [
                    ("stamina", "5"), ("coins", "0"), ("chapter", "2"), ("section", "2"), ("lastUpdate", "1"),
                ])[0])

                over = self._clear_fields([COMPANION, COMPANION, COMPANION])
                status, payload = post(server, "/gd/clear_quest?otk=token&requestID=over", over)
                self.assertEqual((409, "invalid_local_outcome"), (status, payload["error"]))

                clear = self._clear_fields([COMPANION, COMPANION])
                status, payload = post(server, "/gd/clear_quest?otk=token&requestID=clear", clear)
                self.assertEqual(200, status)
                minted = payload["buddyInfo"]["list"]
                self.assertEqual(
                    [(COMPANION, DEFAULT_COMPANION_DROP_LEVEL), (COMPANION, DEFAULT_COMPANION_DROP_LEVEL)],
                    [(row["bid"], row["lv"]) for row in minted],
                )
                self.assertEqual([1, 2], [row["iid"] for row in minted])
            finally:
                server.shutdown()
                thread.join()
                server.server_close()

            restarted, restarted_thread = start()
            try:
                self.assertEqual(
                    (200, payload),
                    post(restarted, "/gd/clear_quest?otk=token&requestID=clear", clear),
                )
                stored = restarted.state.accounts["account"]["userdata"]["buddyInfo"]["list"]
                self.assertEqual(2, len(stored))
            finally:
                restarted.shutdown()
                restarted_thread.join()
                restarted.server_close()
