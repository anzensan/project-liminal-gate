from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import urlencode

from liminal_gate.bootstrap_server import BootstrapState
from liminal_gate.luck_data import character_luck_cap
from liminal_gate.rebirth_catalog import BUNDLED_JOKER_CHARACTER_ID, build_bundled_rebirth_policy, load_rebirth_catalog
from liminal_gate.rebirth_recipe_data import JOKER_SUBSTITUTE_LEVEL, OWNED_DESTINATION_LUCK_BONUS
from tests.support import bootstrap_profile, post, start_server, stop_server, write_json


class RebirthTest(unittest.TestCase):
    def test_http_rebirth_joker_error_and_restart_replay(self) -> None:
        document = {"schema_version": 1, "provenance": "user-supplied", "item_slots": 1, "joker_character_id": 9, "recipes": [{"recipe_id": 1, "source_character_id": 2, "destination_character_id": 3, "coins": 2, "items": {"1": 1}, "materials": [{"character_id": 7, "level": 50}, {"character_id": 8, "level": 50}]}]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); catalog_path = write_json(root / "catalog.json", document)
            profile = bootstrap_profile(); state = root / "state.json"; catalog = load_rebirth_catalog(catalog_path)
            server, thread = start_server(("127.0.0.1", 0), profile, BootstrapState(state), rebirth_catalog=catalog)
            try:
                server.state.create_account("token", "account", {"chrdata": [{"id": 2, "jobLevels": [80.0]}, {"id": 7, "jobLevels": [50.0]}, {"id": 9, "jobLevels": [50.0]}], "itemList": [1], "coins": 2})
                status, retry = post(server, "/gd/rebirth", "first", "rebirthID=1&useJoker=False")
                self.assertEqual((200, True, 7), (status, retry["success"], retry["cmdError"]))
                status, success = post(server, "/gd/rebirth", "second", "rebirthID=1&useJoker=True")
                self.assertEqual((200, True, 0, [0]), (status, success["success"], success["coins"], success["itemList"]))
                # Source 2 becomes 3; material 7 and the Joker standing in for
                # the missing material 8 are both consumed with it.
                self.assertEqual([3], [row["id"] for row in success["chrdata"]])
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
    """Rebirth must not leave a squad naming a character it removed.

    It cannot be repaired after the fact, which is why the main squads are
    refused outright. The recode answer is read by `<Rebirth>...<>m__0`
    (ARM64 `0xFBCD00`) for `buddyInfo` and `chrdata` and nothing else, and
    `teamMembers` is rebuilt only by `LoadUserdataFromJson`, i.e. at login --
    so between the recode and the next launch the client goes on naming a
    character it no longer owns, resolves the slot through
    `GetCharacterByID(id, create: true)`, and mints a level 1 stand-in into
    its own roster.

    The versus squads are not refused, because `GameManager.IsInAnyTeam`
    (`0xD9EB94`) does not read them -- `LoadChrData` ends at
    `CorrectTeamMemeber_VS`, so those the client does repair on the answer.
    Their slots are retargeted here so the save stays consistent meanwhile.
    """

    def scenario(self, already_own_destination: bool, fielded: str = "versus") -> tuple[dict, int, dict]:
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
                "teamMembers": ([recipe.source_character_id, 0, 0, 0, 0, 0]
                                if fielded == "main" else [0] * 6),
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

    def test_the_rebirthed_unit_keeps_its_versus_slot(self) -> None:
        rebirthed, status, userdata = self.scenario(already_own_destination=False)
        self.assertFalse(rebirthed["overlapped"])
        self.assertEqual(623, userdata["teamMembers_VS"][0])
        # Without this the account could not save the party the server gave it.
        self.assertEqual(200, status)

    def test_an_already_owned_destination_empties_the_slot_instead(self) -> None:
        rebirthed, status, userdata = self.scenario(already_own_destination=True)
        self.assertTrue(rebirthed["overlapped"], "the destination was already owned")
        # Naming the destination twice would make the party non-unique.
        self.assertEqual(0, userdata["teamMembers_VS"][0])
        self.assertEqual(200, status)

    def test_a_source_a_main_squad_fields_is_refused_and_costs_nothing(self) -> None:
        rebirthed, _, userdata = self.scenario(already_own_destination=False, fielded="main")
        # `InvalidRebirthID` is the nearest the client has: no `RebirthErrorCode`
        # says "in a party", so this is answered as the recode simply not being
        # available -- the same reading the 100 Luck ceiling already gets.
        self.assertEqual(6, rebirthed["cmdError"])
        catalog = build_bundled_rebirth_policy()
        recipe = catalog.recipes[1]
        # Nothing was taken: the source is still owned, still fielded, and the
        # monsters and Coins are all still there.
        self.assertIn(recipe.source_character_id, [row["id"] for row in userdata["chrdata"]])
        self.assertNotIn(recipe.destination_character_id, [row["id"] for row in userdata["chrdata"]])
        self.assertEqual([recipe.source_character_id, 0, 0, 0, 0, 0], userdata["teamMembers"])
        for material_id, _ in recipe.materials:
            self.assertIn(material_id, [row["id"] for row in userdata["chrdata"]])
        self.assertEqual(recipe.coins + 1000, userdata["coins"])


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
        self.assertEqual(950, destination["skillBoost"])
        self.assertEqual(200, destination["plusCount"])
        # An already-owned destination gains 5.0 Luck on top of what it held,
        # and the source in this fixture carries none of its own.
        self.assertEqual(800 + OWNED_DESTINATION_LUCK_BONUS, destination["luck"])

    def test_a_fresh_copy_still_takes_the_rebirthed_unit(self) -> None:
        """The merge takes the larger of the two, so an undeveloped held copy
        does not hold the rebirthed unit back."""
        destination = self.rebirth_into_a_held_copy({
            "jobLevels": [1.0, 0.0, 0.0], "skillBoost": 0, "luck": 0,
        })
        self.assertEqual([1.0, 0.0, 0.0], destination["jobLevels"])
        self.assertEqual(0, destination["skillBoost"])


class RebirthCarryoverTest(unittest.TestCase):
    """What a recode carries into the character it produces.

    The record this implements: a fifth of each material monster's Skill Boost
    comes across with the source's own, an already-owned destination keeps its
    level and *gains* the carryover, and it takes 5 Luck on top.
    """

    def recode(self, held: dict | None, source_boost: int, source_luck: int,
               material_boost: int, material_luck: int = 0) -> tuple[dict, dict]:
        catalog = build_bundled_rebirth_policy()
        recipe = catalog.recipes[1]
        with tempfile.TemporaryDirectory() as directory:
            state = BootstrapState(Path(directory) / "state.json")
            items = [0] * 181
            for item_id, count in recipe.items.items():
                items[item_id - 1] = count + 5
            rows = [{"id": recipe.source_character_id, "jobID": 0, "jobLevels": [90.0, 0.0, 0.0],
                     "jobSlots": [], "skillBoost": source_boost, "luck": source_luck}]
            rows += [{"id": material_id, "jobID": 0, "jobLevels": [float(level), 0.0, 0.0],
                      "jobSlots": [], "skillBoost": material_boost, "luck": material_luck}
                     for material_id, level in recipe.materials]
            if held is not None:
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
        return payload, next(row for row in payload["chrdata"]
                             if row["id"] == recipe.destination_character_id)

    def test_a_fifth_of_each_material_comes_across(self) -> None:
        # Source at 50.0%, both materials at 100.0% -> 50 + 20 + 20 = 90.0%.
        payload, destination = self.recode(None, source_boost=500, source_luck=300, material_boost=1000)
        self.assertEqual(900, destination["skillBoost"])
        self.assertEqual(300, destination["luck"])
        self.assertEqual([1.0, 0.0, 0.0], destination["jobLevels"])
        self.assertEqual((90, 30), (payload["addedSkillBoost"], payload["addedLuck"]))

    def test_a_fifth_of_each_material_luck_comes_across_too(self) -> None:
        """The rule the transcription dropped, in the reporting tester's numbers.

        A Megacell at its 70.0 cap is a fifth of 70.0 -- 14.0 Luck -- and the
        recode used to carry none of it.
        """
        payload, destination = self.recode(
            None, source_boost=0, source_luck=0, material_boost=0, material_luck=700,
        )
        self.assertEqual(280, destination["luck"], "14.0 from each of the two materials")
        self.assertEqual(28, payload["addedLuck"])

    def test_material_luck_carries_alongside_the_source_and_the_owned_bonus(self) -> None:
        payload, destination = self.recode(
            {"jobLevels": [90.0, 0.0, 0.0], "skillBoost": 0, "luck": 100},
            source_boost=0, source_luck=300, material_boost=0, material_luck=500,
        )
        # 10.0 held + 30.0 source + 10.0 from each material + the owned 5.0.
        self.assertEqual(650, destination["luck"])
        self.assertEqual(55, payload["addedLuck"])

    def test_an_owned_destination_gains_rather_than_being_overwritten(self) -> None:
        payload, destination = self.recode(
            {"jobLevels": [90.0, 0.0, 0.0], "skillBoost": 200, "luck": 100},
            source_boost=500, source_luck=300, material_boost=1000,
        )
        # 20.0% held + 90.0% carried is over the ceiling, so it lands on it.
        self.assertEqual(1000, destination["skillBoost"])
        # 10.0 held + 30.0 carried + the 5.0 an owned destination takes.
        self.assertEqual(450, destination["luck"])
        self.assertEqual([90.0, 0.0, 0.0], destination["jobLevels"], "the level must not reset")
        self.assertEqual((80, 35), (payload["addedSkillBoost"], payload["addedLuck"]))

    def test_the_result_screen_is_told_what_it_gained(self) -> None:
        """All four keys the client's recode callback reads."""
        payload, _ = self.recode(None, source_boost=100, source_luck=0, material_boost=0)
        for key in ("overlapped", "addedSkillBoost", "addedLuck", "addedPlusCount"):
            self.assertIn(key, payload)
        self.assertEqual(0, payload["addedPlusCount"], "nothing grants a plus count yet")


class RebirthMaterialConsumptionTest(unittest.TestCase):
    """The monsters are spent by the recode, and the account may raise them again.

    "The two monsters will also be lost upon recoding, and may be recruited
    again through the usual methods." Keeping them on the roster and instead
    barring their ids for ever was the substitute for that, and it closed the
    loop the same record describes: recoding a character again to raise its
    Skill Boost and Luck needs its monsters again.
    """

    def account(self, state: BootstrapState, recipe, *, extra_rows=()) -> None:
        items = [0] * 181
        for item_id, count in recipe.items.items():
            items[item_id - 1] = (count + 5) * 4
        rows = [{"id": recipe.source_character_id, "jobID": 0, "jobLevels": [90.0, 0.0, 0.0],
                 "jobSlots": [0.0, 0.0, 0.0], "skillBoost": 0, "luck": 0, "buddy": 0}]
        rows += [{"id": material_id, "jobID": 0, "jobLevels": [float(level), 0.0, 0.0],
                  "jobSlots": [0.0, 0.0, 0.0], "skillBoost": 0, "luck": 0, "buddy": 0}
                 for material_id, level in recipe.materials]
        rows += [dict(row) for row in extra_rows]
        state.create_account("token", "account", {
            "coins": recipe.coins * 4 + 1000, "itemList": items, "summonList": [0] * 16,
            "progressCode": 0x01000000 | (9 << 6) | 1, "worldMapNo": 0,
            # A monster a *main* squad fields is refused outright now (see
            # `RebirthMaterialAvailabilityTest`), because nothing can correct
            # the client's `teamMembers` before its next launch. A versus squad
            # can still be fielding one, `LoadChrData` repairs those, and the
            # slot must still empty here -- a consumed character a squad goes
            # on naming is the exact damage this route has done before.
            "teamMembers": [0] * 6,
            "teamMembers_VS": [recipe.materials[0][0]] + [0] * 17,
            "chrdata": rows, "buddyInfo": {"list": [], "record": []},
        })
        with state.lock:
            state.accounts["account"]["tutorial_phase"] = "free_roam"
            state.accounts["account"]["initial_userdata_served"] = True
            state._persist_locked()

    def test_the_monsters_leave_the_roster_and_their_squad_slots_empty(self) -> None:
        catalog = build_bundled_rebirth_policy()
        recipe = catalog.recipes[1]
        with tempfile.TemporaryDirectory() as directory:
            state = BootstrapState(Path(directory) / "state.json")
            self.account(state, recipe)
            server, thread = start_server(("127.0.0.1", 0), bootstrap_profile(), state,
                                          rebirth_catalog=catalog)
            try:
                _, payload = post(server, "/gd/rebirth", "recode", "rebirthID=1&useJoker=False")
                self.assertTrue(payload["success"], payload)
                userdata = state.userdata_for("token")
            finally:
                stop_server(server, thread)
        self.assertEqual([recipe.destination_character_id], [row["id"] for row in userdata["chrdata"]])
        self.assertEqual([0] * 18, userdata["teamMembers_VS"])

    def test_a_material_a_main_squad_fields_is_not_available(self) -> None:
        """A fielded monster cannot be spent, for the reason a fielded source cannot.

        The client marks this itself -- `UIRebirthMonItem.SetItem` tints an
        `IsInAnyTeam` monster and labels it -- so a player should not meet this.
        Leaving the rule to the client is what left the source ungated.
        """
        catalog = build_bundled_rebirth_policy()
        recipe = catalog.recipes[1]
        with tempfile.TemporaryDirectory() as directory:
            state = BootstrapState(Path(directory) / "state.json")
            self.account(state, recipe)
            with state.lock:
                userdata = state.accounts["account"]["userdata"]
                userdata["teamMembers"] = [recipe.materials[0][0], 0, 0, 0, 0, 0]
                userdata["teamMembers_VS"] = [0] * 18
                state._persist_locked()
            server, thread = start_server(("127.0.0.1", 0), bootstrap_profile(), state,
                                          rebirth_catalog=catalog)
            try:
                _, payload = post(server, "/gd/rebirth", "recode", "rebirthID=1&useJoker=False")
                settled = state.userdata_for("token")
            finally:
                stop_server(server, thread)
        # Unavailable is spelled as a monster the account is short of, which is
        # the one message the client has for it and the truth of the matter.
        self.assertEqual(4, payload["cmdError"])
        self.assertIn(recipe.source_character_id, [row["id"] for row in settled["chrdata"]])
        self.assertIn(recipe.materials[0][0], [row["id"] for row in settled["chrdata"]])
        self.assertEqual([recipe.materials[0][0], 0, 0, 0, 0, 0], settled["teamMembers"])

    def test_a_joker_a_main_squad_fields_cannot_stand_in(self) -> None:
        catalog = build_bundled_rebirth_policy()
        recipe = catalog.recipes[1]
        with tempfile.TemporaryDirectory() as directory:
            state = BootstrapState(Path(directory) / "state.json")
            # The account is short the second monster and holds a Joker that
            # could cover it -- but the Joker is fielded, so it cannot be spent.
            self.account(state, recipe, extra_rows=[
                {"id": BUNDLED_JOKER_CHARACTER_ID, "jobID": 0,
                 "jobLevels": [float(JOKER_SUBSTITUTE_LEVEL), 0.0, 0.0],
                 "jobSlots": [0.0, 0.0, 0.0], "skillBoost": 0, "luck": 0, "buddy": 0},
            ])
            with state.lock:
                userdata = state.accounts["account"]["userdata"]
                userdata["chrdata"] = [
                    row for row in userdata["chrdata"]
                    if row["id"] != recipe.materials[1][0]
                ]
                userdata["teamMembers"] = [BUNDLED_JOKER_CHARACTER_ID, 0, 0, 0, 0, 0]
                userdata["teamMembers_VS"] = [0] * 18
                state._persist_locked()
            server, thread = start_server(("127.0.0.1", 0), bootstrap_profile(), state,
                                          rebirth_catalog=catalog)
            try:
                _, payload = post(server, "/gd/rebirth", "recode", "rebirthID=1&useJoker=True")
                settled = state.userdata_for("token")
            finally:
                stop_server(server, thread)
        # Not `NotEnoughMonsButCanUseJoker`: that is an offer, and this one
        # could not be honoured.
        self.assertEqual(4, payload["cmdError"])
        self.assertIn(BUNDLED_JOKER_CHARACTER_ID, [row["id"] for row in settled["chrdata"]])

    def test_the_same_recipe_runs_again_once_the_monsters_are_raised_again(self) -> None:
        """The bar made this impossible, so the documented loop was unreachable."""
        catalog = build_bundled_rebirth_policy()
        recipe = catalog.recipes[1]
        with tempfile.TemporaryDirectory() as directory:
            state = BootstrapState(Path(directory) / "state.json")
            self.account(state, recipe)
            server, thread = start_server(("127.0.0.1", 0), bootstrap_profile(), state,
                                          rebirth_catalog=catalog)
            try:
                _, first = post(server, "/gd/rebirth", "recode-1", "rebirthID=1&useJoker=False")
                self.assertTrue(first["success"], first)
                # Recruit the source and both monsters again, as the record says
                # an account may, and run the same recipe a second time.
                with state.lock:
                    rows = state.accounts["account"]["userdata"]["chrdata"]
                    rows.append({"id": recipe.source_character_id, "jobID": 0, "jobLevels": [90.0, 0.0, 0.0],
                                 "jobSlots": [0.0, 0.0, 0.0], "skillBoost": 0, "luck": 0, "buddy": 0})
                    rows += [{"id": material_id, "jobID": 0, "jobLevels": [float(level), 0.0, 0.0],
                              "jobSlots": [0.0, 0.0, 0.0], "skillBoost": 0, "luck": 700, "buddy": 0}
                             for material_id, level in recipe.materials]
                    state._persist_locked()
                _, second = post(server, "/gd/rebirth", "recode-2", "rebirthID=1&useJoker=False")
            finally:
                stop_server(server, thread)
        self.assertTrue(second["success"], second)
        self.assertTrue(second["overlapped"], "the destination is now the copy the account holds")
        # 5.0 for the owned destination plus a fifth of each monster's 70.0.
        self.assertEqual(33, second["addedLuck"])


class RebirthJokerSubstitutionTest(unittest.TestCase):
    """The Joker stands in for one monster, and only from level 50.

    "Joker Λ can be used as a replacement for one missing or under-leveled
    monster", and, from its own page, "In order to be used as a replacement,
    Joker Λ must be at level 50 and one of the two material monsters must be
    under level 50 or not recruited." Neither half was enforced: one Joker at
    any level covered however many monsters a recipe asked for.
    """

    def recode(self, material_levels: tuple[int | None, int | None], joker_level: int | None,
               *, use_joker: bool, material_luck: int = 0, joker_luck: int = 0) -> dict:
        catalog = build_bundled_rebirth_policy()
        recipe = catalog.recipes[1]
        with tempfile.TemporaryDirectory() as directory:
            state = BootstrapState(Path(directory) / "state.json")
            items = [0] * 181
            for item_id, count in recipe.items.items():
                items[item_id - 1] = count + 5
            rows = [{"id": recipe.source_character_id, "jobID": 0, "jobLevels": [90.0, 0.0, 0.0],
                     "jobSlots": [0.0, 0.0, 0.0], "skillBoost": 0, "luck": 0, "buddy": 0}]
            rows += [{"id": material_id, "jobID": 0, "jobLevels": [float(level), 0.0, 0.0],
                      "jobSlots": [0.0, 0.0, 0.0], "skillBoost": 0, "luck": material_luck, "buddy": 0}
                     for (material_id, _), level in zip(recipe.materials, material_levels)
                     if level is not None]
            if joker_level is not None:
                rows.append({"id": BUNDLED_JOKER_CHARACTER_ID, "jobID": 0,
                             "jobLevels": [float(joker_level), 0.0, 0.0], "jobSlots": [0.0, 0.0, 0.0],
                             "skillBoost": 0, "luck": joker_luck, "buddy": 0})
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
                _, payload = post(server, "/gd/rebirth", "recode",
                                  f"rebirthID=1&useJoker={use_joker}")
                return payload | {"roster": [row["id"] for row in state.userdata_for("token")["chrdata"]]}
            finally:
                stop_server(server, thread)

    def test_a_joker_at_fifty_stands_in_for_the_one_missing_monster(self) -> None:
        payload = self.recode((50, None), JOKER_SUBSTITUTE_LEVEL, use_joker=True)
        self.assertNotIn("cmdError", payload, payload)
        # The monster the account had and the Joker that replaced the one it
        # did not are both spent, and the recoded unit is all that is left.
        self.assertEqual([623], payload["roster"])

    def test_the_offer_is_made_before_the_joker_is_spent(self) -> None:
        """Code 7 is what the client re-submits against with `useJoker=True`."""
        payload = self.recode((50, None), JOKER_SUBSTITUTE_LEVEL, use_joker=False)
        self.assertEqual((True, 7), (payload["success"], payload["cmdError"]))
        self.assertIn(BUNDLED_JOKER_CHARACTER_ID, payload["roster"])

    def test_two_missing_monsters_are_beyond_one_joker(self) -> None:
        """The defect: a single Joker used to cover a recipe's whole monster bill."""
        payload = self.recode((None, None), JOKER_SUBSTITUTE_LEVEL, use_joker=True)
        self.assertEqual((True, 4), (payload["success"], payload["cmdError"]))
        # A refusal spends nothing, so the Joker is still there for a recipe
        # the account can actually meet.
        self.assertIn(BUNDLED_JOKER_CHARACTER_ID, payload["roster"])

    def test_two_missing_monsters_are_never_offered_the_joker(self) -> None:
        """An offer that would be refused must not be made in the first place."""
        payload = self.recode((None, None), JOKER_SUBSTITUTE_LEVEL, use_joker=False)
        self.assertEqual((True, 4), (payload["success"], payload["cmdError"]))

    def test_a_joker_below_fifty_cannot_stand_in_and_is_not_offered(self) -> None:
        under = JOKER_SUBSTITUTE_LEVEL - 1
        self.assertEqual(4, self.recode((50, None), under, use_joker=True)["cmdError"])
        self.assertEqual(4, self.recode((50, None), under, use_joker=False)["cmdError"])

    def test_a_recipe_the_account_can_meet_never_touches_the_joker(self) -> None:
        payload = self.recode((50, 50), JOKER_SUBSTITUTE_LEVEL, use_joker=True)
        self.assertNotIn("cmdError", payload, payload)
        self.assertEqual([623, BUNDLED_JOKER_CHARACTER_ID], sorted(payload["roster"]))

    def test_the_under_level_monster_the_joker_replaced_survives_and_carries_nothing(self) -> None:
        """It was not used, so it is not spent -- and its Luck stays with it.

        The Joker is the material in its place, so the Joker's own fifth is the
        one that comes across.
        """
        payload = self.recode(
            (50, JOKER_SUBSTITUTE_LEVEL - 1), JOKER_SUBSTITUTE_LEVEL,
            use_joker=True, material_luck=700, joker_luck=500,
        )
        self.assertNotIn("cmdError", payload, payload)
        self.assertEqual([145, 623], sorted(payload["roster"]))
        # 14.0 from the monster that was spent and 10.0 from the Joker; the
        # under-level 145 keeps its own 70.0 and contributes none of it.
        self.assertEqual(24, payload["addedLuck"])


class RebirthMaxLuckTest(unittest.TestCase):
    """"Recoding is not available if the recoded character is already at 100 Luck.\""""

    def recode_into(self, held_luck: int) -> dict:
        catalog = build_bundled_rebirth_policy()
        recipe = catalog.recipes[1]
        with tempfile.TemporaryDirectory() as directory:
            state = BootstrapState(Path(directory) / "state.json")
            items = [0] * 181
            for item_id, count in recipe.items.items():
                items[item_id - 1] = count + 5
            rows = [{"id": recipe.source_character_id, "jobID": 0, "jobLevels": [90.0, 0.0, 0.0],
                     "jobSlots": [0.0, 0.0, 0.0], "skillBoost": 0, "luck": 0, "buddy": 0}]
            rows += [{"id": material_id, "jobID": 0, "jobLevels": [float(level), 0.0, 0.0],
                      "jobSlots": [0.0, 0.0, 0.0], "skillBoost": 0, "luck": 0, "buddy": 0}
                     for material_id, level in recipe.materials]
            rows.append({"id": recipe.destination_character_id, "jobID": 0, "jobLevels": [99.0, 0.0, 0.0],
                         "jobSlots": [0.0, 0.0, 0.0], "skillBoost": 0, "luck": held_luck, "buddy": 0})
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
                _, payload = post(server, "/gd/rebirth", "recode", "rebirthID=1&useJoker=False")
                return payload | {"roster": [row["id"] for row in state.userdata_for("token")["chrdata"]]}
            finally:
                stop_server(server, thread)

    def test_a_destination_already_at_its_cap_is_refused_and_spends_nothing(self) -> None:
        catalog = build_bundled_rebirth_policy()
        recipe = catalog.recipes[1]
        payload = self.recode_into(character_luck_cap(recipe.destination_character_id))
        # A refusal reaches the client as `cmdError`, the way the Joker one does.
        self.assertEqual((True, 6), (payload["success"], payload["cmdError"]))
        # The refusal comes before anything is consumed, so the monsters and the
        # source are all still there to try again with.
        self.assertIn(recipe.source_character_id, payload["roster"])
        for material_id, _ in recipe.materials:
            self.assertIn(material_id, payload["roster"])

    def test_a_destination_one_tenth_below_its_cap_still_recodes(self) -> None:
        catalog = build_bundled_rebirth_policy()
        recipe = catalog.recipes[1]
        payload = self.recode_into(character_luck_cap(recipe.destination_character_id) - 1)
        self.assertNotIn("cmdError", payload, "one tenth short of the cap is not maxed")
        self.assertTrue(payload["overlapped"])


class RebirthJobSlotsTest(unittest.TestCase):
    """`jobSlots` is per job, so the source's cannot come across with the row.

    A destination is a different character with a different job list -- one job
    rather than three, for 64 of the 65 bundled recipes -- and a slot standing
    against a job the unit does not have is a shape no other route produces.
    """

    def recode(self, held: dict | None) -> dict:
        catalog = build_bundled_rebirth_policy()
        recipe = catalog.recipes[1]
        with tempfile.TemporaryDirectory() as directory:
            state = BootstrapState(Path(directory) / "state.json")
            items = [0] * 181
            for item_id, count in recipe.items.items():
                items[item_id - 1] = count + 5
            # Three jobs unlocked, all three slots filled: the source is exactly
            # the shape a long-played character has.
            rows = [{"id": recipe.source_character_id, "jobID": 2,
                     "jobLevels": [90.0, 85.0, 80.0], "jobSlots": [387131153.0, 52888865.0, 85132055.0],
                     "skillBoost": 0, "luck": 0}]
            rows += [{"id": material_id, "jobID": 0, "jobLevels": [float(level), 0.0, 0.0],
                      "jobSlots": [0.0, 0.0, 0.0], "skillBoost": 0, "luck": 0}
                     for material_id, level in recipe.materials]
            if held is not None:
                rows.append(held)
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
        return next(row for row in payload["chrdata"]
                    if row["id"] == recipe.destination_character_id)

    def test_the_rebirthed_unit_carries_no_slot_from_the_character_it_replaced(self) -> None:
        destination = self.recode(None)
        self.assertEqual([1.0, 0.0, 0.0], destination["jobLevels"])
        # Two of these stood against jobs the destination has neither unlocked
        # nor got, which is what the client could not draw.
        self.assertEqual([0.0, 0.0, 0.0], destination["jobSlots"])
        self.assertEqual(0, destination["jobID"], "the source's active job is not the new unit's")

    def test_an_already_owned_destination_keeps_its_own_slots_and_job(self) -> None:
        """The held copy's equipment is its own; a level 1 row must not clear it."""
        catalog = build_bundled_rebirth_policy()
        recipe = catalog.recipes[1]
        destination = self.recode({
            "id": recipe.destination_character_id, "jobID": 1,
            "jobLevels": [99.0, 50.0, 0.0], "jobSlots": [11.0, 22.0, 0.0],
            "skillBoost": 0, "luck": 0,
        })
        self.assertEqual([11.0, 22.0, 0.0], destination["jobSlots"])
        self.assertEqual(1, destination["jobID"])
        self.assertEqual([99.0, 50.0, 0.0], destination["jobLevels"], "its levels still survive")


class RebirthJobSlotRepairTest(unittest.TestCase):
    """A save that already carries the copied slots repairs itself on load."""

    def test_only_the_row_whose_slots_outlive_its_jobs_is_cleared(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            state = BootstrapState(path)
            state.create_account("token", "account", {"chrdata": [
                # The reported shape: one job unlocked, three jobs' slots, taken
                # verbatim from a source character that had three.
                {"id": 920, "jobID": 0, "jobLevels": [1.0, 0.0, 0.0],
                 "jobSlots": [387131153.0, 52888865.0, 85132055.0], "buddy": 0},
                # An unlocked job with an empty slot is ordinary and must stay.
                {"id": 25, "jobID": 0, "jobLevels": [15251415126.0, 11101184074.0, 0.0],
                 "jobSlots": [387130663.0, 0.0, 0.0], "buddy": 0},
            ]})
            with state.lock:
                state._persist_locked()
            state.close()

            repaired = BootstrapState(path)
            try:
                rows = {row["id"]: row for row in repaired.userdata_for("token")["chrdata"]}
                self.assertEqual([0.0, 0.0, 0.0], rows[920]["jobSlots"])
                self.assertEqual([387130663.0, 0.0, 0.0], rows[25]["jobSlots"])
                self.assertEqual([1.0, 0.0, 0.0], rows[920]["jobLevels"], "levels are not touched")
            finally:
                repaired.close()


def _companion(inventory_id: int, character_id: int) -> dict:
    """One owned Companion. `bid` tracks `iid` so the derived book holds both."""
    return {"bid": inventory_id, "lv": 1, "date": 0.0, "iid": inventory_id, "exp": 0, "flag": 0, "chrID": character_id}


class RebirthCompanionConsistencyTest(unittest.TestCase):
    """Rebirth must not leave a Companion attached to a character that left.

    A Companion and its character name each other, and `_valid_companion_equipment`
    judges the whole save rather than the part a write touches -- so one
    half-attached link refuses every later party or equip save with a 501,
    for as long as the save exists. Recode is where the link comes apart: the
    source leaves the roster, so its Companion has nothing left to hold on to.
    An already-owned destination keeps its own, which is why only one of the
    two here is unequipped.
    """

    def scenario(self) -> tuple[dict, dict, int]:
        catalog = build_bundled_rebirth_policy()
        recipe = catalog.recipes[1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = bootstrap_profile()
            state = BootstrapState(root / "state.json")
            items = [0] * 181
            for item_id, count in recipe.items.items():
                items[item_id - 1] = count + 5
            # The source carries one Companion and the already-owned
            # destination carries another; both survive the recode.
            rows = [(recipe.source_character_id, 90, 1), (recipe.destination_character_id, 1, 2)]
            rows += [(material_id, level, 0) for material_id, level in recipe.materials]
            state.create_account("token", "account", {
                "coins": recipe.coins + 1000, "itemList": items, "summonList": [0] * 16,
                "progressCode": 0x01000000 | (9 << 6) | 1, "worldMapNo": 0,
                # A fielded source is refused, so this one is benched.
                "teamMembers": [0] * 6,
                "teamMembers_VS": [0] * 18,
                "chrdata": [{"id": i, "jobID": 0, "jobLevels": [float(level), 0.0, 0.0],
                             "jobSlots": [], "skillBoost": 0, "luck": 0, "buddy": buddy}
                            for i, level, buddy in rows],
                "buddyInfo": {
                    "list": [_companion(1, recipe.source_character_id), _companion(2, recipe.destination_character_id)],
                    "record": [_companion(1, recipe.source_character_id), _companion(2, recipe.destination_character_id)],
                },
            })
            with state.lock:
                state.accounts["account"]["tutorial_phase"] = "free_roam"
                state.accounts["account"]["initial_userdata_served"] = True
                state._persist_locked()
            server, thread = start_server(("127.0.0.1", 0), profile, state, rebirth_catalog=catalog)
            try:
                _, rebirthed = post(server, "/gd/rebirth", "rebirth", "rebirthID=1&useJoker=False")
                userdata = state.userdata_for("token")
                # `LoadBuddyInfo` drops the dirty bits a recode's own answer
                # rebuilt, so the save that follows one serialises `[]` --
                # which still puts the whole document past the equipment check.
                save = urlencode([
                    ("chrdata", "[]"), ("buddyInfo", "[]"),
                    ("teamMembers", json.dumps(userdata["teamMembers"])),
                    ("teamMembers_VS", json.dumps(userdata["teamMembers_VS"])),
                    ("teamBuddies_VS", "[]"), ("teamNo", "1"), ("teamNo_VS", "1"),
                    ("summonId", "1"), ("lastUpdate", "1"),
                ])
                status, _ = post(server, "/gd/userdata", "party", save)
            finally:
                stop_server(server, thread)
            return rebirthed, userdata, status

    def test_the_recode_answers_with_the_companions_the_account_owns(self) -> None:
        rebirthed, _, _ = self.scenario()
        # An empty box here is not a no-op: `LoadBuddyInfo` resets the client's
        # own and refills it from what arrives, so an empty one leaves every
        # character drawing against a Companion that is no longer there.
        self.assertEqual([1, 2], [companion["iid"] for companion in rebirthed["buddyInfo"]["list"]])

    def test_the_departed_source_lets_its_companion_go_and_nothing_else_does(self) -> None:
        _, userdata, _ = self.scenario()
        catalog = build_bundled_rebirth_policy()
        destination_id = catalog.recipes[1].destination_character_id
        links = {companion["iid"]: companion["chrID"] for companion in userdata["buddyInfo"]["list"]}
        self.assertEqual({1: 0, 2: destination_id}, links)
        # Every link that remains still names a character that claims it back,
        # which is the whole condition `_valid_companion_equipment` reads. The
        # source is recoded away and both monsters are consumed, so the held
        # destination is all that is left to claim anything.
        held = {row["id"]: row["buddy"] for row in userdata["chrdata"]}
        self.assertEqual({destination_id: 2}, held)
        self.assertEqual(
            {1: 0, 2: destination_id},
            {companion["iid"]: companion["chrID"] for companion in userdata["buddyInfo"]["record"]},
            "the book is derived from the owned list and must be reprojected with it",
        )

    def test_the_account_can_still_save_a_party_afterwards(self) -> None:
        _, _, status = self.scenario()
        # This is the whole cost of a half-attached link: without the repair
        # every party save answers 501 for the life of the save.
        self.assertEqual(200, status)
