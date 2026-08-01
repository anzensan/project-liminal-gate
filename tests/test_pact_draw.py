from __future__ import annotations

import json
from http.client import HTTPConnection
from pathlib import Path
import tempfile
import threading
import unittest

from liminal_gate.bootstrap_server import (
    BootstrapServer,
    BootstrapState,
    _parse_ordinary_pact_draw,
    load_profile,
)
from liminal_gate.pact_draw_catalog import build_bundled_pact_policy, load_pact_draw_catalog


class PactDrawTest(unittest.TestCase):
    def test_ticket_form_is_strict_and_does_not_admit_campaign_variants(self) -> None:
        prefix = "kind=20&count=1&luckType=false&campaignChrID=0&eventFlag=0"
        self.assertEqual(
            (20, 1, False),
            _parse_ordinary_pact_draw(f"{prefix}&lastUpdate=1".encode()),
        )
        self.assertEqual(
            (20, 1, True),
            _parse_ordinary_pact_draw(
                b"kind=20&count=1&luckType=true&campaignChrID=0"
                b"&eventFlag=0&lastUpdate=1"
            ),
        )
        for body in (
            b"kind=20&count=2&luckType=false&campaignChrID=0&eventFlag=0&lastUpdate=1",
            b"kind=20&count=1&luckType=false&campaignChrID=1&eventFlag=0&lastUpdate=1",
            b"kind=20&count=1&luckType=false&campaignChrID=0&eventFlag=1&lastUpdate=1",
            b"kind=20&count=1&luckType=false&campaignChrID=0&eventFlag=0&lastUpdate=2",
        ):
            with self.subTest(body=body):
                self.assertIsNone(_parse_ordinary_pact_draw(body))

    def test_http_fellowship_ticket_spends_once_and_replays_after_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            profile = load_profile(
                Path(__file__).resolve().parents[1]
                / "profiles"
                / "legacy-client-bootstrap.json"
            )
            policy = build_bundled_pact_policy()
            body = (
                "kind=20&count=1&luckType=false&campaignChrID=0"
                "&eventFlag=0&lastUpdate=1"
            )

            def start() -> tuple[BootstrapServer, threading.Thread]:
                server = BootstrapServer(
                    ("127.0.0.1", 0),
                    profile,
                    BootstrapState(state_path),
                    pact_draw_catalog=policy,
                )
                thread = threading.Thread(target=server.serve_forever)
                thread.start()
                return server, thread

            def draw(
                server: BootstrapServer, request_id: str, request_body: str = body,
            ) -> tuple[int, dict[str, object]]:
                connection = HTTPConnection(*server.server_address)
                connection.request(
                    "POST",
                    f"/gd/do_slot?otk=token&requestID={request_id}",
                    body=request_body,
                )
                response = connection.getresponse()
                payload = json.loads(response.read())
                connection.close()
                return response.status, payload

            items = [0] * 181
            items[80] = 1
            server, thread = start()
            try:
                server.state.create_account(
                    "token",
                    "account",
                    {
                        "coins": policy.coin_cost,
                        "energy": 7,
                        "freeEnergy": 11,
                        "itemList": items,
                        "chrdata": [],
                    },
                )
                before_priority_refusal = server.state.userdata_for("token")
                coin_status, coin_refused = draw(
                    server,
                    "coin-before-ticket",
                    (
                        "kind=0&count=1&luckType=false&campaignChrID=0"
                        "&eventFlag=0&lastUpdate=1"
                    ),
                )
                self.assertEqual(
                    (200, True, 2),
                    (
                        coin_status,
                        coin_refused["success"],
                        coin_refused["cmdError"],
                    ),
                )
                self.assertEqual(
                    before_priority_refusal,
                    server.state.userdata_for("token"),
                )

                status, first = draw(server, "ticket-one")
                self.assertEqual((200, True), (status, first["success"]))
                self.assertEqual(
                    (policy.coin_cost, 7, 11, 0, 1),
                    (
                        first["coins"],
                        first["energy"],
                        first["freeEnergy"],
                        first["itemList"][80],
                        len(first["chrdata"]),
                    ),
                )
                self.assertIn(
                    first["chrdata"][0]["id"],
                    {draw.character_id for draw in policy.fellowship_draws},
                )
                self.assertEqual((status, first), draw(server, "ticket-one"))

                before_refusal = server.state.userdata_for("token")
                refused_status, refused = draw(server, "ticket-empty")
                self.assertEqual(
                    (200, True, 2),
                    (refused_status, refused["success"], refused["cmdError"]),
                )
                self.assertEqual(before_refusal, server.state.userdata_for("token"))
            finally:
                server.shutdown()
                thread.join()
                server.server_close()

            restarted, restarted_thread = start()
            try:
                self.assertEqual((200, first), draw(restarted, "ticket-one"))
                persisted = restarted.state.userdata_for("token")
                assert persisted is not None
                self.assertEqual(0, persisted["itemList"][80])
                self.assertEqual(1, len(persisted["chrdata"]))
            finally:
                restarted.shutdown()
                restarted_thread.join()
                restarted.server_close()

    def test_http_fate_ticket_uses_fellowship_luck_policy_without_spending_coins(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            profile = load_profile(
                Path(__file__).resolve().parents[1]
                / "profiles"
                / "legacy-client-bootstrap.json"
            )
            policy = build_bundled_pact_policy()
            selected = policy.fellowship_draws[0]
            roster = [
                {
                    "id": draw.character_id,
                    "buddy": 0,
                    "date": 0.0,
                    "jobSlots": [0.0, 0.0, 0.0],
                    "jobLevels": [10.0, 0.0, 0.0],
                    "jobID": 0,
                    "flags": 0,
                    "skillBoost": 17,
                    "luck": 0
                    if draw.character_id == selected.character_id
                    else policy.max_luck,
                }
                for draw in policy.fellowship_draws
            ]
            items = [0] * 181
            items[80] = 1
            server = BootstrapServer(
                ("127.0.0.1", 0),
                profile,
                BootstrapState(state_path),
                pact_draw_catalog=policy,
            )
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            try:
                server.state.create_account(
                    "token",
                    "account",
                    {
                        "coins": policy.coin_cost,
                        "energy": 0,
                        "freeEnergy": 0,
                        "itemList": items,
                        "chrdata": roster,
                    },
                )
                connection = HTTPConnection(*server.server_address)
                connection.request(
                    "POST",
                    "/gd/do_slot?otk=token&requestID=fate-ticket",
                    body=(
                        "kind=20&count=1&luckType=true&campaignChrID=0"
                        "&eventFlag=0&lastUpdate=1"
                    ),
                )
                response = connection.getresponse()
                payload = json.loads(response.read())
                connection.close()

                self.assertEqual((200, True), (response.status, payload["success"]))
                self.assertEqual(policy.coin_cost, payload["coins"])
                self.assertEqual(0, payload["itemList"][80])
                self.assertEqual(
                    {
                        "id": selected.character_id,
                        "jobID": 0,
                        "jobLevels": [11],
                        "jobSlots": [],
                        "isNew": False,
                        "levelAdded": 1,
                        "skillBoost": 17,
                        "luck": 50,
                        "luckup": 50,
                    },
                    payload["chrdata"][0],
                )
                stored = server.state.userdata_for("token")
                assert stored is not None
                selected_row = next(
                    row for row in stored["chrdata"]
                    if row["id"] == selected.character_id
                )
                self.assertEqual((17, 50), (
                    selected_row["skillBoost"], selected_row["luck"],
                ))
            finally:
                server.shutdown()
                thread.join()
                server.server_close()

    def test_http_pact_draw_replays_and_persists(self) -> None:
        catalog_document = {
            "schema_version": 1, "provenance": "user-supplied", "coin_cost": 10,
            "new_level": 1, "max_level": 9, "max_skill_boost": 100,
            "draws": [{"character_id": 9001, "weight": 1, "duplicate_level_added": 2, "duplicate_skill_boost": 5}],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog_path, state_path = root / "pact.json", root / "state.json"
            catalog_path.write_text(json.dumps(catalog_document), encoding="utf-8")
            profile = load_profile(Path(__file__).resolve().parents[1] / "profiles" / "legacy-client-bootstrap.json")
            catalog = load_pact_draw_catalog(catalog_path)

            def start() -> tuple[BootstrapServer, threading.Thread]:
                server = BootstrapServer(("127.0.0.1", 0), profile, BootstrapState(state_path), pact_draw_catalog=catalog)
                thread = threading.Thread(target=server.serve_forever); thread.start()
                return server, thread

            def post(server: BootstrapServer, request_id: str) -> tuple[int, dict[str, object]]:
                connection = HTTPConnection(*server.server_address)
                connection.request("POST", f"/gd/do_slot?otk=token&requestID={request_id}", body="kind=0&count=1&luckType=false&campaignChrID=0&eventFlag=0&lastUpdate=1")
                response = connection.getresponse(); payload = json.loads(response.read()); connection.close()
                return response.status, payload

            server, thread = start()
            try:
                server.state.create_account("token", "account", {"coins": 20, "energy": 0, "freeEnergy": 0, "chrdata": []})
                status, first = post(server, "one")
                self.assertEqual(200, status)
                self.assertEqual((True, 10, [{"id": 9001, "jobID": 0, "jobLevels": [1], "jobSlots": [], "isNew": True, "levelAdded": 1, "skillBoost": 0}]), (first["success"], first["coins"], first["chrdata"]))
                self.assertEqual((status, first), post(server, "one"))
                _, duplicate = post(server, "two")
                self.assertEqual((0, False, 2, 5), (duplicate["coins"], duplicate["chrdata"][0]["isNew"], duplicate["chrdata"][0]["levelAdded"], duplicate["chrdata"][0]["boostUp"]))
            finally:
                server.shutdown(); thread.join(); server.server_close()
            restarted, restarted_thread = start()
            try:
                self.assertEqual((200, first), post(restarted, "one"))
            finally:
                restarted.shutdown(); restarted_thread.join(); restarted.server_close()

    def test_http_bundled_truth_pacts_charge_the_served_cost_and_persist_wallet_after_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = root / "state.json"
            profile = load_profile(Path(__file__).resolve().parents[1] / "profiles" / "legacy-client-bootstrap.json")
            server = BootstrapServer(("127.0.0.1", 0), profile, BootstrapState(state_path), pact_draw_catalog=build_bundled_pact_policy())
            thread = threading.Thread(target=server.serve_forever); thread.start()
            try:
                # A Truth pull costs 5 Energy, so a ten-pull is exactly the 50
                # free Energy a new local account receives.
                server.state.create_account("token", "account", {"coins": 0, "energy": 0, "freeEnergy": 100, "chrdata": []})

                def draw(request_id: str, count: int) -> tuple[int, dict[str, object]]:
                    connection = HTTPConnection(*server.server_address)
                    connection.request("POST", f"/gd/do_slot?otk=token&requestID={request_id}", body=f"kind=1&count={count}&luckType=false&campaignChrID=0&eventFlag=0&lastUpdate=1")
                    response = connection.getresponse(); payload = json.loads(response.read()); connection.close()
                    return response.status, payload

                status, first = draw("truth-one", 1)
                self.assertEqual(200, status)
                self.assertTrue(first["success"])
                self.assertEqual(95, first["freeEnergy"])
                self.assertEqual(1, len(first["chrdata"]))
                status, ten = draw("truth-ten", 10)
                self.assertEqual(200, status)
                self.assertTrue(ten["success"])
                self.assertEqual(45, ten["freeEnergy"])
                self.assertEqual(10, len(ten["chrdata"]))
                self.assertIn(ten["chrdata"][0]["id"], {draw.character_id for draw in build_bundled_pact_policy().truth_draws})
            finally:
                server.shutdown(); thread.join(); server.server_close()
            restarted = BootstrapState(state_path)
            try:
                persisted = restarted.userdata_for("token")
                self.assertIsNotNone(persisted)
                assert persisted is not None
                self.assertEqual(45, persisted["freeEnergy"])
                self.assertEqual(45, persisted["valuables"]["freeEnergy"])
            finally:
                restarted.close()

    def test_http_truth_pact_accepts_an_affordable_remainder_batch(self) -> None:
        """The ten-pull control can submit 1..10, not only its button labels."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = root / "state.json"
            profile = load_profile(Path(__file__).resolve().parents[1] / "profiles" / "legacy-client-bootstrap.json")

            def start() -> tuple[BootstrapServer, threading.Thread]:
                server = BootstrapServer(
                    ("127.0.0.1", 0), profile, BootstrapState(state_path),
                    pact_draw_catalog=build_bundled_pact_policy(),
                )
                thread = threading.Thread(target=server.serve_forever)
                thread.start()
                return server, thread

            def draw(server: BootstrapServer, request_id: str) -> tuple[int, dict[str, object]]:
                connection = HTTPConnection(*server.server_address)
                connection.request(
                    "POST", f"/gd/do_slot?otk=token&requestID={request_id}",
                    body="kind=1&count=6&luckType=false&campaignChrID=0&eventFlag=0&lastUpdate=1",
                )
                response = connection.getresponse()
                payload = json.loads(response.read())
                connection.close()
                return response.status, payload

            server, thread = start()
            try:
                server.state.create_account(
                    "token", "account",
                    {"coins": 0, "energy": 0, "freeEnergy": 32, "chrdata": []},
                )
                status, first = draw(server, "truth-six")
                self.assertEqual((200, True, 2, 6), (
                    status, first["success"], first["freeEnergy"], len(first["chrdata"]),
                ))
                self.assertEqual((status, first), draw(server, "truth-six"))
            finally:
                server.shutdown()
                thread.join()
                server.server_close()

            restarted, restarted_thread = start()
            try:
                self.assertEqual((200, first), draw(restarted, "truth-six"))
            finally:
                restarted.shutdown()
                restarted_thread.join()
                restarted.server_close()

    def test_migrated_packed_roster_accepts_fate_and_replays_after_restart(self) -> None:
        """The original client stores packed levels as integral JSON doubles."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = root / "state.json"
            profile = load_profile(
                Path(__file__).resolve().parents[1]
                / "profiles"
                / "legacy-client-bootstrap.json"
            )
            policy = build_bundled_pact_policy()
            selected = policy.fellowship_draws[0]
            packed_level = float((12345 << 12) | 20)
            roster = []
            for draw in policy.fellowship_draws:
                roster.append(
                    {
                        "id": draw.character_id,
                        "buddy": 0,
                        "date": 0.0,
                        "jobSlots": [0.0, 0.0, 0.0],
                        "jobLevels": [
                            packed_level
                            if draw.character_id == selected.character_id
                            else 10.0,
                            0.0,
                            0.0,
                        ],
                        "jobID": 0,
                        "flags": 0,
                        "skillBoost": 0,
                        "luck": 0
                        if draw.character_id == selected.character_id
                        else policy.max_luck,
                    }
                )

            def start() -> tuple[BootstrapServer, threading.Thread]:
                server = BootstrapServer(
                    ("127.0.0.1", 0),
                    profile,
                    BootstrapState(state_path),
                    pact_draw_catalog=policy,
                )
                thread = threading.Thread(target=server.serve_forever)
                thread.start()
                return server, thread

            body = (
                "kind=0&count=1&luckType=true&campaignChrID=0"
                "&eventFlag=0&lastUpdate=1"
            )

            def draw(server: BootstrapServer) -> tuple[int, dict[str, object]]:
                connection = HTTPConnection(*server.server_address)
                connection.request(
                    "POST",
                    "/gd/do_slot?otk=token&requestID=fate-packed",
                    body=body,
                )
                response = connection.getresponse()
                payload = json.loads(response.read())
                connection.close()
                return response.status, payload

            server, thread = start()
            try:
                server.state.create_account(
                    "token",
                    "account",
                    {
                        "coins": policy.coin_cost,
                        "energy": 0,
                        "freeEnergy": 0,
                        "chrdata": roster,
                    },
                )
                status, first = draw(server)
                self.assertEqual(200, status)
                self.assertTrue(first["success"])
                self.assertEqual(0, first["coins"])
                self.assertEqual(
                    {
                        "id": selected.character_id,
                        "jobID": 0,
                        "jobLevels": [21],
                        "jobSlots": [],
                        "isNew": False,
                        "levelAdded": 1,
                        "skillBoost": 0,
                        "luck": 50,
                        "luckup": 50,
                    },
                    first["chrdata"][0],
                )
                stored = server.state.userdata_for("token")["chrdata"][0]
                self.assertEqual(float((12345 << 12) | 21), stored["jobLevels"][0])
                self.assertEqual(50, stored["luck"])
                self.assertEqual((status, first), draw(server))
            finally:
                server.shutdown()
                thread.join()
                server.server_close()

            restarted, restarted_thread = start()
            try:
                self.assertEqual((200, first), draw(restarted))
            finally:
                restarted.shutdown()
                restarted_thread.join()
                restarted.server_close()

    def test_a_character_at_the_skill_boost_cap_leaves_the_pool(self) -> None:
        """The retired service stopped offering a character at 100% Skill Boost.

        With a two-entry pool and one member already capped, every draw must
        select the other member; once both are capped the Pact itself refuses
        rather than selecting an ineligible character or granting nothing.
        """
        catalog_document = {
            "schema_version": 1, "provenance": "user-supplied", "coin_cost": 10,
            "new_level": 1, "max_level": 9, "max_skill_boost": 100,
            "draws": [
                {"character_id": 9001, "weight": 1, "duplicate_level_added": 2, "duplicate_skill_boost": 5},
                {"character_id": 9002, "weight": 1, "duplicate_level_added": 2, "duplicate_skill_boost": 5},
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog_path, state_path = root / "pact.json", root / "state.json"
            catalog_path.write_text(json.dumps(catalog_document), encoding="utf-8")
            profile = load_profile(Path(__file__).resolve().parents[1] / "profiles" / "legacy-client-bootstrap.json")
            server = BootstrapServer(("127.0.0.1", 0), profile, BootstrapState(state_path), pact_draw_catalog=load_pact_draw_catalog(catalog_path))
            thread = threading.Thread(target=server.serve_forever); thread.start()

            def post(request_id: str) -> dict[str, object]:
                connection = HTTPConnection(*server.server_address)
                connection.request("POST", f"/gd/do_slot?otk=token&requestID={request_id}", body="kind=0&count=1&luckType=false&campaignChrID=0&eventFlag=0&lastUpdate=1")
                payload = json.loads(connection.getresponse().read()); connection.close()
                return payload

            def owned(character_id: int, skill_boost: int) -> dict[str, object]:
                return {
                    "id": character_id, "buddy": 0, "date": 0.0,
                    "jobSlots": [0.0, 0.0, 0.0], "jobLevels": [1.0, 0.0, 0.0],
                    "jobID": 0, "flags": 0, "skillBoost": skill_boost,
                }

            try:
                # 9001 is already at the catalog's 100% cap, so every draw must
                # land on 9002 even though both carry the same weight.
                server.state.create_account("token", "account", {"coins": 100, "energy": 0, "freeEnergy": 0, "chrdata": [owned(9001, 100)]})
                for index in range(3):
                    payload = post(f"draw-{index}")
                    self.assertTrue(payload["success"])
                    self.assertEqual(9002, payload["chrdata"][0]["id"])
                stored = server.state.userdata_for("token")
                assert stored is not None
                self.assertEqual(100, next(row for row in stored["chrdata"] if row["id"] == 9001)["skillBoost"])

            finally:
                server.shutdown(); thread.join(); server.server_close()

            # With the whole pool capped the Pact refuses rather than selecting
            # an ineligible character or charging for nothing. This needs its
            # own server, because one account per state file owns the host claim.
            exhausted_server = BootstrapServer(("127.0.0.1", 0), profile, BootstrapState(root / "exhausted.json"), pact_draw_catalog=load_pact_draw_catalog(catalog_path))
            exhausted_thread = threading.Thread(target=exhausted_server.serve_forever); exhausted_thread.start()
            try:
                exhausted_server.state.create_account("token", "exhausted", {"coins": 100, "energy": 0, "freeEnergy": 0, "chrdata": [owned(9001, 100), owned(9002, 100)]})
                connection = HTTPConnection(*exhausted_server.server_address)
                connection.request("POST", "/gd/do_slot?otk=token&requestID=draw-exhausted", body="kind=0&count=1&luckType=false&campaignChrID=0&eventFlag=0&lastUpdate=1")
                exhausted = json.loads(connection.getresponse().read()); connection.close()
                # The client's own refusal shape: a successful call reporting a
                # command error, not an HTTP or transport failure.
                self.assertEqual((True, 3), (exhausted["success"], exhausted["cmdError"]))
                self.assertNotIn("chrdata", exhausted)
                self.assertEqual(100, exhausted_server.state.userdata_for("token")["coins"])
            finally:
                exhausted_server.shutdown(); exhausted_thread.join(); exhausted_server.server_close()
