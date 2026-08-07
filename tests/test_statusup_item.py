from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from liminal_gate.bootstrap_server import BootstrapState
from liminal_gate.statusup_catalog import build_bundled_statusup_policy, load_statusup_catalog
from tests.support import bootstrap_profile, get, post, start_server, stop_server, write_json


class StatusupItemTest(unittest.TestCase):
    def test_http_settlement_errors_collision_and_restart_replay(self) -> None:
        catalog_document = {
            "schema_version": 1, "provenance": "user-supplied", "item_slots": 3,
            "level_cap": 90, "skill_boost_cap": 1000,
            "items": [
                {"item_id": 1, "level": 1, "skill_boost": 0, "luck": 0, "species": None},
                {"item_id": 2, "level": 0, "skill_boost": 1, "luck": 0, "species": 8},
                {"item_id": 3, "level": 0, "skill_boost": 0, "luck": 1, "species": None},
            ],
            "characters": [
                {"character_id": 3, "species": 1, "luck_cap": 30},
                {"character_id": 91, "species": 8, "luck_cap": 1000},
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog_path = write_json(root / "statusup.json", catalog_document)
            profile = bootstrap_profile()
            state_path = root / "state.json"
            catalog = load_statusup_catalog(catalog_path)

            server, thread = start_server(("127.0.0.1", 0), profile, BootstrapState(state_path), statusup_catalog=catalog)
            try:
                server.state.create_account("token", "account", {
                    "chrdata": [
                        {"id": 3, "jobLevels": [int((111 << 12) | 89), 0.0], "skillBoost": 990, "luck": 20},
                        {"id": 91, "jobLevels": [1.0], "skillBoost": 0, "luck": 0},
                    ],
                    "itemList": [2, 2, 20],
                })
                status, level = post(server, "/gd/use_statusup_item", "level", "targetChrID=3&useItemID=1&useAmount=2")
                self.assertEqual(200, status)
                self.assertEqual({"chrdata", "itemList", "resultValues", "digest"}, set(level))
                changed = next(item for item in level["chrdata"] if item["id"] == 3)
                self.assertEqual([111, 0], [int(value) >> 12 for value in changed["jobLevels"]])
                self.assertEqual([90, 0], [int(value) & 0xFFF for value in changed["jobLevels"]])
                self.assertEqual({"0": 1}, level["resultValues"]["addedLevels"])
                self.assertEqual((200, level), post(server, "/gd/use_statusup_item", "level", "targetChrID=3&useItemID=1&useAmount=2"))
                # Reusing a spent requestID with a different body is no longer
                # read as a tampered retry: this is a genuine second use, of a
                # luck item, so it applies -- and its own retry still replays
                # rather than spending a second one.
                status, luck = post(server, "/gd/use_statusup_item", "level", "targetChrID=3&useItemID=3&useAmount=1")
                self.assertEqual((200, 1), (status, luck["resultValues"]["addedLuck"]))
                self.assertEqual(30, next(item for item in luck["chrdata"] if item["id"] == 3)["luck"])
                self.assertEqual((status, luck), post(server, "/gd/use_statusup_item", "level", "targetChrID=3&useItemID=3&useAmount=1"))
                status, wrong_species = post(server, "/gd/use_statusup_item", "species", "targetChrID=3&useItemID=2&useAmount=1")
                self.assertEqual((200, True, 3), (status, wrong_species["success"], wrong_species["cmdError"]))
                status, unknown = post(server, "/gd/use_statusup_item", "unknown", "targetChrID=999&useItemID=1&useAmount=1")
                self.assertEqual((200, True, 4), (status, unknown["success"], unknown["cmdError"]))
                # A semantically invalid account record must not retain the
                # speculative level update attempted before its bad scalar is
                # discovered.
                bad = {"id": 3, "jobLevels": [89], "skillBoost": "bad", "luck": 0}
                server.state.accounts["account"]["userdata"]["chrdata"] = [bad]
                server.state.accounts["account"]["userdata"]["itemList"] = [2, 0, 0]
                status, invalid_state = post(server, "/gd/use_statusup_item", "bad-state", "targetChrID=3&useItemID=1&useAmount=1")
                self.assertEqual((200, True, 3), (status, invalid_state["success"], invalid_state["cmdError"]))
                self.assertEqual(([89], 2), (bad["jobLevels"], server.state.accounts["account"]["userdata"]["itemList"][0]))
                server.state.accounts["account"]["userdata"]["chrdata"] = [
                    {"id": 3, "jobLevels": [int((111 << 12) | 90), 0.0], "skillBoost": 990, "luck": 20},
                    {"id": 91, "jobLevels": [1.0], "skillBoost": 0, "luck": 0},
                ]
                server.state.accounts["account"]["userdata"]["itemList"] = [1, 2, 20]
                status, luck = post(server, "/gd/use_statusup_item", "luck", "targetChrID=3&useItemID=3&useAmount=20")
                self.assertEqual((200, 1, 30), (status, luck["resultValues"]["addedLuck"], next(item for item in luck["chrdata"] if item["id"] == 3)["luck"]))
            finally:
                stop_server(server, thread)

            restarted, restarted_thread = start_server(("127.0.0.1", 0), profile, BootstrapState(state_path), statusup_catalog=catalog)
            try:
                self.assertEqual((200, level), post(restarted, "/gd/use_statusup_item", "level", "targetChrID=3&useItemID=1&useAmount=2"))
                status, unavailable = post(restarted, "/gd/use_statusup_item", "missing", "targetChrID=3&useItemID=1&useAmount=1")
                self.assertEqual((200, True, 3), (status, unavailable["success"], unavailable["cmdError"]))
            finally:
                stop_server(restarted, restarted_thread)


class BundledStatusupPolicyRuntimeTest(unittest.TestCase):
    def test_bundled_effects_are_applied_through_the_real_route(self) -> None:
        """The bundled table must settle a real use, not merely load."""
        with tempfile.TemporaryDirectory() as directory:
            profile = bootstrap_profile()
            state = BootstrapState(Path(directory) / "state.json")
            items = [0] * 181
            items[175 - 1] = 4  # item 175 grants three levels per use
            state.create_account("token", "account", {
                "coins": 0, "itemList": items,
                "chrdata": [{
                    "id": 3, "jobID": 0, "jobSlots": [], "skillBoost": 0, "luck": 0,
                    "jobLevels": [(1234 << 12) | 10, (5 << 12) | 4, 0.0],
                }],
            })
            server, thread = start_server(("127.0.0.1", 0), profile, state, statusup_catalog=build_bundled_statusup_policy())
            try:
                status, payload = post(server, "/gd/use_statusup_item", "bundled",
                                       "targetChrID=3&useItemID=175&useAmount=2")
            finally:
                stop_server(server, thread)
            self.assertEqual(200, status)
            self.assertEqual({"0": 6, "1": 6}, payload["resultValues"]["addedLevels"])
            row = next(item for item in payload["chrdata"] if item["id"] == 3)
            # Both unlocked jobs gain 2 x 3 levels; the packed experience high
            # bits survive, and the locked third job is untouched.
            self.assertEqual([(1234, 16), (5, 10), (0, 0)],
                             [(int(v) >> 12, int(v) & 0xFFF) for v in row["jobLevels"]])
            self.assertEqual(2, payload["itemList"][175 - 1])


class StatusupItemAdvertisementTest(unittest.TestCase):
    """The constants block the client's item-use character filter reads.

    Without it `UIChrSelectWindow.CalcMaxUseNum` returns zero for every
    character, and a held candy item reports that nobody can take it.
    """

    def constants(self, statusup: object | None) -> dict:
        with tempfile.TemporaryDirectory() as directory:
            state = BootstrapState(Path(directory) / "state.json")
            state.create_account("token", "account", {"coins": 0, "itemList": [0] * 181, "chrdata": []})
            server, thread = start_server(
                ("127.0.0.1", 0), bootstrap_profile(), state, statusup_catalog=statusup,
            )
            try:
                status, payload = get(server, "/gd/get_server_status?otk=token&requestID=status")
            finally:
                stop_server(server, thread)
        self.assertEqual(200, status)
        return payload["constants"]

    def test_every_bundled_item_is_advertised_as_four_integers(self) -> None:
        rows = self.constants(build_bundled_statusup_policy())["statusUpItems"]
        self.assertEqual(
            ["161", "162", "163", "168", "175", "176", "177"], list(rows),
        )
        # Level, displayed Skill Boost, displayed Luck, designated species.
        # The fourth value is required, not optional: the advertised client
        # version puts `IsStatusUpItemsDesignatedSpeciesImplemented` past its
        # 4.99 threshold, and a three-value row is read as species 1000.
        self.assertEqual([0, 0, 3, 0], rows["177"])  # Luck Candybox
        self.assertEqual([0, 0, 1, 0], rows["163"])  # Luck Candy
        self.assertEqual([0, 1, 0, 8], rows["168"])  # Machine-only
        for item_id, row in rows.items():
            self.assertEqual(4, len(row), item_id)
            # Read through LitJson's int accessor, which raises on a decimal.
            self.assertTrue(all(type(value) is int for value in row), item_id)

    def test_no_items_are_advertised_without_a_local_policy(self) -> None:
        # The route answers `unsupported_statusup_item` with no catalog, so the
        # client is offered nothing rather than a use the server would refuse.
        self.assertNotIn("statusUpItems", self.constants(None))
