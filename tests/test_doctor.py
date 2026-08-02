from __future__ import annotations

import json
import os
import stat
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from liminal_gate import doctor, tool_install, toolchain
from liminal_gate.tool_install import Checksum, Host, ToolInstallError


#: sha256 of b"payload", so a passing case is not merely the absence of a check.
_PAYLOAD_DIGEST = "239f59ed55e737c77147cf55ad0c1b030b6d7ee748a7426952f9b852d5a935e5"


class ChecksumTest(unittest.TestCase):
    def test_matching_content_passes_and_altered_content_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "archive"
            path.write_bytes(b"payload")
            Checksum("sha256", _PAYLOAD_DIGEST).verify(path)
            path.write_bytes(b"payload tampered with")
            with self.assertRaisesRegex(ToolInstallError, "does not match its published sha256"):
                Checksum("sha256", _PAYLOAD_DIGEST).verify(path)


class ArchiveTest(unittest.TestCase):
    def _zip(self, directory: Path, members: dict[str, str], mode: int = 0) -> Path:
        archive = directory / "archive.zip"
        with zipfile.ZipFile(archive, "w") as stream:
            for name, content in members.items():
                info = zipfile.ZipInfo(name)
                info.external_attr = mode << 16
                stream.writestr(info, content)
        return archive

    def test_a_member_escaping_the_destination_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = self._zip(root, {"../escaped": "no"})
            with self.assertRaisesRegex(ToolInstallError, "outside"):
                tool_install.extract(archive, root / "unpacked")
            self.assertFalse((root / "escaped").exists())

    @unittest.skipIf(hasattr(__import__("os"), "startfile"), "Unix permissions only")
    def test_the_executable_bit_survives_unpacking(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = self._zip(root, {"bin/sdkmanager": "#!/bin/sh\n"}, mode=0o755)
            tool_install.extract(archive, root / "unpacked")
            unpacked = root / "unpacked" / "bin" / "sdkmanager"
            # zipfile discards modes, so an sdkmanager unpacked without this
            # repair exists but cannot be run.
            self.assertTrue(unpacked.stat().st_mode & stat.S_IXUSR)

    def test_an_unknown_archive_type_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "tool.rar"
            archive.write_bytes(b"")
            with self.assertRaisesRegex(ToolInstallError, "unsupported archive type"):
                tool_install.extract(archive, Path(temporary) / "unpacked")

    def test_tar_symlink_escaping_the_destination_is_refused_by_compatibility_filter(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "archive.tar.gz"
            with tarfile.open(archive, "w:gz") as stream:
                member = tarfile.TarInfo("bin/link")
                member.type = tarfile.SYMTYPE
                member.linkname = "../../../escaped"
                stream.addfile(member)
            with tarfile.open(archive, "r:gz") as source:
                with self.assertRaisesRegex(ToolInstallError, "outside"):
                    tool_install._safe_tar_members(source, root / "unpacked")


class HostTest(unittest.TestCase):
    def test_vendor_names_are_used_for_each_supported_platform(self) -> None:
        for system, machine, expected in (
            ("Darwin", "arm64", Host("mac", "aarch64")),
            ("Darwin", "x86_64", Host("mac", "x64")),
            ("Windows", "AMD64", Host("windows", "x64")),
            ("Linux", "aarch64", Host("linux", "aarch64")),
        ):
            with self.subTest(system=system), \
                    patch("platform.system", return_value=system), \
                    patch("platform.machine", return_value=machine):
                self.assertEqual(tool_install.detect_host(), expected)

    def test_an_unsupported_platform_says_so_instead_of_guessing(self) -> None:
        with patch("platform.system", return_value="SunOS"), patch("platform.machine", return_value="sparc"):
            with self.assertRaisesRegex(ToolInstallError, "does not cover SunOS"):
                tool_install.detect_host()


class DotnetIndexTest(unittest.TestCase):
    def _index(self, digest: str = "a" * 128) -> dict:
        return {
            "latest-runtime": "8.0.29",
            "releases": [
                {"runtime": {"version": "8.0.28", "files": [
                    {"rid": "osx-arm64", "name": "old.tar.gz", "url": "https://example/old", "hash": "b" * 128},
                ]}},
                {"runtime": {"version": "8.0.29", "files": [
                    {"rid": "osx-arm64", "name": "runtime.pkg", "url": "https://example/pkg", "hash": digest},
                    {"rid": "osx-arm64", "name": "runtime.tar.gz", "url": "https://example/tar", "hash": digest},
                    {"rid": "win-x64", "name": "runtime.zip", "url": "https://example/zip", "hash": digest},
                ]}},
            ],
        }

    def test_the_latest_runtime_archive_is_chosen_over_the_installer(self) -> None:
        url, checksum, version = tool_install._dotnet_runtime_file(self._index(), Host("mac", "aarch64"))
        # The .pkg is listed first and would need an installer to run; the
        # archive is the one that can be unpacked into local storage.
        self.assertEqual(url, "https://example/tar")
        self.assertEqual((checksum.algorithm, version), ("sha512", "8.0.29"))

    def test_windows_takes_the_zip(self) -> None:
        url, _, _ = tool_install._dotnet_runtime_file(self._index(), Host("windows", "x64"))
        self.assertEqual(url, "https://example/zip")

    def test_a_checksum_of_unrecognised_length_is_refused(self) -> None:
        with self.assertRaisesRegex(ToolInstallError, "unknown type"):
            tool_install._dotnet_runtime_file(self._index(digest="abc"), Host("mac", "aarch64"))

    def test_a_platform_with_no_listed_archive_is_reported(self) -> None:
        with self.assertRaisesRegex(ToolInstallError, "no runtime archive"):
            tool_install._dotnet_runtime_file(self._index(), Host("linux", "x64"))


class DumperConfigTest(unittest.TestCase):
    def test_the_exit_keypress_is_disabled_where_it_would_break_a_captured_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            config = directory / "config.json"
            config.write_text(json.dumps({"RequireAnyKey": True, "DumpMethod": True}), encoding="utf-8")
            tool_install._silence_dumper_keypress(directory)
            document = json.loads(config.read_text(encoding="utf-8"))
            self.assertFalse(document["RequireAnyKey"])
            # Every other setting the release ships is left alone.
            self.assertTrue(document["DumpMethod"])

    def test_a_missing_config_does_not_fail_the_install(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            tool_install._silence_dumper_keypress(Path(temporary))


class EnvironmentIsolatedTest(unittest.TestCase):
    """Base for tests that record a location, which applies it to this process.

    Recording is supposed to reach the real environment -- that is how a
    launcher picks the locations up -- so these tests have to put it back. A
    leaked `LIMINAL_GATE_IL2CPPDUMPER` naming a deleted temporary directory
    changes what unrelated suites see setup report.
    """

    def setUp(self) -> None:
        isolated = patch.dict(os.environ)
        isolated.start()
        self.addCleanup(isolated.stop)


def _statuses(**missing: bool) -> list[doctor.ToolStatus]:
    names = ("java", "platform tools", "build tools", "SDK platform", "UnityPy", "Il2CppDumper", "disassembler")
    return [doctor.ToolStatus(name, not missing.get(name.replace(" ", "_"), False), "") for name in names]


class DoctorSurveyTest(unittest.TestCase):
    def test_missing_compile_sdk_is_reported_even_when_build_tools_exist(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            sdk = Path(temporary) / "sdk"
            tools = sdk / "build-tools" / "36.1.0"
            tools.mkdir(parents=True)
            with patch.object(doctor.tester_setup, "find_build_tools", return_value=(tools / "zipalign", tools / "apksigner")):
                statuses = doctor.survey(Host("mac", "aarch64"))
        platform = next(status for status in statuses if status.name == "SDK platform")
        self.assertFalse(platform.ok)
        self.assertIn("platform 35", platform.detail)

    def test_a_missing_tool_carries_its_own_instruction_into_the_report(self) -> None:
        with patch.object(doctor.tester_setup, "find_il2cpp_dumper", return_value=None):
            statuses = doctor.survey(Host("mac", "aarch64"))
        dumper = next(status for status in statuses if status.name == "Il2CppDumper")
        self.assertFalse(dumper.ok)
        self.assertIn("Il2CppDumper", dumper.detail)

    def test_the_disassembler_is_reported_as_beyond_this_commands_reach(self) -> None:
        with patch.object(doctor.tester_setup, "find_aarch64_objdump", return_value=None):
            statuses = doctor.survey(Host("mac", "aarch64"))
        disassembler = next(status for status in statuses if status.name == "disassembler")
        self.assertFalse(disassembler.fixable)
        self.assertIn("xcode-select", disassembler.detail)


class DoctorDiscoveryTest(EnvironmentIsolatedTest):
    def test_a_disassembler_installed_but_off_path_is_recorded_before_judging(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary)
            found = data / "objdump"
            found.write_text("", encoding="utf-8")
            with patch.object(doctor.tester_setup, "find_aarch64_objdump", return_value=None), \
                    patch.object(doctor, "find_objdump", return_value=found):
                updated = doctor.record_discoveries(data, toolchain.Toolchain(), Host("mac", "aarch64"))
            self.assertEqual(updated.objdump, found)
            self.assertEqual(toolchain.load(data).objdump, found.resolve())

    def test_nothing_is_recorded_when_the_disassembler_is_already_reachable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary)
            with patch.object(doctor.tester_setup, "find_aarch64_objdump", return_value="objdump"):
                self.assertTrue(doctor.record_discoveries(data, toolchain.Toolchain(), Host("mac", "aarch64")).is_empty())
            self.assertFalse(toolchain.toolchain_path(data).exists())


class DoctorInstallTest(EnvironmentIsolatedTest):
    def test_unsupported_arm_host_fails_before_downloading_a_jdk_for_the_sdk(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(doctor.shutil, "which", return_value=None), \
                patch.object(doctor.tool_install, "install_jdk") as install_jdk:
            with self.assertRaisesRegex(ToolInstallError, "does not publish"):
                doctor.install_missing(
                    _statuses(platform_tools=True), Path(temporary), Host("linux", "aarch64"),
                    toolchain.Toolchain(), accept_licences=True, packages=(),
                )
        install_jdk.assert_not_called()

    def test_the_android_sdk_is_not_installed_without_accepting_the_licences(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(doctor.shutil, "which", return_value="/usr/bin/java"):
            with self.assertRaisesRegex(ToolInstallError, "licen[cs]es"):
                doctor.install_missing(
                    _statuses(platform_tools=True), Path(temporary), Host("mac", "aarch64"),
                    toolchain.Toolchain(), accept_licences=False, packages=(),
                )

    def test_missing_compile_sdk_triggers_android_package_install(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(doctor.shutil, "which", return_value="/usr/bin/java"), \
                patch.object(doctor.tool_install, "accept_android_licences"), \
                patch.object(doctor.tool_install, "install_android_packages", return_value=Path(temporary) / "sdk") as install:
            doctor.install_missing(
                _statuses(SDK_platform=True), Path(temporary), Host("mac", "aarch64"),
                toolchain.Toolchain(), accept_licences=True,
                packages=tool_install.ANDROID_PACKAGES,
            )
        self.assertIn("platforms;android-35", install.call_args.args[4])

    def test_a_jdk_is_fetched_for_sdkmanager_even_when_keytool_was_found(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary)
            java_home = data / "jdk"
            java_home.mkdir()
            with patch.object(doctor.shutil, "which", return_value=None), \
                    patch.object(doctor.tool_install, "install_jdk", return_value=java_home) as install_jdk, \
                    patch.object(doctor.tool_install, "accept_android_licences") as accept, \
                    patch.object(doctor.tool_install, "install_android_packages", return_value=data / "sdk") as packages:
                doctor.install_missing(
                    _statuses(platform_tools=True), data, Host("mac", "aarch64"),
                    toolchain.Toolchain(), accept_licences=True, packages=("platform-tools",),
                )
            install_jdk.assert_called_once()
            accept.assert_called_once()
            # sdkmanager is itself a Java program, so it has to be handed the
            # JDK that was just installed rather than run with none.
            self.assertEqual(packages.call_args.args[3], java_home)
            self.assertEqual(toolchain.load(data).java_home, java_home.resolve())

    def test_no_jdk_is_fetched_when_java_is_already_runnable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(doctor.shutil, "which", return_value="/usr/bin/java"), \
                patch.object(doctor.tool_install, "install_jdk") as install_jdk, \
                patch.object(doctor, "install_master_import"):
            doctor.install_missing(
                _statuses(UnityPy=True), Path(temporary), Host("mac", "aarch64"),
                toolchain.Toolchain(), accept_licences=False, packages=(),
            )
        install_jdk.assert_not_called()

    def test_a_runtime_is_fetched_only_when_the_managed_dumper_has_none(self) -> None:
        for reachable, expected in ((None, True), (("dotnet", "Il2CppDumper.dll"), False)):
            with self.subTest(reachable=reachable), tempfile.TemporaryDirectory() as temporary:
                data = Path(temporary)
                dumper = data / "Il2CppDumper.dll"
                dumper.write_text("", encoding="utf-8")
                with patch.object(doctor.shutil, "which", return_value="/usr/bin/java"), \
                        patch.object(doctor.tool_install, "install_il2cpp_dumper", return_value=dumper), \
                        patch.object(doctor.tester_setup, "find_il2cpp_dumper", return_value=reachable), \
                        patch.object(doctor.tool_install, "install_dotnet_runtime", return_value=data) as runtime:
                    doctor.install_missing(
                        _statuses(Il2CppDumper=True), data, Host("mac", "aarch64"),
                        toolchain.Toolchain(), accept_licences=False, packages=(),
                    )
                self.assertEqual(runtime.called, expected)

    def test_each_success_is_recorded_before_a_later_step_can_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary)
            java_home = data / "jdk"
            java_home.mkdir()
            with patch.object(doctor.shutil, "which", return_value=None), \
                    patch.object(doctor.tool_install, "install_jdk", return_value=java_home), \
                    patch.object(doctor.tool_install, "accept_android_licences", side_effect=ToolInstallError("network died")):
                with self.assertRaisesRegex(ToolInstallError, "network died"):
                    doctor.install_missing(
                        _statuses(java=True, platform_tools=True), data, Host("mac", "aarch64"),
                        toolchain.Toolchain(), accept_licences=True, packages=(),
                    )
            # The JDK really was installed, so a re-run must not fetch it again.
            self.assertEqual(toolchain.load(data).java_home, java_home.resolve())


class LicenceConfirmationTest(unittest.TestCase):
    def test_only_an_explicit_yes_accepts_someone_elses_licence(self) -> None:
        for answer, expected in (("y", True), ("yes", True), ("", False), ("n", False), ("sure", False)):
            with self.subTest(answer=answer):
                self.assertEqual(doctor.confirm_android_licences(lambda _: answer), expected)

    def test_a_non_interactive_run_does_not_accept_by_default(self) -> None:
        def refuse(_: str) -> str:
            raise EOFError

        self.assertFalse(doctor.confirm_android_licences(refuse))


if __name__ == "__main__":
    unittest.main()
