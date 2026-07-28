from __future__ import annotations

import json
from http.client import HTTPConnection
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.parse import urlencode

from liminal_gate.bootstrap_server import BootstrapServer, BootstrapState, load_profile
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
            profile = load_profile(
                Path(__file__).resolve().parents[1]
                / "profiles"
                / "legacy-client-bootstrap.json"
            )

            def start() -> tuple[BootstrapServer, threading.Thread]:
                server = BootstrapServer(
                    ("127.0.0.1", 0),
                    profile,
                    BootstrapState(state_path),
                    companion_equipment_catalog=equipment_catalog(),
                )
                thread = threading.Thread(target=server.serve_forever)
                thread.start()
                return server, thread

            def post(
                server: BootstrapServer, request_id: str, body: str,
            ) -> tuple[int, dict[str, object]]:
                connection = HTTPConnection(*server.server_address)
                connection.request(
                    "POST",
                    f"/gd/userdata?otk=token&requestID={request_id}",
                    body=body,
                )
                response = connection.getresponse()
                payload = json.loads(response.read())
                connection.close()
                return response.status, payload

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
                server.shutdown()
                thread.join()
                server.server_close()

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
                restarted.shutdown()
                restarted_thread.join()
                restarted.server_close()

    def test_http_equip_enforces_only_character_family_and_species(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            profile = load_profile(
                Path(__file__).resolve().parents[1]
                / "profiles"
                / "legacy-client-bootstrap.json"
            )
            server = BootstrapServer(
                ("127.0.0.1", 0),
                profile,
                BootstrapState(state_path),
                companion_equipment_catalog=equipment_catalog(),
            )
            thread = threading.Thread(target=server.serve_forever)
            thread.start()

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
                connection = HTTPConnection(*server.server_address)
                connection.request(
                    "POST",
                    f"/gd/userdata?otk=token&requestID={request_id}",
                    body=body,
                )
                response = connection.getresponse()
                result = json.loads(response.read())
                connection.close()
                return response.status, result

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
                server.shutdown()
                thread.join()
                server.server_close()

    def test_http_missing_catalog_preserves_existing_link_and_unequip_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            profile = load_profile(
                Path(__file__).resolve().parents[1]
                / "profiles"
                / "legacy-client-bootstrap.json"
            )
            server = BootstrapServer(
                ("127.0.0.1", 0),
                profile,
                BootstrapState(Path(directory) / "state.json"),
            )
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
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
                connection = HTTPConnection(*server.server_address)
                connection.request(
                    "POST",
                    f"/gd/userdata?otk=token&requestID={request_id}",
                    body=body,
                )
                response = connection.getresponse()
                result = json.loads(response.read())
                connection.close()
                return response.status, result

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
                server.shutdown()
                thread.join()
                server.server_close()

    def test_http_delta_write_persists_flag_and_replays_after_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = load_profile(Path(__file__).resolve().parents[1] / "profiles" / "legacy-client-bootstrap.json")
            state_path = root / "state.json"

            def start() -> tuple[BootstrapServer, threading.Thread]:
                server = BootstrapServer(("127.0.0.1", 0), profile, BootstrapState(state_path))
                thread = threading.Thread(target=server.serve_forever)
                thread.start()
                return server, thread

            submitted = [{"bid": 1, "lv": 1, "date": 0.0, "iid": 1, "exp": 0, "flag": 1, "chrID": 0}]
            body = urlencode({"buddyInfo": json.dumps(submitted, separators=(",", ":")), "lastUpdate": "1"})

            def post(server: BootstrapServer, request_id: str, value: str) -> tuple[int, dict[str, object]]:
                connection = HTTPConnection(*server.server_address)
                connection.request("POST", f"/gd/userdata?otk=token&requestID={request_id}", body=value)
                response = connection.getresponse()
                result = json.loads(response.read())
                connection.close()
                return response.status, result

            server, thread = start()
            try:
                server.state.create_account("token", "account", {"buddyInfo": {"list": [{"bid": 1, "lv": 1, "date": 0.0, "iid": 1, "exp": 0, "flag": 0, "chrID": 0}], "record": []}})
                status, first = post(server, "one", body)
                self.assertEqual((200, True, 1.0), (status, first["success"], first["lastupdate"]))
                self.assertEqual(1, server.state.userdata_for("token")["buddyInfo"]["list"][0]["flag"])
                self.assertEqual((status, first), post(server, "one", body))
            finally:
                server.shutdown()
                thread.join()
                server.server_close()

            restarted, restarted_thread = start()
            try:
                self.assertEqual((200, first), post(restarted, "one", body))
            finally:
                restarted.shutdown()
                restarted_thread.join()
                restarted.server_close()
