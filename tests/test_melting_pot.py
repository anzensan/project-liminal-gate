"""Melting Pot: the three chapters inside the client's Donation range.

Chapters 9100--9102 are `[るつぼの都] トカゲ / ケモノ / ヒト`, fifteen sections
each. They were excluded while the range was read as Donation content; see
`docs/findings.md`, 2026-08-07. These tests pin the shape the generator emits,
the folded card the selector receives, and a clear that banks the candy the
chapter programs attach to their own spawns.
"""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import urlencode

from liminal_gate.bootstrap_server import BootstrapState
from liminal_gate.event_catalog import load_event_catalog
from liminal_gate.event_catalog_generator import EventCatalogGeneratorError, build_catalog
from liminal_gate.event_manifest_data import MELTING_POT_MANIFEST_ROWS, MELTING_POT_SECTIONS
from liminal_gate.save_validation import ITEM_SLOTS, MAX_ITEM_STACK
from tests.support import bootstrap_profile, get, request, start_server, stop_server, write_json


CHAPTERS = (9100, 9101, 9102)
#: The record's Lizardfolk stamina curve, which BattleData matches quest for
#: quest: five sections at 5, five at 10, five at 15.
STAMINA_CURVE = (5,) * 5 + (10,) * 5 + (15,) * 5
#: `Chapter910x.Init_DROPPOD` -- the record's Candy Pot -- and the six boss
#: spawns per race. See the module docstring's findings reference.
CANDYBOXES = (175, 176, 177)
CANDIES = (161, 162, 163)


def character(identifier: int) -> dict[str, object]:
    return {
        "id": identifier, "buddy": 0, "date": 0.0, "jobSlots": [0, 0, 0],
        "jobLevels": [1, 0, 0], "jobID": 0, "flags": 0, "skillBoost": 0,
    }


def battledata(sections_per_chapter: int = MELTING_POT_SECTIONS) -> dict[str, object]:
    """A BattleData projection carrying the three Melting Pot chapters."""
    stages = []
    for chapter in CHAPTERS:
        for section in range(1, sections_per_chapter + 1):
            stages.append({
                "chapter": chapter, "section": section,
                "stamina": STAMINA_CURVE[(section - 1) % len(STAMINA_CURVE)],
                "coins": 0, "battle_count": 5, "has_battle": True,
            })
    return {"schema_version": 1, "provenance": "user-derived", "stages": stages}


class MeltingPotCatalogTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.characters = {"schema_version": 1, "provenance": "user-supplied", "characters": []}
        self.character_path = write_json(self.root / "characters.json", self.characters)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def build(self, **kwargs: object) -> dict[str, object]:
        document, _notes = build_catalog(
            battledata(**kwargs), self.characters, self.character_path,
        )
        return document

    def test_the_manifest_names_one_row_per_race(self) -> None:
        self.assertEqual(CHAPTERS, tuple(row[2] for row in MELTING_POT_MANIFEST_ROWS))
        self.assertEqual(
            ("sp_ch_9100", "sp_ch_9101", "sp_ch_9102"),
            tuple(row[1] for row in MELTING_POT_MANIFEST_ROWS),
        )

    def test_every_section_is_generated_with_its_recovered_stamina(self) -> None:
        rows = [r for r in self.build()["stages"] if r["chapter"] in CHAPTERS]
        self.assertEqual(len(CHAPTERS) * MELTING_POT_SECTIONS, len(rows))
        lizardfolk = sorted(
            (r for r in rows if r["chapter"] == 9100), key=lambda r: r["section"],
        )
        self.assertEqual(list(STAMINA_CURVE), [r["stamina"] for r in lizardfolk])
        self.assertEqual(list(range(1, 16)), [r["section"] for r in lizardfolk])

    def test_each_race_is_one_folded_card(self) -> None:
        # The client returns its own hard-coded NumOfDonationQuestSections from
        # GetSectionCount, so it expands the sections itself.
        rows = [r for r in self.build()["stages"] if r["chapter"] in CHAPTERS]
        self.assertEqual({"9100", "9101", "9102"}, {r["selector_id"] for r in rows})

    def test_a_section_count_disagreeing_with_the_client_is_refused(self) -> None:
        with self.assertRaises(EventCatalogGeneratorError) as caught:
            self.build(sections_per_chapter=14)
        self.assertIn("expected 15 BattleData sections", str(caught.exception))

    def test_loaded_stages_settle_from_the_client_s_reported_drops(self) -> None:
        path = write_json(self.root / "events.json", self.build())
        catalog = load_event_catalog(path, self.character_path)
        stages = [s for s in catalog.stages if s.chapter in CHAPTERS]
        self.assertEqual(len(CHAPTERS) * MELTING_POT_SECTIONS, len(stages))
        self.assertTrue(all(stage.projected_rewards for stage in stages))
        self.assertTrue(all(stage.selector == "special" for stage in stages))

    def test_the_folded_cards_appear_only_past_the_local_gate(self) -> None:
        path = write_json(self.root / "events.json", self.build())
        catalog = load_event_catalog(path, self.character_path)
        opened = catalog.client_lists(0x01000000 | (9 << 6) | 1)["specialQuestList"]
        self.assertEqual(["9100", "9101", "9102"], [x for x in opened if x.startswith("91")])
        early = catalog.client_lists(0x01000000 | (2 << 6) | 1)["specialQuestList"]
        self.assertEqual([], [x for x in early if x.startswith("91")])


class MeltingPotRuntimeTest(unittest.TestCase):
    """Entry and clear over the real transport, banking a recovered drop."""

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.state_path = self.root / "state.json"
        characters = {"schema_version": 1, "provenance": "user-supplied", "characters": []}
        character_path = write_json(self.root / "characters.json", characters)
        document, _notes = build_catalog(battledata(), characters, character_path)
        self.catalog = load_event_catalog(
            write_json(self.root / "events.json", document), character_path,
        )
        self.token, self.account_id = "melting-pot-token", "melting-pot-account"
        state = BootstrapState(self.state_path)
        state.create_account(self.token, self.account_id, {
            "coins": 0, "energy": 20, "freeEnergy": 2,
            "progressCode": 0x01000000 | (9 << 6) | 1, "worldMapNo": 0,
            "chrdata": [character(3)],
            "itemList": [0] * ITEM_SLOTS, "summonList": [0] * 16,
        })
        state.accounts[self.account_id]["tutorial_phase"] = "free_roam"
        state._persist_locked()
        state.close()
        self.server, self.thread = start_server(
            ("127.0.0.1", 0), bootstrap_profile(), BootstrapState(self.state_path),
            event_catalog=self.catalog, stamina=True,
        )

    def tearDown(self) -> None:
        stop_server(self.server, self.thread)
        self.temporary_directory.cleanup()

    def post(self, path: str, body: bytes) -> tuple[int, dict]:
        return request(
            self.server, "POST", path, body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    def account(self) -> dict:
        return json.loads(self.state_path.read_text(encoding="utf-8"))["accounts"][self.account_id]

    def clear_body(self, chapter: int, section: int, items: dict[str, int]) -> bytes:
        userdata = self.account()["userdata"]
        inventory = list(userdata["itemList"])
        for item_id, count in items.items():
            inventory[int(item_id) - 1] = min(
                MAX_ITEM_STACK, inventory[int(item_id) - 1] + count,
            )
        return urlencode({
            "progressCode": userdata["progressCode"], "worldMapNo": userdata["worldMapNo"],
            "valuables": json.dumps({
                "energyAppStore": 0, "energy": userdata["energy"], "energyAndApp": 0,
                "freeEnergy": userdata["freeEnergy"], "energyGooglePlay": 0,
                "coins": userdata["coins"],
            }),
            "chrdata": json.dumps(userdata["chrdata"]),
            "itemList": json.dumps(inventory),
            "summonList": json.dumps(userdata["summonList"]),
            "battle_result": json.dumps({
                "coins": 0, "buddies": [], "items": items, "exp": 0,
                "section": section, "monsters": [], "summons": [], "luckynum": 0,
                "chapter": chapter, "unableluckdrop": False, "boostup": [0] * 6,
            }),
            "itmp0": 0, "itmp1": 0, "lastUpdate": 1,
        }).encode()

    def test_the_selector_advertises_three_cards_and_login_supplies_their_flags(self) -> None:
        status, server_status = get(
            self.server, f"/gd/get_server_status?otk={self.token}&requestID=status",
        )
        self.assertEqual(200, status)
        self.assertEqual(
            ["9100", "9101", "9102"],
            [x for x in server_status["constants"]["specialQuestList"] if x.startswith("91")],
        )
        status, login = get(
            self.server, f"/gd/login?otk={self.token}&uuid={self.account_id}&requestID=login",
        )
        self.assertEqual(200, status)
        self.assertLessEqual(
            {"sp_ch_9100", "sp_ch_9101", "sp_ch_9102"}, set(login["eventFlags"]),
        )

    def test_entry_charges_the_recovered_stamina_and_a_clear_banks_the_candy_pot(self) -> None:
        start = urlencode({
            "stamina": "5", "coins": "0", "chapter": "9100", "section": "1", "lastUpdate": "1",
        }).encode()
        status, started = self.post(
            f"/gd/start_quest?otk={self.token}&requestID=mp-start", start,
        )
        self.assertEqual(200, status, started)
        self.assertTrue(started["success"])
        self.assertEqual("generic_story_active", self.account()["tutorial_phase"])

        # Init_DROPPOD drops one of the three Candyboxes at a 100 ratio.
        clear = self.clear_body(9100, 1, {str(CANDYBOXES[0]): 1})
        status, cleared = self.post(
            f"/gd/clear_quest?otk={self.token}&requestID=mp-clear", clear,
        )
        self.assertEqual(200, status, cleared)
        self.assertEqual("free_roam", self.account()["tutorial_phase"])
        self.assertEqual(1, self.account()["userdata"]["itemList"][CANDYBOXES[0] - 1])

    def test_a_clear_stamps_the_date_the_next_section_is_chained_to(self) -> None:
        """The chain is the client's, and it reads only this map.

        `9100-2` carries BattleData `parentQuest` `9100-1`, and
        `UISpecialSelect.IsQuestOpen` drops a section from the list it builds
        unless `UserData.GetQuestClearDate` answers nonzero for that parent. The
        stamp must be a decimal: the client reads it through LitJson's double
        accessor, which raises rather than converting a whole number.
        """
        start = urlencode({
            "stamina": "5", "coins": "0", "chapter": "9100", "section": "1", "lastUpdate": "1",
        }).encode()
        status, _started = self.post(
            f"/gd/start_quest?otk={self.token}&requestID=mp-date-start", start,
        )
        self.assertEqual(200, status)
        status, cleared = self.post(
            f"/gd/clear_quest?otk={self.token}&requestID=mp-date-clear",
            self.clear_body(9100, 1, {str(CANDYBOXES[0]): 1}),
        )
        self.assertEqual(200, status, cleared)
        self.assertEqual(["9100-1"], list(cleared["questClearDate"]))
        stamp = cleared["questClearDate"]["9100-1"]
        self.assertIsInstance(stamp, float)
        self.assertGreater(stamp, 0.0)
        self.assertEqual({"9100-1": stamp}, self.account()["userdata"]["questClearDate"])
        status, userdata = get(
            self.server, f"/gd/userdata?otk={self.token}&requestID=mp-date-read",
        )
        self.assertEqual(200, status)
        self.assertEqual({"9100-1": stamp}, userdata["questClearDate"])

    def test_a_boss_candy_drop_settles_on_a_later_section(self) -> None:
        start = urlencode({
            "stamina": "10", "coins": "0", "chapter": "9101", "section": "6", "lastUpdate": "1",
        }).encode()
        status, _started = self.post(
            f"/gd/start_quest?otk={self.token}&requestID=mp-start-6", start,
        )
        self.assertEqual(200, status)
        # The six boss spawns per race carry {161, 162, 163} at a 3 ratio.
        clear = self.clear_body(9101, 6, {str(CANDIES[2]): 1})
        status, cleared = self.post(
            f"/gd/clear_quest?otk={self.token}&requestID=mp-clear-6", clear,
        )
        self.assertEqual(200, status, cleared)
        self.assertEqual(1, self.account()["userdata"]["itemList"][CANDIES[2] - 1])

    def test_a_clear_never_advances_story_progress(self) -> None:
        before = self.account()["userdata"]["progressCode"]
        start = urlencode({
            "stamina": "5", "coins": "0", "chapter": "9102", "section": "2", "lastUpdate": "1",
        }).encode()
        self.post(f"/gd/start_quest?otk={self.token}&requestID=mp-start-2", start)
        status, _cleared = self.post(
            f"/gd/clear_quest?otk={self.token}&requestID=mp-clear-2",
            self.clear_body(9102, 2, {}),
        )
        self.assertEqual(200, status)
        self.assertEqual(before, self.account()["userdata"]["progressCode"])


if __name__ == "__main__":
    unittest.main()
