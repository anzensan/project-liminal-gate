from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

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
