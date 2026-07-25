from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from liminal_gate.tester_setup import EMULATOR_LOOPBACK_HOST, REQUIRED_RESOURCE_CATEGORIES, TesterSetupError, build_server_origin, check_device_host_suits_device, choose_local_server_options, find_build_tools, install_apk, prepare_local_tester, resolve_resource_root, run_server, select_device, server_arguments, write_password_file


class GuidedServerPolicyTest(unittest.TestCase):
    """The guided path must actually be able to reach each bundled policy."""

    def arguments(self, **options) -> list[str]:
        return server_arguments(Path("resources"), Path("data"), 8696, **options)

    def test_recommended_mode_enables_every_bundled_policy(self) -> None:
        arguments = self.arguments()
        for flag in ("--core-story", "--pacts", "--hunting", "--jobs", "--rebirth", "--status-items", "--companion-draw", "--companion-sale"):
            self.assertIn(flag, arguments)

    def choose(self, mode: str):
        """Answer the mode prompt, then decline the event-catalog question."""
        answers = iter((mode, "n"))
        return choose_local_server_options(None, None, ask=lambda _: next(answers))

    def test_hunting_follows_the_story_choice(self) -> None:
        # Its stages only unlock through story progress, so offering it without
        # the story would present a menu nothing can reach.
        pacts_only = self.choose("3")
        self.assertEqual((False, True, False, False, False, False, False, False), (pacts_only.core_story, pacts_only.pacts, pacts_only.hunting, pacts_only.jobs, pacts_only.rebirth, pacts_only.status_items, pacts_only.companion_draw, pacts_only.companion_sale))
        self.assertNotIn("--hunting", self.arguments(core_story=False, pacts=True, hunting=False))
        story_only = self.choose("2")
        self.assertEqual((True, False, True, True, True, True, True, True), (story_only.core_story, story_only.pacts, story_only.hunting, story_only.jobs, story_only.rebirth, story_only.status_items, story_only.companion_draw, story_only.companion_sale))

    def test_minimal_mode_enables_none_of_them(self) -> None:
        options = self.choose("4")
        arguments = self.arguments(core_story=options.core_story, pacts=options.pacts, hunting=options.hunting, jobs=options.jobs, rebirth=options.rebirth, status_items=options.status_items, companion_draw=options.companion_draw, companion_sale=options.companion_sale)
        for flag in ("--core-story", "--pacts", "--hunting", "--jobs", "--rebirth", "--status-items", "--companion-draw", "--companion-sale"):
            self.assertNotIn(flag, arguments)


class TesterSetupTest(unittest.TestCase):

    def test_optional_dummy_dll_directory_derives_local_character_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); apk = root / "game.apk"; resources = root / "resources"; data = root / "user-data"; dummy = root / "DummyDll"
            apk.write_bytes(b"apk"); dummy.mkdir()
            for category in REQUIRED_RESOURCE_CATEGORIES:
                (resources / category).mkdir(parents=True, exist_ok=True)
            with patch("liminal_gate.tester_setup.build_import_manifest", return_value={}), patch("liminal_gate.tester_setup.write_import_manifest"), patch("liminal_gate.tester_setup.load_character_master_tree", return_value={"infos": [{"ID": 3, "chrType": 1, "isLambda": 0, "rebirthFromID": 0, "rarity": 4, "Jobs": [30]}]}), patch("liminal_gate.tester_setup.build_resource_manifest", return_value={}), patch("liminal_gate.tester_setup.write_resource_manifest"), patch("liminal_gate.tester_setup.prepare_pact_banners"), patch("liminal_gate.tester_setup.generate_legacy_client_plan", return_value={"patches": []}), patch("liminal_gate.tester_setup.load_patch_plan", return_value={}), patch("liminal_gate.tester_setup.apply_patch_plan"), patch("liminal_gate.tester_setup.ensure_keystore"), patch("liminal_gate.tester_setup.find_build_tools", return_value=(root / "zipalign", root / "apksigner")), patch("liminal_gate.tester_setup.sign_apk"):
                prepare_local_tester(apk, resources, data, 8696, None, dummy)
            self.assertTrue((data / "character-catalog.json").is_file())
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

    def test_interactive_options_can_choose_minimal_setup(self) -> None:
        answers = iter(("4", "n"))
        options = choose_local_server_options(None, None, lambda _: next(answers))
        self.assertFalse(options.core_story)
        self.assertFalse(options.pacts)
        self.assertIsNone(options.event_catalog)

    def test_interactive_options_require_local_event_inputs(self) -> None:
        answers = iter(("", "y", "local/events.json", "local/DummyDll"))
        options = choose_local_server_options(None, None, lambda _: next(answers))
        self.assertEqual(Path("local/events.json"), options.event_catalog)
        self.assertEqual(Path("local/DummyDll"), options.dummy_dll_dir)

    def test_runs_server_with_argument_sequence(self) -> None:
        arguments = ["python", "-m", "liminal_gate.bootstrap_server", "--resource-root", r"C:\\Local Files\\android"]
        with patch("liminal_gate.tester_setup.subprocess.run") as run:
            run_server(arguments)
        run.assert_called_once_with(arguments, check=True)
