"""Login must be able to send the drop-eligibility allowlist.

Without `chrBuddyData` the client sets `canDrop = false` on every character and
Companion and discards each drop it rolls, so a server that omits the field
reports empty `monsters`/`buddies` on every clear no matter how the roll went.

The field is opt-in: a login without `--drop-eligibility` is byte-for-byte what
it was before, so enabling the allowlist cannot change an existing install by
accident.
"""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from liminal_gate.bootstrap_server import BootstrapState
from liminal_gate.drop_eligibility import (
    character_master_ids,
    companion_master_ids,
    login_chr_buddy_data,
)
from tests.support import bootstrap_profile, request as http_request, running_server


def _login(drop_eligibility: bool) -> dict:
    with tempfile.TemporaryDirectory() as directory:
        profile = bootstrap_profile()
        with running_server(
            ("127.0.0.1", 0), profile, BootstrapState(Path(directory) / "state.json"),
            drop_eligibility=drop_eligibility,
        ) as server:
            account, token = "local-account", "local-token"
            uuid_field = profile.account_binding["login_query_field"]

            def request(path: str) -> dict:
                return http_request(server, "GET", path, headers={"X-Request-Id": path})[1]

            request(f"{profile.routes['signup']}?{uuid_field}={account}&otk={token}")
            return request(f"{profile.routes['login']}?{uuid_field}={account}&otk={token}")


class DropEligibilityTest(unittest.TestCase):
    def test_allowlist_covers_every_bundled_master(self) -> None:
        data = login_chr_buddy_data()
        self.assertEqual({"chrList", "buddyList", "rebirthList"}, set(data))
        self.assertEqual(character_master_ids(), data["chrList"])
        self.assertEqual(companion_master_ids(), data["buddyList"])
        # Ascending, unique, and positive: the client indexes these directly.
        for key in ("chrList", "buddyList"):
            with self.subTest(key):
                self.assertEqual(sorted(set(data[key])), data[key])
                self.assertTrue(all(isinstance(v, int) and v > 0 for v in data[key]))
        self.assertEqual(497, len(data["buddyList"]))

    def test_every_list_is_present_because_the_client_reads_them_unguarded(self) -> None:
        # The client null-guards chrBuddyData itself and then reads all three
        # child lists unconditionally: an absent list falls into the
        # null-reference thrower inside login and the client hangs on
        # "Connecting..." forever. Omitting one is not a safe degradation.
        data = login_chr_buddy_data()
        self.assertEqual({"chrList", "buddyList", "rebirthList"}, set(data))
        self.assertTrue(all(data[key] for key in data))

    def test_rebirth_versions_are_the_recovered_figures(self) -> None:
        entries = login_chr_buddy_data()["rebirthList"]
        self.assertEqual(65, len(entries))
        self.assertEqual([{"ID", "version"}] * len(entries), [set(entry) for entry in entries])
        ids = [entry["ID"] for entry in entries]
        self.assertEqual(sorted(set(ids)), ids)
        # Every recipe is at or below the final client's own 5.5.7, so none of
        # these versions withholds a recipe.
        self.assertLessEqual(max(entry["version"] for entry in entries), 5.5)

    def test_login_omits_the_field_by_default(self) -> None:
        self.assertNotIn("chrBuddyData", _login(drop_eligibility=False))

    def test_login_sends_the_field_when_enabled(self) -> None:
        body = _login(drop_eligibility=True)
        self.assertIn("chrBuddyData", body)
        self.assertEqual(login_chr_buddy_data(), body["chrBuddyData"])

    def test_enabling_it_changes_nothing_else_on_login(self) -> None:
        off, on = _login(drop_eligibility=False), _login(drop_eligibility=True)
        # `digest` is over the payload, so it is expected to differ, and
        # `lastLogin` is the wall clock at the moment each login was answered.
        for body in (off, on):
            body.pop("digest", None)
            body.pop("lastLogin", None)
        on.pop("chrBuddyData")
        self.assertEqual(off, on)


if __name__ == "__main__":
    unittest.main()
