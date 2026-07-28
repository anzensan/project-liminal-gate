"""The guided setup derives the story Companion drop catalog, or says why not.

Without `user-data/story-outcomes.json` a story clear mints no Companion at all:
the client rolls the drop and `clear_quest` has no authority to write it. The
file cannot be shipped -- it is derived from the operator's own APK -- so the
one-command setup has to build it, and a missing prerequisite has to degrade
rather than fail an install that is otherwise fine.
"""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from liminal_gate.server_setup import DEFAULT_OUTCOME_CATALOG
from liminal_gate.tester_setup import (
    STORY_DROPS_NEED_DUMMY_DLL,
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

    def test_a_missing_dump_cs_is_reported_and_setup_continues(self) -> None:
        with patch("builtins.print") as printed:
            self.assertIsNone(self._derive())
        self.assertIn("dump.cs", " ".join(str(call.args[0]) for call in printed.call_args_list))
        self.assertFalse((self.data / DEFAULT_OUTCOME_CATALOG).exists())

    def test_dump_cs_is_found_beside_the_dummy_dll_directory(self) -> None:
        # It is the sibling Il2CppDumper writes, so setup needs no extra option.
        (self.dummy_dll.parent / "dump.cs").write_text("", encoding="utf-8")
        (self.data / "character-catalog.json").write_text("{}", encoding="utf-8")
        with patch("liminal_gate.tester_setup.find_aarch64_objdump", return_value=None), \
             patch("builtins.print") as printed:
            self.assertIsNone(self._derive())
        message = " ".join(str(call.args[0]) for call in printed.call_args_list)
        self.assertNotIn("dump.cs", message)
        self.assertIn("AArch64", message)

    def test_a_missing_disassembler_names_the_fix(self) -> None:
        (self.dummy_dll.parent / "dump.cs").write_text("", encoding="utf-8")
        (self.data / "character-catalog.json").write_text("{}", encoding="utf-8")
        with patch("liminal_gate.tester_setup.find_aarch64_objdump", return_value=None), \
             patch("builtins.print") as printed:
            self.assertIsNone(self._derive())
        message = " ".join(str(call.args[0]) for call in printed.call_args_list)
        self.assertIn("llvm-objdump", message)

    def test_a_failing_import_does_not_raise_out_of_setup(self) -> None:
        (self.dummy_dll.parent / "dump.cs").write_text("", encoding="utf-8")
        (self.data / "character-catalog.json").write_text("{}", encoding="utf-8")
        with patch("liminal_gate.tester_setup.find_aarch64_objdump", return_value="objdump"), \
             patch("builtins.print"):
            # The APK here is not a real one, so the import fails inside. An
            # install that is otherwise fine must survive that.
            self.assertIsNone(self._derive())

    def test_the_absent_dummy_dll_notice_names_the_option_and_the_exception(self) -> None:
        """Silence here reads as "drops work", and is found hours later.

        Every other feature works without a DummyDll directory, so nothing else
        in the run hints that one outcome is missing.
        """
        self.assertIn("--dummy-dll-dir", STORY_DROPS_NEED_DUMMY_DLL)
        self.assertIn("Metal Zone", STORY_DROPS_NEED_DUMMY_DLL)

    def test_setup_prints_that_notice_when_no_dummy_dll_directory_is_given(self) -> None:
        printed: list[str] = []
        with patch("liminal_gate.tester_setup.build_import_manifest", return_value={}), \
             patch("liminal_gate.tester_setup.write_import_manifest"), \
             patch("liminal_gate.tester_setup.build_resource_manifest", side_effect=_StopSetup), \
             patch("builtins.print", side_effect=lambda *args, **_kw: printed.append(str(args[0]) if args else "")):
            with self.assertRaises(_StopSetup):
                _prepare_after_inputs(self.apk, self.data, dummy_dll_dir=None)
        self.assertIn(STORY_DROPS_NEED_DUMMY_DLL, printed)

    def test_setup_stays_quiet_about_drops_when_it_will_derive_them(self) -> None:
        printed: list[str] = []
        with patch("liminal_gate.tester_setup.build_import_manifest", return_value={}), \
             patch("liminal_gate.tester_setup.write_import_manifest"), \
             patch("liminal_gate.tester_setup.load_master_trees", side_effect=_StopSetup), \
             patch("builtins.print", side_effect=lambda *args, **_kw: printed.append(str(args[0]) if args else "")):
            with self.assertRaises(_StopSetup):
                _prepare_after_inputs(self.apk, self.data, dummy_dll_dir=self.dummy_dll)
        self.assertNotIn(STORY_DROPS_NEED_DUMMY_DLL, printed)

    def test_the_catalog_lands_where_the_server_launcher_looks_for_it(self) -> None:
        # server_setup picks the file up by this name with no further wiring, so
        # the two must not drift apart.
        self.assertEqual("story-outcomes.json", DEFAULT_OUTCOME_CATALOG)


if __name__ == "__main__":
    unittest.main()
