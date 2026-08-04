"""The gauge the client draws between a start, its settlement, and a restart.

Issue 31: the bar read full on a meter the server had already debited, and the
next entry was then refused as insufficient while the client still showed a full
one.  The server's arithmetic was never wrong -- `GET /gd/userdata` returned the
right fill origin across a restart, and the refusal was correct.  The settlement
callbacks were simply silent about the meter, and silence is not neutral here:
`refillStartTime: 0.0` is the client's own assertion that the meter refilled at
the epoch, so an absent field and a full bar are the same statement.

These tests therefore assert the *bar*, not just the field -- `current_stamina`
is the client's recovered curve, so a payload that fails them is one the real
client would draw wrongly.
"""

from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path
from urllib.parse import urlencode

from liminal_gate.bootstrap_server import BootstrapState
from liminal_gate.hunting_catalog import load_hunting_catalog
from liminal_gate.stamina_meter import current_stamina, max_stamina_for_chapter
from liminal_gate.story_catalog import load_story_catalog
from tests.support import bootstrap_profile, request, start_server, stop_server

#: Chapter 2 section 2, the stage the generic-story fixtures already use.
CHAPTER, SECTION, COST = 2, 2, 5
PROGRESS = 16777346
CLEAR_PROGRESS = 16777347
CHARACTER = {
    "id": 9001, "buddy": 0, "date": 0.0, "jobSlots": [0, 0, 0],
    "jobLevels": [1, 0, 0], "jobID": 0, "flags": 0, "skillBoost": 0,
}


class StaminaGaugeContinuityTest(unittest.TestCase):
    """One generic story entry, its clear, and the relaunch that follows."""

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.state_path = self.root / "state.json"
        catalog_path = self.root / "story.json"
        catalog_path.write_text(json.dumps({
            "schema_version": 1, "provenance": "user-supplied",
            "stages": [{
                "chapter": CHAPTER, "section": SECTION, "stamina": COST, "coins": 0,
                "clear_progress_code": CLEAR_PROGRESS, "clear_coins": 30,
            }],
        }), encoding="utf-8")
        self.catalog = load_story_catalog(catalog_path)
        self.profile = bootstrap_profile()
        self.token, self.account_id = "gauge-token", "gauge-account"
        self.start_server()
        self.server.state.create_account(self.token, self.account_id, {
            "coins": 210, "worldMapNo": 0, "progressCode": PROGRESS,
            "chrdata": [CHARACTER], "itemList": [], "summonList": [],
        })
        with self.server.state.lock:
            account = self.server.state.accounts[self.account_id]
            account["tutorial_phase"] = "free_roam"
            account["initial_userdata_served"] = True
            self.server.state._persist_locked()

    def tearDown(self) -> None:
        self.stop_server()
        self.temporary_directory.cleanup()

    def start_server(self) -> None:
        self.server, self.thread = start_server(
            ("127.0.0.1", 0), self.profile, BootstrapState(self.state_path),
            story_catalog=self.catalog,
        )

    def stop_server(self) -> None:
        stop_server(self.server, self.thread)

    def post(self, path: str, fields: list[tuple[str, str]]) -> tuple[int, dict]:
        return request(
            self.server, "POST", path, urlencode(fields),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    def drawn_bar(self, payload: dict) -> int:
        """The stamina the client's own curve would draw from this payload.

        A payload with no `refillStartTime` is read exactly as the client reads
        it: the field defaults to zero, which is a full meter.  The meter is
        quantized to whole refill intervals, so reading it against the wall
        clock a moment after the response is stable.
        """
        return current_stamina(
            float(payload.get("refillStartTime", 0.0)), CHAPTER, time.time(),
        )

    def clear_fields(self) -> list[tuple[str, str]]:
        return [
            ("progressCode", str(CLEAR_PROGRESS)), ("worldMapNo", "0"),
            ("valuables", json.dumps({
                "energyAppStore": 0, "energy": 0, "energyAndApp": 0,
                "freeEnergy": 0, "energyGooglePlay": 0, "coins": 240,
            })),
            ("chrdata", json.dumps([CHARACTER])), ("itemList", "[]"),
            ("summonList", "[]"),
            ("battle_result", json.dumps({
                "chapter": CHAPTER, "section": SECTION, "coins": 30, "exp": 0,
                "items": {}, "buddies": [], "monsters": [], "summons": [],
                "luckynum": 0, "unableluckdrop": False,
                "boostup": [0, 0, 0, 0, 0, 0],
            })),
            ("itmp0", "0"), ("itmp1", "0"), ("lastUpdate", "1"),
        ]

    def test_the_bar_survives_a_clear_and_the_relaunch_after_it(self) -> None:
        maximum = max_stamina_for_chapter(CHAPTER)
        self.assertGreater(maximum, COST)

        status, started = self.post(
            f"/gd/start_quest?otk={self.token}&requestID=start-2-2",
            [("stamina", str(COST)), ("coins", "0"), ("chapter", str(CHAPTER)),
             ("section", str(SECTION)), ("lastUpdate", "1")],
        )
        self.assertEqual(200, status)
        origin = started["refillStartTime"]
        self.assertGreater(origin, 0.0)
        # The entry was charged, so the bar is short by exactly the stage cost.
        self.assertEqual(maximum - COST, self.drawn_bar(started))

        status, cleared = self.post(
            f"/gd/clear_quest?otk={self.token}&requestID=clear-2-2", self.clear_fields(),
        )
        self.assertEqual(200, status)
        # The regression: a settlement that omitted this drew a full bar over
        # the stamina the entry above had just spent.  This stage is not a
        # chapter boundary, so the meter is exactly the one the start reported.
        self.assertEqual(origin, cleared["refillStartTime"])
        self.assertEqual(maximum - COST, self.drawn_bar(cleared))

        # A replay answers the settlement it already committed, meter included.
        status, replay = self.post(
            f"/gd/clear_quest?otk={self.token}&requestID=clear-2-2", self.clear_fields(),
        )
        self.assertEqual(200, status)
        self.assertEqual(origin, replay["refillStartTime"])

        # Close and reopen: the durable origin is what the read-only route
        # reports, and it still draws the same bar.
        self.stop_server()
        self.start_server()
        status, userdata = request(self.server, "GET", f"/gd/userdata?otk={self.token}")
        self.assertEqual(200, status)
        self.assertEqual(origin, userdata["refillStartTime"])
        self.assertEqual(maximum - COST, self.drawn_bar(userdata))


class HuntingGaugeContinuityTest(unittest.TestCase):
    """A Hunting settlement restates the meter its entry debited."""

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.state_path = self.root / "state.json"
        catalog_path = self.root / "hunting.json"
        catalog_path.write_text(json.dumps({
            "schema_version": 1, "provenance": "user-supplied",
            "item_slots": 8, "max_stack": 99,
            "stages": [{
                "family": "pudding", "chapter": 1001, "section": 1,
                "stamina": 3, "coins": 0, "entry_item_id": 0, "entry_item_count": 0,
                "unlock_chapter": 1, "unlock_section": 1,
                "max_coins": 0, "max_exp": 0, "max_items_total": 0, "item_maxima": {},
            }],
        }), encoding="utf-8")
        self.catalog = load_hunting_catalog(catalog_path)
        self.profile = bootstrap_profile()
        self.token, self.account_id = "hunt-gauge-token", "hunt-gauge-account"
        self.server, self.thread = start_server(
            ("127.0.0.1", 0), self.profile, BootstrapState(self.state_path),
            hunting_catalog=self.catalog,
        )
        self.server.state.create_account(self.token, self.account_id, {
            "coins": 100, "worldMapNo": 0, "progressCode": PROGRESS,
            "chrdata": [CHARACTER], "itemList": [0] * 8, "summonList": [0, 0],
        })
        with self.server.state.lock:
            account = self.server.state.accounts[self.account_id]
            account["tutorial_phase"] = "free_roam"
            account["initial_userdata_served"] = True
            self.server.state._persist_locked()

    def tearDown(self) -> None:
        stop_server(self.server, self.thread)
        self.temporary_directory.cleanup()

    def post(self, path: str, fields: list[tuple[str, str]]) -> tuple[int, dict]:
        return request(
            self.server, "POST", path, urlencode(fields),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    def test_a_hunting_settlement_reports_the_debited_meter(self) -> None:
        status, started = self.post(
            f"/gd/start_quest?otk={self.token}&requestID=hunt-start",
            [("stamina", "3"), ("coins", "0"), ("chapter", "1001"),
             ("section", "1"), ("lastUpdate", "1")],
        )
        self.assertEqual(200, status)
        origin = started["refillStartTime"]
        self.assertGreater(origin, 0.0)

        status, cleared = self.post(
            f"/gd/clear_quest?otk={self.token}&requestID=hunt-clear",
            [
                ("progressCode", str(PROGRESS)), ("worldMapNo", "0"),
                ("valuables", json.dumps({
                    "energyAppStore": 0, "energy": 0, "energyAndApp": 0,
                    "freeEnergy": 0, "energyGooglePlay": 0, "coins": 100,
                })),
                ("chrdata", json.dumps([CHARACTER])),
                ("itemList", json.dumps([0] * 8)), ("summonList", "[0, 0]"),
                ("battle_result", json.dumps({
                    "chapter": 1001, "section": 1, "coins": 0, "exp": 0,
                    "items": {}, "buddies": [], "monsters": [], "summons": [],
                    "luckynum": 0, "unableluckdrop": False,
                    "boostup": [0, 0, 0, 0, 0, 0],
                })),
                ("itmp0", "0"), ("itmp1", "0"), ("lastUpdate", "1"),
            ],
        )
        self.assertEqual(200, status)
        # Hunting never refills at a boundary, so the settlement reports the
        # entry's own post-spend origin unchanged.
        self.assertEqual(origin, cleared["refillStartTime"])


if __name__ == "__main__":
    unittest.main()
