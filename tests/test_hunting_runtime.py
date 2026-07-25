from __future__ import annotations

import json
from http.client import HTTPConnection
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.parse import urlencode

from liminal_gate.bootstrap_server import BootstrapServer, BootstrapState, load_profile
from liminal_gate.hunting_catalog import load_hunting_catalog


PUBLIC_ROOT = Path(__file__).resolve().parents[1]
PROGRESS = 0x01000000 | (9 << 6) | 1
LOCKED_STAGE = (1002, 3)


class HuntingRuntimeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.state_path = self.root / "state.json"
        catalog_path = self.root / "hunting.json"
        catalog_path.write_text(json.dumps({
            "schema_version": 1, "provenance": "user-supplied",
            "item_slots": 8, "max_stack": 99,
            "stages": [
                {
                    "family": "pudding", "chapter": 1001, "section": 1,
                    "stamina": 3, "coins": 0, "entry_item_id": 0, "entry_item_count": 0,
                    "unlock_progress_code": 0, "max_coins": 0, "max_exp": 0,
                    "item_maxima": {"2": 5, "3": 2},
                },
                {
                    "family": "coin_creeps", "chapter": 1003, "section": 1,
                    "stamina": 1, "coins": 0, "entry_item_id": 5, "entry_item_count": 1,
                    "unlock_progress_code": 0, "max_coins": 1500, "max_exp": 0,
                    "item_maxima": {},
                },
                {
                    "family": "tin", "chapter": LOCKED_STAGE[0], "section": LOCKED_STAGE[1],
                    "stamina": 1, "coins": 0, "entry_item_id": 0, "entry_item_count": 0,
                    "unlock_progress_code": 0x01000000 | (30 << 6) | 1,
                    "max_coins": 0, "max_exp": 0, "item_maxima": {"2": 1},
                },
            ],
        }), encoding="utf-8")
        self.catalog = load_hunting_catalog(catalog_path)
        self.profile = load_profile(PUBLIC_ROOT / "profiles" / "legacy-client-bootstrap.json")
        self.token, self.account_id = "hunt-token", "hunt-account"
        self.character = {
            "id": 9001, "buddy": 0, "date": 0.0, "jobSlots": [0, 0, 0],
            "jobLevels": [1, 0, 0], "jobID": 0, "flags": 0, "skillBoost": 0,
        }
        self.start_server()
        self.server.state.create_account(self.token, self.account_id, {
            "coins": 100, "energy": 40, "freeEnergy": 2, "worldMapNo": 0,
            "progressCode": PROGRESS, "chrdata": [self.character],
            "itemList": [0, 1, 0, 0, 2, 0, 0, 0], "summonList": [0, 0],
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
        self.server = BootstrapServer(
            ("127.0.0.1", 0), self.profile, BootstrapState(self.state_path),
            hunting_catalog=self.catalog,
        )
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()

    def stop_server(self) -> None:
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()

    def restart(self) -> None:
        self.stop_server()
        self.start_server()

    def post(self, route: str, request_id: str, fields: list[tuple[str, str]]) -> tuple[int, dict]:
        connection = HTTPConnection(*self.server.server_address)
        connection.request(
            "POST", f"{route}?otk={self.token}&requestID={request_id}",
            body=urlencode(fields), headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response = connection.getresponse()
        payload = json.loads(response.read())
        connection.close()
        return response.status, payload

    def userdata(self) -> dict:
        return json.loads(self.state_path.read_text(encoding="utf-8"))["accounts"][self.account_id]["userdata"]

    def phase(self) -> str:
        return json.loads(self.state_path.read_text(encoding="utf-8"))["accounts"][self.account_id]["tutorial_phase"]

    def start(self, request_id: str, chapter: int, section: int, stamina: int) -> tuple[int, dict]:
        return self.post("/gd/start_quest", request_id, [
            ("stamina", str(stamina)), ("coins", "0"), ("chapter", str(chapter)),
            ("section", str(section)), ("lastUpdate", "1"),
        ])

    def clear(self, request_id: str, chapter: int, section: int, *, coins: int = 0,
              items: dict | None = None, item_list: list | None = None, exp: int = 0,
              buddies: list | None = None) -> tuple[int, dict]:
        userdata = self.userdata()
        return self.post("/gd/clear_quest", request_id, [
            ("progressCode", str(userdata["progressCode"])), ("worldMapNo", "0"),
            ("valuables", json.dumps({
                "energyAppStore": 0, "energy": userdata["energy"], "energyAndApp": 0,
                "freeEnergy": userdata["freeEnergy"], "energyGooglePlay": 0,
                "coins": userdata["coins"] + coins,
            })),
            ("chrdata", json.dumps([self.character])),
            ("itemList", json.dumps(userdata["itemList"] if item_list is None else item_list)),
            ("summonList", json.dumps(userdata["summonList"])),
            ("battle_result", json.dumps({
                "chapter": chapter, "section": section, "coins": coins, "exp": exp,
                "items": items or {}, "buddies": buddies or [], "monsters": [], "summons": [],
                "luckynum": 0, "unableluckdrop": False, "boostup": [0, 0, 0, 0, 0, 0],
            })),
            ("itmp0", "0"), ("itmp1", "0"), ("lastUpdate", "1"),
        ])

    def test_stage_charges_stamina_settles_within_bounds_and_survives_restart(self) -> None:
        status, started = self.start("hunt-start", 1001, 1, 3)
        self.assertEqual((200, True), (status, started["success"]))
        # Free Energy is spent before paid Energy, as elsewhere in the wallet.
        self.assertEqual((0, 39), (self.userdata()["freeEnergy"], self.userdata()["energy"]))
        self.assertEqual("hunting_active", self.phase())

        self.restart()
        status, cleared = self.clear("hunt-clear", 1001, 1, items={"2": 4}, item_list=[0, 5, 0, 0, 2, 0, 0, 0])
        self.assertEqual(200, status, cleared)
        self.assertEqual([0, 5, 0, 0, 2, 0, 0, 0], self.userdata()["itemList"])
        self.assertEqual("free_roam", self.phase())
        # Settling a Hunting stage never moves story progress.
        self.assertEqual(PROGRESS, self.userdata()["progressCode"])

        self.assertEqual((status, cleared), self.clear("hunt-clear", 1001, 1, items={"2": 4}, item_list=[0, 5, 0, 0, 2, 0, 0, 0]))
        self.restart()
        self.assertEqual([0, 5, 0, 0, 2, 0, 0, 0], self.userdata()["itemList"])

    def test_entry_item_is_consumed_and_a_missing_one_refuses_entry(self) -> None:
        self.assertEqual(2, self.userdata()["itemList"][4])
        for index, request_id in enumerate(("ticket-one", "ticket-two")):
            status, started = self.start(request_id, 1003, 1, 1)
            self.assertEqual((200, True), (status, started["success"]), request_id)
            self.assertEqual(1 - index, self.userdata()["itemList"][4])
            status, cleared = self.clear(f"clear-{request_id}", 1003, 1, coins=1500)
            self.assertEqual(200, status, cleared)

        # The third entry has no ticket left, and must not charge or start.
        before = self.userdata()
        status, refused = self.start("ticket-three", 1003, 1, 1)
        self.assertEqual((200, False, 2), (status, refused["success"], refused["errorCode"]))
        self.assertEqual((before["itemList"], before["energy"], "free_roam"), (self.userdata()["itemList"], self.userdata()["energy"], self.phase()))

    def test_a_result_outside_the_declared_bounds_is_refused_without_mutation(self) -> None:
        for label, kwargs in (
            ("coins", {"coins": 1}),                      # Pudding declares none
            ("exp", {"exp": 1}),                          # nor any EXP
            ("unlisted-item", {"items": {"7": 1}, "item_list": [0, 1, 0, 0, 2, 0, 1, 0]}),
            ("over-maximum", {"items": {"3": 3}, "item_list": [0, 1, 3, 0, 2, 0, 0, 0]}),
            ("companions", {"buddies": [11]}),            # unbounded without its own catalog
        ):
            with self.subTest(label):
                status, started = self.start(f"start-{label}", 1001, 1, 3)
                self.assertEqual((200, True), (status, started["success"]), f"{label} start")
                before = self.userdata()
                status, refused = self.clear(f"clear-{label}", 1001, 1, **kwargs)
                self.assertEqual(409, status, f"{label}: {refused}")
                self.assertEqual("invalid_local_hunting_result", refused["error"])
                self.assertEqual(before, self.userdata(), f"{label} mutated the save")
                # The stage stays active, so the player may retry it honestly.
                self.assertEqual("hunting_active", self.phase())
                self.assertEqual(200, self.clear(f"settle-{label}", 1001, 1)[0])

    def test_a_locked_stage_and_a_second_battle_are_both_refused(self) -> None:
        status, locked = self.start("locked", *LOCKED_STAGE, 1)
        self.assertEqual((409, "hunting_stage_locked"), (status, locked["error"]))
        self.assertEqual("free_roam", self.phase())

        self.assertEqual(200, self.start("first", 1001, 1, 3)[0])
        status, second = self.start("second", 1003, 1, 1)
        self.assertEqual((409, "tutorial_state_conflict"), (status, second["error"]))
        # A story stage cannot displace an active hunt either.
        status, story = self.post("/gd/start_quest", "story", [
            ("stamina", "5"), ("coins", "0"), ("chapter", "2"), ("section", "1"), ("lastUpdate", "1"),
        ])
        self.assertEqual(409, status, story)

    def test_declining_the_resume_prompt_abandons_a_hunt_rather_than_stranding_it(self) -> None:
        """The client's party save after a declined resume must free the account."""
        self.assertEqual(200, self.start("abandoned", 1001, 1, 3)[0])
        self.assertEqual("hunting_active", self.phase())
        status, saved = self.post("/gd/userdata", "abandon", [
            ("teamMembers", json.dumps([9001, 0, 0, 0, 0, 0])), ("teamMembers_VS", json.dumps([0] * 18)),
            ("teamBuddies_VS", json.dumps([0] * 18)), ("teamNo", "1"), ("teamNo_VS", "1"),
            ("summonId", "1"), ("lastUpdate", "1"),
        ])
        self.assertEqual((200, True), (status, saved["success"]))
        self.assertEqual("free_roam", self.phase())
        self.assertEqual(200, self.start("after-abandon", 1001, 1, 3)[0])

    def test_hunting_is_unavailable_without_a_catalog(self) -> None:
        self.stop_server()
        self.catalog = None
        self.server = BootstrapServer(("127.0.0.1", 0), self.profile, BootstrapState(self.state_path))
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        status, refused = self.start("no-catalog", 1001, 1, 3)
        self.assertEqual(501, status, refused)


if __name__ == "__main__":
    unittest.main()
