from __future__ import annotations

import json
from contextlib import ExitStack
from http.client import HTTPConnection
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from liminal_gate import on_device_state, tester_setup, toolchain
from liminal_gate.bootstrap_server import (
    LOCAL_COMPENDIUM_ROUTE,
    LOCAL_EVENTS_ROUTE,
    LOCAL_STATE_ROUTE,
    BootstrapServer,
    BootstrapState,
    _is_loopback_peer,
    load_profile,
)


def _write_profile(path: Path) -> Path:
    path.write_text(json.dumps({
        "schema_version": 1,
        "routes": {
            "time": "/gd/get_current_time",
            "status": "/gd/get_server_status",
            "signup": "/gd/signup",
            "login": "/gd/login",
            "userdata": "/gd/userdata",
        },
        "response_signing": {
            "algorithm": "md5-uppercase-slice",
            "salt": "user-local-test-value",
            "digest_start": 16,
            "digest_end": 32,
        },
        "account_binding": {"signup_response_field": "id", "login_query_field": "uuid"},
        "responses": {
            "signup": {"success": True, "id": "local-account"},
            "login": {"success": True, "message": "local"},
            "status": {"success": True, "maintenance": False},
        },
        "userdata_seed": {"coins": 0, "progressCode": 1},
    }), encoding="utf-8")
    return path


class _StateRouteHarness(unittest.TestCase):
    """One server around the save-transfer route, loopback- or LAN-bound."""

    host = "127.0.0.1"

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        root = Path(self.temporary_directory.name)
        self.state_path = root / "state.json"
        self.server = BootstrapServer(
            (self.host, 0),
            load_profile(_write_profile(root / "profile.json")),
            BootstrapState(self.state_path),
            root / "events.jsonl",
        )
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.thread.join)
        self.addCleanup(self.server.shutdown)

    def request(self, method: str, path: str, body: bytes | None = None) -> tuple[int, dict[str, object]]:
        connection = HTTPConnection(*self.server.server_address[:2])
        connection.request(method, path, body, {"Content-Type": "application/json"} if body else {})
        response = connection.getresponse()
        payload = json.loads(response.read())
        connection.close()
        return response.status, payload

    def sign_up(self) -> None:
        self.request("GET", "/gd/signup?uuid=local-account&otk=bootstrap-token")


class LocalStateRouteTest(_StateRouteHarness):
    """The loopback save-transfer route the packaged Android build depends on."""

    def test_export_returns_exactly_what_the_save_holds(self) -> None:
        self.sign_up()
        status, document = self.request("GET", LOCAL_STATE_ROUTE)
        self.assertEqual(200, status)
        self.assertEqual(json.loads(self.state_path.read_text(encoding="utf-8")), document)
        self.assertEqual("local-account", document["active_account_id"])

    def test_export_reflects_memory_the_file_has_not_caught_up_with(self) -> None:
        """The running server holds the save; a file copy can lag behind it."""
        self.sign_up()
        self.server.state.accounts["local-account"]["userdata"]["coins"] = 4242
        status, document = self.request("GET", LOCAL_STATE_ROUTE)
        self.assertEqual(200, status)
        self.assertEqual(4242, document["accounts"]["local-account"]["userdata"]["coins"])

    def test_import_replaces_the_save_in_memory_and_on_disk(self) -> None:
        self.sign_up()
        replacement = json.loads(self.state_path.read_text(encoding="utf-8"))
        replacement["accounts"]["local-account"]["userdata"]["coins"] = 210
        status, result = self.request("POST", LOCAL_STATE_ROUTE, json.dumps(replacement).encode())
        self.assertEqual(200, status)
        self.assertEqual("imported", result["status"])
        self.assertEqual("local-account", result["active_account_id"])
        self.assertEqual(210, self.server.state.accounts["local-account"]["userdata"]["coins"])
        self.assertEqual(210, json.loads(self.state_path.read_text(encoding="utf-8"))["accounts"]["local-account"]["userdata"]["coins"])

    def test_import_keeps_the_replaced_save_beside_it(self) -> None:
        self.sign_up()
        original = json.loads(self.state_path.read_text(encoding="utf-8"))
        replacement = json.loads(json.dumps(original))
        replacement["accounts"]["local-account"]["userdata"]["coins"] = 210
        self.request("POST", LOCAL_STATE_ROUTE, json.dumps(replacement).encode())
        backup = self.state_path.with_name(f"{self.state_path.name}.bak.1")
        self.assertTrue(backup.is_file())
        self.assertEqual(original, json.loads(backup.read_text(encoding="utf-8")))

    def test_a_later_mutation_persists_the_imported_save_not_the_replaced_one(self) -> None:
        """The in-memory copy has to move with the file, or the import is undone."""
        self.sign_up()
        replacement = json.loads(self.state_path.read_text(encoding="utf-8"))
        replacement["accounts"]["imported-account"] = replacement["accounts"].pop("local-account")
        replacement["accounts"]["imported-account"]["userdata"]["coins"] = 99
        replacement["tokens"] = {}
        replacement["client_hosts"] = {}
        replacement["active_account_id"] = "imported-account"
        self.request("POST", LOCAL_STATE_ROUTE, json.dumps(replacement).encode())
        self.request("GET", "/gd/login?otk=later-token&uuid=imported-account")
        persisted = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual(["imported-account"], list(persisted["accounts"]))
        self.assertEqual(99, persisted["accounts"]["imported-account"]["userdata"]["coins"])

    def test_import_refuses_a_document_the_next_start_would_reject(self) -> None:
        self.sign_up()
        before = self.state_path.read_text(encoding="utf-8")
        status, result = self.request(
            "POST", LOCAL_STATE_ROUTE,
            json.dumps({"accounts": {"a": {}}, "tokens": {}}).encode(),
        )
        self.assertEqual(400, status)
        self.assertEqual("rejected_local_state", result["error"])
        self.assertIn("invalid account data", result["detail"])
        self.assertEqual(before, self.state_path.read_text(encoding="utf-8"))

    def test_import_refuses_a_body_that_is_not_json(self) -> None:
        status, result = self.request("POST", LOCAL_STATE_ROUTE, b"{not json")
        self.assertEqual(400, status)
        self.assertEqual("invalid_local_state_document", result["error"])


class LanBoundStateRouteTest(_StateRouteHarness):
    """A LAN-bound server still answers its own operator, and only its operator.

    The rule these routes carry is "this device, not the network". That used to
    be asked of the server's *bind* address, which answers it correctly only on
    the all-in-one package, where the listener is always loopback. A dedicated
    host has to bind `0.0.0.0` for a phone to reach the game at all, so the bind
    test refused the operator their own save, their own event log, and their own
    drop reference -- the three things these routes exist to hand them.

    The peer is what the rule was always about, so it is asked directly now. A
    LAN client is still refused, and refused whatever the server is bound to,
    which is a stronger guarantee than the bind test could make rather than a
    weaker one.

    Deliberately not a subclass of `LocalStateRouteTest`: the two now agree on
    the save's behaviour, but inheriting the whole suite would silently adopt
    future loopback-only cases instead of forcing a decision here.
    """

    host = "0.0.0.0"

    def request(self, method: str, path: str, body: bytes | None = None) -> tuple[int, dict[str, object]]:
        connection = HTTPConnection("127.0.0.1", self.server.server_address[1])
        connection.request(method, path, body, {"Content-Type": "application/json"} if body else {})
        response = connection.getresponse()
        payload = json.loads(response.read())
        connection.close()
        return response.status, payload

    def test_the_operators_own_console_reads_the_save(self) -> None:
        self.sign_up()
        status, document = self.request("GET", LOCAL_STATE_ROUTE)
        self.assertEqual(200, status)
        self.assertEqual(json.loads(self.state_path.read_text(encoding="utf-8")), document)

    def test_the_operators_own_console_writes_the_save(self) -> None:
        self.sign_up()
        replacement = json.loads(self.state_path.read_text(encoding="utf-8"))
        replacement["accounts"]["local-account"]["userdata"]["coins"] = 210
        status, result = self.request("POST", LOCAL_STATE_ROUTE, json.dumps(replacement).encode())
        self.assertEqual(200, status)
        self.assertEqual("imported", result["status"])
        self.assertEqual(210, self.server.state.accounts["local-account"]["userdata"]["coins"])

    def test_a_peer_from_the_network_is_refused_however_the_server_is_bound(self) -> None:
        """The decision itself, since binding a real LAN address here would not travel.

        `_serves_local_route` consults exactly this for every one of the three
        routes, so pinning it pins the refusal for all of them.
        """
        for peer in ("192.168.1.50", "10.0.2.2", "::ffff:192.168.1.50", "fe80::1", "8.8.8.8"):
            self.assertFalse(_is_loopback_peer(peer), peer)
        for peer in ("127.0.0.1", "127.0.0.53", "::1", "::ffff:127.0.0.1"):
            self.assertTrue(_is_loopback_peer(peer), peer)


class UpdateCommandTest(unittest.TestCase):
    """`update` protects the save it cannot restore automatically."""

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.uninstalls: list[tuple[str, ...]] = []

    def _args(self, *extra: str) -> object:
        return on_device_state.parse_args([
            "--adb", "adb", "--device", "serial", "--data-dir", str(self.root), "update", *extra,
        ])

    def _enter_common(self, stack: ExitStack) -> None:
        stack.enter_context(patch.object(tester_setup, "resolve_adb", return_value="adb"))
        stack.enter_context(patch.object(tester_setup, "select_device", return_value="serial"))
        stack.enter_context(patch.object(on_device_state, "validate_device"))
        stack.enter_context(patch.object(tester_setup, "package_installed", return_value=True))
        stack.enter_context(patch.object(on_device_state, "launch_apk"))
        stack.enter_context(patch.object(on_device_state, "prepare_on_device_apk", return_value=self.root / "built.apk"))
        stack.enter_context(patch.object(
            on_device_state, "export_state",
            side_effect=on_device_state.StateRouteUnavailable("no route"),
        ))

    def test_a_build_without_the_route_refuses_until_the_risk_is_accepted(self) -> None:
        """The first update onto an older build must still be reachable."""
        with ExitStack() as stack:
            self._enter_common(stack)
            install = stack.enter_context(patch.object(tester_setup, "install_apk"))
            with self.assertRaises(on_device_state.OnDeviceStateError) as raised:
                on_device_state.update(self._args())
        self.assertIn("--allow-missing-backup", str(raised.exception))
        install.assert_not_called()
        with ExitStack() as stack:
            self._enter_common(stack)
            stack.enter_context(patch.object(on_device_state, "wait_for_health", return_value="b" * 64))
            stack.enter_context(patch.object(
                on_device_state, "fetch_state", return_value={"accounts": {"a": {}}, "active_account_id": "a"},
            ))
            stack.enter_context(patch.object(tester_setup, "adb_forward"))
            install = stack.enter_context(patch.object(tester_setup, "install_apk"))
            self.assertEqual(0, on_device_state.update(self._args("--allow-missing-backup")))
        install.assert_called_once()

    def test_a_signature_mismatch_exports_first_and_never_uninstalls(self) -> None:
        document = {"accounts": {"a": {"userdata": {}}}, "tokens": {}, "active_account_id": "a"}
        mismatch = tester_setup.TesterSetupError("signatures do not match previously installed version")
        with (
            patch.object(tester_setup, "resolve_adb", return_value="adb"),
            patch.object(tester_setup, "select_device", return_value="serial"),
            patch.object(on_device_state, "validate_device"),
            patch.object(tester_setup, "package_installed", return_value=True),
            patch.object(on_device_state, "launch_apk"),
            patch.object(on_device_state, "prepare_on_device_apk", return_value=self.root / "built.apk"),
            patch.object(on_device_state, "wait_for_health", return_value="b" * 64),
            patch.object(on_device_state, "fetch_state", return_value=document),
            patch.object(tester_setup, "adb_forward"),
            patch.object(tester_setup, "install_apk", side_effect=mismatch) as install,
            patch.object(tester_setup, "force_stop") as stop,
        ):
            with self.assertRaises(on_device_state.OnDeviceStateError):
                on_device_state.update(self._args())
        self.assertFalse(install.call_args.kwargs["replace_existing"])
        stop.assert_not_called()
        exported = sorted((self.root / on_device_state.BACKUP_DIRECTORY).glob("*.json"))
        self.assertEqual(1, len(exported), "the save must be exported before the install is attempted")
        self.assertEqual(document, json.loads(exported[0].read_text(encoding="utf-8")))

    def test_an_update_that_loses_an_account_says_how_to_restore_it(self) -> None:
        before = {"accounts": {"a": {"userdata": {}}}, "tokens": {}, "active_account_id": "a"}
        after = {"accounts": {}, "tokens": {}, "active_account_id": None}
        with (
            patch.object(tester_setup, "resolve_adb", return_value="adb"),
            patch.object(tester_setup, "select_device", return_value="serial"),
            patch.object(on_device_state, "validate_device"),
            patch.object(tester_setup, "package_installed", return_value=True),
            patch.object(on_device_state, "launch_apk"),
            patch.object(on_device_state, "prepare_on_device_apk", return_value=self.root / "built.apk"),
            patch.object(on_device_state, "wait_for_health", return_value="b" * 64),
            patch.object(on_device_state, "fetch_state", side_effect=[before, after]),
            patch.object(tester_setup, "adb_forward"),
            patch.object(tester_setup, "install_apk"),
        ):
            with self.assertRaises(on_device_state.OnDeviceStateError) as raised:
                on_device_state.update(self._args())
        self.assertIn("missing account(s) a", str(raised.exception))
        self.assertIn("on_device_state import", str(raised.exception))

    def _update_over(self, before: dict, after: dict) -> None:
        with (
            patch.object(tester_setup, "resolve_adb", return_value="adb"),
            patch.object(tester_setup, "select_device", return_value="serial"),
            patch.object(on_device_state, "validate_device"),
            patch.object(tester_setup, "package_installed", return_value=True),
            patch.object(on_device_state, "launch_apk"),
            patch.object(on_device_state, "prepare_on_device_apk", return_value=self.root / "built.apk"),
            patch.object(on_device_state, "wait_for_health", return_value="b" * 64),
            patch.object(on_device_state, "fetch_state", side_effect=[before, after]),
            patch.object(tester_setup, "adb_forward"),
            patch.object(tester_setup, "install_apk"),
        ):
            self.assertEqual(0, on_device_state.update(self._args()))

    def test_an_update_that_keeps_the_account_but_wipes_its_progress_is_refused(self) -> None:
        # The account id surviving is not the save surviving. This exact shape
        # once printed "The save survived the update".
        before = {
            "accounts": {"a": {"userdata": {"progressCode": 999, "coins": 12345}}},
            "tokens": {}, "active_account_id": "a",
        }
        after = {
            "accounts": {"a": {"userdata": {"progressCode": 0, "coins": 0}}},
            "tokens": {}, "active_account_id": "a",
        }
        with self.assertRaises(on_device_state.OnDeviceStateError) as raised:
            self._update_over(before, after)
        message = str(raised.exception)
        self.assertIn("progressCode was 999, is now 0", message)
        self.assertIn("coins was 12345, is now 0", message)
        self.assertIn("on_device_state import", message)

    def test_an_update_that_only_moves_ephemeral_fields_is_accepted(self) -> None:
        # The stamina origin is rebased on load and whole numbers come back as
        # LitJson doubles; neither is lost progress.
        before = {
            "accounts": {"a": {"userdata": {
                "progressCode": 999, "coins": 12345, "refillStartTime": 1.0,
                "chrdata": [{"id": 9001, "jobLevels": [1, 0, 0]}],
            }}},
            "tokens": {}, "active_account_id": "a",
        }
        after = {
            "accounts": {"a": {"userdata": {
                "progressCode": 999, "coins": 12345, "refillStartTime": 987654.0,
                "chrdata": [{"id": 9001, "jobLevels": [1.0, 0.0, 0.0]}],
            }}},
            "tokens": {}, "active_account_id": "a",
        }
        self._update_over(before, after)


class ImportCommandTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.source = Path(self.temporary_directory.name) / "save.json"

    def _write(self, document: dict[str, object]) -> None:
        self.source.write_text(json.dumps(document), encoding="utf-8")

    def test_import_requires_confirmation(self) -> None:
        self._write({"accounts": {}, "tokens": {}})
        with self.assertRaises(on_device_state.OnDeviceStateError) as raised:
            on_device_state.import_state("adb", "serial", self.source, confirmed=False, force=False)
        self.assertIn("--yes", str(raised.exception))

    def test_import_refuses_a_file_missing_an_account_the_device_holds(self) -> None:
        self._write({"accounts": {"b": {"userdata": {}}}, "tokens": {}, "active_account_id": "b"})
        on_device = {"accounts": {"a": {"userdata": {}}, "b": {"userdata": {}}}, "tokens": {}, "active_account_id": "a"}
        with (
            patch.object(tester_setup, "adb_forward"),
            # Isolated from save validation: this is the account-loss gate.
            patch.object(on_device_state, "validate_document", return_value=[]),
            patch.object(on_device_state, "wait_for_health", return_value="b" * 64),
            patch.object(on_device_state, "fetch_state", return_value=on_device),
            patch.object(on_device_state, "push_state") as push,
        ):
            with self.assertRaises(on_device_state.OnDeviceStateError) as raised:
                on_device_state.import_state("adb", "serial", self.source, confirmed=True, force=False)
        self.assertIn("missing account(s) a", str(raised.exception))
        push.assert_not_called()


class ConnectionOptionPlacementTest(unittest.TestCase):
    """Issue 37: every documented command writes `--device` after the subcommand.

    That form was refused with `unrecognized arguments`, which reads as a broken
    checkout rather than as a word order, and it is the form the on-device setup
    and save documentation gives in every example.
    """

    def test_the_documented_form_names_the_device(self) -> None:
        for command in (["export"], ["update"], ["import", "save.json"]):
            with self.subTest(command=command[0]):
                args = on_device_state.parse_args([*command, "--device", "SERIAL"])
                self.assertEqual(command[0], args.command)
                self.assertEqual("SERIAL", args.device)

    def test_the_options_still_precede_the_subcommand(self) -> None:
        args = on_device_state.parse_args([
            "--adb", "/sdk/adb", "--device", "SERIAL", "--data-dir", "/tmp/dd", "export",
        ])
        self.assertEqual(("/sdk/adb", "SERIAL", Path("/tmp/dd")), (args.adb, args.device, args.data_dir))

    def test_an_option_given_only_before_the_subcommand_survives_it(self) -> None:
        """The subcommand's own copy must not overwrite it with its default."""
        args = on_device_state.parse_args(["--device", "SERIAL", "export", "--output", "out.json"])
        self.assertEqual("SERIAL", args.device)
        self.assertEqual("adb", args.adb)
        self.assertEqual(on_device_state.DEFAULT_DATA, args.data_dir)

    def test_the_later_placement_wins_when_both_are_given(self) -> None:
        args = on_device_state.parse_args(["--device", "FIRST", "export", "--device", "SECOND"])
        self.assertEqual("SECOND", args.device)

    def test_omitting_them_entirely_keeps_every_default(self) -> None:
        args = on_device_state.parse_args(["export"])
        self.assertEqual(("adb", None, on_device_state.DEFAULT_DATA), (args.adb, args.device, args.data_dir))


class RecordedToolchainTest(unittest.TestCase):
    """Every command here replays what `doctor` recorded, before any resolver.

    This command was the one launcher that did not, so an operator whose tools
    the doctor had installed privately -- the pinned NDK `llvm-objdump` above
    all, which is deliberately not on `PATH` -- got `update` failing on a
    missing disassembler while `doctor` and `on_device_setup` both passed on
    the same machine.  No flag could correct it: `update` accepts a path for
    the build tools and nothing for the rest.
    """

    def _main_replays(self, argv: list[str]) -> None:
        data = Path("/tmp/liminal-gate-data")
        with ExitStack() as stack:
            # Patched on the module itself rather than through the launcher's
            # name for it, so the test says "the record gets replayed" and not
            # merely "the launcher imports the module".
            replay = stack.enter_context(patch.object(toolchain, "load_and_apply"))
            # Every command's first resolver, made to fail: what is under test
            # is the ordering, so the run must not need a device or an SDK.
            stack.enter_context(patch.object(
                tester_setup, "resolve_adb",
                side_effect=tester_setup.TesterSetupError("stop here"),
            ))
            with self.assertRaises(SystemExit):
                on_device_state.main(["--data-dir", str(data), *argv])
        replay.assert_called_once_with(data)

    def test_every_command_replays_the_record_before_resolving_a_tool(self) -> None:
        for argv in (["export"], ["import", "save.json", "--yes"], ["update"]):
            with self.subTest(command=argv[0]):
                self._main_replays(argv)


if __name__ == "__main__":
    unittest.main()


class LocalEventsRouteTest(_StateRouteHarness):
    """The loopback event-log route, for the same reason the save has one.

    On the packaged Android build `events.jsonl` lives in app-private storage
    and the combined package is not debuggable, so `adb shell run-as` cannot
    reach it. A tester could report that a clear was refused but never which
    check refused it, which is the whole diagnosis.
    """

    def raw(self, path: str) -> tuple[int, str, str]:
        connection = HTTPConnection(*self.server.server_address[:2])
        connection.request("GET", path)
        response = connection.getresponse()
        body = response.read().decode("utf-8")
        content_type = response.headers.get("Content-Type", "")
        connection.close()
        return response.status, content_type, body

    def test_the_log_comes_back_line_delimited(self) -> None:
        self.sign_up()
        status, content_type, body = self.raw(LOCAL_EVENTS_ROUTE)
        self.assertEqual(200, status)
        self.assertEqual("application/x-ndjson", content_type)
        events = [json.loads(line) for line in body.splitlines() if line]
        self.assertTrue(events)
        self.assertEqual({"/gd/signup"}, {event["path"] for event in events})

    def test_a_refusal_names_its_check_in_the_log(self) -> None:
        """The reason this route exists: the log has to answer 'refused why'."""
        self.sign_up()
        self.request("GET", "/gd/get_server_status")
        status, _, body = self.raw(LOCAL_EVENTS_ROUTE)
        self.assertEqual(200, status)
        for line in body.splitlines():
            self.assertIn("status", json.loads(line))

    def test_a_server_started_without_a_log_says_so(self) -> None:
        self.server.events.path = None
        status, _, body = self.raw(LOCAL_EVENTS_ROUTE)
        self.assertEqual(404, status)
        self.assertEqual({"error": "no_local_event_log"}, json.loads(body))


class LocalCompendiumRouteTest(_StateRouteHarness):
    """The drop reference, served to the device that is running the server.

    This route exists for the all-in-one package specifically. There the server
    listens on `127.0.0.1:8002` on the phone itself, so the phone's own browser
    is a loopback client and can read the page with no cable, no workstation,
    and no second copy of the file. The same code on a LAN-bound dedicated
    server refuses it, which is the existing rule for the save and the event log
    rather than a new one.
    """

    def raw(self, path: str) -> tuple[int, str, str]:
        connection = HTTPConnection(*self.server.server_address[:2])
        connection.request("GET", path)
        response = connection.getresponse()
        body = response.read().decode("utf-8")
        content_type = response.headers.get("Content-Type", "")
        connection.close()
        return response.status, content_type, body

    def test_the_page_comes_back_as_html(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            page = Path(directory) / "drop-compendium.html"
            page.write_text("<!doctype html><title>Drop Compendium</title>", encoding="utf-8")
            self.server.drop_compendium = page
            status, content_type, body = self.raw(LOCAL_COMPENDIUM_ROUTE)
        self.assertEqual(200, status)
        self.assertEqual("text/html; charset=utf-8", content_type)
        self.assertIn("Drop Compendium", body)

    def test_a_server_launched_without_the_page_says_so(self) -> None:
        self.server.drop_compendium = None
        status, _, body = self.raw(LOCAL_COMPENDIUM_ROUTE)
        self.assertEqual(404, status)
        self.assertEqual({"error": "no_local_drop_compendium"}, json.loads(body))

    def test_a_build_that_should_carry_the_page_but_does_not_says_so(self) -> None:
        # Distinct from the case above only in cause, but that is the whole
        # value: this one means the build dropped a file it declared.
        self.server.drop_compendium = Path("/nonexistent/drop-compendium.html")
        status, _, body = self.raw(LOCAL_COMPENDIUM_ROUTE)
        self.assertEqual(404, status)
        self.assertEqual({"error": "no_local_drop_compendium"}, json.loads(body))
