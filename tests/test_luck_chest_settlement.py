"""What an authored Luck Treasure Chest actually delivers at clear.

Coins and items were reconciled against the client's own submission from the
start. The other two reward forms were not delivered at all: `chest_companions`
existed and was unit-tested and no caller ever invoked it, while the pools
carried thirty-nine Companion rewards across twenty-seven stage and tier slots.
A chest could show a Companion, the clear could return 200, and the player kept
nothing. Nothing in the suite looked at `active_luck_result` end to end, which
is how that shipped.

The asymmetry is structural rather than an oversight of shape: the generic
story clear body is an exact field tuple carrying `chrdata`, `itemList` and
`summonList` and no Companion box, so there is no field for the client to
report a chest Companion back through. The server authored the chest, so the
server grants it.
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import urlencode

from unittest.mock import patch

from liminal_gate.bootstrap_server import BootstrapState, _award_chest_grants
from liminal_gate.luck_runtime import chest_characters, chest_coins, chest_companions, chest_items
from liminal_gate.story_catalog import load_story_catalog
from tests.support import bootstrap_profile, request, start_server, stop_server


#: Any pooled stage; the settlement tests force the chest rather than rolling
#: one, so they test what a chest delivers and not which reward a seed picks.
#: Rolling would couple them to pool contents, and a pool that gains a reward
#: legitimately shifts every seed's selection within that tier.
CHAPTER, SECTION = 4, 1
ITEM_SLOTS = 181

#: One chest carrying all four wire forms at once.
FORCED_CHEST = ["C50", "I11", "O128", "O129", "M199", "O128"]


def progress(chapter: int, section: int) -> int:
    return (1 << 24) | (chapter << 6) | section


class ChestRewardFormTest(unittest.TestCase):
    """The four wire forms, read off the slots the client renders."""

    SLOTS = ["C50", "I11", "O128", "M199", "", "M199"]

    def test_each_form_is_read_from_its_own_prefix(self) -> None:
        self.assertEqual({11: 1}, chest_items(self.SLOTS))
        self.assertEqual((128,), chest_companions(self.SLOTS))
        self.assertEqual((199, 199), chest_characters(self.SLOTS))

    def test_an_empty_slot_and_a_malformed_one_yield_nothing(self) -> None:
        self.assertEqual((), chest_characters(["", "M", "Mx", "O12"]))


class ChestGrantUnitTest(unittest.TestCase):
    def test_a_duplicate_character_grants_nothing(self) -> None:
        """No source says a chest raised a duplicate's Skill Boost."""
        held = {"id": 199, "buddy": 0, "date": 0.0, "jobSlots": [0, 0, 0],
                "jobLevels": [7.0, 0.0, 0.0], "jobID": 0, "flags": 0, "skillBoost": 40}
        userdata = {"chrdata": [held], "buddyInfo": {"list": [], "record": []}}
        announced = _award_chest_grants(userdata, ["M199"])
        self.assertEqual({}, announced)
        self.assertEqual([held], userdata["chrdata"])

    def test_a_full_box_drops_the_remainder_rather_than_refusing(self) -> None:
        """Refusing would strand a won battle over a reward the player cannot
        make room for in the middle of settlement."""
        owned = [
            {"bid": 1, "lv": 1, "date": 0.0, "iid": i, "exp": 0, "flag": 0, "chrID": 0}
            for i in range(1, 1001)
        ]
        userdata = {"chrdata": [], "buddyInfo": {"list": owned, "record": []},
                    "nextCompanionInventoryId": 1001}
        _award_chest_grants(userdata, ["O128", "O129"])
        self.assertEqual(1000, len(userdata["buddyInfo"]["list"]))

    def test_a_chest_with_neither_form_leaves_the_account_alone(self) -> None:
        """The common case, and it must not create a box that was not there."""
        userdata: dict = {}
        self.assertEqual({}, _award_chest_grants(userdata, ["C50", "I11"]))
        self.assertEqual({}, userdata)


class ChestSettlementTest(unittest.TestCase):
    """Real HTTP through the generic story start and clear."""

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.state_path = self.root / "state.json"
        catalog_path = self.root / "story.json"
        catalog_path.write_text(json.dumps({
            "schema_version": 1, "provenance": "user-supplied",
            "stages": [{
                "chapter": CHAPTER, "section": SECTION, "stamina": 5, "coins": 0,
                "clear_progress_code": progress(CHAPTER, SECTION + 1), "clear_coins": 0,
            }],
        }), encoding="utf-8")
        self.catalog = load_story_catalog(catalog_path)
        self.token, self.account_id = "chest-token", "chest-account"
        # The client's Luck ceiling, so the Companion-bearing tiers are certain
        # and the test does not depend on a roll.
        self.character = {
            "id": 9001, "buddy": 0, "date": 0.0, "jobSlots": [0, 0, 0],
            "jobLevels": [1.0, 0.0, 0.0], "jobID": 0, "flags": 0,
            "skillBoost": 0, "luck": 1000,
        }
        self.start_server()

    def start_server(self) -> None:
        self.server, self.thread = start_server(
            ("127.0.0.1", 0), bootstrap_profile(), BootstrapState(self.state_path),
            story_catalog=self.catalog,
        )
        self.addCleanup(self.stop_server)
        if self.account_id not in self.server.state.accounts:
            self.server.state.create_account(self.token, self.account_id, {
                "coins": 0, "worldMapNo": 0, "progressCode": progress(CHAPTER, SECTION),
                "chrdata": [self.character], "teamMembers": [9001, 0, 0, 0, 0, 0],
                "buddyInfo": {"list": [], "record": []}, "nextCompanionInventoryId": 1,
                "itemList": [0] * ITEM_SLOTS, "summonList": [0] * 16,
            })
            with self.server.state.lock:
                account = self.server.state.accounts[self.account_id]
                account["tutorial_phase"] = "free_roam"
                account["initial_userdata_served"] = True
                self.server.state._persist_locked()

    def stop_server(self) -> None:
        stop_server(self.server, self.thread)

    def restart(self) -> None:
        self.stop_server()
        self.start_server()

    def post(self, path: str, fields: list[tuple[str, str]]):
        return request(
            self.server, "POST", path, urlencode(fields),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    def account(self) -> dict:
        return json.loads(self.state_path.read_text(encoding="utf-8"))["accounts"][self.account_id]

    def start(self, request_id: str = "s1") -> list[str]:
        with patch("liminal_gate.bootstrap_server.roll_luck_result", return_value=list(FORCED_CHEST)):
            status, started = self.post(f"/gd/start_quest?otk={self.token}&requestID={request_id}", [
                ("stamina", "5"), ("coins", "0"), ("chapter", str(CHAPTER)),
                ("section", str(SECTION)), ("lastUpdate", "1"),
            ])
        self.assertEqual(200, status)
        self.assertEqual(FORCED_CHEST, started["luckResult"])
        return started["luckResult"]

    def clear(self, chest: list[str], request_id: str = "c1"):
        items = [0] * ITEM_SLOTS
        for item_id, count in chest_items(chest).items():
            items[item_id - 1] += count
        return self.post(f"/gd/clear_quest?otk={self.token}&requestID={request_id}", [
            ("progressCode", str(progress(CHAPTER, SECTION + 1))), ("worldMapNo", "0"),
            # The client folds the chest's Coins into the balance it submits,
            # which is exactly why that form needs no server-side grant.
            ("valuables", json.dumps({
                "energyAppStore": 0, "energy": 0, "energyAndApp": 0,
                "freeEnergy": 0, "energyGooglePlay": 0, "coins": chest_coins(chest),
            })),
            ("chrdata", json.dumps([self.character])), ("itemList", json.dumps(items)),
            ("summonList", json.dumps([0] * 16)),
            ("battle_result", json.dumps({
                "chapter": CHAPTER, "section": SECTION, "coins": 0, "exp": 0, "items": {},
                "buddies": [], "monsters": [], "summons": [], "luckynum": 0,
                "unableluckdrop": False, "boostup": [0] * 6,
            })),
            ("itmp0", "0"), ("itmp1", "0"), ("lastUpdate", "1"),
        ])

    def box(self) -> dict:
        return self.account()["userdata"]["buddyInfo"]

    def test_a_chest_character_joins_the_roster_and_is_announced(self) -> None:
        chest = self.start()
        expected = chest_characters(chest)
        status, cleared = self.clear(chest)
        self.assertEqual(200, status)
        held = {row["id"] for row in self.account()["userdata"]["chrdata"]}
        self.assertTrue(set(expected) <= held)
        announced = {row["id"] for row in cleared["chrdata"] if row.get("isNew")}
        self.assertEqual(set(expected), announced)

    def test_a_chest_companion_is_granted_instead_of_dropped(self) -> None:
        chest = self.start()
        expected = chest_companions(chest)
        status, _ = self.clear(chest)
        self.assertEqual(200, status)
        self.assertEqual(list(expected), [row["bid"] for row in self.box()["list"]])
        self.assertTrue(all(row["lv"] == 1 for row in self.box()["list"]))
        self.assertEqual("free_roam", self.account()["tutorial_phase"])

    def test_the_book_is_rebuilt_alongside_the_owned_list(self) -> None:
        """This stage's tiers name the same Companion twice, so the book must
        hold one entry where the box holds two."""
        chest = self.start()
        self.assertEqual(200, self.clear(chest)[0])
        box = self.box()
        self.assertEqual(sorted(set(chest_companions(chest))),
                         sorted(row["bid"] for row in box["record"]))
        self.assertGreaterEqual(len(box["list"]), len(box["record"]))

    def test_coins_and_items_still_reconcile(self) -> None:
        """The two forms that already worked must keep working."""
        chest = self.start()
        self.assertEqual(200, self.clear(chest)[0])
        settled = self.account()["userdata"]["itemList"]
        for item_id, count in chest_items(chest).items():
            self.assertEqual(count, settled[item_id - 1])

    def test_an_exact_replay_does_not_grant_twice(self) -> None:
        chest = self.start()
        self.assertEqual(200, self.clear(chest)[0])
        owned = len(self.box()["list"])
        self.assertEqual(200, self.clear(chest)[0])
        self.assertEqual(owned, len(self.box()["list"]))

    def test_the_grant_survives_a_restart_and_still_replays_once(self) -> None:
        chest = self.start()
        self.assertEqual(200, self.clear(chest)[0])
        owned = [row["bid"] for row in self.box()["list"]]
        self.restart()
        self.assertEqual(owned, [row["bid"] for row in self.box()["list"]])
        self.assertEqual(200, self.clear(chest)[0])
        self.assertEqual(owned, [row["bid"] for row in self.box()["list"]])


if __name__ == "__main__":
    unittest.main()
