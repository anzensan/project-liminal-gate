from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from liminal_gate.bootstrap_server import BootstrapState
from liminal_gate.event_flag_data import (
    DAILY_BONUS_EVENT_FLAG,
    daily_bonus_event_flags,
    music_event_flags,
)
from tests.support import bootstrap_profile, get, running_server


class DailyBonusTest(unittest.TestCase):
    def test_gate_has_the_exact_client_key_and_boolean_shape(self) -> None:
        self.assertEqual(
            {
                "enableDailyBonus": {
                    "name": "enableDailyBonus",
                    "value": True,
                },
            },
            daily_bonus_event_flags(),
        )

    def test_login_activates_only_when_the_server_enables_it(self) -> None:
        for enabled in (False, True):
            with self.subTest(enabled=enabled), tempfile.TemporaryDirectory() as directory:
                with running_server(
                    ("127.0.0.1", 0),
                    bootstrap_profile(),
                    BootstrapState(Path(directory) / "state.json"),
                    daily_drop_bonuses=enabled,
                ) as server:
                    self.assertEqual(200, get(server, "/gd/signup?uuid=acct&otk=sig&requestID=s1")[0])
                    status, login = get(server, "/gd/login?uuid=acct&otk=tok&requestID=l1")
                    self.assertEqual(200, status)
                    flags = login.get("eventFlags", {})
                    if enabled:
                        self.assertEqual(music_event_flags() | daily_bonus_event_flags(), flags)
                    else:
                        self.assertNotIn(DAILY_BONUS_EVENT_FLAG, flags)


if __name__ == "__main__":
    unittest.main()
