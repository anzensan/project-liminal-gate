"""Prepare, install, and run the local emulator tester path in one command.

All inputs remain user-local. This command neither downloads nor copies an APK
or resource pack. It redirects a user-supplied APK to the local server only.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
from typing import Sequence

from liminal_gate.apk_patcher import PatchPlanError, apply_patch_plan, load_patch_plan
from liminal_gate.apk_signer import ApkSigningError, sign_apk
from liminal_gate.input_importer import ImportError, build_import_manifest, write_import_manifest
from liminal_gate.legacy_client_apk_plan import generate_legacy_client_plan
from liminal_gate.resource_catalog import ResourceCatalogError
from liminal_gate.resource_catalog_builder import build_resource_manifest, write_resource_manifest


class TesterSetupError(RuntimeError):
    """The local tester environment is incomplete or ambiguous."""


DEFAULT_APK = Path("local-input/terra-battle-5.5.7-170.apk")
DEFAULT_RESOURCES = Path("local-input/resources/data_u2017/android")
DEFAULT_DATA = Path("user-data")
KEY_ALIAS = "liminal-gate-test"


def _adb_devices(adb: str) -> tuple[str, ...]:
    try:
        result = subprocess.run((adb, "devices"), check=True, text=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError) as error:
        raise TesterSetupError("adb is unavailable; start an Android emulator and ensure adb is on PATH") from error
    devices: list[str] = []
    for line in result.stdout.splitlines()[1:]:
        fields = line.split()
        if len(fields) >= 2 and fields[1] == "device":
            devices.append(fields[0])
    return tuple(devices)


def select_emulator(adb: str, requested: str | None) -> str:
    devices = _adb_devices(adb)
    if requested is not None:
        if requested not in devices:
            available = ", ".join(devices) if devices else "none"
            raise TesterSetupError(f"requested emulator {requested!r} is not ready (available: {available})")
        return requested
    if len(devices) == 1:
        return devices[0]
    if not devices:
        raise TesterSetupError("no ready Android emulator found; start one and rerun")
    raise TesterSetupError("multiple Android devices are ready; rerun with --emulator one of: " + ", ".join(devices))


def find_build_tools(explicit: Path | None) -> tuple[Path, Path]:
    if explicit is not None:
        root = explicit
        choices = (root,)
    else:
        sdk_root = Path(os.environ.get("ANDROID_SDK_ROOT", Path.home() / "Library/Android/sdk"))
        build_tools_root = sdk_root / "build-tools"
        choices = tuple(sorted(
            (path for path in build_tools_root.iterdir() if path.is_dir()),
            key=lambda path: tuple((0, int(part)) if part.isdigit() else (1, part) for part in path.name.replace("-", ".").split(".")),
            reverse=True,
        )) if build_tools_root.is_dir() else ()
    for candidate in choices:
        zipalign, apksigner = candidate / "zipalign", candidate / "apksigner"
        if zipalign.is_file() and apksigner.is_file():
            return zipalign, apksigner
    location = str(explicit) if explicit is not None else "$ANDROID_SDK_ROOT/build-tools or ~/Library/Android/sdk/build-tools"
    raise TesterSetupError(f"could not find zipalign and apksigner under {location}; install Android SDK Build Tools or pass --build-tools")


def write_password_file(path: Path, password: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, stat.S_IRUSR | stat.S_IWUSR)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(password)


def ensure_keystore(keystore: Path, password_file: Path) -> None:
    if keystore.is_file() and password_file.is_file():
        return
    if shutil.which("keytool") is None:
        raise TesterSetupError("keytool is unavailable; install a JDK and reopen the terminal")
    password = getpass.getpass("Choose a local test-key password: ")
    if not password:
        raise TesterSetupError("a nonempty local test-key password is required")
    if not keystore.exists() and password != getpass.getpass("Repeat local test-key password: "):
        raise TesterSetupError("test-key passwords did not match")
    if not keystore.exists():
        try:
            subprocess.run((
                "keytool", "-genkeypair", "-v", "-keystore", str(keystore), "-alias", KEY_ALIAS,
                "-keyalg", "RSA", "-keysize", "2048", "-validity", "10000",
                "-dname", "CN=Local Tester, OU=Testing, O=Project Liminal Gate, L=Local, ST=Local, C=US",
                "-storepass", password, "-keypass", password,
            ), check=True)
        except (OSError, subprocess.CalledProcessError) as error:
            raise TesterSetupError("could not create the local test keystore") from error
    write_password_file(password_file, password)


def prepare_local_tester(
    apk: Path, resource_root: Path, data_directory: Path, port: int, build_tools: Path | None,
) -> Path:
    """Build the redirected, locally signed APK and return its path."""
    if not 1 <= port <= 65535:
        raise TesterSetupError("--port must be an integer from 1 through 65535")
    apk, resource_root = apk.resolve(), resource_root.resolve()
    data_directory.mkdir(parents=True, exist_ok=True)
    try:
        imported = build_import_manifest(apk, resource_root, reviewed_android_5_5_7=True)
        write_import_manifest(data_directory / "input-manifest", imported)
        manifest = build_resource_manifest(resource_root)
        resource_manifest = data_directory / "resources.json"
        write_resource_manifest(resource_manifest, manifest)
        plan = generate_legacy_client_plan(apk, f"http://10.0.2.2:{port}")
        plan_path = data_directory / "local-server-plan.json"
        plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        unsigned = data_directory / "liminal-gate-unsigned.apk"
        apply_patch_plan(apk, unsigned, load_patch_plan(plan_path))
        keystore, password_file = data_directory / "liminal-gate-test.keystore", data_directory / "keystore-password.txt"
        ensure_keystore(keystore, password_file)
        zipalign, apksigner = find_build_tools(build_tools)
        signed = data_directory / "liminal-gate-test.apk"
        sign_apk(unsigned, signed, zipalign, apksigner, keystore, KEY_ALIAS, password_file, password_file)
    except (OSError, ImportError, ResourceCatalogError, PatchPlanError, ApkSigningError, ValueError) as error:
        raise TesterSetupError(str(error)) from error
    print(f"Prepared local test APK: {signed}")
    return signed


def server_arguments(resource_root: Path, data_directory: Path, port: int) -> list[str]:
    return [
        sys.executable, "-m", "liminal_gate.bootstrap_server",
        "--profile", "profiles/legacy-client-bootstrap.json",
        "--state-file", str(data_directory / "bootstrap-state.json"),
        "--host", "0.0.0.0", "--port", str(port),
        "--event-log", str(data_directory / "events.jsonl"),
        "--resource-root", str(resource_root),
        "--resource-manifest", str(data_directory / "resources.json"),
        "--core-story",
        "--pacts",
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apk", type=Path, default=DEFAULT_APK)
    parser.add_argument("--resource-root", type=Path, default=DEFAULT_RESOURCES)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--port", type=int, default=8002)
    parser.add_argument("--emulator", help="adb serial; required only when more than one device is ready")
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--build-tools", type=Path, help="Android SDK Build Tools version directory")
    parser.add_argument("--prepare-only", action="store_true", help="build the APK but do not install it or start the server")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        signed = prepare_local_tester(args.apk, args.resource_root, args.data_dir, args.port, args.build_tools)
        if args.prepare_only:
            return 0
        emulator = select_emulator(args.adb, args.emulator)
        subprocess.run((args.adb, "-s", emulator, "install", "-r", str(signed)), check=True)
        print(f"Installed on {emulator}. Starting the local server; press Control-C when finished.")
        os.execv(sys.executable, server_arguments(args.resource_root.resolve(), args.data_dir, args.port))
    except (TesterSetupError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"tester setup failed: {error}") from error
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
