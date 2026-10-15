from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from liminal_gate.bootstrap_server import BootstrapState, _draw_companion_bonus
from liminal_gate.companion_strengthen_catalog import build_bundled_companion_strengthen_policy, load_companion_strengthen_catalog
from tests.support import bootstrap_profile, post, start_server, stop_server, write_json


class CompanionStrengthenTest(unittest.TestCase):
    def test_http_strengthen_consumes_material_and_replays_after_restart(self) -> None:
        document = {"schema_version": 1, "provenance": "user-supplied", "same_companion_multiplier": 2, "byebye_companion_id": None, "byebye_multiplier_percent": 150, "bonus_weights": [{"percent": 0, "weight": 1}], "masters": [{"companion_id": 10, "base_exp": 1, "max_level": 2, "exp_max": 100, "exp_coeff": 1, "same_bonus_bias": 1}, {"companion_id": 11, "base_exp": 100, "max_level": 2, "exp_max": 100, "exp_coeff": 1, "same_bonus_bias": 1}]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog_path = write_json(root / "strengthen.json", document)
            profile = bootstrap_profile()
            state_path = root / "state.json"
            catalog = load_companion_strengthen_catalog(catalog_path)

            server, thread = start_server(("127.0.0.1", 0), profile, BootstrapState(state_path), companion_strengthen_catalog=catalog)
            try:
                server.state.create_account("token", "account", {"coins": 100, "chrdata": [{"id": 3, "buddy": 2}], "buddyInfo": {"list": [{"iid": 1, "bid": 10, "lv": 1, "exp": 0, "flag": 0}, {"iid": 2, "bid": 11, "lv": 1, "exp": 0, "flag": 0, "chrID": 3}], "record": []}})
                status, first = post(server, "/gd/buddy_strengthen", "one", "baseID=1&matList=[2]")
                self.assertEqual(200, status)
                self.assertEqual((True, 50, 100, 0, 0, [1], 0), (first["success"], first["coins"], first["totalEXP"], first["additionalEXP"], first["expBonus"], [row["iid"] for row in first["buddyInfo"]["list"]], first["chrdata"][0]["buddy"]))
                self.assertEqual(2, first["buddyInfo"]["list"][0]["lv"])
                self.assertEqual((status, first), post(server, "/gd/buddy_strengthen", "one", "baseID=1&matList=[2]"))
                # Reusing a spent requestID with a different body is no longer
                # read as a tampered retry; feeding a companion to itself is
                # rejected on its own merits.
                self.assertEqual((501, "unsupported_companion_strengthen"), (post(server, "/gd/buddy_strengthen", "one", "baseID=1&matList=[1]")[0], post(server, "/gd/buddy_strengthen", "one", "baseID=1&matList=[1]")[1]["error"]))
                server.state.create_account("other", "other-account", {"coins": 100, "buddyInfo": {"list": [{"iid": 4, "bid": 10, "lv": 1, "exp": 0, "flag": 0}, {"iid": 5, "bid": 11, "lv": 1, "exp": 0, "flag": 2}], "record": []}})
                # Production signup/login identifies which LAN client owns this
                # account before a rotated token can mutate it.
                server.state.bind_login_token("other", "other-account", "127.0.0.1")
                status, favorite = post(server, "/gd/buddy_strengthen", "favorite", "baseID=4&matList=[5]", "other")
                self.assertEqual((200, True, 6), (status, favorite["success"], favorite["cmdError"]))
                self.assertEqual([4, 5], [row["iid"] for row in server.state.userdata_for("other")["buddyInfo"]["list"]])
            finally:
                stop_server(server, thread)

            restarted, restarted_thread = start_server(("127.0.0.1", 0), profile, BootstrapState(state_path), companion_strengthen_catalog=catalog)
            try:
                # The same emulator last logged into other-account above.
                # Logging back in restores ownership before this account's
                # durable replay is requested.
                restarted.state.bind_login_token("token", "account", "127.0.0.1")
                self.assertEqual((200, first), post(restarted, "/gd/buddy_strengthen", "one", "baseID=1&matList=[2]"))
            finally:
                stop_server(restarted, restarted_thread)


class BundledCompanionStrengthenRuntimeTest(unittest.TestCase):
    def test_bundled_progression_is_applied_through_the_real_route(self) -> None:
        """The bundled masters must settle a real strengthen, not merely load."""
        with tempfile.TemporaryDirectory() as directory:
            profile = bootstrap_profile()
            state = BootstrapState(Path(directory) / "state.json")
            catalog = build_bundled_companion_strengthen_policy()
            # Master 1's base EXP is 671 with a same-Companion bias of 1, so a
            # level 5 material of the same master is worth 5 * 671 * 2.
            state.create_account("token", "account", {
                "coins": 100000, "chrdata": [],
                "buddyInfo": {"list": [
                    {"iid": 1, "bid": 1, "lv": 1, "exp": 0, "flag": 0, "chrID": 0},
                    {"iid": 2, "bid": 1, "lv": 5, "exp": 0, "flag": 0, "chrID": 0},
                ], "record": []},
            })
            server, thread = start_server(("127.0.0.1", 0), profile, state, companion_strengthen_catalog=catalog)
            try:
                status, payload = post(server, "/gd/buddy_strengthen", "bundled",
                                       "baseID=1&matList=[2]&lastUpdate=1")
            finally:
                stop_server(server, thread)
            self.assertEqual(200, status)
            self.assertEqual(6710, payload["totalEXP"])
            self.assertIn(payload["expBonus"], {percent for percent, _ in catalog.bonus_weights})


class CompanionBonusOutcomeTest(unittest.TestCase):
    def test_default_weighted_draw_reaches_every_outcome(self) -> None:
        """Exercise every threshold, without a probabilistic/flaky assertion."""
        catalog = build_bundled_companion_strengthen_policy()
        weights = dict(catalog.bonus_weights)
        total = sum(weights.values())
        with patch("liminal_gate.bootstrap_server.random.SystemRandom") as generator:
            generator.return_value.randrange.side_effect = range(total)
            outcomes = Counter(_draw_companion_bonus(catalog) for _ in range(total))
        self.assertEqual({0: 75, 25: 15, 50: 8, 100: 2}, outcomes)
        self.assertEqual(weights, outcomes)
        for call in generator.return_value.randrange.call_args_list:
            self.assertEqual((total,), call.args)

    def test_each_bonus_is_credited_once_and_replayed_after_restart(self) -> None:
        for bonus, threshold in ((0, 0), (25, 75), (50, 90), (100, 98)):
            with self.subTest(bonus=bonus), tempfile.TemporaryDirectory() as directory:
                state_path = Path(directory) / "state.json"
                profile = bootstrap_profile()
                catalog = build_bundled_companion_strengthen_policy()
                state = BootstrapState(state_path)
                # Buddy 3 has enough EXP headroom for the normal and bonus
                # animations. Four Metal Minion LambdaLambda materials:
                # 4 * 200,000 = 800,000 base EXP, then 0/25/50/100 percent.
                state.create_account("token", "account", {
                    "coins": 10000, "chrdata": [],
                    "buddyInfo": {"list": [
                        {"iid": 1, "bid": 3, "lv": 1, "exp": 0, "flag": 0, "chrID": 0},
                        *[{"iid": iid, "bid": 130, "lv": 1, "exp": 0, "flag": 0, "chrID": 0}
                          for iid in range(2, 6)],
                    ], "record": []},
                })
                body = "baseID=1&matList=[2,3,4,5]&lastUpdate=1"
                log_path = Path(directory) / "events.jsonl"
                server, thread = start_server(("127.0.0.1", 0), profile, state,
                                               companion_strengthen_catalog=catalog, event_log=log_path)
                try:
                    with patch("liminal_gate.bootstrap_server.random.SystemRandom") as generator:
                        generator.return_value.randrange.return_value = threshold
                        status, payload = post(server, "/gd/buddy_strengthen", "bonus", body)
                        self.assertEqual(200, status, payload)
                        self.assertEqual((True, 800000, 800000 * bonus // 100, bonus),
                                         (payload["success"], payload["totalEXP"],
                                          payload["additionalEXP"], payload["expBonus"]))
                        owned = payload["buddyInfo"]["list"]
                        self.assertEqual([1], [row["iid"] for row in owned])
                        self.assertEqual(800000 + payload["additionalEXP"], owned[0]["exp"])
                        self.assertLess(owned[0]["lv"], catalog.masters[3].max_level)
                        self.assertEqual(9800, payload["coins"])
                        event = json.loads(log_path.read_text().splitlines()[-1])
                        self.assertEqual(bonus, event["strengthen_exp_bonus_percent"])
                        self.assertEqual(bonus > 0, event["strengthen_exp_bonus_awarded"])
                        self.assertNotIn("buddyInfo", event)
                        self.assertNotIn("matList", event)
                        settled = state_path.read_bytes()
                        self.assertEqual((status, payload), post(server, "/gd/buddy_strengthen", "bonus", body))
                        self.assertEqual(settled, state_path.read_bytes())
                        generator.return_value.randrange.assert_called_once_with(100)
                finally:
                    stop_server(server, thread)
                restarted, restarted_thread = start_server(("127.0.0.1", 0), profile,
                    BootstrapState(state_path), companion_strengthen_catalog=catalog)
                try:
                    with patch("liminal_gate.bootstrap_server._draw_companion_bonus",
                               side_effect=AssertionError("retry rerolled the EXP bonus")):
                        self.assertEqual((status, payload), post(restarted, "/gd/buddy_strengthen", "bonus", body))
                    self.assertEqual(owned, restarted.state.userdata_for("token")["buddyInfo"]["list"])
                finally:
                    stop_server(restarted, restarted_thread)
