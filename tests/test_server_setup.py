from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, call, patch

from liminal_gate.server_setup import (
    REQUIRED_RESOURCE_CATEGORIES,
    STANDARD_POLICY_FLAGS,
    ServerSetupError,
    main,
    prepare_server,
    resolve_resource_root,
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
        rendered = " ".join(arguments).lower()
        for android_term in ("apk", "adb", "zipalign", "apksigner", "keystore"):
            self.assertNotIn(android_term, rendered)
        self.assertIn("0.0.0.0", arguments)
        self.assertIn("8696", arguments)

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
