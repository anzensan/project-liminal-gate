from __future__ import annotations

import contextlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from liminal_gate import toolchain


#: The checkout, so the subprocess below can import the package under test from
#: wherever the suite happens to be run.
_REPOSITORY = Path(__file__).resolve().parent.parent


class ToolchainRecordTest(unittest.TestCase):
    def test_record_round_trips_and_is_stored_absolute(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary)
            (data / "sdk").mkdir()
            # Recorded from a relative path on purpose: the stored value has to
            # survive setup being run from a different working directory later.
            with contextlib.chdir(temporary):
                saved = toolchain.save(data, toolchain.Toolchain(sdk_root=Path("sdk")))
            self.assertTrue(Path(json.loads(saved.read_text())["tools"]["sdk_root"]).is_absolute())
            self.assertEqual(toolchain.load(data).sdk_root, (data / "sdk").resolve())

    def test_absent_record_is_empty_rather_than_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self.assertTrue(toolchain.load(Path(temporary)).is_empty())

    def test_unreadable_record_is_refused_rather_than_treated_as_empty(self) -> None:
        for content, expected in (
            ("{not json", "not valid JSON"),
            (json.dumps({"version": 99, "tools": {}}), "newer version"),
            (json.dumps({"version": 1, "tools": {"sdk_root": ""}}), "non-empty string"),
            (json.dumps(["sdk"]), "must be a JSON object"),
        ):
            with self.subTest(content=content), tempfile.TemporaryDirectory() as temporary:
                data = Path(temporary)
                toolchain.toolchain_path(data).write_text(content, encoding="utf-8")
                with self.assertRaisesRegex(toolchain.ToolchainError, expected):
                    toolchain.load(data)

    def test_a_record_naming_an_unknown_tool_stays_readable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary)
            toolchain.toolchain_path(data).write_text(
                json.dumps({"version": 1, "tools": {"sdk_root": "/sdk", "future_tool": "/x"}}),
                encoding="utf-8",
            )
            self.assertEqual(toolchain.load(data).sdk_root, Path("/sdk"))

    def test_updates_never_erase_a_tool_already_recorded(self) -> None:
        recorded = toolchain.Toolchain(sdk_root=Path("/sdk"))
        self.assertEqual(recorded.with_updates(java_home=None).sdk_root, Path("/sdk"))
        self.assertEqual(recorded.with_updates(java_home=Path("/jdk")).java_home, Path("/jdk"))

    def test_failed_atomic_replace_preserves_the_previous_record(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary)
            toolchain.save(data, toolchain.Toolchain(sdk_root=Path("/old-sdk")))
            with patch.object(toolchain.os, "replace", side_effect=OSError("interrupted")):
                with self.assertRaisesRegex(toolchain.ToolchainError, "interrupted"):
                    toolchain.save(data, toolchain.Toolchain(sdk_root=Path("/new-sdk")))
            self.assertEqual(Path("/old-sdk"), toolchain.load(data).sdk_root)


class ToolchainEnvironmentTest(unittest.TestCase):
    def test_recorded_locations_fill_the_environment(self) -> None:
        environment: dict[str, str] = {}
        toolchain.apply(
            toolchain.Toolchain(sdk_root=Path("/sdk"), java_home=Path("/jdk")), environment,
        )
        self.assertEqual(environment["ANDROID_SDK_ROOT"], "/sdk")
        self.assertEqual(environment["ANDROID_HOME"], "/sdk")
        self.assertEqual(environment["JAVA_HOME"], "/jdk")

    def test_an_operator_who_set_the_variable_keeps_their_choice(self) -> None:
        environment = {"JAVA_HOME": "/chosen"}
        changed = toolchain.apply(toolchain.Toolchain(java_home=Path("/recorded")), environment)
        self.assertEqual(environment["JAVA_HOME"], "/chosen")
        self.assertNotIn("JAVA_HOME", changed)

    def test_overriding_replaces_the_variable_and_leads_on_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            java_home = Path(temporary) / "jdk"
            (java_home / "bin").mkdir(parents=True)
            environment = {"JAVA_HOME": "/broken", "PATH": "/usr/bin"}
            toolchain.apply(toolchain.Toolchain(java_home=java_home), environment, override=True)
            self.assertEqual(environment["JAVA_HOME"], str(java_home))
            self.assertEqual(environment["PATH"].split(os.pathsep)[0], str(java_home / "bin"))

    def test_path_gains_real_directories_once_and_keeps_the_operators_first(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            sdk = Path(temporary) / "sdk"
            (sdk / "platform-tools").mkdir(parents=True)
            environment = {"PATH": os.pathsep.join(("/usr/bin", str(sdk / "platform-tools")))}
            toolchain.apply(toolchain.Toolchain(sdk_root=sdk), environment)
            entries = environment["PATH"].split(os.pathsep)
            self.assertEqual(entries[0], "/usr/bin")
            self.assertEqual(entries.count(str(sdk / "platform-tools")), 1)
            # cmdline-tools and emulator were never created, so nothing invented them.
            self.assertNotIn(str(sdk / "emulator"), entries)

    def test_roll_forward_is_set_only_for_the_managed_dumper(self) -> None:
        managed: dict[str, str] = {}
        toolchain.apply(toolchain.Toolchain(il2cpp_dumper=Path("/tools/Il2CppDumper.dll")), managed)
        self.assertEqual(managed["DOTNET_ROLL_FORWARD"], "Major")
        native: dict[str, str] = {}
        toolchain.apply(toolchain.Toolchain(il2cpp_dumper=Path("/tools/Il2CppDumper.exe")), native)
        self.assertNotIn("DOTNET_ROLL_FORWARD", native)
        self.assertEqual(native["LIMINAL_GATE_IL2CPPDUMPER"], "/tools/Il2CppDumper.exe")

    def test_a_broken_record_does_not_stop_a_launcher_from_starting(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary)
            toolchain.toolchain_path(data).write_text("{broken", encoding="utf-8")
            self.assertTrue(toolchain.load_and_apply(data).is_empty())


@unittest.skipIf(os.name == "nt", "relies on POSIX PATH and home-directory semantics")
class LauncherIntegrationTest(unittest.TestCase):
    """The whole claim, end to end: a record is what lets a launcher find tools.

    Run as a subprocess rather than in-process, because what is being checked
    is that `tester_setup.main` still replays the record before it resolves
    anything. An in-process call to the resolvers would pass just as happily
    with that line deleted.

    The environment is stripped to nothing but an empty `PATH` and a throwaway
    `HOME`. Both matter: `PATH` is where a developer machine's real `keytool`
    would otherwise be found, and `HOME` is where `_sdk_roots` looks for the
    Android Studio SDK that a developer machine also has. Left alone, either
    would let this pass without the record doing any work at all.
    """

    def _tools(self, root: Path) -> tuple[Path, Path]:
        """Create files shaped like the tools, which nothing here has to run."""
        sdk, java_home = root / "sdk", root / "jdk"
        build_tools = sdk / "build-tools" / "36.1.0"
        build_tools.mkdir(parents=True)
        for name in ("zipalign", "apksigner"):
            (build_tools / name).write_text("", encoding="utf-8")
        (sdk / "platform-tools").mkdir()
        (sdk / "platform-tools" / "adb").write_text("", encoding="utf-8")
        (java_home / "bin").mkdir(parents=True)
        (java_home / "bin" / "keytool").write_text("", encoding="utf-8")
        return sdk, java_home

    def _check(self, data_directory: Path, home: Path) -> dict[str, tuple[str, str]]:
        """Run the launcher's own readiness report and return it row by row."""
        empty = home / "empty-path"
        empty.mkdir(exist_ok=True)
        result = subprocess.run(
            (
                sys.executable, "-m", "liminal_gate.tester_setup", "--check",
                "--data-dir", str(data_directory), "--port", "45999",
            ),
            cwd=_REPOSITORY, text=True, capture_output=True, timeout=300,
            env={"PATH": str(empty), "HOME": str(home), "USERPROFILE": str(home)},
        )
        rows: dict[str, tuple[str, str]] = {}
        for line in result.stdout.splitlines():
            matched = re.match(r"\s+(ok|FAIL|warn)\s+(\S+(?: \S+)??)\s{2,}(.*)$", line)
            if matched is not None:
                rows[matched.group(2)] = (matched.group(1), matched.group(3))
        self.assertIn("build tools", rows, f"unparsed report:\n{result.stdout}\n{result.stderr}")
        return rows

    def test_a_recorded_toolchain_is_what_makes_the_launcher_find_the_tools(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = root / "user-data"
            data.mkdir()
            sdk, java_home = self._tools(root)

            # Without the record, a bare environment cannot reach them. This
            # half is the guard: it fails if the tools were reachable for some
            # other reason, which would leave the other half proving nothing.
            bare = self._check(data, root)
            self.assertEqual(bare["build tools"][0], "FAIL")
            self.assertEqual(bare["adb"][0], "FAIL")
            # keytool is asked for differently, because its absence cannot be
            # arranged: `find_keytools` deliberately falls back to the JDK
            # bundled with Android Studio, at an absolute path no environment
            # controls. On a machine that has it, the honest claim is not that
            # nothing is found but that the recorded JDK is not what is found.
            self.assertNotIn(str(java_home), bare["keytool"][1])

            toolchain.save(data, toolchain.Toolchain(sdk_root=sdk, java_home=java_home))
            recorded = self._check(data, root)
            # Against the resolved paths, because the record stores them that
            # way on purpose, and a temporary directory on macOS is reached
            # through a symlink.
            self.assertEqual(recorded["build tools"], ("ok", str((sdk / "build-tools/36.1.0").resolve())))
            self.assertEqual(recorded["keytool"], ("ok", str((java_home / "bin/keytool").resolve())))
            self.assertEqual(recorded["adb"], ("ok", str((sdk / "platform-tools/adb").resolve())))


if __name__ == "__main__":
    unittest.main()
