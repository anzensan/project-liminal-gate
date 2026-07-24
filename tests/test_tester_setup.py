from __future__ import annotations

import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from liminal_gate.tester_setup import TesterSetupError, find_build_tools, run_server, select_emulator, server_arguments, write_password_file


class TesterSetupTest(unittest.TestCase):
    def test_requires_explicit_choice_when_multiple_emulators_are_ready(self) -> None:
        with patch("liminal_gate.tester_setup._adb_devices", return_value=("emulator-5554", "emulator-5570")):
            with self.assertRaisesRegex(TesterSetupError, "--emulator"):
                select_emulator("adb", None)
            self.assertEqual("emulator-5570", select_emulator("adb", "emulator-5570"))

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
        self.assertIn("0.0.0.0", arguments)

    def test_runs_server_with_argument_sequence(self) -> None:
        arguments = ["python", "-m", "liminal_gate.bootstrap_server", "--resource-root", r"C:\\Local Files\\android"]
        with patch("liminal_gate.tester_setup.subprocess.run") as run:
            run_server(arguments)
        run.assert_called_once_with(arguments, check=True)
