from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import urlencode

from liminal_gate.bootstrap_server import BootstrapState
from liminal_gate.clear_state_catalog import load_clear_state_catalog
from liminal_gate.story_catalog import load_story_catalog
from liminal_gate.story_outcome_catalog import load_story_outcome_catalog
from tests.support import bootstrap_profile, post, start_server, stop_server, write_json


class StoryOutcomeServerTest(unittest.TestCase):
    def test_persists_catalog_bounded_client_reported_outcome(self) -> None:
        character = {"id": 9001, "buddy": 0, "date": 0.0, "jobSlots": [0, 0, 0], "jobLevels": [1, 0, 0], "jobID": 0, "flags": 0, "skillBoost": 0}
        recruited = {**character, "id": 9002}
        story_document = {"schema_version": 1, "provenance": "user-supplied", "stages": [{"chapter": 2, "section": 2, "stamina": 5, "coins": 0, "clear_progress_code": 10, "clear_coins": 30}]}
        outcome_document = {"schema_version": 1, "provenance": "user-supplied", "character_ids": [9001, 9002], "item_slots": 1, "max_stack": 99, "max_companions": 3, "companion_masters": [{"companion_id": 8001, "drop_level": 2}], "stages": [{"chapter": 2, "section": 2, "item_maxima": {"1": 1}, "character_maxima": {"9001": 1, "9002": 1}, "companion_maxima": {"8001": 1}}]}
        clear_state_document = {"schema_version": 1, "provenance": "user-supplied", "team_slots": 6, "max_skill_boost": 9, "max_skill_boost_per_battle": 2, "characters": [{"character_id": 9001, "duplicate_skill_boost": 3, "jobs": [{"maximum_experience": 10, "level_thresholds": [0, 5, 10]}, {"maximum_experience": 0, "level_thresholds": [0]}, {"maximum_experience": 0, "level_thresholds": [0]}]}, {"character_id": 9002, "duplicate_skill_boost": 0, "jobs": [{"maximum_experience": 10, "level_thresholds": [0, 5, 10]}, {"maximum_experience": 0, "level_thresholds": [0]}, {"maximum_experience": 0, "level_thresholds": [0]}]}]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); story_path, outcome_path, clear_state_path, state_path = root / "story.json", root / "outcome.json", root / "clear-state.json", root / "state.json"
            write_json(story_path, story_document); write_json(outcome_path, outcome_document); write_json(clear_state_path, clear_state_document)
            profile = bootstrap_profile()
            story, outcomes, clear_state = load_story_catalog(story_path), load_story_outcome_catalog(outcome_path), load_clear_state_catalog(clear_state_path)
            # Bounding the reported items and monsters is `--outcome-strict`;
            # the default bounds the Companion outcome alone.
            server, thread = start_server(("127.0.0.1", 0), profile, BootstrapState(state_path), story_catalog=story, story_outcome_catalog=outcomes, clear_state_catalog=clear_state, outcome_strict=True)
            try:
                server.state.create_account("token", "account", {"coins": 0, "worldMapNo": 0, "progressCode": 9, "chrdata": [character], "teamMembers": [9001, 0, 0, 0, 0, 0], "itemList": [0], "summonList": [], "buddyInfo": {"list": [], "record": []}})
                with server.state.lock:
                    server.state.accounts["account"]["tutorial_phase"] = "free_roam"; server.state._persist_locked()
                self.assertEqual(200, post(server, "/gd/start_quest", "start", urlencode([("stamina", "5"), ("coins", "0"), ("chapter", "2"), ("section", "2"), ("lastUpdate", "1")]))[0])
                advanced = {**character, "jobLevels": [(8 << 12) | 2, 0, 0], "skillBoost": 4}
                clear = [("progressCode", "10"), ("worldMapNo", "0"), ("valuables", json.dumps({"energyAppStore": 0, "energy": 0, "energyAndApp": 0, "freeEnergy": 0, "energyGooglePlay": 0, "coins": 30})), ("chrdata", json.dumps([advanced, recruited])), ("itemList", "[1]"), ("summonList", "[]"), ("battle_result", json.dumps({"chapter": 2, "section": 2, "coins": 30, "exp": 8, "items": {"1": 1}, "buddies": [8001], "monsters": [9001, 9002], "summons": [], "luckynum": 0, "unableluckdrop": False, "boostup": [1, 0, 0, 0, 0, 0]})), ("itmp0", "0"), ("itmp1", "0"), ("lastUpdate", "1")]
                forged_recruit = {**recruited, "flags": 1}
                forged = list(clear); forged[3] = ("chrdata", json.dumps([advanced, forged_recruit]))
                self.assertEqual((409, "invalid_local_clear_state"), (post(server, "/gd/clear_quest", "forged", urlencode(forged))[0], post(server, "/gd/clear_quest", "forged", urlencode(forged))[1]["error"]))
                rejected = list(clear); rejected[4] = ("itemList", "[2]"); rejected[6] = ("battle_result", json.dumps({"chapter": 2, "section": 2, "coins": 30, "exp": 8, "items": {"1": 2}, "buddies": [8001], "monsters": [9001, 9002], "summons": [], "luckynum": 0, "unableluckdrop": False, "boostup": [1, 0, 0, 0, 0, 0]}))
                self.assertEqual((409, "invalid_local_outcome"), (post(server, "/gd/clear_quest", "rejected", urlencode(rejected))[0], post(server, "/gd/clear_quest", "rejected", urlencode(rejected))[1]["error"]))
                status, payload = post(server, "/gd/clear_quest", "clear", urlencode(clear))
                self.assertEqual(200, status); self.assertEqual((1, 2), (payload["itemList"][0], payload["buddyInfo"]["list"][0]["lv"]))
            finally:
                stop_server(server, thread)
            restarted, restarted_thread = start_server(("127.0.0.1", 0), profile, BootstrapState(state_path), story_catalog=story, story_outcome_catalog=outcomes, clear_state_catalog=clear_state, outcome_strict=True)
            try:
                status, replay = post(restarted, "/gd/clear_quest", "clear", urlencode(clear))
                self.assertEqual((200, payload), (status, replay))
            finally:
                stop_server(restarted, restarted_thread)

    def test_a_full_companion_box_settles_the_clear_instead_of_refusing_it(self) -> None:
        """A won battle is not invalidated by having nowhere to put its drop.

        The client has no error code for a full box, so it enters, wins, and
        reports the drop anyway; refusing that clear reaches it as a transport
        failure and loops against a battle the refusal leaves open.
        """
        character = {"id": 9001, "buddy": 0, "date": 0.0, "jobSlots": [0, 0, 0], "jobLevels": [1, 0, 0], "jobID": 0, "flags": 0, "skillBoost": 0}
        story_document = {"schema_version": 1, "provenance": "user-supplied", "stages": [{"chapter": 2, "section": 2, "stamina": 5, "coins": 0, "clear_progress_code": 10, "clear_coins": 0}]}
        outcome_document = {"schema_version": 1, "provenance": "user-supplied", "character_ids": [9001], "item_slots": 1, "max_stack": 99, "max_companions": 3, "companion_masters": [{"companion_id": 8001, "drop_level": 2}], "stages": [{"chapter": 2, "section": 2, "item_maxima": {}, "character_maxima": {"9001": 1}, "companion_maxima": {"8001": 1}}]}
        full_box = [{"bid": 8001, "lv": 1, "date": 0.0, "iid": iid, "exp": 0, "flag": 0, "chrID": 0} for iid in (1, 2, 3)]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            story_path, outcome_path, state_path = root / "story.json", root / "outcome.json", root / "state.json"
            write_json(story_path, story_document)
            write_json(outcome_path, outcome_document)
            server, thread = start_server(
                ("127.0.0.1", 0), bootstrap_profile(), BootstrapState(state_path),
                story_catalog=load_story_catalog(story_path),
                story_outcome_catalog=load_story_outcome_catalog(outcome_path),
            )
            try:
                server.state.create_account("token", "account", {
                    "coins": 0, "worldMapNo": 0, "progressCode": 9, "chrdata": [character],
                    "teamMembers": [9001, 0, 0, 0, 0, 0], "itemList": [0], "summonList": [],
                    "buddyInfo": {"list": full_box, "record": []}, "nextCompanionInventoryId": 4,
                })
                with server.state.lock:
                    server.state.accounts["account"]["tutorial_phase"] = "free_roam"
                    server.state._persist_locked()
                self.assertEqual(200, post(server, "/gd/start_quest", "start", urlencode([("stamina", "5"), ("coins", "0"), ("chapter", "2"), ("section", "2"), ("lastUpdate", "1")]))[0])
                clear = [
                    ("progressCode", "10"), ("worldMapNo", "0"),
                    ("valuables", json.dumps({"energyAppStore": 0, "energy": 0, "energyAndApp": 0, "freeEnergy": 0, "energyGooglePlay": 0, "coins": 0})),
                    ("chrdata", json.dumps([character])), ("itemList", "[0]"), ("summonList", "[]"),
                    ("battle_result", json.dumps({"chapter": 2, "section": 2, "coins": 0, "exp": 0, "items": {}, "buddies": [8001], "monsters": [], "summons": [], "luckynum": 0, "unableluckdrop": False, "boostup": [0, 0, 0, 0, 0, 0]})),
                    ("itmp0", "0"), ("itmp1", "0"), ("lastUpdate", "1"),
                ]
                status, payload = post(server, "/gd/clear_quest", "clear", urlencode(clear))
                self.assertEqual(200, status, payload)
                # Settled, and the box kept its ceiling rather than growing past it.
                self.assertEqual(3, len(payload["buddyInfo"]["list"]))
                self.assertEqual("free_roam", server.state.accounts["account"]["tutorial_phase"])
            finally:
                stop_server(server, thread)
