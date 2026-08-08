from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import urlencode

from liminal_gate.bootstrap_server import BootstrapState
from liminal_gate.rebirth_catalog import build_bundled_rebirth_policy, load_rebirth_catalog
from tests.support import bootstrap_profile, post, start_server, stop_server, write_json


class RebirthTest(unittest.TestCase):
    def test_http_rebirth_joker_error_and_restart_replay(self) -> None:
        document = {"schema_version": 1, "provenance": "user-supplied", "item_slots": 1, "joker_character_id": 9, "recipes": [{"recipe_id": 1, "source_character_id": 2, "destination_character_id": 3, "coins": 2, "items": {"1": 1}, "materials": [{"character_id": 7, "level": 50}, {"character_id": 8, "level": 50}]}]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); catalog_path = write_json(root / "catalog.json", document)
            profile = bootstrap_profile(); state = root / "state.json"; catalog = load_rebirth_catalog(catalog_path)
            server, thread = start_server(("127.0.0.1", 0), profile, BootstrapState(state), rebirth_catalog=catalog)
            try:
                server.state.create_account("token", "account", {"chrdata": [{"id": 2, "jobLevels": [80.0]}, {"id": 7, "jobLevels": [50.0]}, {"id": 9, "jobLevels": [1.0]}], "itemList": [1], "coins": 2})
                status, retry = post(server, "/gd/rebirth", "first", "rebirthID=1&useJoker=False")
                self.assertEqual((200, True, 7), (status, retry["success"], retry["cmdError"]))
                status, success = post(server, "/gd/rebirth", "second", "rebirthID=1&useJoker=True")
                self.assertEqual((200, True, 0, [0]), (status, success["success"], success["coins"], success["itemList"]))
                self.assertEqual([3, 7, 9], [row["id"] for row in success["chrdata"]])
            finally:
                stop_server(server, thread)
            restarted, restarted_thread = start_server(("127.0.0.1", 0), profile, BootstrapState(state), rebirth_catalog=catalog)
            try:
                self.assertEqual((200, success), post(restarted, "/gd/rebirth", "second", "rebirthID=1&useJoker=True"))
            finally:
                stop_server(restarted, restarted_thread)


class BundledRebirthPolicyRuntimeTest(unittest.TestCase):
    def test_bundled_recipe_is_settled_through_the_real_route(self) -> None:
        """The bundled table must settle a real Rebirth, not merely load."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = bootstrap_profile()
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
            server, thread = start_server(("127.0.0.1", 0), profile, state, rebirth_catalog=build_bundled_rebirth_policy())
            try:
                status, payload = post(server, "/gd/rebirth", "bundled", "rebirthID=1&useJoker=False")
            finally:
                stop_server(server, thread)
            self.assertEqual(200, status)
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
            profile = bootstrap_profile()
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
            server, thread = start_server(("127.0.0.1", 0), profile, state, rebirth_catalog=catalog)
            try:
                _, rebirthed = post(server, "/gd/rebirth", "rebirth", "rebirthID=1&useJoker=False")
                userdata = state.userdata_for("token")
                # The client echoes back the party the server just left it.
                layout = urlencode([
                    ("teamMembers", json.dumps(userdata["teamMembers"])),
                    ("teamMembers_VS", json.dumps(userdata["teamMembers_VS"])),
                    ("teamBuddies_VS", "[]"), ("teamNo", "1"), ("teamNo_VS", "1"),
                    ("summonId", "1"), ("lastUpdate", "1"),
                ])
                status, _ = post(server, "/gd/userdata", "party", layout)
            finally:
                stop_server(server, thread)
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


class RebirthOverlapPreservesProgressTest(unittest.TestCase):
    """Recoding into a character you already own must not destroy that copy.

    The rebirthed unit starts at level 1 carrying the source's Skill Boost and
    Luck, and a held copy can be further along in any of them. Replacing the
    held row outright lost its levels, Skill Boost, Luck and plus count with no
    route to recover them.
    """

    def rebirth_into_a_held_copy(self, held: dict) -> dict:
        catalog = build_bundled_rebirth_policy()
        recipe = catalog.recipes[1]
        with tempfile.TemporaryDirectory() as directory:
            state = BootstrapState(Path(directory) / "state.json")
            items = [0] * 181
            for item_id, count in recipe.items.items():
                items[item_id - 1] = count + 5
            rows = [
                {"id": character_id, "jobID": 0, "jobLevels": [float(level), 0.0, 0.0],
                 "jobSlots": [], "skillBoost": 0, "luck": 0}
                for character_id, level in [(recipe.source_character_id, 90)] + list(recipe.materials)
            ]
            rows.append({"id": recipe.destination_character_id, "jobID": 0, "jobSlots": [], **held})
            state.create_account("token", "account", {
                "coins": recipe.coins + 1000, "itemList": items, "summonList": [0] * 16,
                "progressCode": 0x01000000 | (9 << 6) | 1, "worldMapNo": 0,
                "teamMembers": [0] * 6, "teamMembers_VS": [0] * 18,
                "chrdata": rows, "buddyInfo": {"list": [], "record": []},
            })
            with state.lock:
                state.accounts["account"]["tutorial_phase"] = "free_roam"
                state.accounts["account"]["initial_userdata_served"] = True
                state._persist_locked()
            server, thread = start_server(("127.0.0.1", 0), bootstrap_profile(), state,
                                          rebirth_catalog=catalog)
            try:
                _, payload = post(server, "/gd/rebirth", "rebirth", "rebirthID=1&useJoker=False")
            finally:
                stop_server(server, thread)
        self.assertTrue(payload["success"], payload)
        self.assertTrue(payload["overlapped"])
        return next(row for row in payload["chrdata"]
                    if row["id"] == recipe.destination_character_id)

    def test_a_developed_copy_keeps_everything_it_had(self) -> None:
        destination = self.rebirth_into_a_held_copy({
            "jobLevels": [90.0, 0.0, 0.0], "skillBoost": 950, "luck": 800, "plusCount": 200,
        })
        self.assertEqual([90.0, 0.0, 0.0], destination["jobLevels"])
        self.assertEqual((950, 800, 200),
                         (destination["skillBoost"], destination["luck"], destination["plusCount"]))

    def test_a_fresh_copy_still_takes_the_rebirthed_unit(self) -> None:
        """The merge takes the larger of the two, so an undeveloped held copy
        does not hold the rebirthed unit back."""
        destination = self.rebirth_into_a_held_copy({
            "jobLevels": [1.0, 0.0, 0.0], "skillBoost": 0, "luck": 0,
        })
        self.assertEqual([1.0, 0.0, 0.0], destination["jobLevels"])
        self.assertEqual(0, destination["skillBoost"])
