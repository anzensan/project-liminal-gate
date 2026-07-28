"""The guided setup requires and derives the story Companion drop catalog.

Without `user-data/story-outcomes.json` a story clear mints no Companion at all:
the client rolls the drop and `clear_quest` has no authority to write it. The
file cannot be shipped -- it is derived from the operator's own APK -- so the
one-command setup has to build it. A missing prerequisite must stop before an
install that would otherwise look complete.
"""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from liminal_gate.server_setup import DEFAULT_OUTCOME_CATALOG
from liminal_gate.tester_setup import (
    IL2CPP_LIBRARY_MEMBER,
    IL2CPP_METADATA_MEMBER,
    TesterSetupError,
    ensure_il2cpp_dump,
    derive_story_outcome_catalog,
    find_aarch64_objdump,
    prepare_local_tester,
)


class _StopSetup(Exception):
    """Cut the run short once the branch under test has been reached."""


def _prepare_after_inputs(apk: Path, data: Path, dummy_dll_dir: Path | None):
    """Drive `prepare_local_tester` far enough to reach the derived-data branch."""
    with patch("liminal_gate.tester_setup.resolve_resource_root", side_effect=lambda value: value), \
         patch("liminal_gate.tester_setup.ensure_keystore"), \
         patch("liminal_gate.tester_setup.find_build_tools", return_value=("zipalign", "apksigner")):
        return prepare_local_tester(
            apk, data, data, 8002, None, dummy_dll_dir=dummy_dll_dir,
        )


class FindAarch64ObjdumpTest(unittest.TestCase):
    """Support is confirmed, not assumed.

    A distribution's stock GNU `objdump` is frequently single-target and cannot
    read an AArch64 library at all. Choosing it would surface as a confusing
    failure thousands of disassembly calls into the import.
    """

    def _run(self, outputs: dict[str, str]):
        def fake_run(arguments, **_kwargs):
            class Result:
                stdout = outputs.get(arguments[0], "")
            return Result()
        return fake_run

    def test_prefers_a_disassembler_that_lists_aarch64(self) -> None:
        with patch("liminal_gate.tester_setup.shutil.which", side_effect=lambda name: f"/usr/bin/{name}"), \
             patch("liminal_gate.tester_setup.subprocess.run", side_effect=self._run({
                 "llvm-objdump": "LLVM\n Registered Targets:\n  aarch64 - AArch64",
             })):
            self.assertEqual("llvm-objdump", find_aarch64_objdump())

    def test_skips_a_single_target_build_that_cannot_read_aarch64(self) -> None:
        with patch("liminal_gate.tester_setup.shutil.which", side_effect=lambda name: f"/usr/bin/{name}"), \
             patch("liminal_gate.tester_setup.subprocess.run", side_effect=self._run({
                 "llvm-objdump": "LLVM 17\n Registered Targets:\n  x86-64",
                 "objdump": "GNU objdump 2.42\nsupported architectures: i386 aarch64",
             })):
            self.assertEqual("objdump", find_aarch64_objdump())

    def test_returns_none_when_nothing_on_path_can_read_aarch64(self) -> None:
        with patch("liminal_gate.tester_setup.shutil.which", return_value=None):
            self.assertIsNone(find_aarch64_objdump())

    def test_a_disassembler_that_will_not_run_is_passed_over(self) -> None:
        with patch("liminal_gate.tester_setup.shutil.which", side_effect=lambda name: f"/usr/bin/{name}"), \
             patch("liminal_gate.tester_setup.subprocess.run", side_effect=OSError):
            self.assertIsNone(find_aarch64_objdump())


class DeriveStoryOutcomeCatalogTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.data = self.root / "user-data"
        self.data.mkdir()
        self.dummy_dll = self.root / "il2cpp-output" / "DummyDll"
        self.dummy_dll.mkdir(parents=True)
        self.apk = self.root / "game.apk"
        self.apk.write_bytes(b"not a real apk")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _derive(self):
        return derive_story_outcome_catalog(self.apk, self.dummy_dll, self.data)

    def test_a_missing_dump_cs_stops_complete_setup(self) -> None:
        with self.assertRaisesRegex(TesterSetupError, "dump.cs"):
            self._derive()
        self.assertFalse((self.data / DEFAULT_OUTCOME_CATALOG).exists())

    def test_dump_cs_is_found_beside_the_dummy_dll_directory(self) -> None:
        # It is the sibling Il2CppDumper writes, so setup needs no extra option.
        (self.dummy_dll.parent / "dump.cs").write_text("", encoding="utf-8")
        (self.data / "character-catalog.json").write_text("{}", encoding="utf-8")
        with patch("liminal_gate.tester_setup.find_aarch64_objdump", return_value=None), \
             self.assertRaisesRegex(TesterSetupError, "AArch64"):
            self._derive()

    def test_a_missing_disassembler_names_the_fix(self) -> None:
        (self.dummy_dll.parent / "dump.cs").write_text("", encoding="utf-8")
        (self.data / "character-catalog.json").write_text("{}", encoding="utf-8")
        with patch("liminal_gate.tester_setup.find_aarch64_objdump", return_value=None), \
             self.assertRaisesRegex(TesterSetupError, "llvm-objdump"):
            self._derive()

    def test_a_failing_import_does_not_raise_out_of_setup(self) -> None:
        (self.dummy_dll.parent / "dump.cs").write_text("", encoding="utf-8")
        (self.data / "character-catalog.json").write_text("{}", encoding="utf-8")
        with patch("liminal_gate.tester_setup.find_aarch64_objdump", return_value="objdump"), \
             self.assertRaises(TesterSetupError):
            # The APK here is not a real one, so the import must halt rather
            # than install a build that silently loses story Companions.
            self._derive()

    def test_setup_rejects_an_absent_dummy_dll_before_building(self) -> None:
        # Pinned rather than left to the machine: a developer with Il2CppDumper
        # installed would otherwise take the auto-produce path and never reach
        # the rejection this is about.
        with patch("liminal_gate.tester_setup.find_il2cpp_dumper", return_value=None):
            with self.assertRaisesRegex(TesterSetupError, "--dummy-dll-dir"):
                _prepare_after_inputs(self.apk, self.data, dummy_dll_dir=None)

    def test_an_absent_dummy_dll_is_produced_when_il2cppdumper_is_installed(self) -> None:
        # The default location is a hint, not a requirement; having the tool is
        # enough, because both its inputs are inside the APK setup already has.
        # The other two prerequisites are pinned so this passes or fails on the
        # branch it is about rather than on what this machine has installed.
        with patch("liminal_gate.tester_setup.find_il2cpp_dumper", return_value=("Il2CppDumper",)), \
             patch("liminal_gate.tester_setup.find_missing_master_import", return_value=()), \
             patch("liminal_gate.tester_setup.find_aarch64_objdump", return_value="llvm-objdump"), \
             patch("liminal_gate.tester_setup.ensure_il2cpp_dump", side_effect=_StopSetup) as produced, \
             patch("liminal_gate.tester_setup.build_import_manifest", return_value={}), \
             patch("liminal_gate.tester_setup.write_import_manifest"), \
             patch("builtins.print"):
            with self.assertRaises(_StopSetup):
                _prepare_after_inputs(self.apk, self.data, dummy_dll_dir=None)
        produced.assert_called_once()

    def test_a_missing_disassembler_stops_before_anything_expensive(self) -> None:
        """The check used to sit after the hashing and the IL2CPP dump.

        Both of those cost minutes on a real pack, and neither is any use to a
        machine that cannot disassemble AArch64, so the toolchain is settled
        first.
        """
        inventoried = []
        with patch("liminal_gate.tester_setup.find_missing_master_import", return_value=()), \
             patch("liminal_gate.tester_setup.find_aarch64_objdump", return_value=None), \
             patch("liminal_gate.tester_setup.build_import_manifest", side_effect=lambda *_, **__: inventoried.append(1) or {}), \
             patch("liminal_gate.tester_setup.ensure_il2cpp_dump", side_effect=_StopSetup):
            with self.assertRaisesRegex(TesterSetupError, "AArch64"):
                _prepare_after_inputs(self.apk, self.data, dummy_dll_dir=self.dummy_dll)
        self.assertEqual([], inventoried, "must not hash the tree before naming the missing tool")

    def test_missing_master_import_packages_stop_before_anything_expensive(self) -> None:
        # This one used to surface from inside UnityPy, after a completed
        # inventory and a completed dump, as an import error about a package.
        inventoried = []
        with patch("liminal_gate.tester_setup.find_missing_master_import", return_value=("UnityPy",)), \
             patch("liminal_gate.tester_setup.build_import_manifest", side_effect=lambda *_, **__: inventoried.append(1) or {}), \
             patch("liminal_gate.tester_setup.ensure_il2cpp_dump", side_effect=_StopSetup):
            with self.assertRaisesRegex(TesterSetupError, "master-import"):
                _prepare_after_inputs(self.apk, self.data, dummy_dll_dir=self.dummy_dll)
        self.assertEqual([], inventoried)

    def test_the_catalog_lands_where_the_server_launcher_looks_for_it(self) -> None:
        # server_setup picks the file up by this name with no further wiring, so
        # the two must not drift apart.
        self.assertEqual("story-outcomes.json", DEFAULT_OUTCOME_CATALOG)


class EnsureIl2cppDumpTest(unittest.TestCase):
    """Exercises the real extract-and-run path, not a mocked stand-in.

    The unit tests around it patch the surrounding calls, so a fault inside --
    a missing import, a wrong archive member -- shows up only when the code
    actually runs. This runs it, against a stub dumper.
    """

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.data = self.root / "user-data"
        self.data.mkdir()
        self.apk = self.root / "game.apk"
        with zipfile.ZipFile(self.apk, "w") as archive:
            archive.writestr(IL2CPP_LIBRARY_MEMBER, b"library")
            archive.writestr(IL2CPP_METADATA_MEMBER, b"metadata")
        self.stub = self.root / "stub_dumper.py"
        self.stub.write_text(
            "import pathlib, sys\n"
            "library, metadata, output = sys.argv[1], sys.argv[2], pathlib.Path(sys.argv[3])\n"
            "assert pathlib.Path(library).read_bytes() == b'library'\n"
            "assert pathlib.Path(metadata).read_bytes() == b'metadata'\n"
            "(output / 'DummyDll').mkdir(parents=True, exist_ok=True)\n"
            "(output / 'DummyDll' / 'Assembly-CSharp.dll').write_bytes(b'')\n"
            "(output / 'dump.cs').write_text('')\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _command(self):
        return (sys.executable, str(self.stub))

    def test_extracts_both_inputs_from_the_apk_and_runs_the_dumper(self) -> None:
        with patch("liminal_gate.tester_setup.find_il2cpp_dumper", return_value=self._command()), \
             patch("builtins.print"):
            dummy_dll, dump_cs = ensure_il2cpp_dump(self.apk, self.data)
        # The stub asserts it was handed the real member bytes, so reaching here
        # means both were located inside the APK and staged correctly.
        self.assertTrue(dummy_dll.is_dir() and any(dummy_dll.glob("*.dll")))
        self.assertTrue(dump_cs.is_file())

    def test_a_second_run_reuses_the_dump_instead_of_repeating_it(self) -> None:
        with patch("liminal_gate.tester_setup.find_il2cpp_dumper", return_value=self._command()), \
             patch("builtins.print"):
            ensure_il2cpp_dump(self.apk, self.data)
            with patch("liminal_gate.tester_setup.subprocess.run") as ran:
                ensure_il2cpp_dump(self.apk, self.data)
        ran.assert_not_called()

    def test_a_dumper_that_produces_nothing_stops_setup(self) -> None:
        empty = self.root / "empty_dumper.py"
        empty.write_text("", encoding="utf-8")
        with patch("liminal_gate.tester_setup.find_il2cpp_dumper", return_value=(sys.executable, str(empty))), \
             patch("builtins.print"):
            with self.assertRaisesRegex(TesterSetupError, "DummyDll"):
                ensure_il2cpp_dump(self.apk, self.data)

    def test_an_absent_dumper_names_how_to_install_it(self) -> None:
        with patch("liminal_gate.tester_setup.find_il2cpp_dumper", return_value=None):
            with self.assertRaisesRegex(TesterSetupError, "Il2CppDumper"):
                ensure_il2cpp_dump(self.apk, self.data)


if __name__ == "__main__":
    unittest.main()
