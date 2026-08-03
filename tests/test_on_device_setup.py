from __future__ import annotations

from io import StringIO
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from liminal_gate import on_device_setup


class OnDeviceSetupTest(unittest.TestCase):
    def test_preflight_warning_summary_does_not_claim_no_device_is_running(self) -> None:
        checks = [on_device_setup.Check("device", False, "choose --device", required=False)]
        with patch("sys.stdout", new_callable=StringIO) as output:
            self.assertEqual(0, on_device_setup.report_preflight(checks))
        self.assertIn("resolve each warning", output.getvalue())
        self.assertNotIn("start a device", output.getvalue())

    def test_build_id_changes_with_embedded_host_source_but_ignores_build_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = root / "resources.json"
            manifest.write_text("{}", encoding="utf-8")
            host = root / "host"
            source = host / "app/src/main"
            source.mkdir(parents=True)
            authored = source / "HostedActivity.java"
            authored.write_text("first", encoding="utf-8")
            first = on_device_setup._build_id(
                "a" * 64, "b" * 64, manifest, {}, {}, host,
            )
            generated = host / "app/build/generated.bin"
            generated.parent.mkdir(parents=True)
            generated.write_bytes(b"ignored")
            self.assertEqual(
                first,
                on_device_setup._build_id(
                    "a" * 64, "b" * 64, manifest, {}, {}, host,
                ),
            )
            authored.write_text("second", encoding="utf-8")
            self.assertNotEqual(
                first,
                on_device_setup._build_id(
                    "a" * 64, "b" * 64, manifest, {}, {}, host,
                ),
            )

    def test_device_requires_supported_abi_not_both(self) -> None:
        with patch.object(on_device_setup, "device_facts", return_value=(34, ("arm64-v8a",), 5 * 1024**3)):
            self.assertIn("arm64-v8a", on_device_setup.validate_device("adb", "phone"))

    def test_device_rejects_old_api_low_space_and_unknown_abi(self) -> None:
        for facts, expected in (
            ((23, ("arm64-v8a",), 5 * 1024**3), "API 24"),
            ((34, ("x86",), 5 * 1024**3), "does not advertise"),
            ((34, ("armeabi-v7a",), 3 * 1024**3), "free"),
        ):
            with self.subTest(facts=facts), patch.object(on_device_setup, "device_facts", return_value=facts):
                with self.assertRaisesRegex(on_device_setup.OnDeviceSetupError, expected):
                    on_device_setup.validate_device("adb", "device")

    def test_preflight_rejects_unreviewed_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            apk = Path(temporary) / "game.apk"; apk.write_bytes(b"not reviewed")
            checks = on_device_setup.preflight_checks(apk, Path(temporary), Path(temporary), Path(temporary), None, "adb", None)
        source = next(check for check in checks if check.name == "APK")
        self.assertFalse(source.ok)
        self.assertIn("reviewed", source.detail)

    def test_gradle_is_cached_only_under_work_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary) / "user-data/work"
            executable = on_device_setup._gradle_path(work)
            executable.parent.mkdir(parents=True); executable.write_text("local", encoding="utf-8")
            executable.chmod(0o755)
            self.assertEqual(executable, on_device_setup.ensure_gradle(work, download=False))

    def test_gradle_download_uses_the_published_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(on_device_setup.tool_install, "download", side_effect=on_device_setup.tool_install.ToolInstallError("checksum mismatch")) as fetch:
            with self.assertRaisesRegex(on_device_setup.OnDeviceSetupError, "checksum mismatch"):
                on_device_setup.ensure_gradle(Path(temporary), download=True)
        checksum = fetch.call_args.args[3]
        self.assertEqual(("sha256", on_device_setup.GRADLE_SHA256), (checksum.algorithm, checksum.hexdigest))


    def test_prepare_runs_guided_derivation_then_fixed_loopback_assembly(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); apk = root / "game.apk"; apk.write_bytes(b"source")
            resources = root / "resources"; resources.mkdir(); data = root / "data"; host = root / "host"; host.mkdir()
            for name in on_device_setup.REQUIRED_CATALOGS:
                data.mkdir(exist_ok=True); (data / name).write_text("{}", encoding="utf-8")
            banners = data / "public_data" / "banners"; banners.mkdir(parents=True)
            for name in on_device_setup.PACT_BANNERS:
                (banners / f"{name}_en.png").write_bytes(b"png")
            coin_creeps = data / "public_data" / "banner_resources"
            coin_creeps.mkdir()
            for alias in on_device_setup.COIN_CREEPS_BANNER_ALIASES:
                (coin_creeps / on_device_setup.hashed_resource_name(alias)).write_bytes(b"enca")
            plan = {"schema_version": 1}
            signed = data / "on-device-liminal-gate.apk"
            with patch.object(on_device_setup, "sha256_file", return_value=on_device_setup.REVIEWED_SOURCE_SHA256), \
                 patch.object(on_device_setup.tester_setup, "resolve_resource_root", return_value=resources), \
                 patch.object(on_device_setup.tester_setup, "prepare_local_tester") as derive, \
                 patch.object(on_device_setup.tester_setup, "ensure_keystore"), \
                 patch.object(on_device_setup.tester_setup, "find_build_tools", return_value=(root / "zipalign", root / "apksigner")), \
                 patch.object(on_device_setup, "generate_legacy_client_plan", return_value=plan), \
                 patch.object(on_device_setup, "load_patch_plan", return_value=object()), \
                 patch.object(on_device_setup, "apply_patch_plan"), \
                 patch.object(on_device_setup, "_build_id", return_value="a" * 64), \
                 patch.object(on_device_setup, "build_host_apk", return_value=root / "host.apk"), \
                 patch.object(on_device_setup, "_assembly_module", return_value=object()), \
                 patch.object(on_device_setup, "_call_assembler") as assemble, \
                 patch.object(on_device_setup, "sign_apk"):
                self.assertEqual(signed, on_device_setup.prepare_on_device_apk(apk, resources, data, host, None, False))
            derive.assert_called_once()
            self.assertEqual(on_device_setup.LOOPBACK_PORT, derive.call_args.args[3])
            self.assertEqual("a" * 64, assemble.call_args.kwargs["build_id"])
            self.assertEqual(
                {"server.json"} | {
                    f"public_data/banners/{name}_en.png"
                    for name in on_device_setup.PACT_BANNERS
                } | {
                    f"public_data/banner_resources/{on_device_setup.hashed_resource_name(alias)}"
                    for alias in on_device_setup.COIN_CREEPS_BANNER_ALIASES
                },
                set(assemble.call_args.kwargs["runtime_files"]),
            )

    def test_launch_happens_only_after_install(self) -> None:
        completed = subprocess.CompletedProcess((), 0, "Status: ok\n", "")
        with patch.object(on_device_setup.subprocess, "run", return_value=completed) as run:
            on_device_setup.launch_apk("adb", "serial")
        command = run.call_args.args[0]
        self.assertIn("am", command)
        self.assertIn(
            f"{on_device_setup.tester_setup.PACKAGE_NAME}/{on_device_setup.HOST_ACTIVITY}",
            command,
        )
