from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, call, patch

from liminal_gate.server_setup import (
    DEFAULT_COMPANION_EQUIPMENT_CATALOG,
    DEFAULT_OUTCOME_CATALOG,
    REQUIRED_RESOURCE_CATEGORIES,
    STANDARD_POLICY_FLAGS,
    ServerSetupError,
    main,
    prepare_server,
    resolve_companion_equipment_catalog,
    resolve_resource_root,
    resolve_story_outcome_catalog,
    run_server,
    server_arguments,
)


class ServerOnlySetupTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.resources = self.root / "gdresources" / "data_u2017" / "android"
        for category in REQUIRED_RESOURCE_CATEGORIES:
            (self.resources / category).mkdir(parents=True, exist_ok=True)
        (self.resources / "BG" / "sample.bin").write_bytes(b"local resource")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_detects_final_android_resource_root(self) -> None:
        self.assertEqual(
            self.resources.resolve(),
            resolve_resource_root(self.root),
        )

    def test_rejects_wrong_resource_nesting(self) -> None:
        with self.assertRaisesRegex(ServerSetupError, "data_u2017/android"):
            resolve_resource_root(self.resources / "BG")

    def test_prepares_hash_manifest_and_durable_data_directory(self) -> None:
        resource_root, data_directory, resource_count = prepare_server(
            self.root, self.root / "state"
        )
        self.assertEqual(self.resources.resolve(), resource_root)
        self.assertEqual((self.root / "state").resolve(), data_directory)
        self.assertEqual(1, resource_count)
        self.assertTrue((data_directory / "resources.json").is_file())

    def test_server_command_enables_standard_policies_without_android_tools(self) -> None:
        arguments = server_arguments(
            self.resources.resolve(),
            (self.root / "state").resolve(),
            "0.0.0.0",
            8696,
            self.root / "profile.json",
        )
        for flag in STANDARD_POLICY_FLAGS:
            self.assertIn(flag, arguments)
        self.assertNotIn("--summon-skills", arguments)
        rendered = " ".join(arguments).lower()
        for android_term in ("apk", "adb", "zipalign", "apksigner", "keystore"):
            self.assertNotIn(android_term, rendered)
        self.assertIn("0.0.0.0", arguments)
        self.assertIn("8696", arguments)

    def test_story_outcome_catalog_is_picked_up_from_the_data_directory(self) -> None:
        data_directory = self.root / "state"
        data_directory.mkdir()
        self.assertIsNone(resolve_story_outcome_catalog(None, data_directory))
        catalog = data_directory / DEFAULT_OUTCOME_CATALOG
        catalog.write_text("{}", encoding="utf-8")
        self.assertEqual(catalog.resolve(), resolve_story_outcome_catalog(None, data_directory))

    def test_a_mistyped_story_outcome_catalog_is_an_error_not_a_silent_skip(self) -> None:
        # Skipping it quietly would present as the exact failure the catalog is
        # there to fix: a server that discards every Companion the client rolls.
        with self.assertRaisesRegex(ServerSetupError, "does not exist"):
            resolve_story_outcome_catalog(self.root / "absent.json", self.root)

    def test_a_story_outcome_catalog_is_passed_without_strictness(self) -> None:
        catalog = self.root / "story-outcomes.json"
        catalog.write_text("{}", encoding="utf-8")
        without = server_arguments(
            self.resources.resolve(), (self.root / "state").resolve(), "0.0.0.0", 8696,
            self.root / "profile.json",
        )
        self.assertNotIn("--story-outcome-catalog", without)
        arguments = server_arguments(
            self.resources.resolve(), (self.root / "state").resolve(), "0.0.0.0", 8696,
            self.root / "profile.json", story_outcome_catalog=catalog,
        )
        self.assertEqual(str(catalog), arguments[arguments.index("--story-outcome-catalog") + 1])
        # Bounding the reported items and monsters on top can only refuse a
        # clear, never enable one, so the guided launcher never asks for it.
        self.assertNotIn("--outcome-strict", arguments)

    def test_companion_equipment_catalog_is_discovered_and_passed(self) -> None:
        data_directory = self.root / "state"
        data_directory.mkdir()
        self.assertIsNone(
            resolve_companion_equipment_catalog(None, data_directory)
        )
        catalog = data_directory / DEFAULT_COMPANION_EQUIPMENT_CATALOG
        catalog.write_text("{}", encoding="utf-8")
        self.assertEqual(
            catalog.resolve(),
            resolve_companion_equipment_catalog(None, data_directory),
        )
        arguments = server_arguments(
            self.resources.resolve(),
            data_directory.resolve(),
            "0.0.0.0",
            8696,
            self.root / "profile.json",
            companion_equipment_catalog=catalog,
        )
        self.assertEqual(
            str(catalog),
            arguments[
                arguments.index("--companion-equipment-catalog") + 1
            ],
        )

    def test_mistyped_companion_equipment_catalog_is_an_error(self) -> None:
        with self.assertRaisesRegex(ServerSetupError, "does not exist"):
            resolve_companion_equipment_catalog(
                self.root / "absent.json", self.root,
            )

    def test_prepare_only_never_launches_server(self) -> None:
        data_directory = self.root / "state"
        with patch.object(
            sys,
            "argv",
            [
                "server_setup",
                "--resource-root",
                str(self.resources),
                "--data-dir",
                str(data_directory),
                "--prepare-only",
            ],
        ), patch("liminal_gate.server_setup.run_server") as run_server:
            self.assertEqual(0, main())
        run_server.assert_not_called()
        self.assertTrue((data_directory / "resources.json").is_file())

    def test_control_c_terminates_the_child_server_cleanly(self) -> None:
        process = Mock()
        process.wait.side_effect = [KeyboardInterrupt, 0]
        with patch("liminal_gate.server_setup.subprocess.Popen", return_value=process):
            run_server(["python", "-m", "liminal_gate.bootstrap_server"])
        process.terminate.assert_called_once_with()
        process.kill.assert_not_called()
        self.assertEqual(
            [call(), call(timeout=5)],
            process.wait.call_args_list,
        )

    def test_failed_child_server_is_reported(self) -> None:
        process = Mock()
        process.wait.return_value = 3
        with patch("liminal_gate.server_setup.subprocess.Popen", return_value=process):
            with self.assertRaises(subprocess.CalledProcessError):
                run_server(["python", "-m", "liminal_gate.bootstrap_server"])


if __name__ == "__main__":
    unittest.main()
