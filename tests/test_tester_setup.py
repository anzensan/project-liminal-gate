from __future__ import annotations

from unittest import mock

import contextlib
import io
import json
from liminal_gate import tester_setup

import subprocess
import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from liminal_gate.tester_setup import DEFAULT_EVENT_CATALOG, EMULATOR_LOOPBACK_HOST, MINIMUM_KEY_PASSWORD_LENGTH, REQUIRED_RESOURCE_CATEGORIES, TesterSetupError, build_server_origin, check_device_host_suits_device, choose_local_server_options, derive_archive_event_catalog, ensure_keystore, find_build_tools, find_keytools, install_apk, prepare_local_tester, prompt_key_password, resolve_adb, resolve_resource_root, run_server, select_device, server_arguments, write_password_file


class GuidedServerPolicyTest(unittest.TestCase):
    """The guided path must actually be able to reach each bundled policy."""

    def arguments(self, **options) -> list[str]:
        return server_arguments(Path("resources"), Path("data"), 8696, **options)

    def test_recommended_mode_enables_current_solo_policies(self) -> None:
        arguments = self.arguments()
        for flag in ("--core-story", "--pacts", "--hunting", "--jobs", "--rebirth", "--status-items", "--companion-draw", "--companion-sale",
                     "--companion-strengthen", "--companion-evolution", "--trading-post", "--drop-eligibility", "--achievements"):
            self.assertIn(flag, arguments)
        self.assertEqual(
            str((Path("data") / "companion-equipment.json").resolve()),
            arguments[arguments.index("--companion-equipment-catalog") + 1],
        )
        self.assertNotIn("--summon-skills", arguments)

    def choose(self):
        """The standard setup has no feature-selection prompt."""
        return choose_local_server_options(
            None, ask=lambda _: self.fail("standard setup must not ask an advanced question"),
        )

    def test_setup_enables_every_built_in_policy(self) -> None:
        # The mode prompt was removed: it only ever subtracted content from a
        # preservation build, and isolating a feature is a bootstrap_server
        # job, not a setup question.
        options = self.choose()
        self.assertEqual(
            (True,) * 11,
            (options.core_story, options.pacts, options.hunting, options.jobs,
             options.rebirth, options.status_items, options.companion_draw, options.companion_sale,
             options.companion_strengthen, options.companion_evolution, options.trading_post),
        )
        for flag in ("--core-story", "--pacts", "--hunting", "--jobs", "--rebirth",
                     "--status-items", "--companion-draw", "--companion-sale",
                     "--companion-strengthen", "--companion-evolution", "--trading-post", "--drop-eligibility", "--achievements"):
            self.assertIn(flag, self.arguments())
        self.assertNotIn("--summon-skills", self.arguments())


class TesterSetupTest(unittest.TestCase):

    def test_guided_archive_catalog_is_derived_and_validated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            characters = root / "character-catalog.json"
            characters.write_text(
                json.dumps({"characters": [{"character_id": 148}]}),
                encoding="utf-8",
            )
            battledata = {
                "chapters": [{
                    "chapterNo": 2000,
                    "sections": [{
                        "rawStamina": 10,
                        "coins": 0,
                        "battleCnt": 5,
                    }],
                }],
            }
            output = root / DEFAULT_EVENT_CATALOG
            document, notes = derive_archive_event_catalog(
                battledata, "a" * 64, characters, output,
            )
            self.assertTrue(output.is_file())
            self.assertEqual([], [
                note for note in notes if note.startswith("bahamut_descent:")
            ])
            self.assertEqual(
                {
                    "event_id": "bahamut_descent",
                    "flag": "sp_ch_2000",
                    "chapter": 2000,
                    "section": 1,
                    "stamina": 10,
                    "coins": 0,
                    "clear_coins": 0,
                    "unlock_after_chapter": 2,
                    "selector_id": "2000",
                    "character_ids": [148],
                },
                document["stages"][0],
            )

    def test_required_dummy_dll_directory_derives_local_character_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); apk = root / "game.apk"; resources = root / "resources"; data = root / "user-data"; dummy = root / "DummyDll"
            apk.write_bytes(b"apk"); dummy.mkdir()
            (dummy / "Assembly-CSharp.dll").write_bytes(b"")
            (dummy.parent / "dump.cs").write_text("", encoding="utf-8")
            for category in REQUIRED_RESOURCE_CATEGORIES:
                (resources / category).mkdir(parents=True, exist_ok=True)
            with patch("liminal_gate.tester_setup.build_import_manifest", return_value={}), patch("liminal_gate.tester_setup.write_import_manifest"), patch("liminal_gate.tester_setup.load_master_trees", return_value={
                "ChrDatabase": {
                    "infos": [{"ID": 3, "chrType": 1, "isLambda": 0, "rebirthFromID": 0, "rarity": 4, "ancestorChrID": 0, "Jobs": [30]}],
                    "data": [{"ID": 30, "Species": 1}],
                },
                "ItemSet": {"itemSet": []},
                "BuddyDatabase": {"data": [{"ID": 1, "exclusiveChrID": 0, "exclusiveSpeciesID": 0}]},
            }), patch("liminal_gate.tester_setup.write_local_names"), patch("liminal_gate.tester_setup.derive_story_outcome_catalog", return_value=data / "story-outcomes.json"), patch("liminal_gate.tester_setup.build_resource_manifest", return_value={}), patch("liminal_gate.tester_setup.write_resource_manifest"), patch("liminal_gate.tester_setup.prepare_pact_banners"), patch("liminal_gate.tester_setup.generate_legacy_client_plan", return_value={"patches": []}), patch("liminal_gate.tester_setup.load_patch_plan", return_value={}), patch("liminal_gate.tester_setup.apply_patch_plan"), patch("liminal_gate.tester_setup.ensure_keystore"), patch("liminal_gate.tester_setup.check_derivation_prerequisites"), patch("liminal_gate.tester_setup.find_build_tools", return_value=(root / "zipalign", root / "apksigner")), patch("liminal_gate.tester_setup.sign_apk"):
                prepare_local_tester(apk, resources, data, 8696, None, dummy)
            self.assertTrue((data / "character-catalog.json").is_file())
            self.assertTrue((data / "companion-equipment.json").is_file())
    def test_requires_explicit_choice_when_multiple_devices_are_ready(self) -> None:
        with patch("liminal_gate.tester_setup._adb_devices", return_value=("emulator-5554", "emulator-5570")):
            with self.assertRaisesRegex(TesterSetupError, "--device"):
                select_device("adb", None)
            self.assertEqual("emulator-5570", select_device("adb", "emulator-5570"))

    def test_selects_a_physical_device_serial(self) -> None:
        with patch("liminal_gate.tester_setup._adb_devices", return_value=("R52T80ABCDE",)):
            self.assertEqual("R52T80ABCDE", select_device("adb", None))
            self.assertEqual("R52T80ABCDE", select_device("adb", "R52T80ABCDE"))

    def test_device_host_defaults_to_the_emulator_loopback_alias(self) -> None:
        self.assertEqual("http://10.0.2.2:8696", build_server_origin(EMULATOR_LOOPBACK_HOST, 8696))

    def test_device_host_accepts_any_lan_address_with_a_four_digit_port(self) -> None:
        # The longest IPv4 address with the longest permitted port is the exact
        # worst case the guarded routing literals can still express.
        self.assertEqual("http://192.168.100.100:8696", build_server_origin("192.168.100.100", 8696))

    def test_device_host_rejects_an_origin_the_routing_literals_cannot_hold(self) -> None:
        with self.assertRaisesRegex(TesterSetupError, "at most 27"):
            build_server_origin("192.168.100.100", 18696)
        with self.assertRaisesRegex(TesterSetupError, "at most 27"):
            build_server_origin("liminal-gate.local", 8696)

    def test_device_host_rejects_a_url_instead_of_a_host(self) -> None:
        with self.assertRaisesRegex(TesterSetupError, "not a URL"):
            build_server_origin("http://192.168.1.10", 8696)

    def test_device_host_rejects_an_embedded_port_or_bare_ipv6(self) -> None:
        for value in ("192.168.1.10:8696", "::1"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(TesterSetupError, "must not contain a port"):
                    build_server_origin(value, 8696)

    def test_device_host_rejects_an_address_meaning_the_client_itself(self) -> None:
        # These would build a client that talks to the phone or emulator rather
        # than to the machine running the server.
        for value in ("localhost", "127.0.0.1", "0.0.0.0"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(TesterSetupError, "client's own device"):
                    build_server_origin(value, 8696)

    def test_signature_conflict_explains_the_fix_without_uninstalling(self) -> None:
        conflict = subprocess.CompletedProcess(
            (), 1, stdout="", stderr="Failure [INSTALL_FAILED_UPDATE_INCOMPATIBLE: signatures do not match]",
        )
        with patch("liminal_gate.tester_setup.subprocess.run", return_value=conflict) as run:
            with self.assertRaisesRegex(TesterSetupError, "--replace-existing"):
                install_apk("adb", "emulator-5556", Path("built.apk"))
            self.assertEqual(1, run.call_count, "must not uninstall without being asked")

    def test_replace_existing_uninstalls_then_installs(self) -> None:
        conflict = subprocess.CompletedProcess(
            (), 1, stdout="", stderr="Failure [INSTALL_FAILED_UPDATE_INCOMPATIBLE: signatures do not match]",
        )
        with patch("liminal_gate.tester_setup.subprocess.run", side_effect=[conflict, None, None]) as run:
            install_apk("adb", "emulator-5556", Path("built.apk"), replace_existing=True)
        self.assertIn("uninstall", run.call_args_list[1].args[0])

    def test_large_apk_install_can_disable_adb_incremental_mode(self) -> None:
        success = subprocess.CompletedProcess((), 0, stdout="Success", stderr="")
        with patch("liminal_gate.tester_setup.subprocess.run", return_value=success) as run:
            install_apk(
                "adb", "emulator-5556", Path("built.apk"),
                no_incremental=True,
            )
        self.assertIn("--no-incremental", run.call_args.args[0])

    def test_other_install_failures_are_reported_verbatim(self) -> None:
        failure = subprocess.CompletedProcess((), 1, stdout="", stderr="Failure [INSTALL_FAILED_NO_MATCHING_ABIS]")
        with patch("liminal_gate.tester_setup.subprocess.run", return_value=failure):
            with self.assertRaisesRegex(TesterSetupError, "NO_MATCHING_ABIS"):
                install_apk("adb", "emulator-5556", Path("built.apk"))

    def test_physical_device_refuses_the_emulator_only_address(self) -> None:
        check_device_host_suits_device("emulator-5570", EMULATOR_LOOPBACK_HOST)
        check_device_host_suits_device("R52T80ABCDE", "192.168.1.10")
        with self.assertRaisesRegex(TesterSetupError, "does not look like an emulator"):
            check_device_host_suits_device("R52T80ABCDE", EMULATOR_LOOPBACK_HOST)

    def test_detects_android_resource_root_below_common_parent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "gdresources" / "data_u2017" / "android"
            for category in REQUIRED_RESOURCE_CATEGORIES:
                (root / category).mkdir(parents=True)
            self.assertEqual(root.resolve(), resolve_resource_root(root.parents[2]))
            with self.assertRaisesRegex(TesterSetupError, "data_u2017/android"):
                resolve_resource_root(root.parent / "datau2017")

    def test_finds_supplied_build_tools_and_writes_private_password_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tools = root / "build-tools"
            tools.mkdir()
            for name in ("zipalign", "apksigner"):
                (tools / name).write_text("local", encoding="utf-8")
            self.assertEqual((tools / "zipalign", tools / "apksigner"), find_build_tools(tools))
            password = root / "user-data" / "password.txt"
            write_password_file(password, "local-secret")
            self.assertEqual("local-secret", password.read_text(encoding="utf-8"))
            self.assertEqual(0o600, password.stat().st_mode & 0o777)

    def test_finds_standard_windows_build_tools_with_windows_executable_names(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            local_app_data = Path(temporary)
            tools = local_app_data / "Android/Sdk/build-tools/36.0.0"
            tools.mkdir(parents=True)
            for name in ("zipalign.exe", "apksigner.bat"):
                (tools / name).write_text("local", encoding="utf-8")
            with patch.dict("liminal_gate.tester_setup.os.environ", {"LOCALAPPDATA": str(local_app_data)}, clear=True):
                self.assertEqual((tools / "zipalign.exe", tools / "apksigner.bat"), find_build_tools(None))

    def test_server_arguments_keep_resource_and_state_files_local(self) -> None:
        arguments = server_arguments(Path("local-input/resources/data_u2017/android"), Path("user-data"), 8696)
        self.assertIn("8696", arguments)
        self.assertIn("user-data/bootstrap-state.json", arguments)
        self.assertIn("user-data/resources.json", arguments)
        self.assertIn("user-data/public_data", arguments)
        self.assertIn("0.0.0.0", arguments)
        self.assertEqual(
            str((Path("user-data") / "story-outcomes.json").resolve()),
            arguments[arguments.index("--story-outcome-catalog") + 1],
        )
        self.assertEqual(
            str((Path("user-data") / DEFAULT_EVENT_CATALOG).resolve()),
            arguments[arguments.index("--event-catalog") + 1],
        )
        self.assertEqual(
            str((Path("user-data") / "character-catalog.json").resolve()),
            arguments[arguments.index("--character-catalog") + 1],
        )

    def test_event_catalog_is_started_with_the_matching_local_character_catalog(self) -> None:
        data = Path("user-data")
        event_catalog = Path("local-config/events.json")
        arguments = server_arguments(Path("local-input/resources/data_u2017/android"), data, 8696, event_catalog)
        self.assertEqual(
            ["--event-catalog", str(event_catalog.resolve()), "--character-catalog", str((data / "character-catalog.json").resolve())],
            arguments[-4:],
        )

    def test_event_catalog_requires_dummy_dll_for_matching_character_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); apk = root / "game.apk"; resources = root / "resources"
            apk.write_bytes(b"apk")
            for category in REQUIRED_RESOURCE_CATEGORIES:
                (resources / category).mkdir(parents=True, exist_ok=True)
            with self.assertRaisesRegex(TesterSetupError, "--dummy-dll-dir"):
                prepare_local_tester(apk, resources, root / "user-data", 8696, None, event_catalog=root / "events.json")

    def test_standard_setup_does_not_ask_about_advanced_events(self) -> None:
        options = choose_local_server_options(
            None, lambda _: self.fail("the standard path must not prompt"),
        )
        self.assertIsNone(options.event_catalog)

    def test_an_explicit_event_catalog_is_enabled_without_a_prompt(self) -> None:
        options = choose_local_server_options(
            Path("local/events.json"),
            lambda _: self.fail("an explicit option must not be confirmed again"),
        )
        self.assertEqual(Path("local/events.json"), options.event_catalog)

    def test_runs_server_with_argument_sequence(self) -> None:
        arguments = ["python", "-m", "liminal_gate.bootstrap_server", "--resource-root", r"C:\\Local Files\\android"]
        with patch("liminal_gate.tester_setup.subprocess.run") as run:
            run_server(arguments)
        run.assert_called_once_with(arguments, check=True)


class ProgressReportingTest(unittest.TestCase):
    """Long phases must show they are alive without spoiling a redirected log.

    Hashing a multi-gigabyte tree and running a disassembler thousands of times
    both used to print one line and then go silent for minutes, which reads as a
    hang; a tester who interrupts it pays for the whole phase again.
    """

    class _Terminal(io.StringIO):
        def isatty(self) -> bool:
            return True

    def test_a_terminal_sees_the_counter_move(self) -> None:
        stream = self._Terminal()
        line = tester_setup.ProgressLine("hashing", total=2, stream=stream)
        line.update(1, "1.0 GiB")
        line.update(2, "2.0 GiB")
        written = stream.getvalue()
        self.assertIn("2/2", written)
        self.assertIn("2.0 GiB", written)
        self.assertIn("\r", written, "the line is repainted rather than scrolled")

    def test_a_redirected_log_gets_the_summary_and_nothing_else(self) -> None:
        stream = io.StringIO()
        line = tester_setup.ProgressLine("hashing", total=2, stream=stream)
        line.update(1, "1.0 GiB")
        line.update(2, "2.0 GiB")
        self.assertEqual("", stream.getvalue())
        line.done("2 files")
        self.assertEqual("  hashing: 2 files\n", stream.getvalue())

    def test_intermediate_updates_are_throttled_but_the_last_always_lands(self) -> None:
        stream = self._Terminal()
        line = tester_setup.ProgressLine("hashing", total=3, stream=stream)
        for done in (1, 2, 3):
            line.update(done)
        painted = stream.getvalue()
        self.assertIn("3/3", painted, "reaching the total is never throttled away")
        self.assertNotIn("2/3", painted, "intermediate repaints are rate limited")

    def test_a_total_learned_while_running_is_adopted(self) -> None:
        stream = self._Terminal()
        line = tester_setup.ProgressLine("generators", stream=stream)
        line.advance(4, 4)
        self.assertIn("4/4", stream.getvalue())

    def test_byte_counts_read_the_way_an_operator_says_them(self) -> None:
        self.assertEqual("512 B", tester_setup._format_bytes(512))
        self.assertEqual("1.0 KiB", tester_setup._format_bytes(1024))
        self.assertEqual("4.5 GiB", tester_setup._format_bytes(int(4.5 * 1024 ** 3)))


class HeartbeatTest(unittest.TestCase):
    """Il2CppDumper captures all its own output and can run for minutes."""

    def test_output_and_status_survive_the_heartbeat_wrapper(self) -> None:
        completed = tester_setup.run_with_heartbeat(
            (sys.executable, "-c", "import sys; print('out'); print('err', file=sys.stderr); sys.exit(3)"),
            "stub", timeout=60,
        )
        self.assertEqual(3, completed.returncode)
        self.assertIn("out", completed.stdout)
        self.assertIn("err", completed.stderr)

    def test_a_child_that_overruns_its_budget_is_killed(self) -> None:
        with patch.object(tester_setup, "PROGRESS_INTERVAL_SECONDS", 0.05):
            with self.assertRaises(subprocess.TimeoutExpired):
                tester_setup.run_with_heartbeat(
                    (sys.executable, "-c", "import time; time.sleep(30)"), "stub", timeout=0.1,
                )


class LocalSigningToolTest(unittest.TestCase):
    """keytool and adb must be found where Android Studio actually puts them.

    A tester whose only Java is the runtime bundled with Android Studio has
    keytool on no `PATH` entry the SDK instructions add, and copying the
    executables into the project directory should never be the fix.
    """

    def test_reprompts_a_password_keytool_would_reject_for_length(self) -> None:
        short = "x" * (MINIMUM_KEY_PASSWORD_LENGTH - 1)
        long = "x" * MINIMUM_KEY_PASSWORD_LENGTH
        answers = iter((short, long, long))
        self.assertEqual(long, prompt_key_password(confirm=True, ask=lambda _: next(answers)))

    def test_states_the_length_requirement_in_the_prompt_itself(self) -> None:
        prompts: list[str] = []
        prompt_key_password(confirm=False, ask=lambda prompt: prompts.append(prompt) or "longenough")
        self.assertIn(str(MINIMUM_KEY_PASSWORD_LENGTH), prompts[0])

    def test_reprompts_when_the_confirmation_does_not_match(self) -> None:
        answers = iter(("chosen1", "mistyped", "chosen1", "chosen1"))
        self.assertEqual("chosen1", prompt_key_password(confirm=True, ask=lambda _: next(answers)))

    def test_a_non_interactive_prompt_explains_itself_instead_of_looping(self) -> None:
        def refuse(_: str) -> str:
            raise EOFError

        with self.assertRaisesRegex(TesterSetupError, "interactive terminal"):
            prompt_key_password(confirm=True, ask=refuse)

    def test_finds_the_java_home_keytool_when_it_is_not_on_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            java_home = Path(temporary) / "jdk"
            (java_home / "bin").mkdir(parents=True)
            (java_home / "bin/keytool.exe").write_text("local", encoding="utf-8")
            with patch("liminal_gate.tester_setup.shutil.which", return_value=None), \
                 patch.dict("liminal_gate.tester_setup.os.environ", {"JAVA_HOME": str(java_home)}, clear=True):
                # Best first; a real Android Studio on this machine may follow.
                self.assertEqual(java_home / "bin/keytool.exe", find_keytools()[0])

    def test_finds_the_keytool_bundled_with_windows_android_studio(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            local_app_data = Path(temporary)
            bundled = local_app_data / "Programs/Android Studio/jbr/bin"
            bundled.mkdir(parents=True)
            (bundled / "keytool.exe").write_text("local", encoding="utf-8")
            with patch("liminal_gate.tester_setup.shutil.which", return_value=None), \
                 patch.dict("liminal_gate.tester_setup.os.environ", {"LOCALAPPDATA": str(local_app_data)}, clear=True):
                self.assertEqual(bundled / "keytool.exe", find_keytools()[0])

    def test_a_missing_keytool_names_the_jdk_rather_than_the_sdk(self) -> None:
        # The bundled locations are emptied rather than merely unset: this
        # machine may genuinely have an Android Studio runtime installed.
        with patch("liminal_gate.tester_setup.shutil.which", return_value=None), \
             patch("liminal_gate.tester_setup._bundled_java_bin_directories", return_value=()), \
             patch.dict("liminal_gate.tester_setup.os.environ", {}, clear=True):
            with self.assertRaisesRegex(TesterSetupError, "JDK"):
                find_keytools()

    def test_falls_back_to_the_sdk_platform_tools_adb(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            sdk_root = Path(temporary) / "Sdk"
            (sdk_root / "platform-tools").mkdir(parents=True)
            (sdk_root / "platform-tools/adb.exe").write_text("local", encoding="utf-8")
            with patch("liminal_gate.tester_setup.shutil.which", return_value=None), \
                 patch.dict("liminal_gate.tester_setup.os.environ", {"ANDROID_SDK_ROOT": str(sdk_root)}, clear=True):
                self.assertEqual(str(sdk_root / "platform-tools/adb.exe"), resolve_adb("adb"))

    def test_an_explicit_adb_path_is_never_silently_substituted(self) -> None:
        with patch("liminal_gate.tester_setup.shutil.which", return_value=None):
            with self.assertRaisesRegex(TesterSetupError, "requested path"):
                resolve_adb("/nowhere/adb")

    def test_a_keystore_failure_reports_what_keytool_said(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary)
            failure = subprocess.CalledProcessError(1, ("keytool",), stderr="keytool error: password too short")
            with patch("liminal_gate.tester_setup.find_keytools", return_value=(Path("keytool"),)), \
                 patch("liminal_gate.tester_setup.prompt_key_password", return_value="longenough"), \
                 patch("liminal_gate.tester_setup.subprocess.run", side_effect=failure):
                with self.assertRaisesRegex(TesterSetupError, "password too short"):
                    ensure_keystore(data / "test.keystore", data / "password.txt")

    def test_every_prerequisite_is_checked_before_the_resource_tree_is_inventoried(self) -> None:
        """An incomplete toolchain must not cost a completed resource inventory.

        Each of these used to surface at a different, later point -- the
        disassembler only after the tree had been hashed and an IL2CPP dump
        produced -- so the order is pinned rather than left to how the body
        happens to read.
        """
        order: list[str] = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); apk = root / "game.apk"; resources = root / "resources"
            apk.write_bytes(b"apk")
            for category in REQUIRED_RESOURCE_CATEGORIES:
                (resources / category).mkdir(parents=True, exist_ok=True)
            # Setup now requires the master-data layout, so one is supplied and
            # the derivations that consume it are stubbed; this is about the
            # order of the checks, not about what they produce.
            dummy_dll = root / "DummyDll"
            dummy_dll.mkdir()
            (dummy_dll / "Assembly-CSharp.dll").write_bytes(b"")
            (dummy_dll.parent / "dump.cs").write_text("", encoding="utf-8")
            with patch("liminal_gate.tester_setup.load_master_trees", return_value={"ChrDatabase": {}, "BuddyDatabase": {}}), \
                 patch("liminal_gate.tester_setup.build_character_catalog", return_value={}), \
                 patch("liminal_gate.tester_setup.write_character_catalog"), \
                 patch("liminal_gate.tester_setup.build_companion_equipment_catalog", return_value={}), \
                 patch("liminal_gate.tester_setup.write_companion_equipment_catalog"), \
                 patch("liminal_gate.tester_setup.write_local_names"), \
                 patch("liminal_gate.tester_setup.derive_story_outcome_catalog"), \
                 patch("liminal_gate.tester_setup.ensure_keystore", side_effect=lambda *_: order.append("keystore")), \
                 patch("liminal_gate.tester_setup.find_build_tools", side_effect=lambda *_: order.append("build-tools") or (root / "zipalign", root / "apksigner")), \
                 patch("liminal_gate.tester_setup.check_derivation_prerequisites", side_effect=lambda *_: order.append("prerequisites")), \
                 patch("liminal_gate.tester_setup.build_import_manifest", side_effect=lambda *_, **__: order.append("inventory") or {}), \
                 patch("liminal_gate.tester_setup.write_import_manifest"), patch("liminal_gate.tester_setup.build_resource_manifest", return_value={}), \
                 patch("liminal_gate.tester_setup.write_resource_manifest"), patch("liminal_gate.tester_setup.prepare_pact_banners"), \
                 patch("liminal_gate.tester_setup.generate_legacy_client_plan", return_value={"patches": []}), \
                 patch("liminal_gate.tester_setup.load_patch_plan", return_value={}), patch("liminal_gate.tester_setup.apply_patch_plan"), \
                 patch("liminal_gate.tester_setup.sign_apk"):
                prepare_local_tester(apk, resources, root / "user-data", 8696, None, dummy_dll_dir=dummy_dll)
        self.assertEqual(["keystore", "build-tools", "prerequisites", "inventory"], order)


class AccountReportTest(unittest.TestCase):
    """Reinstalling reads as lost progress; the launch report is the antidote.

    An account is keyed by the client's device UUID, so clearing app data signs
    the client into a new, empty account while the real save stays in the same
    file. Nothing in the client says so.
    """

    def _report(self, document: dict) -> str:
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            (data / "bootstrap-state.json").write_text(json.dumps(document), encoding="utf-8")
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                tester_setup.report_existing_accounts(data)
            return stream.getvalue()

    @staticmethod
    def _account(progress: int | None, played: bool = True) -> dict:
        return {
            "username": "Player",
            "tutorial_phase": "free_roam" if played else "initial",
            "tutorial_requests": {"a": {}} if played else {},
            "userdata": {} if progress is None else {"progressCode": progress},
        }

    def test_lists_every_account_and_marks_the_active_one(self) -> None:
        # The listing reports; acting on it is the picker's job.
        output = self._report({
            "accounts": {"old": self._account(16777601), "new": self._account(16777346)},
            "active_account_id": "new", "tokens": {}, "client_hosts": {},
        })
        self.assertIn("unlocked chapter 6-1", output)
        self.assertIn("unlocked chapter 2-2", output)
        self.assertIn("* new", output)
        self.assertIn("signed into", output)

    def test_says_nothing_extra_for_a_single_account(self) -> None:
        output = self._report({
            "accounts": {"only": self._account(16777601)},
            "active_account_id": "only", "tokens": {}, "client_hosts": {},
        })
        self.assertIn("unlocked chapter 6-1", output)
        self.assertNotIn("signed into", output)

    def test_lists_without_advising_when_the_active_account_is_furthest(self) -> None:
        output = self._report({
            "accounts": {"old": self._account(16777346), "new": self._account(16777601)},
            "active_account_id": "new", "tokens": {}, "client_hosts": {},
        })
        self.assertNotIn("more progress", output)

    def test_an_unplayed_account_reads_as_not_started(self) -> None:
        output = self._report({
            "accounts": {"fresh": self._account(None, played=False)},
            "active_account_id": "fresh", "tokens": {}, "client_hosts": {},
        })
        self.assertIn("not started", output)

    def test_silent_when_no_state_file_exists(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                tester_setup.report_existing_accounts(Path(directory))
            self.assertEqual("", stream.getvalue())


class AccountSwitchPromptTest(unittest.TestCase):
    """The picker only appears when it has something worth offering."""

    def _run(self, accounts: dict, active: str, answer: str) -> tuple[str, dict]:
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            state = data / "bootstrap-state.json"
            state.write_text(json.dumps({
                "accounts": accounts, "active_account_id": active,
                "tokens": {"t": active}, "client_hosts": {},
            }), encoding="utf-8")
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                tester_setup.offer_account_switch(data, ask=lambda _prompt: answer)
            return stream.getvalue(), json.loads(state.read_text(encoding="utf-8"))

    @staticmethod
    def _account(progress: int, played: bool = True) -> dict:
        return {
            "username": "Player",
            "tutorial_phase": "free_roam" if played else "initial",
            "tutorial_requests": {"a": {}} if played else {},
            "userdata": {"progressCode": progress},
        }

    def test_switches_to_the_chosen_account(self) -> None:
        output, document = self._run(
            {"far": self._account(16777601), "here": self._account(16777346)}, "here", "1",
        )
        self.assertIn("chapter 6-1", output)
        self.assertEqual(16777601, document["accounts"]["here"]["userdata"]["progressCode"])
        # Reversible: the displaced save is still there.
        self.assertEqual(16777346, document["accounts"]["far"]["userdata"]["progressCode"])

    def test_declining_changes_nothing(self) -> None:
        for answer in ("0", "", "nonsense"):
            with self.subTest(answer=answer):
                _output, document = self._run(
                    {"far": self._account(16777601), "here": self._account(16777346)}, "here", answer,
                )
                self.assertEqual(16777346, document["accounts"]["here"]["userdata"]["progressCode"])

    def test_silent_when_the_active_account_is_already_furthest(self) -> None:
        output, _document = self._run(
            {"behind": self._account(16777346), "here": self._account(16777601)}, "here", "1",
        )
        self.assertEqual("", output)

    def test_silent_with_a_single_account(self) -> None:
        output, _document = self._run({"only": self._account(16777601)}, "only", "1")
        self.assertEqual("", output)

    def test_ignores_never_played_accounts(self) -> None:
        # An untouched account is not a save worth offering.
        output, _document = self._run(
            {"empty": self._account(0, played=False), "here": self._account(16777346)}, "here", "1",
        )
        self.assertEqual("", output)

    def test_offers_a_played_save_when_the_active_account_is_a_fresh_reinstall(self) -> None:
        output, document = self._run(
            {"old": self._account(16777601), "fresh": self._account(0, played=False)},
            "fresh",
            "1",
        )
        self.assertIn("chapter 6-1", output)
        self.assertEqual(
            16777601,
            document["accounts"]["fresh"]["userdata"]["progressCode"],
        )
        self.assertEqual(
            0,
            document["accounts"]["old"]["userdata"]["progressCode"],
        )


class KeystoreFallbackTest(unittest.TestCase):
    """A keytool that cannot start should not end setup.

    On Windows a broken Java installation returns an NT status code and no
    output at all, so the tester sees a bare number. Android Studio's bundled
    runtime is usually intact, so it is worth trying.
    """

    def test_decodes_exit_codes_that_mean_the_program_never_ran(self) -> None:
        self.assertIn("0xC0000135", tester_setup.describe_tool_exit(3221225781) or "")
        # An ordinary non-zero exit is keytool reporting a real problem.
        self.assertIsNone(tester_setup.describe_tool_exit(1))
        self.assertIsNone(tester_setup.describe_tool_exit(0))

    def _run(self, results: list, keytools: tuple[Path, ...]) -> tuple[str, list]:
        calls: list = []

        def fake_run(command, **_kwargs):
            calls.append(command[0])
            outcome = results[len(calls) - 1]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        stream = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            keystore = Path(directory) / "test.keystore"
            password_file = Path(directory) / "password.txt"
            with contextlib.ExitStack() as stack:
                stack.enter_context(mock.patch.object(tester_setup, "find_keytools", return_value=keytools))
                stack.enter_context(mock.patch.object(tester_setup, "prompt_key_password", return_value="testing123"))
                stack.enter_context(mock.patch.object(tester_setup.subprocess, "run", fake_run))
                stack.enter_context(contextlib.redirect_stdout(stream))
                tester_setup.ensure_keystore(keystore, password_file)
        return stream.getvalue(), calls

    def test_falls_back_to_the_next_keytool_when_one_cannot_start(self) -> None:
        launch_failure = subprocess.CalledProcessError(3221225781, "keytool", output="", stderr="")
        output, calls = self._run([launch_failure, None], (Path("/broken/keytool"), Path("/bundled/keytool")))
        self.assertEqual(["/broken/keytool", "/bundled/keytool"], calls)
        self.assertIn("trying another", output)

    def test_does_not_retry_a_keytool_that_reported_a_real_problem(self) -> None:
        # It refused the request; another copy would refuse it identically.
        refusal = subprocess.CalledProcessError(1, "keytool", output="", stderr="Key password is too short")
        with self.assertRaisesRegex(tester_setup.TesterSetupError, "too short"):
            self._run([refusal, None], (Path("/a/keytool"), Path("/b/keytool")))

    def test_reports_every_attempt_when_all_of_them_fail_to_start(self) -> None:
        failure = subprocess.CalledProcessError(3221225781, "keytool", output="", stderr="")
        with self.assertRaises(tester_setup.TesterSetupError) as caught:
            self._run([failure, failure], (Path("/a/keytool"), Path("/b/keytool")))
        message = str(caught.exception)
        self.assertIn("/a/keytool", message)
        self.assertIn("/b/keytool", message)
        self.assertIn("0xC0000135", message)
        self.assertIn("JAVA_HOME", message)
