from __future__ import annotations

from liminal_gate import account_state

import json
import os
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
        # The signup address tells two otherwise-identical fresh signups apart.
        self.assertEqual(["10.0.0.5"], reports[0]["accounts"][0]["clientHosts"])
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

    def test_adopt_survives_a_platform_that_cannot_open_a_directory(self) -> None:
        """Windows refuses `os.open` on a directory, which is not our failure.

        Publishing a save fsyncs the directory the rename went through.  That
        handle does not exist on Windows, and taking the refusal as an error
        made every command that writes -- adopt, restore, link, switch, apply --
        die with a bare `Permission denied: 'user-data'` naming the save's own
        folder, which reads like a file the operator has to go fix.
        """
        real_open = os.open

        def windows_open(path, flags, *args, **kwargs):
            if Path(path).is_dir():
                raise PermissionError(13, "Permission denied", str(path))
            return real_open(path, flags, *args, **kwargs)

        self.reinstall()
        self.state.close()
        with patch("os.open", windows_open):
            result = adopt(self.state_path, OLD_DEVICE, NEW_DEVICE, confirmed=True, force=False)
        self.assertEqual("adopted", result["status"])
        # The backup preserved before the write is the operator's undo; it is
        # written through the same directory fsync and must survive too.
        self.assertEqual(50000, json.loads(Path(result["preservedPrimary"]).read_text())["accounts"][OLD_DEVICE]["userdata"]["coins"])
        reloaded = BootstrapState(self.state_path)
        self.addCleanup(reloaded.close)
        self.assertEqual([NEW_DEVICE], sorted(reloaded.accounts))
        self.assertEqual(50000, reloaded.accounts[NEW_DEVICE]["userdata"]["coins"])
        # The server writes through the same path and must also keep playing.
        with patch("os.open", windows_open), reloaded.lock:
            reloaded.accounts[NEW_DEVICE]["userdata"]["coins"] = 60000
            reloaded._persist_locked()
        self.assertEqual(60000, json.loads(self.state_path.read_text())["accounts"][NEW_DEVICE]["userdata"]["coins"])

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


class LinkTest(unittest.TestCase):
    """One save, two devices: `link` records the second UUID as an alias.

    The wire protocol has no account system — the silently stored device UUID
    is the only credential — so sharing a save across devices is operator
    bookkeeping, exactly like `adopt` but without moving the save.
    """

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.state_path = Path(self.temporary_directory.name) / "bootstrap-state.json"
        state = BootstrapState(self.state_path)
        state.create_account("phone-token", OLD_DEVICE, {"coins": 50000, "progressCode": 16777400, "chrdata": [{"id": 3}]}, client_host="10.0.0.5")
        with state.lock:
            state.accounts[OLD_DEVICE]["tutorial_phase"] = "free_roam"
            state._persist_locked()
        # The owner's tablet signed up on its own, into a fresh empty account.
        state.create_account("tablet-token", NEW_DEVICE, {"coins": 0, "progressCode": 1, "chrdata": []}, client_host="10.0.0.6")
        state.close()

    def test_link_gives_a_second_device_the_same_save(self) -> None:
        result = account_state.link(self.state_path, NEW_DEVICE, OLD_DEVICE, confirmed=True, force=False)
        self.assertEqual("linked", result["status"])
        self.assertEqual(NEW_DEVICE, result["discardedAccount"])
        self.assertIsNotNone(result["preservedPrimary"])
        by_id = {item["accountId"]: item for item in result["accounts"]}
        self.assertEqual([NEW_DEVICE], by_id[OLD_DEVICE]["linkedDevices"])

        reloaded = BootstrapState(self.state_path)
        self.addCleanup(reloaded.close)
        self.assertEqual([OLD_DEVICE], sorted(reloaded.accounts))
        # The tablet logs in under its own UUID and lands on the shared save.
        self.assertTrue(reloaded.bind_login_token("tablet-login", NEW_DEVICE, "10.0.0.6"))
        self.assertEqual(OLD_DEVICE, reloaded.tokens["tablet-login"])
        userdata = reloaded.userdata_for("tablet-login")
        assert userdata is not None
        self.assertEqual(50000, userdata["coins"])
        # A tablet reinstall signs up again with the linked UUID; the shared
        # save must win over a fresh empty account.
        reloaded.create_account("tablet-resignup", NEW_DEVICE, {"coins": 0})
        self.assertEqual([OLD_DEVICE], sorted(reloaded.accounts))
        self.assertEqual(OLD_DEVICE, reloaded.tokens["tablet-resignup"])

    def test_link_accepts_a_device_that_has_not_signed_up_yet(self) -> None:
        unseen = "DDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDD"
        result = account_state.link(self.state_path, unseen, OLD_DEVICE, confirmed=True, force=False)
        self.assertIsNone(result["discardedAccount"])
        reloaded = BootstrapState(self.state_path)
        self.addCleanup(reloaded.close)
        reloaded.create_account("first-signup", unseen, {"coins": 0}, client_host="10.0.0.7")
        self.assertEqual(OLD_DEVICE, reloaded.tokens["first-signup"])

    def test_link_will_not_quietly_discard_a_played_account(self) -> None:
        document = json.loads(self.state_path.read_text(encoding="utf-8"))
        document["accounts"][NEW_DEVICE]["tutorial_phase"] = "free_roam"
        self.state_path.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaisesRegex(AccountStateError, "--force"):
            account_state.link(self.state_path, NEW_DEVICE, OLD_DEVICE, confirmed=True, force=False)
        self.assertEqual({OLD_DEVICE, NEW_DEVICE}, set(json.loads(self.state_path.read_text())["accounts"]))
        result = account_state.link(self.state_path, NEW_DEVICE, OLD_DEVICE, confirmed=True, force=True)
        self.assertEqual(NEW_DEVICE, result["discardedAccount"])

    def test_link_requires_confirmation_and_a_known_target(self) -> None:
        with self.assertRaisesRegex(AccountStateError, "requires --yes"):
            account_state.link(self.state_path, NEW_DEVICE, OLD_DEVICE, confirmed=False, force=False)
        with self.assertRaisesRegex(AccountStateError, "no account NOPE"):
            account_state.link(self.state_path, NEW_DEVICE, "NOPE", confirmed=True, force=False)
        # Linking to a linked device points at the wrong layer; say which
        # account to use instead.
        account_state.link(self.state_path, NEW_DEVICE, OLD_DEVICE, confirmed=True, force=False)
        with self.assertRaisesRegex(AccountStateError, OLD_DEVICE):
            account_state.link(self.state_path, "EEEE", NEW_DEVICE, confirmed=True, force=False)

    def test_unlink_detaches_the_device(self) -> None:
        account_state.link(self.state_path, NEW_DEVICE, OLD_DEVICE, confirmed=True, force=False)
        with self.assertRaisesRegex(AccountStateError, "requires --yes"):
            account_state.unlink(self.state_path, NEW_DEVICE, confirmed=False)
        result = account_state.unlink(self.state_path, NEW_DEVICE, confirmed=True)
        self.assertEqual("unlinked", result["status"])
        self.assertEqual(OLD_DEVICE, result["account"])
        with self.assertRaisesRegex(AccountStateError, "not a linked device"):
            account_state.unlink(self.state_path, NEW_DEVICE, confirmed=True)
        reloaded = BootstrapState(self.state_path)
        self.addCleanup(reloaded.close)
        # The detached UUID is a stranger again: login is refused, and a fresh
        # signup starts its own account.
        self.assertIsNone(reloaded.bind_login_token("stray-login", NEW_DEVICE, "10.0.0.6"))
        reloaded.create_account("stray-signup", NEW_DEVICE, {"coins": 0})
        self.assertEqual({OLD_DEVICE, NEW_DEVICE}, set(reloaded.accounts))

    def test_adopt_repoints_linked_devices_with_the_moved_save(self) -> None:
        account_state.link(self.state_path, NEW_DEVICE, OLD_DEVICE, confirmed=True, force=False)
        # The owner's phone is reinstalled and now sends a third UUID.
        reinstalled = "CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC"
        adopt(self.state_path, OLD_DEVICE, reinstalled, confirmed=True, force=False)
        document = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual({NEW_DEVICE: reinstalled}, document["account_aliases"])
        # The invariant the server refuses to load without: a UUID never names
        # both an account and a link.
        reloaded = BootstrapState(self.state_path)
        self.addCleanup(reloaded.close)
        self.assertTrue(reloaded.bind_login_token("tablet-login", NEW_DEVICE, "10.0.0.6"))
        self.assertEqual(reinstalled, reloaded.tokens["tablet-login"])


if __name__ == "__main__":
    unittest.main()


class WalletProjectionInvariantTest(unittest.TestCase):
    """`valuables` must equal the flat wallet in every save this server writes.

    The nested block is a projection the client reads; the flat fields beside
    it are what the server spends and grants. Keeping them in step used to be a
    per-site chore and most sites skipped it, so a tester's exported save failed
    `account_state validate` after a ten-draw: `valuables.freeEnergy` read 72
    against `freeEnergy` 22, the difference being the fifty the draw spent.
    """

    def _seed(self) -> dict[str, object]:
        return {
            "coins": 30_000, "energy": 0, "freeEnergy": 72,
            "energyAppStore": 0, "energyGooglePlay": 0, "energyAndApp": 0,
            "itemList": [0] * 181, "chrdata": [], "summonList": [0] * 16,
            "buddyInfo": {"list": [], "record": []},
        }

    def test_a_ten_draw_paid_with_energy_leaves_the_projection_in_step(self) -> None:
        from liminal_gate.bootstrap_server import BootstrapState
        from liminal_gate.pact_draw_catalog import build_bundled_pact_policy
        from tests.support import bootstrap_profile, post, start_server, stop_server

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            server, thread = start_server(
                ("127.0.0.1", 0), bootstrap_profile(), BootstrapState(root / "state.json"),
                pact_draw_catalog=build_bundled_pact_policy(),
            )
            try:
                server.state.create_account("token", "account", self._seed())
                status, payload = post(
                    server, "/gd/do_slot", "ten-pull",
                    "kind=1&count=10&luckType=false&campaignChrID=0&eventFlag=0&lastUpdate=1",
                )
                self.assertEqual((200, True), (status, payload["success"]))
                userdata = server.state.accounts["account"]["userdata"]
                # The draw really did spend it, and the projection followed.
                self.assertEqual(22, userdata["freeEnergy"])
                self.assertEqual(userdata["freeEnergy"], userdata["valuables"]["freeEnergy"])
                for name in ("coins", "energy", "energyAppStore", "energyGooglePlay", "energyAndApp"):
                    self.assertEqual(userdata[name], userdata["valuables"][name], name)
            finally:
                stop_server(server, thread)

    def test_a_save_that_already_drifted_is_repaired_when_it_loads(self) -> None:
        from liminal_gate.bootstrap_server import BootstrapState

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "drifted.json"
            userdata = self._seed()
            userdata["freeEnergy"] = 22
            userdata["valuables"] = {
                "coins": 30_000, "energy": 0, "freeEnergy": 72,
                "energyAppStore": 0, "energyGooglePlay": 0, "energyAndApp": 0,
            }
            path.write_text(json.dumps({
                "accounts": {"a": {"userdata": userdata, "tutorial_phase": "free_roam"}},
                "tokens": {}, "active_account_id": "a",
            }), encoding="utf-8")

            state = BootstrapState(path)
            try:
                # The flat value is the truth: the player really was charged.
                repaired = state.accounts["a"]["userdata"]
                self.assertEqual(22, repaired["freeEnergy"])
                self.assertEqual(22, repaired["valuables"]["freeEnergy"])
            finally:
                state.close()

    def test_an_inbox_present_keeps_the_projection_in_step(self) -> None:
        from liminal_gate.bootstrap_server import BootstrapState
        from liminal_gate.message_catalog import load_message_catalog
        from tests.support import bootstrap_profile, get, post, start_server, stop_server
        from urllib.parse import urlencode

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog_path = root / "messages.toml"
            catalog_path.write_text(
                'schema_version = 1\nprovenance = "user-supplied"\nitem_slots = 181\n'
                'max_free_energy = 999\nmax_coins = 99999\nmax_stack = 99\n\n'
                '[[messages]]\nid = "m1"\ndate = 7.0\ndays_last = 3\n'
                'messages = { default = "d", ja = "j", en = "e" }\n'
                'coins = 500\nfree_energy = 3\nitems = {}\n',
                encoding="utf-8",
            )
            catalog = load_message_catalog(catalog_path)
            server, thread = start_server(
                ("127.0.0.1", 0), bootstrap_profile(), BootstrapState(root / "state.json"),
                message_catalog=catalog,
            )
            try:
                server.state.create_account("token", "account", self._seed(), catalog)
                get(server, "/gd/login?otk=token&uuid=account")
                status, _ = post(
                    server, "/gd/read_messages", "r1",
                    urlencode({"idlist": json.dumps(["m1"]), "lastUpdate": "1"}),
                )
                self.assertEqual(200, status)
                userdata = server.state.accounts["account"]["userdata"]
                self.assertEqual(30_500, userdata["coins"])
                self.assertEqual(userdata["coins"], userdata["valuables"]["coins"])
                self.assertEqual(userdata["freeEnergy"], userdata["valuables"]["freeEnergy"])
            finally:
                stop_server(server, thread)
