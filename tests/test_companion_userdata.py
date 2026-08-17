from __future__ import annotations

import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.parse import urlencode

from liminal_gate.bootstrap_server import BootstrapServer, BootstrapState
from tests.support import bootstrap_profile, start_server, stop_server
from tests.support import post as support_post
from liminal_gate.companion_equipment_catalog import (
    CharacterEquipmentMaster,
    CompanionEquipmentCatalog,
    CompanionEquipmentMaster,
)


def equipment_catalog() -> CompanionEquipmentCatalog:
    return CompanionEquipmentCatalog(
        "a" * 64,
        {
            3: CharacterEquipmentMaster(3, 0, (1,)),
            25: CharacterEquipmentMaster(25, 3, (7,)),
            44: CharacterEquipmentMaster(44, 0, (2,)),
            46: CharacterEquipmentMaster(46, 0, (7,)),
            47: CharacterEquipmentMaster(47, 0, (2,)),
        },
        {
            1: CompanionEquipmentMaster(1, 0, 0),
            2: CompanionEquipmentMaster(2, 3, 0),
            3: CompanionEquipmentMaster(3, 0, 7),
            4: CompanionEquipmentMaster(4, 25, 0),
        },
    )


class CompanionUserdataTest(unittest.TestCase):
    def test_http_equip_commits_both_links_atomically_and_replays_after_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            profile = bootstrap_profile()

            def start() -> tuple[BootstrapServer, threading.Thread]:
                return start_server(
                    ("127.0.0.1", 0),
                    profile,
                    BootstrapState(state_path),
                    companion_equipment_catalog=equipment_catalog(),
                )

            def post(
                server: BootstrapServer, request_id: str, body: str,
            ) -> tuple[int, dict[str, object]]:
                return support_post(server, "/gd/userdata", request_id, body)

            roster = [
                {"id": 3, "buddy": 1, "jobID": 0, "jobLevels": [10.0]},
                {"id": 25, "buddy": 0, "jobID": 0, "jobLevels": [10.0]},
            ]
            companion = {
                "bid": 1,
                "lv": 1,
                "date": 0.0,
                "iid": 1,
                "exp": 0,
                "flag": 0,
                "chrID": 3,
            }
            moved_roster = [{"id": 3, "buddy": 0}, {"id": 25, "buddy": 1}]

            def equip_body(companion_chr_id: int) -> str:
                moved_companion = {**companion, "chrID": companion_chr_id}
                return urlencode([
                    ("chrdata", json.dumps(moved_roster, separators=(",", ":"))),
                    ("buddyInfo", json.dumps([moved_companion], separators=(",", ":"))),
                    ("lastUpdate", "1"),
                ])

            server, thread = start()
            try:
                server.state.create_account(
                    "token",
                    "account",
                    {
                        "chrdata": roster,
                        "buddyInfo": {"list": [companion], "record": []},
                    },
                )
                with server.state.lock:
                    server.state.accounts["account"]["tutorial_phase"] = "free_roam"
                    server.state._persist_locked()

                before = server.state.userdata_for("token")
                bad_status, bad = post(server, "mismatched-equip", equip_body(3))
                self.assertEqual(
                    (501, "unsupported_companion_userdata"),
                    (bad_status, bad["error"]),
                )
                self.assertEqual(before, server.state.userdata_for("token"))

                one_sided = urlencode([
                    (
                        "buddyInfo",
                        json.dumps(
                            [{**companion, "chrID": 25}],
                            separators=(",", ":"),
                        ),
                    ),
                    ("lastUpdate", "1"),
                ])
                one_status, one = post(server, "one-sided-equip", one_sided)
                self.assertEqual(
                    (501, "unsupported_companion_userdata"),
                    (one_status, one["error"]),
                )
                self.assertEqual(before, server.state.userdata_for("token"))

                status, first = post(server, "move-equip", equip_body(25))
                self.assertEqual((200, True), (status, first["success"]))
                self.assertEqual(
                    (status, first),
                    post(server, "move-equip", equip_body(25)),
                )
                stored = server.state.userdata_for("token")
                assert stored is not None
                self.assertEqual(
                    ([0, 1], 25),
                    (
                        [row["buddy"] for row in stored["chrdata"]],
                        stored["buddyInfo"]["list"][0]["chrID"],
                    ),
                )
            finally:
                stop_server(server, thread)

            restarted, restarted_thread = start()
            try:
                self.assertEqual(
                    (200, first),
                    post(restarted, "move-equip", equip_body(25)),
                )
                stored = restarted.state.userdata_for("token")
                assert stored is not None
                self.assertEqual(
                    ([0, 1], 25),
                    (
                        [row["buddy"] for row in stored["chrdata"]],
                        stored["buddyInfo"]["list"][0]["chrID"],
                    ),
                )
            finally:
                stop_server(restarted, restarted_thread)

    def test_http_equip_enforces_only_character_family_and_species(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            profile = bootstrap_profile()
            server, thread = start_server(
                ("127.0.0.1", 0),
                profile,
                BootstrapState(state_path),
                companion_equipment_catalog=equipment_catalog(),
            )

            roster = [
                {
                    "id": character_id,
                    "buddy": 0,
                    "jobID": 0,
                    # Level one deliberately proves RequiredLevel is not an
                    # equip-selection restriction.
                    "jobLevels": [1.0],
                }
                for character_id in (3, 25, 44, 46, 47)
            ]
            companions = [
                {
                    "bid": companion_id,
                    "lv": 1,
                    "date": 0.0,
                    "iid": inventory_id,
                    "exp": 0,
                    "flag": 0,
                    "chrID": 0,
                }
                for inventory_id, companion_id in (
                    (1, 1), (2, 2), (3, 3), (4, 999),
                )
            ]

            def post(
                request_id: str,
                character_delta: list[dict[str, int]],
                inventory_id: int,
                target: int,
            ) -> tuple[int, dict[str, object]]:
                companion = next(
                    row for row in companions if row["iid"] == inventory_id
                )
                current = server.state.userdata_for("token")
                assert current is not None
                durable = next(
                    row
                    for row in current["buddyInfo"]["list"]
                    if row["iid"] == inventory_id
                )
                submitted = {**companion, **durable, "chrID": target}
                body = urlencode([
                    (
                        "chrdata",
                        json.dumps(character_delta, separators=(",", ":")),
                    ),
                    (
                        "buddyInfo",
                        json.dumps([submitted], separators=(",", ":")),
                    ),
                    ("lastUpdate", "1"),
                ])
                return support_post(server, "/gd/userdata", request_id, body)

            try:
                server.state.create_account(
                    "token",
                    "account",
                    {
                        "chrdata": roster,
                        "buddyInfo": {"list": companions, "record": []},
                    },
                )
                with server.state.lock:
                    server.state.accounts["account"]["tutorial_phase"] = "free_roam"
                    server.state._persist_locked()

                # Direct character restriction.
                direct = post("direct", [{"id": 3, "buddy": 2}], 2, 3)
                self.assertEqual(
                    (200, True),
                    (direct[0], direct[1]["success"]),
                )
                # The same restriction accepts a descendant whose recovered
                # ancestor is character 3.
                self.assertEqual(
                    200,
                    post(
                        "ancestor",
                        [{"id": 3, "buddy": 0}, {"id": 25, "buddy": 2}],
                        2,
                        25,
                    )[0],
                )
                # Species restriction and unrestricted low-level equip.
                self.assertEqual(
                    200,
                    post("species", [{"id": 46, "buddy": 3}], 3, 46)[0],
                )
                self.assertEqual(
                    200,
                    post("unrestricted", [{"id": 44, "buddy": 1}], 1, 44)[0],
                )

                before = server.state.userdata_for("token")
                bad_character = post(
                    "bad-character",
                    [{"id": 25, "buddy": 0}, {"id": 47, "buddy": 2}],
                    2,
                    47,
                )
                self.assertEqual(
                    (501, "unsupported_companion_userdata"),
                    (bad_character[0], bad_character[1]["error"]),
                )
                self.assertEqual(before, server.state.userdata_for("token"))

                bad_species = post(
                    "bad-species",
                    [{"id": 46, "buddy": 0}, {"id": 47, "buddy": 3}],
                    3,
                    47,
                )
                self.assertEqual(
                    (501, "unsupported_companion_userdata"),
                    (bad_species[0], bad_species[1]["error"]),
                )
                self.assertEqual(before, server.state.userdata_for("token"))

                unknown = post(
                    "unknown-master",
                    [{"id": 47, "buddy": 4}],
                    4,
                    47,
                )
                self.assertEqual(
                    (501, "unsupported_companion_userdata"),
                    (unknown[0], unknown[1]["error"]),
                )
                self.assertEqual(before, server.state.userdata_for("token"))
            finally:
                stop_server(server, thread)

    def test_http_missing_catalog_preserves_existing_link_and_unequip_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            profile = bootstrap_profile()
            server, thread = start_server(
                ("127.0.0.1", 0),
                profile,
                BootstrapState(Path(directory) / "state.json"),
            )
            companion = {
                "bid": 1, "lv": 1, "date": 0.0, "iid": 1,
                "exp": 0, "flag": 0, "chrID": 3,
            }

            def post(
                request_id: str,
                characters: list[dict[str, int]],
                target: int,
            ) -> tuple[int, dict[str, object]]:
                body = urlencode([
                    (
                        "chrdata",
                        json.dumps(characters, separators=(",", ":")),
                    ),
                    (
                        "buddyInfo",
                        json.dumps(
                            [{**companion, "chrID": target}],
                            separators=(",", ":"),
                        ),
                    ),
                    ("lastUpdate", "1"),
                ])
                return support_post(server, "/gd/userdata", request_id, body)

            try:
                server.state.create_account(
                    "token",
                    "account",
                    {
                        "chrdata": [
                            {
                                "id": 3, "buddy": 1, "jobID": 0,
                                "jobLevels": [1.0],
                            },
                            {
                                "id": 25, "buddy": 0, "jobID": 0,
                                "jobLevels": [1.0],
                            },
                        ],
                        "buddyInfo": {"list": [companion], "record": []},
                    },
                )
                with server.state.lock:
                    server.state.accounts["account"]["tutorial_phase"] = "free_roam"
                    server.state._persist_locked()
                unchanged = post(
                    "unchanged",
                    [{"id": 3, "buddy": 1}],
                    3,
                )
                self.assertEqual(
                    (200, True),
                    (unchanged[0], unchanged[1]["success"]),
                )
                unequip = post(
                    "unequip",
                    [{"id": 3, "buddy": 0}],
                    0,
                )
                self.assertEqual(
                    (200, True),
                    (unequip[0], unequip[1]["success"]),
                )
                before = server.state.userdata_for("token")
                new_equip = post(
                    "new-equip",
                    [{"id": 25, "buddy": 1}],
                    25,
                )
                self.assertEqual(
                    (501, "unsupported_companion_userdata"),
                    (new_equip[0], new_equip[1]["error"]),
                )
                self.assertEqual(before, server.state.userdata_for("token"))
            finally:
                stop_server(server, thread)

    def test_http_delta_write_persists_flag_and_replays_after_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = bootstrap_profile()
            state_path = root / "state.json"

            def start() -> tuple[BootstrapServer, threading.Thread]:
                return start_server(("127.0.0.1", 0), profile, BootstrapState(state_path))

            submitted = [{"bid": 1, "lv": 1, "date": 0.0, "iid": 1, "exp": 0, "flag": 1, "chrID": 0}]
            body = urlencode({"buddyInfo": json.dumps(submitted, separators=(",", ":")), "lastUpdate": "1"})

            def post(server: BootstrapServer, request_id: str, value: str) -> tuple[int, dict[str, object]]:
                return support_post(server, "/gd/userdata", request_id, value)

            server, thread = start()
            try:
                server.state.create_account("token", "account", {"buddyInfo": {"list": [{"bid": 1, "lv": 1, "date": 0.0, "iid": 1, "exp": 0, "flag": 0, "chrID": 0}], "record": []}})
                status, first = post(server, "one", body)
                self.assertEqual((200, True, 1.0), (status, first["success"], first["lastupdate"]))
                self.assertEqual(1, server.state.userdata_for("token")["buddyInfo"]["list"][0]["flag"])
                self.assertEqual((status, first), post(server, "one", body))
            finally:
                stop_server(server, thread)

            restarted, restarted_thread = start()
            try:
                self.assertEqual((200, first), post(restarted, "one", body))
            finally:
                stop_server(restarted, restarted_thread)

    def test_http_empty_companion_delta_settles_without_changing_the_box(self) -> None:
        """A save carrying no dirty Companion is a save, not a bad request.

        A tester saw a Network Error after every Companion sale.  The sale
        itself settles: what fails is the ordinary save behind it.
        `SendDirtyData` posts whatever `UserData`'s dirty flag names, and the
        sale's own answer rebuilds every `Buddy` through `LoadBuddyInfo`, which
        discards the per-Companion dirty bits while `UserDataKind.Buddies` is
        still pending.  `SerializeJsonUserData` then serialises the empty list
        as `[]` -- it only omits the field when the value is the empty string --
        so the client posts a delta naming nobody.  Refusing that answered a
        routine save with a 501 the client shows as a Network Error, and the
        `chrdata` half accepted the same empty array all along.
        """
        with tempfile.TemporaryDirectory() as directory:
            profile = bootstrap_profile()
            state = BootstrapState(Path(directory) / "state.json")
            state.create_account("token", "account", {
                "chrdata": [{"id": 3, "buddy": 1}],
                "buddyInfo": {"list": [{"bid": 1, "lv": 1, "date": 0.0, "iid": 1, "exp": 0, "flag": 1, "chrID": 3}], "record": []},
            })
            state.accounts["account"]["tutorial_phase"] = "free_roam"
            before = json.loads(json.dumps(state.userdata_for("token")["buddyInfo"]["list"]))
            server, thread = start_server(("127.0.0.1", 0), profile, state)
            try:
                empty = json.dumps([], separators=(",", ":"))
                alone = urlencode({"buddyInfo": empty, "lastUpdate": "1"})
                status, payload = support_post(server, "/gd/userdata", "alone", alone)
                self.assertEqual((200, True, 1.0), (status, payload["success"], payload["lastupdate"]))
                # The equip form carries both halves; a sale empties both.
                both = urlencode({"chrdata": json.dumps([], separators=(",", ":")), "buddyInfo": empty, "lastUpdate": "1"})
                status, payload = support_post(server, "/gd/userdata", "both", both)
                self.assertEqual((200, True), (status, payload["success"]))
                # A blank or non-array value stays a malformed body.
                for value in ("", "{}"):
                    body = urlencode({"buddyInfo": value, "lastUpdate": "1"})
                    self.assertEqual(501, support_post(server, "/gd/userdata", "bad" + value, body)[0])
                self.assertEqual(before, server.state.userdata_for("token")["buddyInfo"]["list"])
            finally:
                stop_server(server, thread)

    def test_a_save_already_carrying_a_half_link_repairs_itself_on_load(self) -> None:
        """A Rebirth run before the fix left a save no party write could pass.

        `_valid_companion_equipment` reads the whole document, so a Companion
        still naming a character the recode removed answers 501 to every later
        party or equip save -- and nothing the player can reach from the client
        repairs a link the client cannot see. Fixing the recode repairs the
        accounts that have not run one; this repairs the ones that have.
        """
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            state = BootstrapState(path)
            state.create_account("token", "account", {
                "chrdata": [{"id": 3, "buddy": 1}],
                "buddyInfo": {"list": [{"bid": 1, "lv": 1, "date": 0.0, "iid": 1, "exp": 0, "flag": 0, "chrID": 3}], "record": []},
            })
            with state.lock:
                state._persist_locked()
            state.close()

            # Exactly what a recode used to leave behind: the character is off
            # the roster and its Companion still names it.
            document = json.loads(path.read_text(encoding="utf-8"))
            document["accounts"]["account"]["userdata"]["chrdata"] = []
            path.write_text(json.dumps(document), encoding="utf-8")

            repaired = BootstrapState(path)
            try:
                userdata = repaired.userdata_for("token")
                assert userdata is not None
                self.assertEqual([0], [companion["chrID"] for companion in userdata["buddyInfo"]["list"]])
                self.assertEqual([0], [companion["chrID"] for companion in userdata["buddyInfo"]["record"]])
            finally:
                repaired.close()
