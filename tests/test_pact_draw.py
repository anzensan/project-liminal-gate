from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from liminal_gate.bootstrap_server import (
    BootstrapServer,
    BootstrapState,
    _parse_ordinary_pact_draw,
)
from liminal_gate.pact_draw_catalog import build_bundled_pact_policy, load_pact_draw_catalog
from tests.support import bootstrap_profile, post, start_server, stop_server, write_json


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
        # The ticket shares the ten-pull control the Coin and Energy forms use:
        # `UIBarSlot.InitChrMenu` sizes the batch from the held Item 81 count,
        # so a ticket batch is as ordinary as any other batch this size.
        self.assertEqual(
            (20, 10, False),
            _parse_ordinary_pact_draw(
                b"kind=20&count=10&luckType=false&campaignChrID=0"
                b"&eventFlag=0&lastUpdate=2"
            ),
        )
        for body in (
            b"kind=20&count=11&luckType=false&campaignChrID=0&eventFlag=0&lastUpdate=1",
            b"kind=20&count=0&luckType=false&campaignChrID=0&eventFlag=0&lastUpdate=1",
            b"kind=20&count=1&luckType=false&campaignChrID=1&eventFlag=0&lastUpdate=1",
            b"kind=20&count=1&luckType=false&campaignChrID=0&eventFlag=1&lastUpdate=1",
        ):
            with self.subTest(body=body):
                self.assertIsNone(_parse_ordinary_pact_draw(body))

    def test_http_fellowship_ticket_spends_once_and_replays_after_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            profile = bootstrap_profile()
            policy = build_bundled_pact_policy()
            body = (
                "kind=20&count=1&luckType=false&campaignChrID=0"
                "&eventFlag=0&lastUpdate=1"
            )

            def draw(
                server: BootstrapServer, request_id: str, request_body: str = body,
            ) -> tuple[int, dict[str, object]]:
                return post(server, "/gd/do_slot", request_id, request_body)

            items = [0] * 181
            items[80] = 1
            server, thread = start_server(
                ("127.0.0.1", 0),
                profile,
                BootstrapState(state_path),
                pact_draw_catalog=policy,
            )
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
                stop_server(server, thread)

            restarted, restarted_thread = start_server(
                ("127.0.0.1", 0),
                profile,
                BootstrapState(state_path),
                pact_draw_catalog=policy,
            )
            try:
                self.assertEqual((200, first), draw(restarted, "ticket-one"))
                persisted = restarted.state.userdata_for("token")
                assert persisted is not None
                self.assertEqual(0, persisted["itemList"][80])
                self.assertEqual(1, len(persisted["chrdata"]))
            finally:
                stop_server(restarted, restarted_thread)

    def test_http_fellowship_ticket_batch_spends_one_ticket_per_result(self) -> None:
        """The ten-pull control spends the batch it sized from the inventory.

        Its count is the held ticket count capped at ten, so a three-ticket
        batch must settle three results for three tickets and leave the
        player's Coins untouched.
        """
        with tempfile.TemporaryDirectory() as directory:
            profile = bootstrap_profile()
            policy = build_bundled_pact_policy()
            items = [0] * 181
            items[80] = 3
            server, thread = start_server(
                ("127.0.0.1", 0),
                profile,
                BootstrapState(Path(directory) / "state.json"),
                pact_draw_catalog=policy,
            )
            try:
                server.state.create_account(
                    "token", "account",
                    {"coins": policy.coin_cost, "energy": 0, "freeEnergy": 0, "itemList": items, "chrdata": []},
                )
                status, payload = post(
                    server, "/gd/do_slot", "ticket-batch",
                    "kind=20&count=3&luckType=false&campaignChrID=0&eventFlag=0&lastUpdate=1",
                )
                short_status, short = post(
                    server, "/gd/do_slot", "ticket-batch-short",
                    "kind=20&count=2&luckType=false&campaignChrID=0&eventFlag=0&lastUpdate=1",
                )
            finally:
                stop_server(server, thread)
            self.assertEqual((200, 200), (status, short_status))
            self.assertTrue(payload["success"], payload)
            self.assertEqual(
                (3, 0, policy.coin_cost),
                (len(payload["chrdata"]), payload["itemList"][80], payload["coins"]),
            )
            pool = {draw.character_id for draw in policy.fellowship_draws}
            self.assertLessEqual({row["id"] for row in payload["chrdata"]}, pool)
            # A batch larger than the tickets left is refused, not part-paid.
            self.assertEqual(2, short["cmdError"])

    def test_http_fate_ticket_uses_fellowship_luck_policy_without_spending_coins(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            profile = bootstrap_profile()
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
            server, thread = start_server(
                ("127.0.0.1", 0),
                profile,
                BootstrapState(state_path),
                pact_draw_catalog=policy,
            )
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
                status, payload = post(
                    server,
                    "/gd/do_slot",
                    "fate-ticket",
                    (
                        "kind=20&count=1&luckType=true&campaignChrID=0"
                        "&eventFlag=0&lastUpdate=1"
                    ),
                )

                self.assertEqual((200, True), (status, payload["success"]))
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
                stop_server(server, thread)

    def test_http_pact_draw_replays_and_persists(self) -> None:
        catalog_document = {
            "schema_version": 1, "provenance": "user-supplied", "coin_cost": 10,
            "new_level": 1, "max_level": 9, "max_skill_boost": 100,
            "draws": [{"character_id": 9001, "weight": 1, "duplicate_level_added": 2, "duplicate_skill_boost": 5}],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog_path, state_path = root / "pact.json", root / "state.json"
            write_json(catalog_path, catalog_document)
            profile = bootstrap_profile()
            catalog = load_pact_draw_catalog(catalog_path)

            def draw(server: BootstrapServer, request_id: str) -> tuple[int, dict[str, object]]:
                return post(server, "/gd/do_slot", request_id, "kind=0&count=1&luckType=false&campaignChrID=0&eventFlag=0&lastUpdate=1")

            server, thread = start_server(("127.0.0.1", 0), profile, BootstrapState(state_path), pact_draw_catalog=catalog)
            try:
                server.state.create_account("token", "account", {"coins": 20, "energy": 0, "freeEnergy": 0, "chrdata": []})
                status, first = draw(server, "one")
                self.assertEqual(200, status)
                self.assertEqual((True, 10, [{"id": 9001, "jobID": 0, "jobLevels": [1], "jobSlots": [], "isNew": True, "levelAdded": 1, "skillBoost": 0}]), (first["success"], first["coins"], first["chrdata"]))
                self.assertEqual((status, first), draw(server, "one"))
                _, duplicate = draw(server, "two")
                self.assertEqual((0, False, 2, 5), (duplicate["coins"], duplicate["chrdata"][0]["isNew"], duplicate["chrdata"][0]["levelAdded"], duplicate["chrdata"][0]["boostUp"]))
            finally:
                stop_server(server, thread)
            restarted, restarted_thread = start_server(("127.0.0.1", 0), profile, BootstrapState(state_path), pact_draw_catalog=catalog)
            try:
                self.assertEqual((200, first), draw(restarted, "one"))
            finally:
                stop_server(restarted, restarted_thread)

    def test_http_bundled_truth_pacts_charge_the_served_cost_and_persist_wallet_after_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = root / "state.json"
            profile = bootstrap_profile()
            server, thread = start_server(("127.0.0.1", 0), profile, BootstrapState(state_path), pact_draw_catalog=build_bundled_pact_policy())
            try:
                # A Truth pull costs 5 Energy, so a ten-pull is exactly the 50
                # free Energy a new local account receives.
                server.state.create_account("token", "account", {"coins": 0, "energy": 0, "freeEnergy": 100, "chrdata": []})

                def draw(request_id: str, count: int) -> tuple[int, dict[str, object]]:
                    return post(server, "/gd/do_slot", request_id, f"kind=1&count={count}&luckType=false&campaignChrID=0&eventFlag=0&lastUpdate=1")

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
                stop_server(server, thread)
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
            profile = bootstrap_profile()

            def draw(server: BootstrapServer, request_id: str) -> tuple[int, dict[str, object]]:
                return post(
                    server, "/gd/do_slot", request_id,
                    "kind=1&count=6&luckType=false&campaignChrID=0&eventFlag=0&lastUpdate=1",
                )

            server, thread = start_server(
                ("127.0.0.1", 0), profile, BootstrapState(state_path),
                pact_draw_catalog=build_bundled_pact_policy(),
            )
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
                stop_server(server, thread)

            restarted, restarted_thread = start_server(
                ("127.0.0.1", 0), profile, BootstrapState(state_path),
                pact_draw_catalog=build_bundled_pact_policy(),
            )
            try:
                self.assertEqual((200, first), draw(restarted, "truth-six"))
            finally:
                stop_server(restarted, restarted_thread)

    def test_migrated_packed_roster_accepts_fate_and_replays_after_restart(self) -> None:
        """The original client stores packed levels as integral JSON doubles."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = root / "state.json"
            profile = bootstrap_profile()
            policy = build_bundled_pact_policy()
            selected = policy.fellowship_draws[0]
            packed_level = float((12345 << 12) | 20)
            roster = []
            for draw_entry in policy.fellowship_draws:
                roster.append(
                    {
                        "id": draw_entry.character_id,
                        "buddy": 0,
                        "date": 0.0,
                        "jobSlots": [0.0, 0.0, 0.0],
                        "jobLevels": [
                            packed_level
                            if draw_entry.character_id == selected.character_id
                            else 10.0,
                            0.0,
                            0.0,
                        ],
                        "jobID": 0,
                        "flags": 0,
                        "skillBoost": 0,
                        "luck": 0
                        if draw_entry.character_id == selected.character_id
                        else policy.max_luck,
                    }
                )

            body = (
                "kind=0&count=1&luckType=true&campaignChrID=0"
                "&eventFlag=0&lastUpdate=1"
            )

            def draw(server: BootstrapServer) -> tuple[int, dict[str, object]]:
                return post(server, "/gd/do_slot", "fate-packed", body)

            server, thread = start_server(
                ("127.0.0.1", 0),
                profile,
                BootstrapState(state_path),
                pact_draw_catalog=policy,
            )
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
                stop_server(server, thread)

            restarted, restarted_thread = start_server(
                ("127.0.0.1", 0),
                profile,
                BootstrapState(state_path),
                pact_draw_catalog=policy,
            )
            try:
                self.assertEqual((200, first), draw(restarted))
            finally:
                stop_server(restarted, restarted_thread)

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
            write_json(catalog_path, catalog_document)
            profile = bootstrap_profile()
            server, thread = start_server(("127.0.0.1", 0), profile, BootstrapState(state_path), pact_draw_catalog=load_pact_draw_catalog(catalog_path))

            def draw(request_id: str) -> dict[str, object]:
                return post(server, "/gd/do_slot", request_id, "kind=0&count=1&luckType=false&campaignChrID=0&eventFlag=0&lastUpdate=1")[1]

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
                    payload = draw(f"draw-{index}")
                    self.assertTrue(payload["success"])
                    self.assertEqual(9002, payload["chrdata"][0]["id"])
                stored = server.state.userdata_for("token")
                assert stored is not None
                self.assertEqual(100, next(row for row in stored["chrdata"] if row["id"] == 9001)["skillBoost"])

            finally:
                stop_server(server, thread)

            # With the whole pool capped the Pact refuses rather than selecting
            # an ineligible character or charging for nothing. This needs its
            # own server, because one account per state file owns the host claim.
            exhausted_server, exhausted_thread = start_server(("127.0.0.1", 0), profile, BootstrapState(root / "exhausted.json"), pact_draw_catalog=load_pact_draw_catalog(catalog_path))
            try:
                exhausted_server.state.create_account("token", "exhausted", {"coins": 100, "energy": 0, "freeEnergy": 0, "chrdata": [owned(9001, 100), owned(9002, 100)]})
                _, exhausted = post(exhausted_server, "/gd/do_slot", "draw-exhausted", "kind=0&count=1&luckType=false&campaignChrID=0&eventFlag=0&lastUpdate=1")
                # The client's own refusal shape: a successful call reporting a
                # command error, not an HTTP or transport failure.
                self.assertEqual((True, 3), (exhausted["success"], exhausted["cmdError"]))
                self.assertNotIn("chrdata", exhausted)
                self.assertEqual(100, exhausted_server.state.userdata_for("token")["coins"])
            finally:
                stop_server(exhausted_server, exhausted_thread)
