from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from liminal_gate.bootstrap_server import (
    BootstrapServer,
    BootstrapState,
    _parse_ordinary_pact_draw,
)
from liminal_gate.pact_draw_catalog import build_bundled_pact_policy, load_pact_draw_catalog
from liminal_gate.save_validation import ITEM_SLOTS
from liminal_gate.tuning import DEFAULT_TUNING
from tests.support import bootstrap_profile, post, start_server, stop_server, write_json


#: The bundled tuning with the "+" Pact turned off, which its own rate permits.
NO_PLUS_PACT = replace(
    DEFAULT_TUNING, pact=replace(DEFAULT_TUNING.pact, plus_chance_percent=0),
)

#: The same tuning with the "+" on every pull, so what it does to a roster row
#: can be asserted rather than sampled.  Its rate is the only thing forced; the
#: levels and tenths it grants stay the policy's own random ranges.
ALWAYS_PLUS_PACT = replace(
    DEFAULT_TUNING, pact=replace(DEFAULT_TUNING.pact, plus_chance_percent=100),
)


# These pin exact result rows, durable packed levels and replayed payloads, so
# the "+" Pact roll is held off across the class: they are about the draw
# contract rather than the decoration, and a random gain would make them flap.
# `PlusPactTest` below exercises the roll at its real rate.
@patch("liminal_gate.bootstrap_server.DEFAULT_TUNING", NO_PLUS_PACT)
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

    def test_http_fellowship_pool_is_gated_by_the_account_chapter(self) -> None:
        """Early accounts cannot draw members recorded as later unlocks."""
        policy = build_bundled_pact_policy()
        early = {draw.character_id for draw in policy.draws_for_kind(0, 1)}
        late = {draw.character_id for draw in policy.draws_for_kind(0, 38)} - early
        self.assertTrue(late)
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            profile = bootstrap_profile()
            server, thread = start_server(("127.0.0.1", 0), profile, BootstrapState(state_path), pact_draw_catalog=policy)
            try:
                server.state.create_account("token", "account", {"coins": policy.coin_cost * 10, "energy": 0, "freeEnergy": 0, "progressCode": 0, "chrdata": []})
                status, drawn = post(server, "/gd/do_slot", "fellowship-ten", f"kind=0&count=10&luckType=false&campaignChrID=0&eventFlag=0&lastUpdate=1")
                self.assertEqual((200, True), (status, drawn["success"]))
                self.assertEqual(10, len(drawn["chrdata"]))
                identifiers = {row["id"] for row in drawn["chrdata"]}
                self.assertTrue(identifiers <= early)
                self.assertFalse(identifiers & late)
            finally:
                stop_server(server, thread)

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


class PlusPactTest(unittest.TestCase):
    """The "+" Pact, which the client draws from the second gain fields.

    A pull that never fills `levelAdded2` and its siblings can never show a
    "+", which is why none had ever appeared
    ([#53](https://github.com/anzensan/project-liminal-gate/issues/53)).
    """

    FORM = "kind=1&count=10&luckType={luck}&campaignChrID=0&eventFlag=0&lastUpdate=1"

    def pulls(self, luck: str, rounds: int) -> list[dict]:
        rows: list[dict] = []
        with tempfile.TemporaryDirectory() as directory:
            state = BootstrapState(Path(directory) / "state.json")
            state.create_account("token", "account", {
                "coins": 90_000_000, "energy": 99_000, "freeEnergy": 0,
                "progressCode": 0x01000000 | (40 << 6) | 1, "worldMapNo": 0,
                "chrdata": [], "itemList": [0] * ITEM_SLOTS, "summonList": [0] * 16,
                "teamMembers": [0] * 6,
            })
            with state.lock:
                state.accounts["account"]["tutorial_phase"] = "free_roam"
                state.accounts["account"]["initial_userdata_served"] = True
                state._persist_locked()
            server, thread = start_server(("127.0.0.1", 0), bootstrap_profile(), state,
                                          pact_draw_catalog=build_bundled_pact_policy())
            try:
                for index in range(rounds):
                    _, payload = post(
                        server, "/gd/do_slot", f"pull-{luck}-{index}", self.FORM.format(luck=luck),
                        token="token", headers={"Content-Type": "application/x-www-form-urlencoded"},
                    )
                    rows.extend(payload.get("chrdata", []))
            finally:
                stop_server(server, thread)
        return rows

    def test_a_skill_boost_pact_decorates_some_of_its_pulls(self) -> None:
        rows = self.pulls("false", 40)
        decorated = [row for row in rows if "levelAdded2" in row]
        self.assertTrue(decorated, "no '+' appeared at all, which is the reported defect")
        # Loose enough that the roll itself cannot fail the suite, tight enough
        # that a broken rate would not pass: the policy is 20%.
        self.assertLess(len(decorated) / len(rows), 0.5)
        for row in decorated:
            self.assertTrue(1 <= row["levelAdded2"] <= 5)
            self.assertTrue(5 <= row["boostUp2"] <= 30)
            self.assertNotIn("luckup2", row, "Skill Boost pacts do not grant Luck")

    def test_a_fate_pact_grants_luck_where_the_others_grant_skill_boost(self) -> None:
        rows = self.pulls("true", 40)
        decorated = [row for row in rows if "levelAdded2" in row]
        self.assertTrue(decorated)
        for row in decorated:
            self.assertTrue(5 <= row["luckup2"] <= 30)
            self.assertNotIn("boostUp2", row)

    def test_the_gain_lands_on_the_roster_and_not_only_the_screen(self) -> None:
        """The client renders what it is told and then reads the roster back."""
        rows = [row for row in self.pulls("false", 40) if "levelAdded2" in row]
        self.assertTrue(rows)
        for row in rows:
            # The reported level and Skill Boost are the post-bonus values.
            self.assertGreaterEqual(row["jobLevels"][0], row["levelAdded2"])
            self.assertGreaterEqual(row["skillBoost"], row["boostUp2"])


class PactRefusalWalletTest(unittest.TestCase):
    """A Pact you cannot afford is refused with the wallet still on the wire.

    The client does not gate the button locally, so pressing a Pact while short
    is an ordinary thing to do. Its pull callback reads `coins` and `energy`
    off the response before it branches on the refusal code, so a bare
    `{success, errorCode}` left it reading keys that were not there
    ([#8](https://github.com/anzensan/project-liminal-gate/issues/8)).
    """

    FORM = "kind={kind}&count=1&luckType=false&campaignChrID=0&eventFlag=0&lastUpdate=1"

    def refuse(self, coins: int, energy: int, kind: int) -> dict:
        with tempfile.TemporaryDirectory() as directory:
            state = BootstrapState(Path(directory) / "state.json")
            state.create_account("token", "account", {
                "coins": coins, "energy": energy, "freeEnergy": 0,
                "progressCode": 0x01000000 | (40 << 6) | 1, "worldMapNo": 0,
                "chrdata": [], "itemList": [0] * ITEM_SLOTS, "summonList": [0] * 16,
                "teamMembers": [0] * 6,
            })
            with state.lock:
                state.accounts["account"]["tutorial_phase"] = "free_roam"
                state.accounts["account"]["initial_userdata_served"] = True
                state._persist_locked()
            server, thread = start_server(("127.0.0.1", 0), bootstrap_profile(), state,
                                          pact_draw_catalog=build_bundled_pact_policy())
            try:
                _, payload = post(server, "/gd/do_slot", "short", self.FORM.format(kind=kind),
                                  token="token",
                                  headers={"Content-Type": "application/x-www-form-urlencoded"})
            finally:
                stop_server(server, thread)
        return payload

    def test_a_truth_pull_short_of_energy_still_reports_the_wallet(self) -> None:
        payload = self.refuse(coins=100, energy=2, kind=1)
        self.assertEqual(1, payload["cmdError"])
        self.assertEqual((100, 2, 0),
                         (payload["coins"], payload["energy"], payload["freeEnergy"]))

    def test_a_fellowship_pull_short_of_coins_still_reports_the_wallet(self) -> None:
        payload = self.refuse(coins=1, energy=0, kind=0)
        self.assertEqual(2, payload["cmdError"])
        self.assertEqual((1, 0, 0),
                         (payload["coins"], payload["energy"], payload["freeEnergy"]))

    def test_a_refusal_spends_nothing(self) -> None:
        payload = self.refuse(coins=100, energy=2, kind=1)
        self.assertEqual(2, payload["energy"], "a refused pull must not charge")


@patch("liminal_gate.bootstrap_server.DEFAULT_TUNING", NO_PLUS_PACT)
class DuplicateJobLevelTest(unittest.TestCase):
    """A duplicate raises every job the character has unlocked.

    The "+" Pact is held off here because this pins exact packed job levels and
    the "+" adds a random one to five on top of them. That guard was doing more
    than it said: the roll it silenced was itself only levelling the first slot,
    so a real defect read as a 22% flake for a week. `PlusPactJobLevelTest`
    below now forces the roll on and asserts it, so nothing is hidden by turning
    it off here.

    Granting only the first slot is what a tester reported: pulling a duplicate
    levelled J1 alone, so the reason to unlock a character's jobs *before*
    pulling more of it -- levelling them all at once instead of by hand -- was
    gone. The first slot is also not necessarily the active job, so the reply
    named the active `jobID` beside a level belonging to a different one.
    """

    def test_every_unlocked_job_gains_and_the_locked_one_does_not(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            policy = build_bundled_pact_policy()
            selected = policy.fellowship_draws[0]
            # Two jobs unlocked at different levels, the third never unlocked,
            # and the *second* is active. Job experience rides in the high bits.
            roster = [
                {
                    "id": draw.character_id, "buddy": 0, "date": 0.0,
                    "jobSlots": [0.0, 0.0, 0.0],
                    "jobLevels": [float((5 << 12) | 10), float((7 << 12) | 20), 0.0],
                    "jobID": 1, "flags": 0, "skillBoost": 17,
                    "luck": 0 if draw.character_id == selected.character_id else policy.max_luck,
                }
                for draw in policy.fellowship_draws
            ]
            items = [0] * 181
            items[80] = 1
            server, thread = start_server(
                ("127.0.0.1", 0), bootstrap_profile(),
                BootstrapState(Path(directory) / "state.json"),
                pact_draw_catalog=policy,
            )
            try:
                server.state.create_account("token", "account", {
                    "coins": policy.coin_cost, "energy": 0, "freeEnergy": 0,
                    "itemList": items, "chrdata": roster,
                })
                status, payload = post(
                    server, "/gd/do_slot", "fate-ticket-jobs",
                    "kind=20&count=1&luckType=true&campaignChrID=0&eventFlag=0&lastUpdate=1",
                )
                self.assertEqual((200, True), (status, payload["success"]))
                stored = next(
                    row for row in server.state.userdata_for("token")["chrdata"]
                    if row["id"] == selected.character_id
                )
                added = selected.duplicate_level_added
                levels = [int(value) & 0xFFF for value in stored["jobLevels"]]
                self.assertEqual([10 + added, 20 + added, 0], levels)
                # Job experience is untouched by a level grant.
                self.assertEqual([5, 7, 0], [int(value) >> 12 for value in stored["jobLevels"]])
                # The reply describes the active job, which is the second.
                self.assertEqual(1, payload["chrdata"][0]["jobID"])
                self.assertEqual([20 + added], payload["chrdata"][0]["jobLevels"])
                self.assertEqual(added, payload["chrdata"][0]["levelAdded"])
            finally:
                stop_server(server, thread)


@patch("liminal_gate.bootstrap_server.DEFAULT_TUNING", ALWAYS_PLUS_PACT)
class PlusPactJobLevelTest(unittest.TestCase):
    """The "+" raises every unlocked job too, and reports the active one.

    `PlusPactTest` pulls against an empty roster, so every row it decorates is a
    brand new character with one unlocked job -- which is why it never noticed
    that the "+" wrote slot 0 and nothing else. A tester did, on the second half
    of [#69](https://github.com/anzensan/project-liminal-gate/issues/69): the
    duplicate grant had been fixed to raise every unlocked job and the "+" on
    top of it still landed on the first.

    Between them those two defects hid each other. This same roster under
    `DuplicateJobLevelTest` failed about one run in five while the "+" was live,
    and the failure was read as a flaky test and silenced by turning the roll
    off rather than as the roll being wrong. The rate is forced to 100 here so
    the decoration is asserted head-on instead of sampled.
    """

    def test_the_plus_levels_reach_every_unlocked_job(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            policy = build_bundled_pact_policy()
            selected = policy.fellowship_draws[0]
            # The same row `DuplicateJobLevelTest` uses: two jobs unlocked at
            # different levels, the third never unlocked, the *second* active.
            roster = [
                {
                    "id": draw.character_id, "buddy": 0, "date": 0.0,
                    "jobSlots": [0.0, 0.0, 0.0],
                    "jobLevels": [float((5 << 12) | 10), float((7 << 12) | 20), 0.0],
                    "jobID": 1, "flags": 0, "skillBoost": 17,
                    "luck": 0 if draw.character_id == selected.character_id else policy.max_luck,
                }
                for draw in policy.fellowship_draws
            ]
            items = [0] * 181
            items[80] = 1
            server, thread = start_server(
                ("127.0.0.1", 0), bootstrap_profile(),
                BootstrapState(Path(directory) / "state.json"),
                pact_draw_catalog=policy,
            )
            try:
                server.state.create_account("token", "account", {
                    "coins": policy.coin_cost, "energy": 0, "freeEnergy": 0,
                    "itemList": items, "chrdata": roster,
                })
                status, payload = post(
                    server, "/gd/do_slot", "fate-ticket-plus-jobs",
                    "kind=20&count=1&luckType=true&campaignChrID=0&eventFlag=0&lastUpdate=1",
                )
                self.assertEqual((200, True), (status, payload["success"]))
                stored = next(
                    row for row in server.state.userdata_for("token")["chrdata"]
                    if row["id"] == selected.character_id
                )
                row = payload["chrdata"][0]
                added = selected.duplicate_level_added
                plus = row["levelAdded2"]
                self.assertTrue(1 <= plus <= 5, "the '+' must grant the policy's own range")
                levels = [int(value) & 0xFFF for value in stored["jobLevels"]]
                # Both unlocked jobs carry the duplicate gain *and* the "+" on
                # top of it; the job the character never unlocked carries
                # neither.
                self.assertEqual([10 + added + plus, 20 + added + plus, 0], levels)
                # Job experience is untouched by either level grant.
                self.assertEqual([5, 7, 0], [int(value) >> 12 for value in stored["jobLevels"]])
                # The reply describes the active job, which is the second, and
                # reports the two gains separately -- the duplicate's as
                # `levelAdded` and the "+" as `levelAdded2`.
                self.assertEqual(1, row["jobID"])
                self.assertEqual([20 + added + plus], row["jobLevels"])
                self.assertEqual(added, row["levelAdded"])
            finally:
                stop_server(server, thread)
