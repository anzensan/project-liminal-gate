"""What a mutation leaves behind when durable publication fails.

The dangerous case is not the failed request -- the client sees that one. It is
the *next* one: a mutation writes account state and its replay-cache entry
before publishing, so a failure used to leave both in memory, and an exact retry
was then answered from that cache with a success the save did not contain. The
change survived until the next restart and then vanished.
"""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import urlencode

from liminal_gate.bootstrap_server import BootstrapState
from tests.support import bootstrap_profile, request, start_server, stop_server


class PersistFailureTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.state_path = Path(self.temporary_directory.name) / "state.json"
        self.token, self.account_id = "persist-token", "persist-account"
        state = BootstrapState(self.state_path)
        state.create_account(self.token, self.account_id, {
            "coins": 0, "worldMapNo": 0, "progressCode": 16777346,
            "chrdata": [], "itemList": [], "summonList": [],
        })
        state.accounts[self.account_id]["username"] = "Player"
        state.accounts[self.account_id]["tutorial_phase"] = "free_roam"
        state._persist_locked()
        state.close()
        self.server, self.thread = start_server(
            ("127.0.0.1", 0), bootstrap_profile(), BootstrapState(self.state_path),
        )

    def tearDown(self) -> None:
        stop_server(self.server, self.thread)
        self.temporary_directory.cleanup()

    def rename(self, name: str, request_id: str) -> tuple[int, dict]:
        return request(
            self.server, "POST",
            f"/gd/change_uname?otk={self.token}&requestID={request_id}",
            urlencode({"name": name}).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    def persisted_username(self) -> str | None:
        document = json.loads(self.state_path.read_text(encoding="utf-8"))
        return document["accounts"][self.account_id].get("username")

    def fail_next_publication_of(self, name: str) -> dict[str, bool]:
        """Break exactly the publication that would durably record `name`.

        Only that one: token binding and the account seed publish through the
        same method, and failing those would test a different moment.
        """
        state_type = type(self.server.state)
        original, fired = state_type._publish_locked, {"done": False}

        def flaky(state: BootstrapState) -> None:
            account = state.accounts.get(self.account_id, {})
            if not fired["done"] and account.get("username") == name:
                fired["done"] = True
                raise OSError("simulated disk failure")
            return original(state)

        state_type._publish_locked = flaky
        self.addCleanup(setattr, state_type, "_publish_locked", original)
        return fired

    def test_a_failed_write_leaves_no_trace_in_memory(self) -> None:
        fired = self.fail_next_publication_of("Alice")
        with self.assertRaises(Exception):
            self.rename("Alice", "rename-1")
        self.assertTrue(fired["done"])
        # Memory and disk agree on the state that was actually published.
        self.assertEqual(
            "Player", self.server.state.accounts[self.account_id].get("username"),
        )
        self.assertEqual("Player", self.persisted_username())

    def test_an_exact_retry_after_a_failed_write_really_saves(self) -> None:
        # The regression: the retry used to be answered from the replay cache
        # with a success the disk never took.
        self.fail_next_publication_of("Alice")
        with self.assertRaises(Exception):
            self.rename("Alice", "rename-1")
        status, payload = self.rename("Alice", "rename-1")
        self.assertEqual((200, "Alice"), (status, payload["name"]))
        self.assertEqual("Alice", self.persisted_username())

    def test_the_rollback_survives_a_restart(self) -> None:
        self.fail_next_publication_of("Alice")
        with self.assertRaises(Exception):
            self.rename("Alice", "rename-1")
        stop_server(self.server, self.thread)
        self.server, self.thread = start_server(
            ("127.0.0.1", 0), bootstrap_profile(), BootstrapState(self.state_path),
        )
        self.assertEqual(
            "Player", self.server.state.accounts[self.account_id].get("username"),
        )
        # And the name is still claimable afterwards, under a fresh request id.
        status, payload = self.rename("Bob", "rename-2")
        self.assertEqual((200, "Bob"), (status, payload["name"]))
        self.assertEqual("Bob", self.persisted_username())

    def test_a_replay_cache_entry_is_not_left_answering_for_a_lost_write(self) -> None:
        self.fail_next_publication_of("Alice")
        with self.assertRaises(Exception):
            self.rename("Alice", "rename-1")
        requests = self.server.state.accounts[self.account_id].get("tutorial_requests", {})
        self.assertEqual(
            [], [key for key in requests if "rename-1" in str(key)],
        )


if __name__ == "__main__":
    unittest.main()
