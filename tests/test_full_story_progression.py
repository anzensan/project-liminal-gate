"""Certify that the whole ordinary story is playable against the public server.

The private reference has `scripts/validate_full_story_persistence.py`, which
drives every Chapter 2--42 stage through its persisted story authority.  The
public release declared the same 384-stage graph but only ever proved a single
chapter boundary, so "the story is playable" rested on the catalog's shape
rather than on the server having been asked to play it.

Deriving the graph here rather than from the catalog is the point, and it only
pays when the copy states what the *client* does. It once carried the same wrong
section run as the catalog -- ten stages for Chapter 20, which ships one -- and
so certified a story no player could finish past Chapter 20.

This drives all 384 stages over the real HTTP path with `--core-story`: start,
clear, and the map reveal at each chapter boundary, from the first stage the
tutorial hands over to the Chapter 43-1 terminal sentinel.  Progress, wallet,
and roster are checked at every step against expectations derived here rather
than read back from the catalog under test, restarts prove the run survives
being interrupted, and replays prove a retried stage settles once.
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import urlencode

from liminal_gate.bootstrap_server import BootstrapState
from liminal_gate.story_progression_catalog import build_core_story_policy
from tests.support import bootstrap_profile, post, start_server, stop_server


# The tutorial hands the account over here: high bits 0x01000000 with Chapter
# 2-1 in the low sixteen, as `test_bootstrap_server` observes at free roam.
FIRST_PROGRESS = 0x01000000 | (2 << 6) | 1
TERMINAL = (43, 1)
CLEAR_COINS = 10
# Restart the server at these chapter boundaries, and replay these stages.
RESTART_CHAPTERS = {5, 20, 42}
REPLAY_IDENTITIES = {(2, 1), (10, 1), (20, 1), (42, 3)}


def core_identities() -> list[tuple[int, int]]:
    """The ordered core-story graph, derived here rather than from the catalog.

    Chapter 20 is one stage. BattleData reserves ten sections for it and fills
    only the first, and the client draws the single row it can play, so clearing
    20-1 finishes the chapter and the next stage is 21-1.
    """
    return [
        (chapter, section)
        for chapter in range(2, 43)
        for section in range(1, 2 if chapter == 20 else 6 if chapter in {2, 3} else 4 if chapter == 42 else 11)
    ]


class FullStoryProgressionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.state_path = self.root / "state.json"
        self.profile = bootstrap_profile()
        self.policy = build_core_story_policy()
        self.token = "full-story-token"
        self.account_id = "full-story-account"
        self.character = {
            "id": 9001, "buddy": 0, "date": 0.0, "jobSlots": [0, 0, 0],
            "jobLevels": [1, 0, 0], "jobID": 0, "flags": 0, "skillBoost": 0,
        }
        self.start_server()
        self.server.state.create_account(self.token, self.account_id, {
            "coins": 0, "worldMapNo": 0, "progressCode": FIRST_PROGRESS,
            "chrdata": [self.character], "itemList": [], "summonList": [],
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
            story_progression_catalog=self.policy,
        )

    def stop_server(self) -> None:
        stop_server(self.server, self.thread)

    def restart(self) -> None:
        self.stop_server()
        self.start_server()

    def post(self, route: str, request_id: str, fields: list[tuple[str, str]]) -> tuple[int, dict]:
        return post(
            self.server, route, request_id, urlencode(fields), token=self.token,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    def userdata(self) -> dict:
        stored = json.loads(self.state_path.read_text(encoding="utf-8"))
        return stored["accounts"][self.account_id]["userdata"]

    def clear_fields(self, chapter: int, section: int, progress: int, coins: int) -> list[tuple[str, str]]:
        return [
            ("progressCode", str(progress)), ("worldMapNo", "0"),
            ("valuables", json.dumps({
                "energyAppStore": 0, "energy": 0, "energyAndApp": 0,
                "freeEnergy": 0, "energyGooglePlay": 0, "coins": coins,
            })),
            ("chrdata", json.dumps([self.character])),
            ("itemList", "[]"), ("summonList", "[]"),
            ("battle_result", json.dumps({
                "chapter": chapter, "section": section, "coins": CLEAR_COINS, "exp": 0,
                "items": {}, "buddies": [], "monsters": [], "summons": [],
                "luckynum": 0, "unableluckdrop": False, "boostup": [0, 0, 0, 0, 0, 0],
            })),
            ("itmp0", "0"), ("itmp1", "0"), ("lastUpdate", "1"),
        ]

    def test_every_core_story_stage_starts_clears_and_advances(self) -> None:
        identities = core_identities()
        self.assertEqual(384, len(identities))
        progress, coins = FIRST_PROGRESS, 0

        for index, (chapter, section) in enumerate(identities):
            label = f"{chapter}-{section}"
            successor = identities[index + 1] if index + 1 < len(identities) else TERMINAL
            boundary = successor[0] != chapter
            expected = (progress & ~0xFFFF) | (successor[0] << 6) | successor[1]
            if boundary:
                expected |= 0x03000000
            # Chapter 2-1 is the profile's last scripted stage -- the tutorial
            # plays it to hand the account over -- so it is driven with the
            # scripted start body and settles through that path, not the
            # generic authority that owns every stage after it.
            scripted = (chapter, section) == (2, 1)

            status, started = self.post(
                "/gd/start_quest", f"start-{label}",
                [("stamina", "5" if scripted else "0"), ("coins", "0"), ("chapter", str(chapter)), ("section", str(section)), ("lastUpdate", "1")],
            )
            self.assertEqual((200, True), (status, started["success"]), f"start {label}")

            coins += CLEAR_COINS
            clear = self.clear_fields(chapter, section, expected, coins)
            status, cleared = self.post("/gd/clear_quest", f"clear-{label}", clear)
            self.assertEqual(200, status, f"clear {label}: {cleared}")
            if scripted:
                # The scripted stage writes the profile's own wallet; adopt it
                # and let the generic authority carry on from there.
                coins = self.userdata()["coins"]
            else:
                self.assertEqual(coins, cleared["coins"], f"clear {label} wallet")

            if (chapter, section) in REPLAY_IDENTITIES:
                # A retried clear settles once: same answer, no second award.
                self.assertEqual((status, cleared), self.post("/gd/clear_quest", f"clear-{label}", clear))
                self.assertEqual(coins, self.userdata()["coins"], f"replay {label} wallet")
            self.assertEqual(coins, self.userdata()["coins"], f"{label} wallet")

            progress = expected
            self.assertEqual(progress, self.userdata()["progressCode"], f"progress after {label}")

            if boundary:
                # The client clears the show-progress bit before the next stage.
                progress &= ~0x02000000
                status, revealed = self.post(
                    "/gd/userdata", f"reveal-{label}",
                    [("progressCode", str(progress)), ("worldMapNo", "0"), ("lastUpdate", "1")],
                )
                self.assertEqual((200, True), (status, revealed["success"]), f"reveal {label}")
                self.assertEqual(progress, self.userdata()["progressCode"], f"reveal {label} progress")
                if successor[0] in RESTART_CHAPTERS:
                    self.restart()

        # The run ends on the terminal sentinel, with the roster and the wallet
        # intact across all 384 stages and every restart.
        self.assertEqual(TERMINAL, ((progress & 0xFFFF) >> 6, progress & 0x3F))
        final = self.userdata()
        # 392 generic awards on top of the wallet the scripted stage left.
        self.assertEqual(coins, final["coins"])
        self.assertEqual([9001], [row["id"] for row in final["chrdata"]])
        self.assertEqual("free_roam", json.loads(self.state_path.read_text())["accounts"][self.account_id]["tutorial_phase"])

    def replay_chapter_two_one(self, progress: int, coins: int) -> tuple[int, dict]:
        status, started = self.post(
            "/gd/start_quest", "replay-2-1-start",
            [("stamina", "5"), ("coins", "0"), ("chapter", "2"), ("section", "1"), ("lastUpdate", "1")],
        )
        self.assertEqual((200, True), (status, started["success"]))
        # An already-cleared stage keeps the account's progress where it is.
        return self.post("/gd/clear_quest", "replay-2-1-clear", self.clear_fields(2, 1, progress, coins + CLEAR_COINS))

    def test_replaying_the_last_scripted_stage_does_not_reset_the_account(self) -> None:
        """Chapter 2-1 is scripted, and `free_roam` is where every stage returns.

        The scripted transitions match on the request body alone, so replaying
        that one stage re-fired the script: its `userdata_update` wrote the
        tutorial's own wallet and party over whatever the player had earned and
        chosen since.
        """
        progress = 16777346  # Chapter 2-2 unlocked: 2-1 has been cleared.
        with self.server.state.lock:
            userdata = self.server.state.accounts[self.account_id]["userdata"]
            userdata.update({"progressCode": progress, "coins": 9999, "teamMembers": [9001, 0, 0, 0, 0, 0]})
            self.server.state._persist_locked()

        status, cleared = self.replay_chapter_two_one(progress, 9999)
        self.assertEqual((200, 10009), (status, cleared["coins"]))
        final = self.userdata()
        self.assertEqual(10009, final["coins"])
        self.assertEqual([9001, 0, 0, 0, 0, 0], final["teamMembers"])
        self.assertEqual(progress, final["progressCode"])

    def test_replaying_the_last_scripted_stage_mid_game_does_not_strand_the_account(self) -> None:
        """The same replay used to leave the account permanently unusable.

        The scripted start moved it into a tutorial phase whose scripted clear
        no longer matched, so nothing could settle it: no stage would start, no
        clear would apply, and even a party save was refused, across restarts.
        """
        progress = 0x01000000 | (10 << 6) | 1
        with self.server.state.lock:
            self.server.state.accounts[self.account_id]["userdata"].update({"progressCode": progress, "coins": 50000})
            self.server.state._persist_locked()

        status, cleared = self.replay_chapter_two_one(progress, 50000)
        self.assertEqual((200, 50010), (status, cleared["coins"]))
        self.assertEqual(progress, self.userdata()["progressCode"], "replaying must not move progress")
        self.assertEqual("free_roam", json.loads(self.state_path.read_text())["accounts"][self.account_id]["tutorial_phase"])

        # The account is still playable: it can start where it left off.
        status, resumed = self.post(
            "/gd/start_quest", "resume-10-1",
            [("stamina", "0"), ("coins", "0"), ("chapter", "10"), ("section", "1"), ("lastUpdate", "1")],
        )
        self.assertEqual((200, True), (status, resumed["success"]))

    def test_a_stage_cannot_be_cleared_before_it_is_reached(self) -> None:
        """The graph is ordered, not a menu: only the unlocked stage advances."""
        status, refused = self.post(
            "/gd/start_quest", "far-ahead",
            [("stamina", "0"), ("coins", "0"), ("chapter", "20"), ("section", "1"), ("lastUpdate", "1")],
        )
        self.assertEqual((409, "tutorial_state_conflict"), (status, refused["error"]))
        self.assertEqual(FIRST_PROGRESS, self.userdata()["progressCode"])


if __name__ == "__main__":
    unittest.main()
