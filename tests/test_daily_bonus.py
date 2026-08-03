from __future__ import annotations

from http.client import HTTPConnection
import json
from pathlib import Path
import tempfile
import threading
import unittest

from liminal_gate.bootstrap_server import BootstrapServer, BootstrapState, load_profile
from liminal_gate.event_flag_data import DAILY_BONUS_EVENT_FLAG, daily_bonus_event_flags


class DailyBonusTest(unittest.TestCase):
    PROFILE = Path(__file__).resolve().parents[1] / "profiles" / "legacy-client-bootstrap.json"

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
                server = BootstrapServer(
                    ("127.0.0.1", 0),
                    load_profile(self.PROFILE),
                    BootstrapState(Path(directory) / "state.json"),
                    daily_drop_bonuses=enabled,
                )
                thread = threading.Thread(target=server.serve_forever)
                thread.start()

                def get(path: str) -> tuple[int, dict[str, object]]:
                    connection = HTTPConnection(*server.server_address)
                    connection.request("GET", path)
                    response = connection.getresponse()
                    payload = json.loads(response.read())
                    connection.close()
                    return response.status, payload

                try:
                    self.assertEqual(200, get("/gd/signup?uuid=acct&otk=sig&requestID=s1")[0])
                    status, login = get("/gd/login?uuid=acct&otk=tok&requestID=l1")
                    self.assertEqual(200, status)
                    flags = login.get("eventFlags", {})
                    if enabled:
                        self.assertEqual(daily_bonus_event_flags(), flags)
                    else:
                        self.assertNotIn(DAILY_BONUS_EVENT_FLAG, flags)
                finally:
                    server.shutdown()
                    thread.join()
                    server.server_close()


if __name__ == "__main__":
    unittest.main()
