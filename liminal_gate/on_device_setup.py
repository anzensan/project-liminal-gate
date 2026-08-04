"""Build a private single-APK Android test package for the on-device server.

The generated APK is intentionally a local artifact.  It contains neither a
downloaded client nor project-distributed game resources: both inputs must be
supplied by the tester.  The embedded server is always bound to
``127.0.0.1:8002`` inside the Android app.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import importlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

from liminal_gate import tester_setup, tool_install, toolchain
from liminal_gate.android_entrypoint import LOOPBACK_HOST, LOOPBACK_PORT
from liminal_gate.apk_patcher import apply_patch_plan, load_patch_plan
from liminal_gate.apk_signer import sign_apk
from liminal_gate.legacy_client_apk_plan import generate_legacy_client_plan
from liminal_gate.coin_creeps_banner import ALIASES as COIN_CREEPS_BANNER_ALIASES, hashed_resource_name
from liminal_gate.pact_banner_importer import PACT_BANNERS


DEFAULT_APK = tester_setup.DEFAULT_APK
DEFAULT_RESOURCES = tester_setup.DEFAULT_RESOURCES
DEFAULT_DATA = tester_setup.DEFAULT_DATA
DEFAULT_HOST_SOURCE = Path("android-host")
HOST_ACTIVITY = "org.liminalgate.android.HostedActivity"
MINIMUM_DEVICE_API = 24
MINIMUM_DEVICE_FREE_BYTES = 4 * 1024**3
REVIEWED_SOURCE_SHA256 = "f2c0ffa188255f4694f0f60e898a58b372c2cc3fff7dd312a01d593189bd7a15"
GRADLE_VERSION = "8.11.1"
GRADLE_URL = f"https://services.gradle.org/distributions/gradle-{GRADLE_VERSION}-bin.zip"
GRADLE_SHA256 = "f397b287023acdba1e9f6fc5ea72d22dd63669d59ed4a289a29b1a76eee151c6"
GRADLE_JAVA_MINIMUM = 17
GRADLE_JAVA_MAXIMUM = 23
REQUIRED_CATALOGS = (
    "character-catalog.json", "companion-equipment.json", "event-catalog.json", "story-outcomes.json",
)


class OnDeviceSetupError(RuntimeError):
    """The private on-device package cannot safely be prepared or installed."""


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str
    required: bool = True

    @property
    def marker(self) -> str:
        return "ok  " if self.ok else ("FAIL" if self.required else "warn")


def _assembly_module():
    """Load the separately owned APK assembler only when its functionality is used."""
    try:
        return importlib.import_module("liminal_gate.on_device_apk")
    except ImportError as error:
        raise OnDeviceSetupError(
            "the on-device APK assembler is unavailable; update this source checkout so "
            "liminal_gate.on_device_apk and android-host are present before building"
        ) from error


def _call_assembler(module: object, **kwargs: object) -> object:
    """Call the assembly entry point without duplicating packaging/signing logic here."""
    assemble = getattr(module, "assemble_on_device_apk", None)
    if not callable(assemble):
        raise OnDeviceSetupError(
            "liminal_gate.on_device_apk must provide assemble_on_device_apk; update both "
            "on-device modules from the same source revision"
        )
    try:
        result = assemble(**kwargs)
    except (OSError, ValueError, RuntimeError) as error:
        raise OnDeviceSetupError(str(error)) from error
    return result


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _gradle_path(work_directory: Path) -> Path:
    suffix = ".bat" if os.name == "nt" else ""
    return work_directory.resolve() / "gradle" / f"gradle-{GRADLE_VERSION}" / "bin" / f"gradle{suffix}"


def ensure_gradle(work_directory: Path, *, download: bool) -> Path:
    """Use only a pinned Gradle distribution under ignored user-local work data."""
    executable = _gradle_path(work_directory)
    if executable.is_file():
        if os.name != "nt" and not os.access(executable, os.X_OK):
            if not download:
                raise OnDeviceSetupError(
                    f"cached Gradle launcher is not executable at {executable}; the normal setup "
                    "command repairs its local mode before building"
                )
            executable.chmod(
                executable.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH,
            )
        return executable
    if not download:
        raise OnDeviceSetupError(
            f"pinned Gradle {GRADLE_VERSION} is not cached at {executable}. Run the normal setup "
            "command once while online; it downloads only into ignored user-data/work/."
        )
    archive = work_directory / "gradle" / f"gradle-{GRADLE_VERSION}-bin.zip"
    archive.parent.mkdir(parents=True, exist_ok=True)
    try:
        tool_install.download(
            GRADLE_URL,
            archive,
            f"Gradle {GRADLE_VERSION}",
            tool_install.Checksum("sha256", GRADLE_SHA256),
        )
        with zipfile.ZipFile(archive) as source:
            root = (work_directory / "gradle").resolve()
            for member in source.infolist():
                target = (root / member.filename).resolve()
                if target != root and root not in target.parents:
                    raise OnDeviceSetupError("Gradle distribution contained an unsafe path")
            source.extractall(root)
    except (OSError, zipfile.BadZipFile, tool_install.ToolInstallError) as error:
        raise OnDeviceSetupError(
            f"could not download pinned Gradle {GRADLE_VERSION} into {archive.parent}: {error}"
        ) from error
    if not executable.is_file():
        raise OnDeviceSetupError("pinned Gradle download did not contain its expected executable")
    if os.name != "nt":
        executable.chmod(
            executable.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH,
        )
    return executable


def resolve_gradle_java_home() -> tuple[Path, int]:
    """Find a JDK supported by pinned Gradle, preferring explicit local choices."""
    candidates: list[Path] = []
    for variable in ("JAVA_HOME", "STUDIO_JDK", "JDK_HOME"):
        value = os.environ.get(variable)
        if value:
            candidates.append(Path(value))
    candidates.extend((
        Path("/Applications/Android Studio.app/Contents/jbr/Contents/Home"),
        Path("/opt/android-studio/jbr"),
    ))
    program_files = os.environ.get("PROGRAMFILES")
    if program_files:
        candidates.append(Path(program_files) / "Android/Android Studio/jbr")
    current_java = shutil.which("java")
    if current_java:
        candidates.append(Path(current_java).resolve().parent.parent)
    seen: set[Path] = set()
    found: list[str] = []
    for candidate in candidates:
        candidate = candidate.expanduser().resolve()
        if candidate in seen:
            continue
        seen.add(candidate)
        java = candidate / "bin" / ("java.exe" if os.name == "nt" else "java")
        if not java.is_file():
            continue
        try:
            result = subprocess.run(
                (str(java), "-version"), text=True, capture_output=True, check=True,
            )
        except (OSError, subprocess.CalledProcessError):
            continue
        output = f"{result.stdout}\n{result.stderr}"
        match = re.search(r'version\s+"(?:1\.)?(\d+)', output)
        if match is None:
            continue
        major = int(match.group(1))
        found.append(f"{candidate} (Java {major})")
        if GRADLE_JAVA_MINIMUM <= major <= GRADLE_JAVA_MAXIMUM:
            return candidate, major
    detail = "; found " + ", ".join(found) if found else ""
    raise OnDeviceSetupError(
        f"the Android host build needs Java {GRADLE_JAVA_MINIMUM}-{GRADLE_JAVA_MAXIMUM}; "
        f"install Android Studio or set JAVA_HOME to a compatible JDK{detail}"
    )


def catalog_inputs(data_directory: Path) -> dict[str, Path]:
    """Require the shared tester derivations instead of recreating gameplay setup."""
    result = {name: data_directory / name for name in REQUIRED_CATALOGS}
    missing = [name for name, path in result.items() if not path.is_file()]
    if missing:
        raise OnDeviceSetupError(
            "guided catalog derivation did not create every required input: "
            + ", ".join(missing)
        )
    return result


def public_data_inputs(data_directory: Path) -> dict[str, Path]:
    """Name the generated UI/resource payloads used by the full setup."""
    result = {
        f"public_data/banners/{name}_en.png":
            data_directory / "public_data" / "banners" / f"{name}_en.png"
        for name in PACT_BANNERS
    }
    for alias in COIN_CREEPS_BANNER_ALIASES:
        filename = hashed_resource_name(alias)
        path = data_directory / "public_data" / "banner_resources" / filename
        if path.is_file():
            result[f"public_data/banner_resources/{filename}"] = path
    missing = [name for name, path in result.items() if not path.is_file()]
    if missing:
        raise OnDeviceSetupError(
            "complete on-device setup could not derive every Pact banner; missing: "
            + ", ".join(missing)
        )
    return result


def _build_id(
    source_sha256: str,
    patched_sha256: str,
    resource_manifest: Path,
    catalogs: dict[str, Path],
    public_data: dict[str, Path],
    host_source: Path,
) -> str:
    """Bind readiness to the exact client, content, and embedded host sources."""
    digest = hashlib.sha256()
    digest.update(source_sha256.encode())
    digest.update(patched_sha256.encode())
    digest.update(sha256_file(resource_manifest).encode())
    for name, path in sorted(catalogs.items()):
        digest.update(name.encode())
        digest.update(sha256_file(path).encode())
    for name, path in sorted(public_data.items()):
        digest.update(name.encode())
        digest.update(sha256_file(path).encode())
    _update_source_tree_digest(
        digest,
        host_source,
        "android-host",
        ignored=(".gradle", "build", "__pycache__", "*.pyc"),
    )
    _update_source_tree_digest(
        digest,
        Path(__file__).parent,
        "liminal_gate",
        ignored=("__pycache__", "*.pyc", "test*"),
    )
    profile = Path(__file__).resolve().parent.parent / "profiles/legacy-client-bootstrap.json"
    digest.update(b"profile\0")
    digest.update(sha256_file(profile).encode())
    digest.update(f"{LOOPBACK_HOST}:{LOOPBACK_PORT}".encode())
    return digest.hexdigest()


def _update_source_tree_digest(
    digest: Any,
    root: Path,
    label: str,
    *,
    ignored: tuple[str, ...],
) -> None:
    """Hash the authored files copied into the isolated Android host build."""
    try:
        root = root.resolve(strict=True)
    except OSError as error:
        raise OnDeviceSetupError(f"embedded source tree is unavailable: {root}") from error
    if not root.is_dir():
        raise OnDeviceSetupError(f"embedded source tree is not a directory: {root}")
    files: list[tuple[str, Path]] = []
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if any(
            fnmatch.fnmatch(part, pattern)
            for part in relative.parts
            for pattern in ignored
        ):
            continue
        if path.is_symlink():
            raise OnDeviceSetupError(f"embedded source tree contains a symbolic link: {path}")
        if path.is_file():
            files.append((relative.as_posix(), path))
    if not files:
        raise OnDeviceSetupError(f"embedded source tree contains no authored files: {root}")
    for relative, path in sorted(files):
        digest.update(label.encode())
        digest.update(b"\0")
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update(sha256_file(path).encode())


def write_server_runtime(path: Path, build_id: str, catalogs: dict[str, Path]) -> None:
    """Render the Android entrypoint's strict, app-private server config."""
    if set(catalogs) != set(REQUIRED_CATALOGS):
        raise OnDeviceSetupError(
            "Android server runtime requires exactly these generated catalogs: "
            + ", ".join(REQUIRED_CATALOGS)
        )
    profile_path = Path(__file__).resolve().parent.parent / "profiles/legacy-client-bootstrap.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    config = {
        "profile": profile, "state_file": "state.json", "host": LOOPBACK_HOST, "port": LOOPBACK_PORT,
        "event_log": "events.jsonl", "public_data_root": "public_data",
        "core_story": True, "pacts": True, "hunting": True,
        "daily_quests": True, "secondary_worlds": True, "jobs": True, "rebirth": True,
        "status_items": True, "companion_draw": True, "companion_sale": True,
        "companion_strengthen": True, "companion_evolution": True, "trading_post": True,
        "drop_eligibility": True, "achievements": True,
        "story_outcome_catalog": "catalogs/story-outcomes.json",
        "event_catalog": "catalogs/event-catalog.json",
        "character_catalog": "catalogs/character-catalog.json",
        "companion_equipment_catalog": "catalogs/companion-equipment.json",
    }
    path.write_text(json.dumps({"schema_version": 1, "config": config, "build_id": build_id}, sort_keys=True) + "\n", encoding="utf-8")


def build_host_apk(
    host_source: Path,
    work_directory: Path,
    build_id: str,
    android_sdk: Path | None = None,
) -> Path:
    """Build an isolated host copy with only authored Python source staged into it."""
    gradle = ensure_gradle(work_directory, download=True)
    staged = work_directory / "host-source"
    if staged.exists():
        shutil.rmtree(staged)
    shutil.copytree(
        host_source, staged,
        ignore=shutil.ignore_patterns(".gradle", "build", "*.pyc", "__pycache__"),
    )
    python_target = staged / "app/src/main/python/liminal_gate"
    python_target.parent.mkdir(parents=True, exist_ok=True)
    source_package = Path(__file__).parent
    shutil.copytree(
        source_package, python_target,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "test*"),
    )
    java_home, _java_major = resolve_gradle_java_home()
    environment = os.environ | {
        "GRADLE_USER_HOME": str((work_directory / "gradle-user-home").resolve()),
        "JAVA_HOME": str(java_home),
        "PATH": str(java_home / "bin") + os.pathsep + os.environ.get("PATH", ""),
    }
    if android_sdk is not None:
        sdk = android_sdk.resolve()
        environment["ANDROID_HOME"] = str(sdk)
        environment["ANDROID_SDK_ROOT"] = str(sdk)
    try:
        subprocess.run(
            (str(gradle), "--no-daemon", f"-PliminalGateBuildId={build_id}", ":app:assembleDebug"),
            cwd=staged, env=environment, check=True, text=True, capture_output=True,
        )
    except OSError as error:
        raise OnDeviceSetupError(
            "Android host Gradle build could not start; verify the cached launcher and JDK",
        ) from error
    except subprocess.CalledProcessError as error:
        detail = "\n".join(
            value.strip() for value in (error.stdout, error.stderr) if value and value.strip()
        )
        if len(detail) > 4000:
            detail = detail[-4000:]
        raise OnDeviceSetupError(
            "Android host Gradle build failed; verify the Android SDK/JDK setup"
            + (f":\n{detail}" if detail else ""),
        ) from error
    output = staged / "app/build/outputs/apk/debug/app-debug.apk"
    if not output.is_file():
        raise OnDeviceSetupError(f"Android host build did not produce {output}")
    return output


def _adb_shell(adb: str, device: str, *command: str) -> str:
    try:
        result = subprocess.run(
            (adb, "-s", device, "shell", *command), check=True, text=True, capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise OnDeviceSetupError(
            f"could not query {device} through adb; reconnect it, accept USB debugging, and rerun"
        ) from error
    return result.stdout.strip()


def device_facts(adb: str, device: str) -> tuple[int, tuple[str, ...], int]:
    """Return SDK level, advertised ABIs, and free data bytes for an adb target."""
    raw_api = _adb_shell(adb, device, "getprop", "ro.build.version.sdk")
    try:
        api = int(raw_api)
    except ValueError as error:
        raise OnDeviceSetupError(f"{device} did not report a valid Android API level ({raw_api!r})") from error
    raw_abis = _adb_shell(adb, device, "getprop", "ro.product.cpu.abilist")
    abis = tuple(value.strip() for value in raw_abis.split(",") if value.strip())
    # POSIX df's last field is available blocks; Android toybox uses 1K blocks.
    df = _adb_shell(adb, device, "df", "-k", "/data")
    lines = [line.split() for line in df.splitlines() if line.split()]
    try:
        free_bytes = int(lines[-1][-3]) * 1024
    except (IndexError, ValueError) as error:
        raise OnDeviceSetupError(f"could not determine free space on {device} from: {df!r}") from error
    return api, abis, free_bytes


def validate_device(adb: str, device: str) -> str:
    api, abis, free_bytes = device_facts(adb, device)
    if api < MINIMUM_DEVICE_API:
        raise OnDeviceSetupError(
            f"{device} runs Android API {api}; this package requires API {MINIMUM_DEVICE_API} or newer"
        )
    supported = {"arm64-v8a", "armeabi-v7a"}.intersection(abis)
    if not supported:
        raise OnDeviceSetupError(
            f"{device} does not advertise arm64-v8a or armeabi-v7a (reported: "
            f"{', '.join(abis) or 'none'}). Use a supported Android device or image."
        )
    if free_bytes < MINIMUM_DEVICE_FREE_BYTES:
        raise OnDeviceSetupError(
            f"{device} has only {free_bytes / 1024**3:.1f} GiB free under /data; free at least "
            f"{MINIMUM_DEVICE_FREE_BYTES // 1024**3} GiB before installation"
        )
    return f"API {api}; supported {', '.join(sorted(supported))}; {free_bytes / 1024**3:.1f} GiB free"


def _probe(name: str, action: Callable[[], str], required: bool = True) -> Check:
    try:
        return Check(name, True, action(), required)
    except (OnDeviceSetupError, tester_setup.TesterSetupError, OSError) as error:
        return Check(name, False, str(error), required)


def preflight_checks(
    apk: Path, resource_root: Path, data_directory: Path, host_source: Path,
    build_tools: Path | None, adb: str, device: str | None,
    dummy_dll_dir: Path | None = tester_setup.DEFAULT_DUMMY_DLL,
) -> list[Check]:
    """Mirror every non-mutating prerequisite of a real on-device build."""
    def source_apk() -> str:
        if not apk.is_file():
            raise OnDeviceSetupError(f"no APK at {apk}; pass --apk with your own Terra Battle 5.5.7-170 APK")
        digest = sha256_file(apk)
        if digest != REVIEWED_SOURCE_SHA256:
            raise OnDeviceSetupError(
                f"APK SHA-256 is {digest}, not the reviewed 5.5.7-170 value {REVIEWED_SOURCE_SHA256}"
            )
        return str(apk.resolve())

    def host() -> str:
        if not host_source.is_dir():
            raise OnDeviceSetupError(
                f"Android host source is missing at {host_source}; use a complete private source checkout"
            )
        if not (host_source / "app" / "build.gradle").is_file():
            raise OnDeviceSetupError(f"Android host project is incomplete at {host_source}; app/build.gradle is missing")
        return str(host_source.resolve())

    def gradle() -> str:
        return str(ensure_gradle(data_directory / "work", download=False))

    def gradle_jdk() -> str:
        home, major = resolve_gradle_java_home()
        return f"Java {major} at {home}"

    def resources() -> str:
        return str(tester_setup.resolve_resource_root(resource_root))

    def tools() -> str:
        zipalign, apksigner = tester_setup.find_build_tools(build_tools)
        sdk = zipalign.parent.parent.parent
        platform = sdk / "platforms" / f"android-{tool_install.ANDROID_PLATFORM_API}" / "android.jar"
        if not platform.is_file():
            raise OnDeviceSetupError(
                f"Android SDK platform {tool_install.ANDROID_PLATFORM_API} is unavailable below {sdk};"
                " install it with Android Studio"
            )
        return f"{zipalign.parent} ({apksigner.name}); SDK {sdk} with platform {tool_install.ANDROID_PLATFORM_API}"

    def keytool() -> str:
        return str(tester_setup.find_keytools()[0])

    def derivation() -> str:
        missing = tester_setup.find_missing_master_import()
        if missing:
            raise OnDeviceSetupError(tester_setup.describe_missing_master_import(missing))
        tester_setup.check_derivation_prerequisites(dummy_dll_dir, data_directory, None)
        if tester_setup.find_aarch64_objdump() is None:
            raise OnDeviceSetupError(tester_setup.AARCH64_DISASSEMBLER_MISSING)
        return "master import, IL2CPP layout, and AArch64 disassembler ready"

    def device_check() -> Check:
        try:
            selected = tester_setup.select_device(tester_setup.resolve_adb(adb), device)
            return Check("device", True, validate_device(tester_setup.resolve_adb(adb), selected))
        except (OnDeviceSetupError, tester_setup.TesterSetupError, OSError) as error:
            return Check("device", False, str(error), required=device is not None)

    return [
        Check("python", sys.version_info >= (3, 11), f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"),
        _probe("APK", source_apk),
        _probe("resources", resources),
        _probe("build tools", tools),
        _probe("keytool", keytool),
        _probe("guided derivations", derivation),
        _probe("Android host", host),
        _probe("Gradle cache", gradle, required=False),
        _probe("Gradle JDK", gradle_jdk),
        _probe("adb", lambda: tester_setup.resolve_adb(adb)),
        device_check(),
    ]


def report_preflight(checks: Sequence[Check]) -> int:
    print("Checking the private on-device build environment; nothing is modified.\n")
    width = max(len(check.name) for check in checks)
    for check in checks:
        print(f"  {check.marker}  {check.name.ljust(width)}  {check.detail}")
    failures = [check for check in checks if not check.ok and check.required]
    if failures:
        print(f"\n{len(failures)} required check(s) failed. Fix every FAIL before building.")
        return 1
    print(
        "\nEverything required is ready."
        if all(check.ok for check in checks)
        else "\nBuild prerequisites are ready; resolve each warning before installing."
    )
    return 0


def prepare_on_device_apk(
    apk: Path, resource_root: Path, data_directory: Path, host_source: Path,
    build_tools: Path | None, seed_state: bool, dummy_dll_dir: Path | None = None,
    disable_google_services: bool = False,
) -> Path:
    """Prepare the combined APK using the assembly module and stable local signing key."""
    resource_root = tester_setup.resolve_resource_root(resource_root)
    if not apk.is_file():
        raise OnDeviceSetupError(f"no APK at {apk}; pass --apk with your own Terra Battle 5.5.7-170 APK")
    data_directory.mkdir(parents=True, exist_ok=True)
    keystore = data_directory / "liminal-gate-test.keystore"
    password_file = data_directory / "keystore-password.txt"
    tester_setup.ensure_keystore(keystore, password_file)
    zipalign, apksigner = tester_setup.find_build_tools(build_tools)
    if not host_source.is_dir():
        raise OnDeviceSetupError(f"Android host source is missing at {host_source}; use a complete private source checkout")
    work_directory = data_directory / "work" / "on-device"
    work_directory.mkdir(parents=True, exist_ok=True)
    source = apk.resolve()
    source_sha256 = sha256_file(source)
    if source_sha256 != REVIEWED_SOURCE_SHA256:
        raise OnDeviceSetupError(
            "source APK SHA-256 is not the reviewed 5.5.7-170 input; do not build an on-device "
            f"package from it (got {source_sha256})"
        )
    tester_setup.prepare_local_tester(
        source, resource_root, data_directory, LOOPBACK_PORT, build_tools,
        dummy_dll_dir=dummy_dll_dir, device_host=tester_setup.EMULATOR_LOOPBACK_HOST,
        disable_google_services=disable_google_services,
    )
    catalogs = catalog_inputs(data_directory)
    public_data = public_data_inputs(data_directory)
    # The existing plan is the reviewed literal patch path. It guards source
    # bytes before any combined-APK work and keeps both original ABIs intact.
    plan_path = work_directory / "loopback-patch-plan.json"
    plan_path.write_text(json.dumps(
        generate_legacy_client_plan(
            source, f"http://{LOOPBACK_HOST}:{LOOPBACK_PORT}", disable_google_services,
        ),
        sort_keys=True,
    ), encoding="utf-8")
    patched = work_directory / "patched-base.apk"
    apply_patch_plan(source, patched, load_patch_plan(plan_path))
    patched_sha256 = sha256_file(patched)
    build_id = _build_id(
        source_sha256,
        patched_sha256,
        data_directory / "resources.json",
        catalogs,
        public_data,
        host_source,
    )
    server_runtime = work_directory / "server.json"
    write_server_runtime(server_runtime, build_id, catalogs)
    host_apk = build_host_apk(
        host_source.resolve(), data_directory / "work", build_id,
        android_sdk=zipalign.parent.parent.parent,
    )
    unsigned = work_directory / "on-device-unsigned.apk"
    seed = data_directory / "seed-state.json" if seed_state else None
    if seed is not None and not seed.is_file():
        raise OnDeviceSetupError(f"--seed-state requested but no seed state exists at {seed}")
    _call_assembler(
        _assembly_module(), patched_apk=patched, host_apk=host_apk, output_apk=unsigned,
        patched_sha256=patched_sha256, resource_root=resource_root, catalogs=catalogs,
        runtime_files={"server.json": server_runtime, **public_data},
        build_id=build_id, seed_state=seed,
    )
    signed = data_directory / "on-device-liminal-gate.apk"
    sign_apk(unsigned, signed, zipalign, apksigner, keystore, tester_setup.KEY_ALIAS, password_file, password_file)
    return signed


def launch_apk(adb: str, device: str) -> None:
    result = subprocess.run(
        (
            adb,
            "-s",
            device,
            "shell",
            "am",
            "start",
            "-W",
            "-n",
            f"{tester_setup.PACKAGE_NAME}/{HOST_ACTIVITY}",
        ),
        text=True, capture_output=True,
    )
    output = f"{result.stdout}\n{result.stderr}".strip()
    if result.returncode or "Status: ok" not in result.stdout:
        raise OnDeviceSetupError(
            f"could not launch {tester_setup.PACKAGE_NAME}: "
            f"{output or result.returncode}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apk", type=Path, default=DEFAULT_APK)
    parser.add_argument("--resource-root", type=Path, default=DEFAULT_RESOURCES)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--host-source", type=Path, default=DEFAULT_HOST_SOURCE)
    parser.add_argument("--build-tools", type=Path)
    parser.add_argument("--dummy-dll-dir", type=Path, default=tester_setup.DEFAULT_DUMMY_DLL)
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--device", help="adb serial to install on; required only when multiple devices are ready")
    parser.add_argument("--check", action="store_true", help="check the exact build prerequisites without writing or installing")
    parser.add_argument("--prepare-only", action="store_true", help="build the private APK but do not install or launch it")
    parser.add_argument("--seed-state", action="store_true", help="include the optional first-install-only seed state")
    parser.add_argument("--replace-existing", action="store_true", help="allow replacing a differently signed install; this clears its app data")
    parser.add_argument(
        "--disable-google-services", action="store_true",
        help=(
            "make the client's Google Play Services bind actions unresolvable. Needed on Android "
            "versions whose ServiceConnection interface the 2017 client cannot proxy, where the app "
            "crashes on launch with NoSuchMethodError in bitter.jnibridge"
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    # Same reason as the emulator path: the SDK, JDK, and dumper resolvers all
    # read the environment, so any locations the doctor recorded go back into it
    # before the first of them runs. Pinned Gradle also reads JAVA_HOME here.
    toolchain.load_and_apply(args.data_dir)
    if args.check:
        return report_preflight(preflight_checks(
            args.apk, args.resource_root, args.data_dir, args.host_source,
            args.build_tools, args.adb, args.device, args.dummy_dll_dir,
        ))
    try:
        # Selecting and validating the device happens before an expensive build,
        # and before any installation mutation.
        adb, device = args.adb, None
        if not args.prepare_only:
            adb = tester_setup.resolve_adb(args.adb)
            device = tester_setup.select_device(adb, args.device)
            validate_device(adb, device)
        signed = prepare_on_device_apk(
            args.apk, args.resource_root, args.data_dir, args.host_source,
            args.build_tools, args.seed_state, args.dummy_dll_dir,
            args.disable_google_services,
        )
        print(f"Prepared private on-device APK: {signed}")
        if device is None:
            return 0
        tester_setup.install_apk(
            adb, device, signed, replace_existing=args.replace_existing,
            no_incremental=True,
        )
        launch_apk(adb, device)
        print(f"Installed and launched on {device}. The embedded server binds only to {LOOPBACK_HOST}:{LOOPBACK_PORT}.")
        return 0
    except (OnDeviceSetupError, tester_setup.TesterSetupError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"on-device setup failed: {error}") from error


if __name__ == "__main__":
    raise SystemExit(main())
