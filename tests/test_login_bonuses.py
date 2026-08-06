from __future__ import annotations

import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

from liminal_gate.bootstrap_server import BootstrapServer, BootstrapState, build_server
from liminal_gate.message_catalog import login_bonus_messages
from liminal_gate.server_config import ServerConfig
from tests.support import DEFAULT_PROFILE_PATH, bootstrap_profile, request, start_server, stop_server


class LoginBonusTest(unittest.TestCase):
    PROFILE = DEFAULT_PROFILE_PATH

    def test_core_story_launch_enables_the_standard_login_schedule(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            server = build_server(ServerConfig(
                profile=self.PROFILE,
                state_file=Path(directory) / "state.json",
                host="127.0.0.1",
                port=0,
                core_story=True,
            ))
            try:
                self.assertTrue(server.login_bonuses)
                self.assertTrue(server.daily_drop_bonuses)
                self.assertIsNotNone(server.message_catalog)
            finally:
                server.server_close()

    def test_published_reward_schedule_and_eight_day_cycle(self) -> None:
        consecutive = [
            (login_bonus_messages(day, day, 1.0)[0].coins,
             login_bonus_messages(day, day, 1.0)[0].free_energy)
            for day in range(1, 9)
        ]
        self.assertEqual(
            [(500, 0), (800, 0), (1_000, 0), (1_500, 0),
             (0, 2), (2_000, 0), (3_000, 0), (0, 3)],
            consecutive,
        )
        self.assertEqual(
            [("login:consecutive:11", 500, 0)],
            [(message.message_id, message.coins, message.free_energy) for message in login_bonus_messages(9, 11, 1.0)],
        )
        expected_overall = {
            1: (3_000, 5), 2: (0, 3), 3: (0, 2), 4: (0, 3),
            5: (0, 2), 6: (0, 2), 7: (0, 2), 8: (0, 2), 9: (0, 2),
            10: (0, 3), 30: (0, 3), 60: (0, 3), 100: (0, 5),
            150: (0, 5), 200: (0, 5),
        }
        actual_overall = {}
        for total_day in expected_overall:
            overall = next(
                message for message in login_bonus_messages(1, total_day, 1.0)
                if message.message_id.startswith("login:overall:")
            )
            actual_overall[total_day] = (overall.coins, overall.free_energy)
        self.assertEqual(expected_overall, actual_overall)
        for total_day in (11, 29, 50, 99, 101, 149):
            self.assertEqual(1, len(login_bonus_messages(1, total_day, 1.0)))

    def test_utc_issuance_read_delete_restart_and_missed_day_reset(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"

            def start() -> tuple[BootstrapServer, threading.Thread]:
                return start_server(
                    ("127.0.0.1", 0), bootstrap_profile(self.PROFILE), BootstrapState(state_path),
                    login_bonuses=True,
                )

            def login(server: BootstrapServer, now: float):
                with patch("liminal_gate.bootstrap_server.time.time", return_value=now):
                    return request(server, "GET", "/gd/login?otk=token&uuid=account")

            def mutate(server: BootstrapServer, route: str, request_id: str, message_ids: list[str]):
                body = urlencode({"idlist": json.dumps(message_ids), "lastUpdate": "1"})
                return request(server, "POST", f"/gd/{route}?otk=token&requestID={request_id}", body)

            server, thread = start()
            try:
                server.state.create_account("signup", "account", {
                    "progressCode": 0,
                    "chrdata": [], "buddyInfo": {"list": [], "record": []},
                    "summonList": [0] * 16, "itemList": [0] * 181,
                    "coins": 0, "freeEnergy": 0, "energy": 0,
                    "energyAppStore": 0, "energyGooglePlay": 0, "energyAndApp": 0,
                }, server.message_catalog)
                first_day = 20_000 * 86_400 + 12_345
                status, first = login(server, first_day)
                first_ids = sorted(message["id"] for message in first["messageList"])
                self.assertEqual((200, ["login:consecutive:1", "login:overall:1"]), (status, first_ids))

                status, claimed = mutate(server, "read_messages", "read-day-one", first_ids)
                self.assertEqual((200, 3_500, 5), (status, claimed["result"]["coins"], claimed["result"]["freeEnergy"]))
                status, deleted = mutate(server, "delete_messages", "delete-day-one", first_ids)
                self.assertEqual((200, first_ids), (status, deleted["deletelist"]))
            finally:
                stop_server(server, thread)

            restarted, thread = start()
            try:
                status, same_day = login(restarted, first_day + 30_000)
                self.assertEqual((200, []), (status, same_day["messageList"]))
                status, clock_rollback = login(restarted, first_day - 86_400)
                self.assertEqual((200, []), (status, clock_rollback["messageList"]))

                status, second = login(restarted, first_day + 86_400)
                second_ids = sorted(message["id"] for message in second["messageList"])
                self.assertEqual((200, ["login:consecutive:2", "login:overall:2"]), (status, second_ids))
                second_consecutive = next(message for message in second["messageList"] if message["id"] == "login:consecutive:2")
                self.assertEqual((800, 0), (second_consecutive["coins"], second_consecutive["energy"]))

                status, third = login(restarted, first_day + 3 * 86_400)
                third_ids = sorted(message["id"] for message in third["messageList"])
                self.assertEqual(
                    (200, [
                        "login:consecutive:2", "login:consecutive:3",
                        "login:overall:2", "login:overall:3",
                    ]),
                    (status, third_ids),
                )
                third_consecutive = next(message for message in third["messageList"] if message["id"] == "login:consecutive:3")
                self.assertEqual("Consecutive login bonus day 1", third_consecutive["messages"]["en"])
                account = restarted.state.accounts["account"]
                self.assertEqual((1, 3), (
                    account["login_bonus_consecutive_days"],
                    account["login_bonus_total_days"],
                ))
            finally:
                stop_server(restarted, thread)


if __name__ == "__main__":
    unittest.main()
