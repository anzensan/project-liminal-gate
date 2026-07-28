"""Drive a story-outcome catalog that can only speak to some of its stages.

The catalog carries three ceilings and they are not equally well evidenced. The
Companion ceiling is complete -- every stage carries its own `dropBuddies`
allowlist inside the client -- so it is always enforced. The item and character
ceilings come from joining an encounter map to `EnemyData`, and no encounter map
reaches the chapters whose enemy rows the client never shipped or the archived
event chapters.

Because an empty ceiling forbids, those two facts collide: a stage nobody could
recover evidence for would refuse a clear reporting an ordinary item drop. So
the ceilings are enforced only under `--outcome-strict`, and even then only per
stage, against a recorded declaration of what could be evidenced at all.
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
from liminal_gate.story_outcome_generator import MAX_COMPANIONS


COMPANION, OTHER_COMPANION = 111, 226
CHARACTER, RECRUIT = 9001, 9002
CLEAR_COINS = 30
DROP_LEVEL = 1
#: A one-based item slot no stage here declares a ceiling for.
ITEM_SLOT = 4
#: Section 2 could be joined to an encounter map and section 3 could not.  Both
#: end up with an empty item and character ceiling; only the first one means it.
EVIDENCED, UNEVIDENCED = 2, 3
_START_PROGRESS = {EVIDENCED: 9, UNEVIDENCED: 10}
_CLEAR_PROGRESS = {EVIDENCED: 10, UNEVIDENCED: 11}


def _character(character_id: int) -> dict[str, object]:
    return {"id": character_id, "buddy": 0, "date": 0.0, "jobSlots": [0, 0, 0], "jobLevels": [1, 0, 0], "jobID": 0, "flags": 0, "skillBoost": 0}


class OutcomeEvidenceTest(unittest.TestCase):
    def _catalog_document(self) -> dict[str, object]:
        def stage(section: int, evidence: list[str]) -> dict[str, object]:
            return {
                "chapter": 2, "section": section, "evidence": evidence,
                "item_maxima": {}, "character_maxima": {},
                "companion_maxima": {str(COMPANION): 2},
            }
        return {
            "schema_version": 1,
            "provenance": "user-supplied",
            "character_ids": [CHARACTER, RECRUIT],
            "item_slots": BUNDLED_ITEM_SLOTS,
            "max_stack": 999,
            "max_companions": MAX_COMPANIONS,
            "companion_masters": [
                {"companion_id": COMPANION, "drop_level": DROP_LEVEL},
                {"companion_id": OTHER_COMPANION, "drop_level": DROP_LEVEL},
            ],
            "stages": [stage(EVIDENCED, ["items", "characters"]), stage(UNEVIDENCED, [])],
        }

    def _clear_fields(
        self,
        section: int,
        buddies: list[int],
        items: dict[str, int] | None = None,
        monsters: list[int] | None = None,
        roster: list[int] | None = None,
    ) -> list[tuple[str, str]]:
        reported = items or {}
        item_list = [0] * BUNDLED_ITEM_SLOTS
        for slot, count in reported.items():
            item_list[int(slot) - 1] += count
        return [
            ("progressCode", str(_CLEAR_PROGRESS[section])), ("worldMapNo", "0"),
            ("valuables", json.dumps({"energyAppStore": 0, "energy": 0, "energyAndApp": 0, "freeEnergy": 0, "energyGooglePlay": 0, "coins": CLEAR_COINS})),
            ("chrdata", json.dumps([_character(value) for value in (roster or [CHARACTER])])),
            ("itemList", json.dumps(item_list)), ("summonList", "[]"),
            ("battle_result", json.dumps({
                "chapter": 2, "section": section, "coins": CLEAR_COINS, "exp": 8, "items": reported,
                "buddies": buddies, "monsters": monsters or [], "summons": [],
                "luckynum": 0, "unableluckdrop": False, "boostup": [0, 0, 0, 0, 0, 0],
            })),
            ("itmp0", "0"), ("itmp1", "0"), ("lastUpdate", "1"),
        ]

    def _serve(self, root: Path, strict: bool, section: int):
        root.mkdir(parents=True, exist_ok=True)
        story_document = {"schema_version": 1, "provenance": "user-supplied", "stages": [
            {"chapter": 2, "section": value, "stamina": 5, "coins": 0,
             "clear_progress_code": _CLEAR_PROGRESS[value], "clear_coins": CLEAR_COINS}
            for value in (EVIDENCED, UNEVIDENCED)
        ]}
        story_path, outcome_path = root / "story.json", root / "outcome.json"
        story_path.write_text(json.dumps(story_document), encoding="utf-8")
        outcome_path.write_text(json.dumps(self._catalog_document()), encoding="utf-8")
        profile = load_profile(Path(__file__).resolve().parents[1] / "profiles" / "legacy-client-bootstrap.json")
        server = BootstrapServer(
            ("127.0.0.1", 0), profile, BootstrapState(root / "state.json"),
            story_catalog=load_story_catalog(story_path),
            story_outcome_catalog=load_story_outcome_catalog(outcome_path),
            outcome_strict=strict,
        )
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        server.state.create_account("token", "account", {
            "coins": 0, "worldMapNo": 0, "progressCode": _START_PROGRESS[section],
            "chrdata": [_character(CHARACTER)],
            "teamMembers": [CHARACTER, 0, 0, 0, 0, 0], "itemList": [0] * BUNDLED_ITEM_SLOTS,
            "summonList": [], "buddyInfo": {"list": [], "record": []},
        })
        with server.state.lock:
            server.state.accounts["account"]["tutorial_phase"] = "free_roam"
            server.state._persist_locked()
        return server, thread

    @staticmethod
    def _post(server: BootstrapServer, path: str, fields: list[tuple[str, str]]) -> tuple[int, dict[str, object]]:
        connection = HTTPConnection(*server.server_address)
        connection.request("POST", path, body=urlencode(fields))
        response = connection.getresponse()
        payload = json.loads(response.read())
        connection.close()
        return response.status, payload

    def _clear(self, strict: bool, section: int, request_id: str, **fields) -> tuple[int, dict[str, object]]:
        with tempfile.TemporaryDirectory() as directory:
            server, thread = self._serve(Path(directory), strict, section)
            try:
                self.assertEqual(200, self._post(server, f"/gd/start_quest?otk=token&requestID={request_id}-start", [
                    ("stamina", "5"), ("coins", "0"), ("chapter", "2"), ("section", str(section)), ("lastUpdate", "1"),
                ])[0])
                return self._post(
                    server, f"/gd/clear_quest?otk=token&requestID={request_id}",
                    self._clear_fields(section, **fields),
                )
            finally:
                server.shutdown()
                thread.join()
                server.server_close()

    # --- the default: Companions bounded, everything else left alone ---

    def test_by_default_a_reported_item_settles_on_either_stage(self) -> None:
        for section in (EVIDENCED, UNEVIDENCED):
            with self.subTest(section=section):
                status, payload = self._clear(
                    False, section, f"item-{section}", buddies=[], items={str(ITEM_SLOT): 1},
                )
                self.assertEqual(200, status)
                self.assertEqual(1, payload["itemList"][ITEM_SLOT - 1])

    def test_by_default_a_recruited_monster_settles(self) -> None:
        status, _payload = self._clear(
            False, EVIDENCED, "monster", buddies=[], monsters=[RECRUIT], roster=[CHARACTER, RECRUIT],
        )
        self.assertEqual(200, status)

    def test_the_companion_ceiling_is_enforced_by_default(self) -> None:
        for label, buddies in (("over-ceiling", [COMPANION] * 3), ("undeclared", [OTHER_COMPANION])):
            with self.subTest(label=label):
                status, payload = self._clear(False, EVIDENCED, label, buddies=buddies)
                self.assertEqual((409, "invalid_local_outcome"), (status, payload["error"]))

    def test_the_rolled_companion_is_minted_by_default(self) -> None:
        status, payload = self._clear(
            False, EVIDENCED, "mint", buddies=[COMPANION, COMPANION], items={str(ITEM_SLOT): 2},
        )
        self.assertEqual(200, status)
        minted = payload["buddyInfo"]["list"]
        self.assertEqual([(COMPANION, DROP_LEVEL)] * 2, [(row["bid"], row["lv"]) for row in minted])
        self.assertEqual([1, 2], [row["iid"] for row in minted])
        self.assertEqual(2, payload["itemList"][ITEM_SLOT - 1])

    # --- strict: enforced, but only where something could be evidenced ---

    def test_strict_refuses_a_reported_item_only_where_the_ceiling_is_evidenced(self) -> None:
        status, payload = self._clear(True, EVIDENCED, "strict-item", buddies=[], items={str(ITEM_SLOT): 1})
        self.assertEqual((409, "invalid_local_outcome"), (status, payload["error"]))
        # Same empty ceiling, but nothing could speak to this stage, so the
        # emptiness is an admission rather than a statement.
        self.assertEqual(
            200, self._clear(True, UNEVIDENCED, "strict-item-unevidenced", buddies=[], items={str(ITEM_SLOT): 1})[0],
        )

    def test_strict_refuses_a_recruit_only_where_the_ceiling_is_evidenced(self) -> None:
        arguments = {"buddies": [], "monsters": [RECRUIT], "roster": [CHARACTER, RECRUIT]}
        status, payload = self._clear(True, EVIDENCED, "strict-monster", **arguments)
        self.assertEqual((409, "invalid_local_outcome"), (status, payload["error"]))
        self.assertEqual(200, self._clear(True, UNEVIDENCED, "strict-monster-unevidenced", **arguments)[0])

    def test_strict_still_enforces_the_companion_ceiling_on_an_unevidenced_stage(self) -> None:
        status, payload = self._clear(True, UNEVIDENCED, "strict-over", buddies=[COMPANION] * 3)
        self.assertEqual((409, "invalid_local_outcome"), (status, payload["error"]))

    def test_a_roster_the_client_has_not_read_back_does_not_cost_a_clear(self) -> None:
        """The durable roster may legitimately lead the client's own copy.

        `_preserved_roster` documents why: a Pact draw whose response never
        arrived, an event or achievement grant.  That lag is bookkeeping, not a
        claim about this battle, so it must not be refused even under strict.
        """
        with tempfile.TemporaryDirectory() as directory:
            server, thread = self._serve(Path(directory), True, EVIDENCED)
            try:
                with server.state.lock:
                    server.state.accounts["account"]["userdata"]["chrdata"].append(_character(RECRUIT))
                    server.state._persist_locked()
                self.assertEqual(200, self._post(server, "/gd/start_quest?otk=token&requestID=lag-start", [
                    ("stamina", "5"), ("coins", "0"), ("chapter", "2"), ("section", str(EVIDENCED)), ("lastUpdate", "1"),
                ])[0])
                status, payload = self._post(
                    server, "/gd/clear_quest?otk=token&requestID=lagging",
                    self._clear_fields(EVIDENCED, [COMPANION], roster=[CHARACTER]),
                )
                self.assertEqual(200, status)
                self.assertEqual([COMPANION], [row["bid"] for row in payload["buddyInfo"]["list"]])
            finally:
                server.shutdown()
                thread.join()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
