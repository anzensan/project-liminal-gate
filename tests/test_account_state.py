from __future__ import annotations

from liminal_gate import account_state

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from liminal_gate.account_state import (
    REPLAY_CACHE_FIELDS,
    AccountStateError,
    adopt,
    apply_edited,
    candidates,
    restore,
    snapshot,
    summarize,
)
from liminal_gate.bootstrap_server import BootstrapState


OLD_DEVICE = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
NEW_DEVICE = "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB"


class AccountStateToolTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.state_path = Path(self.temporary_directory.name) / "bootstrap-state.json"
        state = BootstrapState(self.state_path)
        state.create_account("played-token", OLD_DEVICE, {"coins": 50000, "progressCode": 16777400, "chrdata": [{"id": index} for index in range(1, 41)]}, client_host="10.0.0.5")
        with state.lock:
            state.accounts[OLD_DEVICE]["tutorial_phase"] = "free_roam"
            state.accounts[OLD_DEVICE]["username"] = "Veteran"
            state._persist_locked()
        self.state = state

    def tearDown(self) -> None:
        self.state.close()
        self.temporary_directory.cleanup()

    def reinstall(self) -> None:
        """The client's app data is cleared, so it signs up with a new UUID."""
        self.state.create_account("reinstalled-token", NEW_DEVICE, {"coins": 0, "progressCode": 1, "chrdata": []}, client_host="10.0.0.5")

    def test_inspect_reports_the_save_and_every_retained_state(self) -> None:
        self.state.close()
        reports = [summarize(path) for path in candidates(self.state_path)]
        self.assertTrue(reports[0]["valid"])
        self.assertEqual([OLD_DEVICE], [item["accountId"] for item in reports[0]["accounts"]])
        self.assertEqual(50000, reports[0]["accounts"][0]["coins"])
        self.assertTrue(reports[0]["accounts"][0]["played"])
        self.assertTrue(any(item["exists"] for item in reports[1:]))
        self.assertTrue(all(not item["exists"] or item["valid"] for item in reports[1:]))

    def test_restore_replaces_the_save_and_preserves_the_current_one(self) -> None:
        with self.state.lock:
            self.state.accounts[OLD_DEVICE]["userdata"]["coins"] = 7
            self.state._persist_locked()
        self.state.close()
        backup = self.state_path.with_name(f"{self.state_path.name}.bak.1")
        result = restore(self.state_path, backup, confirmed=True)
        self.assertEqual("restored", result["status"])
        self.assertEqual(50000, json.loads(self.state_path.read_text())["accounts"][OLD_DEVICE]["userdata"]["coins"])
        self.assertEqual(7, json.loads(Path(result["preservedPrimary"]).read_text())["accounts"][OLD_DEVICE]["userdata"]["coins"])
        # The restored save is a save, not a fragment: the server can load it.
        reloaded = BootstrapState(self.state_path)
        self.assertEqual(50000, reloaded.accounts[OLD_DEVICE]["userdata"]["coins"])
        reloaded.close()

    def test_restore_and_adopt_refuse_a_save_a_server_still_holds(self) -> None:
        with self.assertRaises(AccountStateError) as refused:
            restore(self.state_path, self.state_path, confirmed=True)
        self.assertIn("stop the local server", str(refused.exception))
        with self.assertRaises(AccountStateError):
            adopt(self.state_path, OLD_DEVICE, NEW_DEVICE, confirmed=True, force=False)

    def test_restore_and_adopt_require_confirmation(self) -> None:
        self.state.close()
        with self.assertRaises(AccountStateError):
            restore(self.state_path, self.state_path, confirmed=False)
        with self.assertRaises(AccountStateError):
            adopt(self.state_path, OLD_DEVICE, NEW_DEVICE, confirmed=False, force=False)

    def test_adopt_returns_a_save_to_a_reinstalled_client(self) -> None:
        self.reinstall()
        self.state.close()
        result = adopt(self.state_path, OLD_DEVICE, NEW_DEVICE, confirmed=True, force=False)
        self.assertEqual("adopted", result["status"])
        self.assertIsNotNone(result["preservedPrimary"])

        reloaded = BootstrapState(self.state_path)
        self.addCleanup(reloaded.close)
        self.assertEqual([NEW_DEVICE], sorted(reloaded.accounts))
        # The reinstalled client logs in under the UUID it now sends.
        self.assertTrue(reloaded.bind_login_token("fresh-token", NEW_DEVICE, "10.0.0.5"))
        userdata = reloaded.userdata_for("fresh-token")
        assert userdata is not None
        self.assertEqual(50000, userdata["coins"])
        self.assertEqual(40, len(userdata["chrdata"]))
        self.assertEqual("Veteran", reloaded.accounts[NEW_DEVICE]["username"])
        # No binding may still name the account that no longer exists.
        self.assertEqual({NEW_DEVICE}, set(reloaded.tokens.values()))
        self.assertEqual({NEW_DEVICE}, set(reloaded.client_hosts.values()))
        self.assertEqual(NEW_DEVICE, reloaded.active_account_id)

    def test_adopt_will_not_quietly_discard_a_played_account(self) -> None:
        self.reinstall()
        with self.state.lock:
            self.state.accounts[NEW_DEVICE]["tutorial_phase"] = "free_roam"
            self.state._persist_locked()
        self.state.close()
        with self.assertRaises(AccountStateError) as refused:
            adopt(self.state_path, OLD_DEVICE, NEW_DEVICE, confirmed=True, force=False)
        self.assertIn("--force", str(refused.exception))
        self.assertEqual({OLD_DEVICE, NEW_DEVICE}, set(json.loads(self.state_path.read_text())["accounts"]))
        result = adopt(self.state_path, OLD_DEVICE, NEW_DEVICE, confirmed=True, force=True)
        self.assertEqual(NEW_DEVICE, result["discardedAccount"])
        self.assertEqual(50000, json.loads(self.state_path.read_text())["accounts"][NEW_DEVICE]["userdata"]["coins"])

    def test_adopt_rejects_an_unknown_source(self) -> None:
        self.state.close()
        with self.assertRaises(AccountStateError) as refused:
            adopt(self.state_path, "NOPE", NEW_DEVICE, confirmed=True, force=False)
        self.assertIn("no account NOPE", str(refused.exception))

    def test_snapshot_writes_a_loadable_copy_without_touching_the_save(self) -> None:
        self.state.close()
        original = self.state_path.read_bytes()
        result = snapshot(self.state_path, None)
        self.assertEqual("snapshot_created", result["status"])
        self.assertEqual(original, self.state_path.read_bytes())
        copied = BootstrapState(Path(result["path"]))
        self.assertEqual(50000, copied.accounts[OLD_DEVICE]["userdata"]["coins"])
        copied.close()

    def test_apply_can_clear_every_durable_mutation_replay_cache(self) -> None:
        with self.state.lock:
            account = self.state.accounts[OLD_DEVICE]
            for field in REPLAY_CACHE_FIELDS:
                account[field] = {
                    "old": {"body_sha256": "x", "payload": {"coins": 1}}
                }
            self.state._persist_locked()
        self.state.close()
        edited = self.state_path.with_name("edited.json")
        edited.write_bytes(self.state_path.read_bytes())

        result = apply_edited(
            self.state_path,
            edited,
            confirmed=True,
            force=True,
            clear_replay_cache=True,
        )

        self.assertTrue(result["clearedReplayCache"])
        document = json.loads(self.state_path.read_text(encoding="utf-8"))
        for field in REPLAY_CACHE_FIELDS:
            self.assertEqual({}, document["accounts"][OLD_DEVICE][field])


if __name__ == "__main__":
    unittest.main()


class SwitchTest(unittest.TestCase):
    """Choosing a save must be reversible; `adopt` is not.

    `adopt` moves a save onto another UUID and discards what was there, which
    is right for recovering from a reinstall and wrong for picking. `switch`
    exchanges the two accounts instead, so switching back is the same command.
    """

    def _state(self, directory: Path, active: str = "uuid-C") -> Path:
        def account(progress: int, name: str) -> dict:
            return {
                "username": name, "tutorial_phase": "free_roam",
                "tutorial_requests": {"a": {}},
                "userdata": {"progressCode": progress, "coins": 0, "chrdata": [{"id": 3}]},
            }
        path = directory / "bootstrap-state.json"
        path.write_text(json.dumps({
            "accounts": {"uuid-A": account(16777601, "Far"), "uuid-C": account(16777346, "Fresh")},
            "active_account_id": active,
            "tokens": {"tok": "uuid-C"}, "client_hosts": {"10.0.0.2": "uuid-C"},
        }), encoding="utf-8")
        return path

    @staticmethod
    def _active(path: Path) -> dict:
        document = json.loads(path.read_text(encoding="utf-8"))
        return document["accounts"][document["active_account_id"]]

    def test_the_chosen_save_becomes_the_one_the_client_sees(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = self._state(Path(directory))
            account_state.switch(state, "uuid-A", confirmed=True)
            self.assertEqual(16777601, self._active(state)["userdata"]["progressCode"])

    def test_the_displaced_save_survives(self) -> None:
        # The whole point: picking is not destroying.
        with tempfile.TemporaryDirectory() as directory:
            state = self._state(Path(directory))
            account_state.switch(state, "uuid-A", confirmed=True)
            document = json.loads(state.read_text(encoding="utf-8"))
            self.assertEqual(
                16777346, document["accounts"]["uuid-A"]["userdata"]["progressCode"]
            )
            self.assertEqual({"uuid-A", "uuid-C"}, set(document["accounts"]))

    def test_switching_twice_returns_to_the_start(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = self._state(Path(directory))
            before = state.read_text(encoding="utf-8")
            account_state.switch(state, "uuid-A", confirmed=True)
            account_state.switch(state, "uuid-A", confirmed=True)
            self.assertEqual(json.loads(before), json.loads(state.read_text(encoding="utf-8")))

    def test_tokens_and_hosts_are_untouched(self) -> None:
        # They name the UUID the client sends, which must keep resolving.
        with tempfile.TemporaryDirectory() as directory:
            state = self._state(Path(directory))
            account_state.switch(state, "uuid-A", confirmed=True)
            document = json.loads(state.read_text(encoding="utf-8"))
            self.assertEqual({"tok": "uuid-C"}, document["tokens"])
            self.assertEqual({"10.0.0.2": "uuid-C"}, document["client_hosts"])
            self.assertEqual("uuid-C", document["active_account_id"])

    def test_preserves_the_previous_file_first(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = self._state(Path(directory))
            result = account_state.switch(state, "uuid-A", confirmed=True)
            self.assertIsNotNone(result["preservedPrimary"])
            self.assertTrue(Path(result["preservedPrimary"]).is_file())

    def test_same_second_switches_create_distinct_immutable_safety_copies(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = self._state(Path(directory))
            original = state.read_bytes()
            with patch(
                "liminal_gate.account_state.timestamp",
                return_value="20260727T120000Z",
            ):
                first = account_state.switch(state, "uuid-A", confirmed=True)
                intermediate = state.read_bytes()
                second = account_state.switch(state, "uuid-A", confirmed=True)
            first_path = Path(first["preservedPrimary"])
            second_path = Path(second["preservedPrimary"])
            self.assertNotEqual(first_path, second_path)
            self.assertEqual(original, first_path.read_bytes())
            self.assertEqual(intermediate, second_path.read_bytes())

    def test_refuses_without_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = self._state(Path(directory))
            with self.assertRaisesRegex(account_state.AccountStateError, "requires --yes"):
                account_state.switch(state, "uuid-A", confirmed=False)

    def test_refuses_an_unknown_or_already_active_account(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = self._state(Path(directory))
            with self.assertRaisesRegex(account_state.AccountStateError, "no account"):
                account_state.switch(state, "missing", confirmed=True)
            with self.assertRaisesRegex(account_state.AccountStateError, "already the active"):
                account_state.switch(state, "uuid-C", confirmed=True)
