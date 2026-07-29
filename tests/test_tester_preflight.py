"""`--check` answers "is this machine ready" in one pass, changing nothing.

Every prerequisite setup needs used to be discovered one failure at a time, each
after a slower step than the last, so a machine missing three of them took three
runs to say so.
"""

from __future__ import annotations

import contextlib
import io
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from liminal_gate import tester_setup
from liminal_gate.tester_setup import (
    Check,
    REQUIRED_RESOURCE_CATEGORIES,
    TesterSetupError,
    generate_key_password,
    port_is_free,
    preflight_checks,
    report_preflight,
)


class PreflightReportTest(unittest.TestCase):
    def _report(self, checks: list[Check]) -> tuple[str, int]:
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            status = report_preflight(checks)
        return stream.getvalue(), status

    def test_a_complete_machine_reports_success(self) -> None:
        output, status = self._report([Check("adb", True, "/usr/bin/adb")])
        self.assertEqual(0, status)
        self.assertIn("ok", output)
        self.assertIn("Everything is ready", output)

    def test_a_failure_sets_a_non_zero_status_and_names_the_fix(self) -> None:
        output, status = self._report([
            Check("adb", True, "/usr/bin/adb"),
            Check("UnityPy", False, "install it with: python3 -m pip install"),
        ])
        self.assertEqual(1, status)
        self.assertIn("FAIL", output)
        self.assertIn("pip install", output)
        self.assertIn("1 required check(s) failed", output)

    def test_an_optional_check_warns_rather_than_failing(self) -> None:
        # --prepare-only is a real path, and a tester who has not started the
        # emulator yet still wants the rest of the list.
        output, status = self._report([Check("device", False, "no device", required=False)])
        self.assertEqual(0, status)
        self.assertIn("warn", output)
        self.assertNotIn("FAIL", output)

    def test_a_long_fix_is_wrapped_under_its_own_row(self) -> None:
        detail = "install this tool and then " + "and then ".join(["do the next thing"] * 8)
        output, _status = self._report([Check("tool", False, detail)])
        self.assertTrue(all(len(line) <= 90 for line in output.splitlines()), output)


class PreflightChecksTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.apk = self.root / "game.apk"
        self.apk.write_bytes(b"apk")
        self.resources = self.root / "android"
        for category in REQUIRED_RESOURCE_CATEGORIES:
            (self.resources / category).mkdir(parents=True)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _checks(self, **overrides) -> dict[str, Check]:
        arguments = {
            "apk": self.apk, "resource_root": self.resources, "dummy_dll_dir": None,
            "port": 0, "adb": "adb", "device": None, "build_tools": None,
        }
        arguments.update(overrides)
        return {check.name: check for check in preflight_checks(**arguments)}

    def _stub_environment(self) -> contextlib.ExitStack:
        """Pin everything machine-dependent so the assertions are about the code."""
        stack = contextlib.ExitStack()
        stack.enter_context(patch.object(tester_setup, "resolve_adb", return_value="/usr/bin/adb"))
        stack.enter_context(patch.object(tester_setup, "find_build_tools", return_value=(self.root / "zipalign", self.root / "apksigner")))
        stack.enter_context(patch.object(tester_setup, "find_keytools", return_value=(Path("/usr/bin/keytool"),)))
        stack.enter_context(patch.object(tester_setup, "find_missing_master_import", return_value=()))
        stack.enter_context(patch.object(tester_setup, "find_il2cpp_dumper", return_value=("Il2CppDumper",)))
        stack.enter_context(patch.object(tester_setup, "probe_il2cpp_dumper", return_value="Il2CppDumper"))
        stack.enter_context(patch.object(tester_setup, "find_aarch64_objdump", return_value="llvm-objdump"))
        stack.enter_context(patch.object(tester_setup, "select_device", return_value="emulator-5570"))
        stack.enter_context(patch.object(tester_setup, "port_is_free", return_value=True))
        return stack

    def test_a_ready_machine_passes_every_check(self) -> None:
        with self._stub_environment():
            checks = self._checks()
        self.assertTrue(all(check.ok for check in checks.values()), checks)

    def test_nothing_is_written_by_checking(self) -> None:
        before = sorted(path.name for path in self.root.iterdir())
        with self._stub_environment():
            self._checks()
        self.assertEqual(before, sorted(path.name for path in self.root.iterdir()))

    def test_each_missing_prerequisite_is_reported_in_the_same_pass(self) -> None:
        """The whole point: three missing tools take one run to discover."""
        with self._stub_environment() as stack:
            stack.enter_context(patch.object(tester_setup, "find_missing_master_import", return_value=("UnityPy",)))
            stack.enter_context(patch.object(tester_setup, "find_il2cpp_dumper", return_value=None))
            stack.enter_context(patch.object(tester_setup, "find_aarch64_objdump", return_value=None))
            checks = self._checks()
        self.assertFalse(checks["UnityPy"].ok)
        self.assertFalse(checks["Il2CppDumper"].ok)
        self.assertFalse(checks["disassembler"].ok)
        # ...and the checks that had nothing to do with them still report.
        self.assertTrue(checks["APK"].ok)
        self.assertTrue(checks["resources"].ok)

    def test_a_supplied_dummy_dll_makes_the_dumper_unnecessary(self) -> None:
        dummy = self.root / "DummyDll"
        dummy.mkdir()
        with self._stub_environment() as stack:
            stack.enter_context(patch.object(tester_setup, "find_il2cpp_dumper", return_value=None))
            checks = self._checks(dummy_dll_dir=dummy)
        self.assertTrue(checks["Il2CppDumper"].ok)
        self.assertIn("not needed", checks["Il2CppDumper"].detail)

    def test_a_dumper_that_cannot_find_dotnet_fails_preflight(self) -> None:
        with self._stub_environment() as stack:
            stack.enter_context(patch.object(
                tester_setup,
                "probe_il2cpp_dumper",
                side_effect=TesterSetupError(
                    "Il2CppDumper could not start: You must install .NET"
                ),
            ))
            checks = self._checks()
        self.assertFalse(checks["Il2CppDumper"].ok)
        self.assertIn("could not start", checks["Il2CppDumper"].detail)

    def test_the_dumper_probe_accepts_the_real_usage_shape(self) -> None:
        completed = tester_setup.subprocess.CompletedProcess(
            ("Il2CppDumper",),
            1,
            "usage: Il2CppDumper <executable-file> <global-metadata> <output-directory>\n",
            "",
        )
        with patch.object(tester_setup.subprocess, "run", return_value=completed) as run:
            detail = tester_setup.probe_il2cpp_dumper(("Il2CppDumper",))
        self.assertEqual("Il2CppDumper", detail)
        self.assertEqual(tester_setup.subprocess.DEVNULL, run.call_args.kwargs["stdin"])

    def test_the_dumper_probe_names_the_dll_fix_for_a_missing_runtime(self) -> None:
        completed = tester_setup.subprocess.CompletedProcess(
            ("Il2CppDumper",),
            150,
            "",
            "You must install .NET to run this application.\n",
        )
        with patch.object(tester_setup.subprocess, "run", return_value=completed):
            with self.assertRaisesRegex(
                TesterSetupError,
                "LIMINAL_GATE_IL2CPPDUMPER.*Il2CppDumper.dll",
            ):
                tester_setup.probe_il2cpp_dumper(("Il2CppDumper",))

    def test_a_missing_apk_and_resource_tree_are_reported_not_raised(self) -> None:
        with self._stub_environment():
            checks = self._checks(apk=self.root / "absent.apk", resource_root=self.root / "absent")
        self.assertFalse(checks["APK"].ok)
        self.assertIn("--apk", checks["APK"].detail)
        self.assertFalse(checks["resources"].ok)

    def test_an_absent_device_warns_instead_of_failing(self) -> None:
        with self._stub_environment() as stack:
            stack.enter_context(patch.object(
                tester_setup, "select_device", side_effect=TesterSetupError("no ready Android device found"),
            ))
            checks = self._checks()
        self.assertFalse(checks["device"].ok)
        self.assertFalse(checks["device"].required)

    def test_a_port_already_listening_is_reported_before_the_build(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as taken:
            taken.bind(("0.0.0.0", 0))
            taken.listen(1)
            port = taken.getsockname()[1]
            self.assertFalse(port_is_free(port))
            with self._stub_environment() as stack:
                stack.enter_context(patch.object(tester_setup, "port_is_free", return_value=False))
                checks = self._checks(port=port)
        self.assertFalse(checks["port"].ok)
        self.assertIn("--port", checks["port"].detail)

    def test_an_unused_port_is_free(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("0.0.0.0", 0))
            port = probe.getsockname()[1]
        self.assertTrue(port_is_free(port))


class GeneratedKeyPasswordTest(unittest.TestCase):
    """The key signs one throwaway local build and its password is stored beside it.

    Choosing it by hand therefore protects nothing and cost the first run two
    prompts, so it is generated unless the operator asks to choose.
    """

    def _ensure(self, prompt: bool, existing_keystore: bool = False):
        created: dict[str, str] = {}

        def fake_run(command, **_kwargs):
            # keytool would create the file; record the password it was given.
            created["password"] = command[command.index("-storepass") + 1]
            Path(command[command.index("-keystore") + 1]).write_text("key", encoding="utf-8")
            return None

        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            keystore, password_file = data / "test.keystore", data / "password.txt"
            if existing_keystore:
                keystore.write_text("key", encoding="utf-8")
            with patch.object(tester_setup, "find_keytools", return_value=(Path("keytool"),)), \
                 patch.object(tester_setup.subprocess, "run", fake_run), \
                 patch.object(tester_setup, "prompt_key_password", return_value="chosen-by-hand"), \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                tester_setup.ensure_keystore(keystore, password_file, prompt)
            return created.get("password"), password_file.read_text(encoding="utf-8"), output.getvalue()

    def test_a_generated_password_is_long_and_unpredictable(self) -> None:
        self.assertNotEqual(generate_key_password(), generate_key_password())
        self.assertGreaterEqual(len(generate_key_password()), tester_setup.MINIMUM_KEY_PASSWORD_LENGTH)

    def test_the_first_run_asks_for_nothing_and_saves_what_it_generated(self) -> None:
        used, saved, output = self._ensure(prompt=False)
        self.assertEqual(used, saved, "the saved password must be the one the key was made with")
        self.assertNotEqual("chosen-by-hand", used)
        self.assertIn("--prompt-key-password", output, "the operator is told the choice exists")

    def test_prompting_is_still_available_on_request(self) -> None:
        used, saved, _output = self._ensure(prompt=True)
        self.assertEqual("chosen-by-hand", used)
        self.assertEqual("chosen-by-hand", saved)

    def test_an_existing_key_is_always_asked_about(self) -> None:
        # Its password cannot be generated: it has to match what the key was
        # made with, and only the operator knows that.
        _used, saved, _output = self._ensure(prompt=False, existing_keystore=True)
        self.assertEqual("chosen-by-hand", saved)


class ConfiguredDumperTest(unittest.TestCase):
    """`LIMINAL_GATE_IL2CPPDUMPER` says what it wants and why it was not met.

    A tester on Windows completed every other check and could not get this one
    past "install Il2CppDumper" -- with the tool installed -- because a variable
    naming the extracted folder, and a variable naming a path that does not
    exist, both produced the text for a variable that was never set.
    """

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)

    @contextlib.contextmanager
    def _configured(self, value: str | None):
        environment = {} if value is None else {tester_setup.IL2CPP_DUMPER_ENVIRONMENT: value}
        with patch.dict(tester_setup.os.environ, environment, clear=True):
            yield

    def _release(self, member: str) -> Path:
        directory = self.root / "Il2CppDumper-win"
        directory.mkdir(exist_ok=True)
        (directory / member).write_text("", encoding="utf-8")
        return directory

    def test_a_directory_holding_a_release_is_accepted(self) -> None:
        directory = self._release("Il2CppDumper.exe")
        with self._configured(str(directory)):
            self.assertEqual(
                (str(directory / "Il2CppDumper.exe"),), tester_setup.find_il2cpp_dumper()
            )

    def test_a_native_build_is_preferred_to_the_assembly_beside_it(self) -> None:
        directory = self._release("Il2CppDumper.dll")
        (directory / "Il2CppDumper.exe").write_text("", encoding="utf-8")
        with self._configured(str(directory)):
            command = tester_setup.find_il2cpp_dumper()
        self.assertEqual((str(directory / "Il2CppDumper.exe"),), command)

    def test_a_directory_holding_only_the_assembly_runs_through_dotnet(self) -> None:
        directory = self._release("Il2CppDumper.dll")
        with self._configured(str(directory)), \
                patch.object(tester_setup.shutil, "which", return_value="/usr/bin/dotnet"):
            command = tester_setup.find_il2cpp_dumper()
        self.assertEqual(("/usr/bin/dotnet", str(directory / "Il2CppDumper.dll")), command)

    def test_surrounding_quotes_are_not_part_of_the_path(self) -> None:
        directory = self._release("Il2CppDumper.exe")
        with self._configured(f'"{directory}"'):
            self.assertIsNotNone(tester_setup.find_il2cpp_dumper())

    def test_an_empty_directory_names_itself_and_what_it_lacks(self) -> None:
        empty = self.root / "empty"
        empty.mkdir()
        with self._configured(str(empty)):
            detail = tester_setup.describe_missing_il2cpp_dumper()
        self.assertIn(str(empty), detail)
        self.assertIn("Il2CppDumper.exe", detail)
        self.assertNotIn("Pass --dummy-dll-dir", detail, "this operator has installed it")

    def test_a_path_that_does_not_exist_says_so(self) -> None:
        absent = self.root / "typo" / "Il2CppDumper.exe"
        with self._configured(str(absent)):
            detail = tester_setup.describe_missing_il2cpp_dumper()
        self.assertIn(str(absent), detail)
        self.assertIn("does not exist", detail)
        self.assertIn("same window", detail, "the variable is per-terminal, which is the usual cause")

    def test_an_assembly_with_no_dotnet_names_the_runtime(self) -> None:
        directory = self._release("Il2CppDumper.dll")
        with self._configured(str(directory)), \
                patch.object(tester_setup.shutil, "which", return_value=None):
            detail = tester_setup.describe_missing_il2cpp_dumper()
        self.assertIn("dotnet", detail)
        self.assertIn(str(directory / "Il2CppDumper.dll"), detail)

    def test_an_unset_variable_still_says_how_to_install(self) -> None:
        with self._configured(None):
            detail = tester_setup.describe_missing_il2cpp_dumper()
        self.assertEqual(tester_setup.IL2CPP_DUMPER_MISSING, detail)
        self.assertIn("github.com/Perfare/Il2CppDumper", detail)

    def test_the_caller_chooses_the_text_for_a_variable_that_was_never_set(self) -> None:
        with self._configured(None):
            self.assertEqual("its own advice", tester_setup.describe_missing_il2cpp_dumper("its own advice"))

    def test_a_misconfigured_variable_overrides_the_caller_s_install_text(self) -> None:
        """The specific reason wins: "install it" cannot help someone who did."""
        absent = self.root / "typo"
        with self._configured(str(absent)):
            self.assertIn(str(absent), tester_setup.describe_missing_il2cpp_dumper("install it"))


if __name__ == "__main__":
    unittest.main()
