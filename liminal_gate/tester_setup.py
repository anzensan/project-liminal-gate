"""Prepare, install, and run the local emulator tester path in one command.

All inputs remain user-local. This command neither downloads nor copies an APK
or resource pack. It redirects a user-supplied APK to the local server only.
"""

from __future__ import annotations

import argparse
import getpass
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import textwrap
import zipfile
from dataclasses import dataclass
from typing import Callable, Sequence

from liminal_gate.apk_patcher import PatchPlanError, apply_patch_plan, load_patch_plan
from liminal_gate.apk_signer import ApkSigningError, sign_apk
from liminal_gate.file_digests import DigestCache, count_files
from liminal_gate.input_importer import ImportError, build_import_manifest, write_import_manifest
from liminal_gate.il2cpp_plan_generator import PlanGenerationError
from liminal_gate.legacy_client_apk_plan import METADATA_MEMBER, generate_legacy_client_plan, normalize_server_origin
from liminal_gate.master_strings import (
    MasterStringError, build_character_names, build_companion_names, build_item_names, build_name_file,
    load_inverse_table,
)
from liminal_gate.resource_catalog import ResourceCatalogError
from liminal_gate.resource_catalog_builder import build_resource_manifest, write_resource_manifest
from liminal_gate.setup_progress import (
    DEFAULT_PROGRESS_INTERVAL_SECONDS,
    ProgressLine,
    format_bytes as _format_bytes,
    run_with_heartbeat as _run_with_heartbeat,
)
from liminal_gate.pact_banner_importer import PactBannerImportError, prepare_pact_banners
from liminal_gate import account_state
from liminal_gate.character_catalog_importer import CharacterCatalogImportError, build_character_catalog, load_master_trees, sha256_file, write_character_catalog
from liminal_gate.native_encounter_importer import (
    NativeEncounterImportError,
    import_encounters as import_native_encounters,
    write_document as write_native_document,
)
from liminal_gate.scenario_encounter_importer import (
    ScenarioEncounterImportError,
    import_encounters as import_scenario_encounters,
    write_document as write_scenario_document,
)
from liminal_gate.server_setup import DEFAULT_OUTCOME_CATALOG
from liminal_gate.story_outcome_catalog import StoryOutcomeCatalogError, load_story_outcome_catalog
from liminal_gate.story_outcome_generator import (
    StoryOutcomeGeneratorError,
    build_catalog as build_story_outcome_catalog,
    build_derivation_source as build_outcome_source,
    write_catalog as write_story_outcome_catalog,
)


class TesterSetupError(RuntimeError):
    """The local tester environment is incomplete or ambiguous."""


@dataclass(frozen=True)
class LocalServerOptions:
    """Supported, explicit local policies selected during tester setup."""

    core_story: bool = True
    drop_eligibility: bool = True
    achievements: bool = True
    summon_skills: bool = True
    pacts: bool = True
    hunting: bool = True
    jobs: bool = True
    rebirth: bool = True
    status_items: bool = True
    companion_draw: bool = True
    companion_sale: bool = True
    companion_strengthen: bool = True
    companion_evolution: bool = True
    trading_post: bool = True
    event_catalog: Path | None = None


DEFAULT_APK = Path("local-input/terra-battle-5.5.7-170.apk")
DEFAULT_RESOURCES = Path("local-input/resources/data_u2017/android")
DEFAULT_DATA = Path("user-data")
DEFAULT_DUMMY_DLL = Path("local-input/il2cpp-output/DummyDll")
#: Matches every worked example in the README. The value only has to be a free
#: local port of at most four digits, but setup and the documentation disagreeing
#: about it is a needless way to end up with a client pointed somewhere else.
DEFAULT_PORT = 8696
KEY_ALIAS = "liminal-gate-test"
# Inside an Android emulator this alias reaches the host machine's loopback.
# A physical phone or tablet must instead be given the host's own LAN address.
EMULATOR_LOOPBACK_HOST = "10.0.2.2"
# From the client's perspective these name the phone, tablet, or emulator
# itself, never the machine running the server.
LOOPBACK_HOSTS = frozenset({"localhost", "::1", "0.0.0.0"})
PACKAGE_NAME = "com.mistwalkercorp.guardians"
ZIPALIGN_NAMES = ("zipalign", "zipalign.exe")
APKSIGNER_NAMES = ("apksigner", "apksigner.bat", "apksigner.exe")
KEYTOOL_NAMES = ("keytool", "keytool.exe")
ADB_NAMES = ("adb", "adb.exe")
# keytool refuses a shorter store or key password, and it only says so after the
# prompt has been answered, so setup states and checks the rule itself.
MINIMUM_KEY_PASSWORD_LENGTH = 6
#: Entropy for a generated local key password. The key signs one throwaway test
#: build and its password is stored beside it, so this is about not inventing a
#: guessable value rather than about protecting anything.
GENERATED_KEY_PASSWORD_BYTES = 24
REQUIRED_RESOURCE_CATEGORIES = ("BG", "BGM", "Banner", "BuddyImages", "BuddyThumbs", "Illust", "Pieces", "SE", "Scenario")

# Compatibility-facing override retained here because callers and tests have
# historically tuned the heartbeat interval through `tester_setup`.
PROGRESS_INTERVAL_SECONDS = DEFAULT_PROGRESS_INTERVAL_SECONDS


def run_with_heartbeat(
    command: Sequence[str], label: str, timeout: float,
) -> subprocess.CompletedProcess:
    """Run a long child with the shared progress renderer.

    The wrapper preserves the original public surface and its tunable interval
    while keeping process supervision independent of Android setup.
    """
    return _run_with_heartbeat(
        command, label, timeout, interval=PROGRESS_INTERVAL_SECONDS,
    )


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


def select_device(adb: str, requested: str | None) -> str:
    """Choose the one adb target to install on, without guessing between several.

    An emulator serial and a physical phone or tablet serial are equally valid
    here; `adb devices` reports both the same way.
    """
    devices = _adb_devices(adb)
    if requested is not None:
        if requested not in devices:
            available = ", ".join(devices) if devices else "none"
            raise TesterSetupError(f"requested device {requested!r} is not ready (available: {available})")
        return requested
    if len(devices) == 1:
        return devices[0]
    if not devices:
        raise TesterSetupError(
            "no ready Android device found; start an emulator, or connect a phone or tablet "
            "with USB debugging enabled and accept its authorization prompt, then rerun"
        )
    raise TesterSetupError("multiple Android devices are ready; rerun with --device one of: " + ", ".join(devices))


def build_server_origin(device_host: str, port: int) -> str:
    """Build the origin baked into the client, checking it before any patching.

    Every rejection here describes the mistake in terms of what was passed, not
    of the resulting URL, because the address is compiled into the APK and a
    wrong one produces a client that fails only later, at launch.
    """
    host = device_host.strip()
    if not host or any(character.isspace() for character in host):
        raise TesterSetupError("--device-host must be a host name or address with no spaces")
    if "://" in host or "/" in host:
        raise TesterSetupError(f"--device-host must be only a host or address, not a URL (got {device_host!r})")
    if ":" in host:
        # Both a mistakenly appended port and a bare IPv6 address land here; an
        # unbracketed IPv6 address would otherwise build a malformed origin.
        raise TesterSetupError(
            f"--device-host must not contain a port or a bare IPv6 address (got {device_host!r}); "
            f"pass only the address, and set the port with --port"
        )
    if host.lower() in LOOPBACK_HOSTS or host.startswith("127."):
        raise TesterSetupError(
            f"--device-host {device_host!r} refers to the client's own device, not to this machine. "
            f"Use {EMULATOR_LOOPBACK_HOST} for an Android emulator, or this machine's LAN address "
            f"for a physical phone or tablet."
        )
    try:
        return normalize_server_origin(f"http://{host}:{port}")
    except PlanGenerationError as error:
        raise TesterSetupError(str(error)) from error


def install_apk(adb: str, device: str, apk: Path, replace_existing: bool = False) -> None:
    """Install the signed local APK, explaining a signing-key conflict.

    A build made from a different checkout carries a different local test key,
    and Android refuses to replace an installed package whose signature differs.
    The only remedy is uninstalling first, which also clears that app's local
    data, so it is never done implicitly.
    """
    result = subprocess.run(
        (adb, "-s", device, "install", "-r", str(apk)), text=True, capture_output=True,
    )
    if result.returncode == 0:
        return
    output = f"{result.stdout}\n{result.stderr}"
    if "INSTALL_FAILED_UPDATE_INCOMPATIBLE" not in output and "signatures do not match" not in output:
        raise TesterSetupError(f"adb install failed: {output.strip() or result.returncode}")
    if not replace_existing:
        raise TesterSetupError(
            f"{PACKAGE_NAME} is already installed on {device} from a build signed with a different "
            f"local key, so Android refused to replace it. Rerun with --replace-existing to uninstall "
            f"it first, or uninstall it yourself with: "
            f"{adb} -s {device} uninstall {PACKAGE_NAME}. Either way the app's local data on that "
            f"device is cleared, so it downloads resources again and starts a new local account."
        )
    print(f"Uninstalling the differently signed {PACKAGE_NAME} from {device} before installing.")
    subprocess.run((adb, "-s", device, "uninstall", PACKAGE_NAME), check=True)
    subprocess.run((adb, "-s", device, "install", "-r", str(apk)), check=True)


def check_device_host_suits_device(device: str, device_host: str) -> None:
    """Refuse the emulator-only address when the target is not an emulator.

    `10.0.2.2` exists only inside an emulator, so pairing it with a physical
    serial silently produces an APK that cannot reach the server at all. The
    check is escapable by passing the address explicitly, because an emulator
    attached over TCP does not use an `emulator-` serial.
    """
    if device_host != EMULATOR_LOOPBACK_HOST or device.startswith("emulator-"):
        return
    raise TesterSetupError(
        f"{device!r} does not look like an emulator, and --device-host is still the emulator-only "
        f"address {EMULATOR_LOOPBACK_HOST}, which a physical phone or tablet cannot reach. "
        f"Pass --device-host with this machine's LAN address (for example --device-host 192.168.1.10), "
        f"or pass --device-host {EMULATOR_LOOPBACK_HOST} explicitly if this really is an emulator."
    )


def resolve_resource_root(requested: Path) -> Path:
    """Validate the final Android resource folder or find it beneath a common parent."""
    candidates = (
        requested,
        requested / "android",
        requested / "data_u2017" / "android",
        requested / "gdresources" / "data_u2017" / "android",
    )
    for candidate in candidates:
        if candidate.is_dir() and all((candidate / category).is_dir() for category in REQUIRED_RESOURCE_CATEGORIES):
            resolved = candidate.resolve()
            if resolved != requested.resolve():
                print(f"Using detected Android resource root: {resolved}")
            return resolved
    expected = "data_u2017/android containing " + ", ".join(REQUIRED_RESOURCE_CATEGORIES)
    if not requested.exists():
        raise TesterSetupError(f"resource path does not exist: {requested}; expected {expected}")
    missing = [category for category in REQUIRED_RESOURCE_CATEGORIES if not (requested / category).is_dir()]
    raise TesterSetupError(f"resource path is not the final Android resource folder; expected {expected} (missing here: {', '.join(missing)})")


def _sdk_roots() -> tuple[Path, ...]:
    """Return likely Android SDK roots, preferring explicit shell configuration."""
    configured = tuple(
        Path(value) for value in (os.environ.get("ANDROID_SDK_ROOT"), os.environ.get("ANDROID_HOME")) if value
    )
    defaults = (
        Path(os.environ["LOCALAPPDATA"]) / "Android/Sdk" if os.environ.get("LOCALAPPDATA") else None,
        Path.home() / "Library/Android/sdk",
        Path.home() / "Android/Sdk",
    )
    roots: list[Path] = []
    for root in (*configured, *defaults):
        if root is not None and root not in roots:
            roots.append(root)
    return tuple(roots)


def _build_tool_choices(roots: tuple[Path, ...]) -> tuple[Path, ...]:
    choices: list[Path] = []
    for sdk_root in roots:
        build_tools_root = sdk_root / "build-tools"
        if not build_tools_root.is_dir():
            continue
        choices.extend(sorted(
            (path for path in build_tools_root.iterdir() if path.is_dir()),
            key=lambda path: tuple((0, int(part)) if part.isdigit() else (1, part) for part in path.name.replace("-", ".").split(".")),
            reverse=True,
        ))
    return tuple(choices)


def _find_tool(directory: Path, names: tuple[str, ...]) -> Path | None:
    return next((directory / name for name in names if (directory / name).is_file()), None)


def find_build_tools(explicit: Path | None) -> tuple[Path, Path]:
    choices = (explicit,) if explicit is not None else _build_tool_choices(_sdk_roots())
    for candidate in choices:
        zipalign = _find_tool(candidate, ZIPALIGN_NAMES)
        apksigner = _find_tool(candidate, APKSIGNER_NAMES)
        if zipalign is not None and apksigner is not None:
            return zipalign, apksigner
    location = str(explicit) if explicit is not None else (
        "$ANDROID_SDK_ROOT/build-tools, $ANDROID_HOME/build-tools, "
        "%LOCALAPPDATA%\\Android\\Sdk\\build-tools, ~/Library/Android/sdk/build-tools, or ~/Android/Sdk/build-tools"
    )
    raise TesterSetupError(f"could not find zipalign and apksigner under {location}; install Android SDK Build Tools or pass --build-tools")


def _bundled_java_bin_directories() -> tuple[Path, ...]:
    """Directories inside an Android Studio installation that hold its own JDK.

    `keytool` ships with a JDK, not with the Android SDK, so putting the SDK on
    `PATH` never provides it. A machine whose only Java is the runtime bundled
    with Android Studio is the common case on Windows, and it is found here
    rather than asking the tester to install a second JDK.
    """
    local_app_data, program_files = os.environ.get("LOCALAPPDATA"), os.environ.get("ProgramFiles")
    installations = (
        Path(local_app_data) / "Programs/Android Studio" if local_app_data else None,
        Path(program_files) / "Android/Android Studio" if program_files else None,
        Path("/Applications/Android Studio.app/Contents"),
        Path.home() / "Applications/Android Studio.app/Contents",
        Path("/opt/android-studio"),
        Path.home() / "android-studio",
    )
    # Android Studio has used both layouts, and macOS nests a second Home level.
    return tuple(
        installation / relative
        for installation in installations if installation is not None
        for relative in ("jbr/bin", "jbr/Contents/Home/bin", "jre/bin", "jre/Contents/Home/bin")
    )


#: Windows NT status codes a process returns when it never started. These are
#: reported as an exit code with no output at all, so the number is the only
#: evidence the tester ever sees.
WINDOWS_LAUNCH_FAILURES = {
    3221225781: "a DLL it needs could not be loaded (0xC0000135)",
    3221225595: "a DLL it needs is the wrong version (0xC0000139)",
    3221225477: "it could not be initialised (0xC0000005)",
}


def describe_tool_exit(returncode: int) -> str | None:
    """Explain an exit code that means the program never ran, if it is one."""
    return WINDOWS_LAUNCH_FAILURES.get(returncode)


def find_keytools() -> tuple[Path, ...]:
    """Every keytool worth trying, best first.

    More than one is returned deliberately.  A `keytool` on `PATH` can belong to
    a broken or half-removed Java installation and fail before it runs, which on
    Windows surfaces as an exit code and no output whatsoever.  Android Studio's
    bundled runtime is almost always intact, so it is worth trying next rather
    than stopping at the first candidate.
    """
    candidates: list[Path] = []
    on_path = shutil.which("keytool")
    if on_path is not None:
        candidates.append(Path(on_path))
    java_home = os.environ.get("JAVA_HOME")
    directories = ((Path(java_home) / "bin",) if java_home else ()) + _bundled_java_bin_directories()
    for directory in directories:
        keytool = _find_tool(directory, KEYTOOL_NAMES)
        if keytool is not None and keytool not in candidates:
            candidates.append(keytool)
    if candidates:
        return tuple(candidates)
    raise TesterSetupError(
        "keytool is unavailable. It comes with a JDK rather than with the Android SDK, so adding the "
        "SDK to PATH does not provide it. Install a JDK, or point JAVA_HOME at the runtime bundled "
        "with Android Studio, then reopen the terminal and run setup again."
    )


def resolve_adb(requested: str) -> str:
    """Return a runnable adb, falling back to the SDK's own platform-tools.

    A tester whose shell does not have the SDK on `PATH` still has adb, because
    Android Studio always installs it in the same place. Only the default name
    falls back: an explicitly requested path that does not exist is an error
    rather than a silent substitution.
    """
    if shutil.which(requested) is not None:
        return requested
    if requested != "adb":
        raise TesterSetupError(f"adb is unavailable at the requested path: {requested}")
    for sdk_root in _sdk_roots():
        adb = _find_tool(sdk_root / "platform-tools", ADB_NAMES)
        if adb is not None:
            print(f"Using the adb from your Android SDK: {adb}")
            return str(adb)
    raise TesterSetupError(
        "adb is unavailable: it is not on PATH and no Android SDK platform-tools directory was found. "
        "Install Android SDK Platform-Tools in Android Studio, or pass --adb with the full path to adb."
    )


def write_password_file(path: Path, password: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, stat.S_IRUSR | stat.S_IWUSR)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(password)


def prompt_key_password(confirm: bool, ask: Callable[[str], str] = getpass.getpass) -> str:
    """Prompt until the tester supplies a password keytool will actually accept.

    The length rule is stated in the prompt and rechecked here, and a rejected
    answer is asked again rather than ending the run, because this prompt sits
    ahead of every expensive step and a typo should not cost the whole setup.
    """
    while True:
        try:
            password = ask(f"Choose a local test-key password (at least {MINIMUM_KEY_PASSWORD_LENGTH} characters): ")
            if len(password) < MINIMUM_KEY_PASSWORD_LENGTH:
                print(f"That password is {len(password)} characters. keytool requires at least {MINIMUM_KEY_PASSWORD_LENGTH}.")
                continue
            if not confirm or password == ask("Repeat local test-key password: "):
                return password
            print("Those two passwords did not match.")
        except EOFError as error:
            raise TesterSetupError(
                "setup needs an interactive terminal to choose a local test-key password; "
                "run it directly in a terminal, or create the keystore first as described in the README"
            ) from error


def generate_key_password() -> str:
    """Invent the password for a key whose password protects nothing.

    The key signs one local test build, and `keytool` needs *a* password, which
    setup then has to store beside the keystore so later runs can sign without
    asking again. Choosing it by hand therefore buys no security and costs the
    first run two prompts, so it is only asked for on request.
    """
    return secrets.token_urlsafe(GENERATED_KEY_PASSWORD_BYTES)


def ensure_keystore(keystore: Path, password_file: Path, prompt: bool = False) -> None:
    if keystore.is_file() and password_file.is_file():
        return
    keytools = find_keytools()
    keystore.parent.mkdir(parents=True, exist_ok=True)
    if keystore.exists():
        # The key is already here and only its saved password is missing, so
        # this one cannot be generated: it has to match what the key was made
        # with, and only the operator knows that.
        password = prompt_key_password(confirm=False)
    elif prompt:
        password = prompt_key_password(confirm=True)
    else:
        password = generate_key_password()
    if not keystore.exists():
        attempts: list[str] = []
        for index, keytool in enumerate(keytools):
            try:
                subprocess.run((
                    str(keytool), "-genkeypair", "-v", "-keystore", str(keystore), "-alias", KEY_ALIAS,
                    "-keyalg", "RSA", "-keysize", "2048", "-validity", "10000",
                    "-dname", "CN=Local Tester, OU=Testing, O=Project Liminal Gate, L=Local, ST=Local, C=US",
                    "-storepass", password, "-keypass", password,
                ), check=True, text=True, capture_output=True)
                break
            except subprocess.CalledProcessError as error:
                # keytool's own message is the useful part. When it is empty the
                # program never ran, and the exit code is the only evidence.
                reported = (error.stderr or error.stdout or "").strip()
                launch_failure = describe_tool_exit(error.returncode)
                attempts.append(f"{keytool}: {reported or launch_failure or f'exited {error.returncode}'}")
                # A keytool that refused the request will refuse it again, so
                # only a failure to start is worth retrying elsewhere.
                if not launch_failure and reported:
                    raise TesterSetupError(
                        f"could not create the local test keystore: {reported}"
                    ) from error
            except OSError as error:
                attempts.append(f"{keytool}: {error}")
            if index + 1 < len(keytools):
                print(f"That keytool could not run; trying another: {keytools[index + 1]}")
        else:
            joined = "\n  ".join(attempts)
            raise TesterSetupError(
                "could not create the local test keystore. Every keytool found failed to run:\n  "
                f"{joined}\nThis usually means the Java installation those belong to is incomplete. "
                "Installing a current JDK, or pointing JAVA_HOME at the runtime bundled with Android "
                "Studio, gives setup a working one."
            )
        print(f"Created the local test signing key: {keystore}")
        if not prompt:
            print(
                f"  Its password was generated and saved to {password_file} (owner-only). "
                "Pass --prompt-key-password to choose one yourself instead."
            )
    write_password_file(password_file, password)


def write_local_names(path: Path, apk: Path, trees: dict[str, dict[str, object]]) -> bool:
    """Decode character names from the tester's own APK for the save editor.

    Names are read from the metadata the tester already owns and written only
    into the ignored data directory, so no game text enters the repository.
    A failure here is reported and skipped rather than raised: names are a
    convenience for one optional tool, and nothing else depends on them.
    """
    try:
        with zipfile.ZipFile(apk) as archive:
            table = load_inverse_table(archive.read(METADATA_MEMBER))
        names = build_character_names(trees["ChrDatabase"], table)
        items = build_item_names(trees["ItemSet"], table)
        companions = build_companion_names(trees["BuddyDatabase"], table)
        document = build_name_file(names, sha256_file(apk), items=items, companions=companions)
        path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, KeyError, zipfile.BadZipFile, MasterStringError) as error:
        print(f"Name decoding skipped, so the save editor will show bare IDs: {error}")
        return False
    print(f"Decoded {len(names)} character, {len(items)} item, and {len(companions)} Companion names: {path}")
    return True


#: Disassemblers tried, in order, for the native encounter import.  LLVM's leads
#: on purpose: it is built with every target, whereas a distribution's stock GNU
#: `objdump` is frequently single-target and cannot read an AArch64 library at
#: all unless `binutils-multiarch` is installed.
_OBJDUMP_CANDIDATES = ("llvm-objdump", "objdump", "gobjdump")


#: The two APK members Il2CppDumper needs.  **arm64-v8a deliberately.**  The APK
#: also ships `armeabi-v7a`, whose addresses differ from every offset this
#: project records, and a 32-bit dump would produce type trees that parse but
#: encounter data that does not line up.
IL2CPP_LIBRARY_MEMBER = "lib/arm64-v8a/libil2cpp.so"
IL2CPP_METADATA_MEMBER = "assets/bin/Data/Managed/Metadata/global-metadata.dat"

#: Where setup keeps a dump it produced itself, so a second run reuses it rather
#: than spending the time again.
IL2CPP_OUTPUT_DIRECTORY = "il2cpp"

#: How to reach Il2CppDumper.  It is a separate .NET project, not shipped here:
#: this release is source-only and its output is derived from the operator's own
#: copyrighted game data, so neither the tool nor its results can be bundled.
#: An explicit path wins; otherwise a native build on PATH, then a managed
#: assembly run through `dotnet`.
IL2CPP_DUMPER_ENVIRONMENT = "LIMINAL_GATE_IL2CPPDUMPER"
IL2CPP_DUMPER_NAMES = ("Il2CppDumper", "Il2CppDumper.exe")

IL2CPP_DUMPER_MISSING = (
    "complete guided setup requires Il2CppDumper, which recovers the master-data field layout "
    "an IL2CPP build strips. Install it (https://github.com/Perfare/Il2CppDumper), then either "
    f"put it on PATH or set {IL2CPP_DUMPER_ENVIRONMENT} to the executable or its .dll, and re-run "
    "setup. Pass --dummy-dll-dir instead if you already have its output."
)

#: How long Il2CppDumper may run before setup gives up on it.
IL2CPP_DUMPER_TIMEOUT_SECONDS = 1800

#: The distributions `pyproject.toml` installs under the `master-import` extra.
#: Reading master data out of the APK needs both, so the guided path needs both.
MASTER_IMPORT_DISTRIBUTIONS = ("UnityPy", "TypeTreeGeneratorAPI")

AARCH64_DISASSEMBLER_MISSING = (
    "complete guided setup requires an AArch64 disassembler; install LLVM "
    "(llvm-objdump) or binutils-multiarch, then re-run setup"
)


def _installed(distribution: str) -> bool:
    """Report whether one master-import dependency is importable here.

    Distribution metadata is asked first because that is what `pip install
    ".[master-import]"` records and its name is the one worth printing. A vendored
    copy carries no metadata, so an importable module of the same name counts too.
    """
    try:
        importlib.metadata.version(distribution)
        return True
    except importlib.metadata.PackageNotFoundError:
        pass
    try:
        return importlib.util.find_spec(distribution) is not None
    except (ImportError, ValueError):
        return False


def find_missing_master_import() -> tuple[str, ...]:
    """Return the master-import distributions that are not installed."""
    return tuple(name for name in MASTER_IMPORT_DISTRIBUTIONS if not _installed(name))


def describe_missing_master_import(missing: Sequence[str]) -> str:
    return (
        f"complete guided setup reads master data out of your own APK with {', '.join(missing)}, "
        'which is not installed. Install it with: python3 -m pip install ".[master-import]" '
        "(on Windows, py -3 -m pip install \".[master-import]\")"
    )


def check_derivation_prerequisites(dummy_dll_dir: Path | None) -> None:
    """Confirm every tool the master-data derivations need, before any hashing.

    All three are checked together, beside the SDK tools and the signing
    password, because each of them is fatal to the guided path and each used to
    surface at a different, later point: the disassembler only after the resource
    tree had been inventoried and an IL2CPP dump produced, and UnityPy later
    still. An incomplete toolchain should cost seconds and name every missing
    piece it can, not one piece per attempt.
    """
    if (dummy_dll_dir is None or not dummy_dll_dir.is_dir()) and find_il2cpp_dumper() is None:
        raise TesterSetupError(
            "complete guided setup needs the master-data layout an IL2CPP build strips, without "
            "which story clears mint no Companion. Either point --dummy-dll-dir at an Il2CppDumper "
            f"DummyDll directory (default {DEFAULT_DUMMY_DLL}), or install Il2CppDumper "
            "(https://github.com/Perfare/Il2CppDumper) and put it on PATH or in "
            f"{IL2CPP_DUMPER_ENVIRONMENT} so setup can produce one from your APK."
        )
    missing = find_missing_master_import()
    if missing:
        raise TesterSetupError(describe_missing_master_import(missing))
    if find_aarch64_objdump() is None:
        raise TesterSetupError(AARCH64_DISASSEMBLER_MISSING)


def find_il2cpp_dumper() -> tuple[str, ...] | None:
    """Return the command that runs Il2CppDumper, or `None` if it is absent."""
    configured = os.environ.get(IL2CPP_DUMPER_ENVIRONMENT, "").strip()
    if configured:
        path = Path(configured)
        if path.is_file():
            if path.suffix.lower() == ".dll":
                dotnet = shutil.which("dotnet")
                return (dotnet, str(path)) if dotnet else None
            return (str(path),)
        return None
    for name in IL2CPP_DUMPER_NAMES:
        located = shutil.which(name)
        if located is not None:
            return (located,)
    return None


def ensure_il2cpp_dump(apk: Path, data_directory: Path) -> tuple[Path, Path]:
    """Produce `(DummyDll, dump.cs)` from the APK, reusing an earlier run.

    Both inputs live inside the APK, so nothing here asks the operator for a
    file they would have to extract themselves.  A shortfall stops setup before
    the APK is patched and installed: the guided path is the complete supported
    local game, and an install that silently loses every story Companion the
    client rolls is not that.
    """
    output = data_directory / IL2CPP_OUTPUT_DIRECTORY
    dummy_dll, dump_cs = output / "DummyDll", output / "dump.cs"
    if dummy_dll.is_dir() and any(dummy_dll.glob("*.dll")) and dump_cs.is_file():
        print(f"Reusing the local IL2CPP dump in {output}.")
        return dummy_dll, dump_cs
    command = find_il2cpp_dumper()
    if command is None:
        raise TesterSetupError(IL2CPP_DUMPER_MISSING)
    print("Recovering the master-data layout from your APK with Il2CppDumper (this can take several minutes)...")
    try:
        output.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as directory:
            staged = Path(directory)
            with zipfile.ZipFile(apk) as archive:
                for member, name in (
                    (IL2CPP_LIBRARY_MEMBER, "libil2cpp.so"),
                    (IL2CPP_METADATA_MEMBER, "global-metadata.dat"),
                ):
                    (staged / name).write_bytes(archive.read(member))
            completed = run_with_heartbeat(
                (*command, str(staged / "libil2cpp.so"), str(staged / "global-metadata.dat"), str(output)),
                "Il2CppDumper", IL2CPP_DUMPER_TIMEOUT_SECONDS,
            )
    except (OSError, KeyError, zipfile.BadZipFile, subprocess.SubprocessError) as error:
        raise TesterSetupError(f"complete guided setup could not run Il2CppDumper: {error}") from error
    if completed.returncode or not dummy_dll.is_dir() or not dump_cs.is_file():
        detail = (completed.stderr or completed.stdout or "").strip().splitlines()
        raise TesterSetupError(
            "complete guided setup needs Il2CppDumper to produce a DummyDll directory and dump.cs"
            + (f", but it reported: {detail[-1]}" if detail else "")
        )
    return dummy_dll, dump_cs


def find_aarch64_objdump(candidates: tuple[str, ...] = _OBJDUMP_CANDIDATES) -> str | None:
    """Return the first disassembler on PATH that can read AArch64, if any.

    Support is confirmed rather than assumed: LLVM lists its registered targets
    under ``--version`` and GNU lists its architectures under ``--info``, and a
    stock GNU build on an x86 host commonly lists neither.  Picking one that
    cannot read the library would surface as a confusing failure thousands of
    disassembly calls later.
    """
    for candidate in candidates:
        if shutil.which(candidate) is None:
            continue
        for flag in ("--version", "--info"):
            try:
                completed = subprocess.run(
                    (candidate, flag), stdin=subprocess.DEVNULL,
                    capture_output=True, text=True, timeout=30,
                )
            except (OSError, subprocess.SubprocessError):
                continue
            if "aarch64" in completed.stdout.lower():
                return candidate
    return None


def derive_story_outcome_catalog(
    apk: Path, dummy_dll_dir: Path, data_directory: Path, dump_cs: Path | None = None,
) -> Path:
    """Compose the required story-outcome catalog for the guided local game.

    Without this file a clear mints no Companion at all: the client rolls the
    drop and `clear_quest` has no authority to write it, so the whole story can
    be played without one appearing.  It cannot be shipped -- it is derived from
    the operator's own APK -- so the guided setup derives it, leaving it under
    the name `server_setup` already looks for.

    The guided setup is the complete supported local path, not a reduced
    fallback. Missing inputs or tools therefore stop before the APK is patched
    and installed rather than presenting a game that silently loses every
    story Companion the client rolls.
    """
    resolved_dump_cs = dump_cs if dump_cs is not None else dummy_dll_dir.parent / "dump.cs"
    if not resolved_dump_cs.is_file():
        raise TesterSetupError(
            "complete guided setup requires dump.cs beside the DummyDll directory "
            f"(looked for {resolved_dump_cs}); it is written by the same Il2CppDumper run"
        )
    objdump = find_aarch64_objdump()
    if objdump is None:
        raise TesterSetupError(AARCH64_DISASSEMBLER_MISSING)
    character_catalog = data_directory / "character-catalog.json"
    if not character_catalog.is_file():
        raise TesterSetupError("complete guided setup could not derive the local character catalog")
    derived = data_directory / "derived"
    derived.mkdir(parents=True, exist_ok=True)
    catalog_path = data_directory / DEFAULT_OUTCOME_CATALOG
    try:
        print(f"Deriving story Companion drops (disassembling chapter programs with {objdump})...")
        native_path = derived / "native-encounters.json"
        disassembly = ProgressLine("chapter generators")
        write_native_document(native_path, import_native_encounters(
            apk, resolved_dump_cs, objdump, progress=disassembly.advance,
        ))
        disassembly.done("all read")
        # Chapters 2-7 have no compiled battle program; their encounters come
        # from the client's MoonSharp scripts instead.
        scenario_path = derived / "scenario-encounters.json"
        scenario_document, _report = import_scenario_encounters(apk, resolved_dump_cs)
        write_scenario_document(scenario_path, scenario_document)
        native_document, characters = _read_json(native_path), _read_json(character_catalog)
        trees = load_master_trees(apk, dummy_dll_dir, ("BattleData", "EnemyData", "ChrDatabase"))
        catalog, report, notes = build_story_outcome_catalog(
            native_document,
            trees["BattleData"], trees["EnemyData"], trees["ChrDatabase"], characters,
            source=build_outcome_source(
                native_document, characters, sha256_file(apk),
                sha256_file(native_path), sha256_file(character_catalog), None,
                scenario_document, sha256_file(scenario_path),
            ),
            scenario=scenario_document,
        )
        write_story_outcome_catalog(catalog_path, catalog)
        load_story_outcome_catalog(catalog_path)
    except (
        NativeEncounterImportError, ScenarioEncounterImportError, StoryOutcomeGeneratorError,
        StoryOutcomeCatalogError, CharacterCatalogImportError, OSError,
    ) as error:
        raise TesterSetupError(f"complete guided setup could not derive story Companion drops: {error}") from error
    print(
        f"Story Companion drops: ON -- {report['core_stages_with_companion_ceiling']} story stage(s) "
        f"can mint a Companion, {report['distinct_companions']} distinct Companion(s)."
    )
    for note in notes:
        print(f"  note: {note}")
    return catalog_path


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def prepare_local_tester(
    apk: Path, resource_root: Path, data_directory: Path, port: int, build_tools: Path | None,
    dummy_dll_dir: Path | None = None, event_catalog: Path | None = None,
    device_host: str = EMULATOR_LOOPBACK_HOST,
    dump_cs: Path | None = None, prompt_for_key_password: bool = False,
) -> Path:
    """Build the redirected, locally signed APK and return its path."""
    if not 1 <= port <= 65535:
        raise TesterSetupError("--port must be an integer from 1 through 65535")
    if event_catalog is not None and dummy_dll_dir is None:
        raise TesterSetupError("--event-catalog requires --dummy-dll-dir so setup can derive the matching local character catalog")
    # Resolved before the input hashing below, so a rejected address fails in
    # seconds instead of after the whole resource tree has been inventoried.
    server_origin = build_server_origin(device_host, port)
    apk, resource_root = apk.resolve(), resolve_resource_root(resource_root)
    if not apk.is_file():
        raise TesterSetupError(f"no APK to redirect at {apk}; pass --apk with the path to your own copy")
    data_directory.mkdir(parents=True, exist_ok=True)
    # Asked and located here for the same reason as the address above: a missing
    # SDK tool, a missing JDK, or a mistyped password should cost seconds rather
    # than surface after the whole resource tree has been inventoried.
    keystore, password_file = data_directory / "liminal-gate-test.keystore", data_directory / "keystore-password.txt"
    ensure_keystore(keystore, password_file, prompt_for_key_password)
    zipalign, apksigner = find_build_tools(build_tools)
    # Checked alongside the SDK tools and the signing password, so an incomplete
    # toolchain costs seconds rather than surfacing after the whole resource tree
    # has been inventoried. Either route to the master-data layout will do; only
    # having neither stops setup.
    check_derivation_prerequisites(dummy_dll_dir)
    try:
        # One shared cache, so the two inventories below read the tree once
        # between them instead of once each. Deliberately scoped to the APK and
        # the resource tree: both are immutable for the length of a run, which
        # nothing setup writes afterwards is.
        hashing = ProgressLine("hashing local inputs", count_files(resource_root) + 1)
        digests = DigestCache(on_hash=lambda files, read: hashing.update(files, _format_bytes(read)))
        imported = build_import_manifest(apk, resource_root, reviewed_android_5_5_7=True, digests=digests)
        write_import_manifest(data_directory / "input-manifest", imported)
        if dummy_dll_dir is None or not dummy_dll_dir.is_dir():
            # The default location is a hint, not a requirement. When nothing is
            # there, setup produces the dump itself: both Il2CppDumper inputs
            # live inside the APK it was already given, so this asks the
            # operator for nothing beyond having the tool installed.
            dummy_dll_dir, discovered = ensure_il2cpp_dump(apk, data_directory)
            dump_cs = dump_cs if dump_cs is not None else discovered
        trees = load_master_trees(apk, dummy_dll_dir, ("ChrDatabase", "ItemSet", "BuddyDatabase"))
        character_catalog = build_character_catalog(trees["ChrDatabase"], sha256_file(apk))
        write_character_catalog(data_directory / "character-catalog.json", character_catalog)
        write_local_names(data_directory / "names.json", apk, trees)
        derive_story_outcome_catalog(apk, dummy_dll_dir, data_directory, dump_cs)
        manifest = build_resource_manifest(resource_root, digests=digests)
        resource_manifest = data_directory / "resources.json"
        write_resource_manifest(resource_manifest, manifest)
        hashing.done(
            f"{digests.hashed_files} file(s), {_format_bytes(digests.hashed_bytes)} read once "
            f"and reused {digests.reused} time(s)"
        )
        try:
            prepare_pact_banners(apk, resource_root, data_directory / "public_data")
        except PactBannerImportError as error:
            print(f"Pact banner preparation skipped: {error}")
        plan = generate_legacy_client_plan(apk, server_origin)
        plan_path = data_directory / "local-server-plan.json"
        plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        unsigned = data_directory / "liminal-gate-unsigned.apk"
        apply_patch_plan(apk, unsigned, load_patch_plan(plan_path))
        signed = data_directory / "liminal-gate-test.apk"
        sign_apk(unsigned, signed, zipalign, apksigner, keystore, KEY_ALIAS, password_file, password_file)
    except (OSError, ImportError, ResourceCatalogError, PatchPlanError, ApkSigningError, CharacterCatalogImportError, ValueError) as error:
        raise TesterSetupError(str(error)) from error
    print(f"Prepared local test APK: {signed}")
    print(f"This build reaches the server at {server_origin} and only that address.")
    return signed


def server_arguments(
    resource_root: Path, data_directory: Path, port: int, event_catalog: Path | None = None,
    core_story: bool = True, drop_eligibility: bool = True, achievements: bool = True, summon_skills: bool = True, pacts: bool = True, hunting: bool = True, jobs: bool = True, rebirth: bool = True, status_items: bool = True, companion_draw: bool = True, companion_sale: bool = True,
    companion_strengthen: bool = True, companion_evolution: bool = True,
    trading_post: bool = True,
) -> list[str]:
    arguments = [
        sys.executable, "-m", "liminal_gate.bootstrap_server",
        "--profile", "profiles/legacy-client-bootstrap.json",
        "--state-file", str(data_directory / "bootstrap-state.json"),
        "--host", "0.0.0.0", "--port", str(port),
        "--event-log", str(data_directory / "events.jsonl"),
        "--resource-root", str(resource_root),
        "--resource-manifest", str(data_directory / "resources.json"),
        "--public-data-root", str(data_directory / "public_data"),
    ]
    if core_story:
        arguments.append("--core-story")
    if pacts:
        arguments.append("--pacts")
    if hunting:
        arguments.append("--hunting")
    if jobs:
        arguments.append("--jobs")
    if rebirth:
        arguments.append("--rebirth")
    if status_items:
        arguments.append("--status-items")
    if companion_draw:
        arguments.append("--companion-draw")
    if companion_sale:
        arguments.append("--companion-sale")
    if companion_strengthen:
        arguments.append("--companion-strengthen")
    if companion_evolution:
        arguments.append("--companion-evolution")
    if trading_post:
        arguments.append("--trading-post")
    if drop_eligibility:
        # Without this the client discards every drop it rolls, so guided
        # setups would report empty monsters/buddies on every clear.
        arguments.append("--drop-eligibility")
    if achievements:
        arguments.append("--achievements")
    if summon_skills:
        arguments.append("--summon-skills")
    arguments.extend((
        "--story-outcome-catalog", str((data_directory / DEFAULT_OUTCOME_CATALOG).resolve()),
    ))
    if event_catalog is not None:
        arguments.extend((
            "--event-catalog", str(event_catalog.resolve()),
            "--character-catalog", str((data_directory / "character-catalog.json").resolve()),
        ))
    return arguments


def _ask_yes_no(prompt: str, default: bool, ask: Callable[[str], str] = input) -> bool:
    suffix = "Y/n" if default else "y/N"
    while True:
        answer = ask(f"{prompt} [{suffix}] ").strip().lower()
        if not answer:
            return default
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False
        print("Please answer y or n.")


def choose_local_server_options(
    event_catalog: Path | None, ask: Callable[[str], str] = input,
) -> LocalServerOptions:
    """Prompt only for what an operator must actually supply.

    Every built-in policy is on.  They were briefly selectable, but the modes
    only ever subtracted content from a preservation build: nobody testing this
    wants the story without the Tavern, and the one genuine case -- isolating a
    feature while troubleshooting -- is better served by running
    ``liminal_gate.bootstrap_server`` directly with the flags you want, which
    ``docs/advanced-configuration.md`` documents.
    """
    print("\nLocal setup")
    print("Story, Hunting zones, Pacts, and Companions are all enabled.")
    print("Custom drop-rate controls are not available yet.")
    enable_events = _ask_yes_no(
        "Do you already have an advanced local event catalog", event_catalog is not None, ask,
    )
    if not enable_events:
        return LocalServerOptions()
    if event_catalog is None:
        raw = ask("Path to your local event catalog JSON: ").strip()
        if not raw:
            raise TesterSetupError("an event catalog path is required when local events are enabled")
        event_catalog = Path(raw)
    return LocalServerOptions(event_catalog=event_catalog)


@dataclass(frozen=True)
class Check:
    """One preflight result, in the terms the operator has to act on."""

    name: str
    ok: bool
    detail: str
    required: bool = True

    @property
    def marker(self) -> str:
        return "ok  " if self.ok else ("FAIL" if self.required else "warn")


def _probe(name: str, resolve: Callable[[], str], required: bool = True) -> Check:
    """Run one check, turning its own refusal message into the reported detail."""
    try:
        return Check(name, True, resolve(), required)
    except (TesterSetupError, OSError) as error:
        return Check(name, False, str(error), required)


def port_is_free(port: int) -> bool:
    """Report whether the guided server could bind the port it was given.

    Checked on the same interface the server actually listens on, because a port
    free on loopback and taken on 0.0.0.0 would pass a narrower test and then
    fail at launch.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("0.0.0.0", port))
        except OSError:
            return False
    return True


def preflight_checks(
    apk: Path, resource_root: Path, dummy_dll_dir: Path | None, port: int,
    adb: str, device: str | None, build_tools: Path | None,
) -> list[Check]:
    """Answer every question setup would otherwise ask one failure at a time."""
    def build_tool_paths() -> str:
        zipalign, apksigner = find_build_tools(build_tools)
        return str(zipalign.parent)

    def master_import() -> str:
        missing = find_missing_master_import()
        if missing:
            raise TesterSetupError(describe_missing_master_import(missing))
        return ", ".join(MASTER_IMPORT_DISTRIBUTIONS)

    def il2cpp_dumper() -> str:
        if dummy_dll_dir is not None and dummy_dll_dir.is_dir():
            return f"not needed; using {dummy_dll_dir}"
        command = find_il2cpp_dumper()
        if command is None:
            raise TesterSetupError(IL2CPP_DUMPER_MISSING)
        return " ".join(command)

    def disassembler() -> str:
        objdump = find_aarch64_objdump()
        if objdump is None:
            raise TesterSetupError(AARCH64_DISASSEMBLER_MISSING)
        return f"{objdump} (reads AArch64)"

    def local_apk() -> str:
        if not apk.is_file():
            raise TesterSetupError(f"no APK at {apk}; pass --apk with the path to your own copy")
        return f"{apk} ({_format_bytes(apk.stat().st_size)})"

    def resources() -> str:
        return str(resolve_resource_root(resource_root))

    def free_port() -> str:
        if not port_is_free(port):
            raise TesterSetupError(f"port {port} is already in use; choose another with --port")
        return f"{port} is free"

    def ready_device() -> str:
        return select_device(resolve_adb(adb), device)

    return [
        Check("python", True, f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"),
        _probe("adb", lambda: resolve_adb(adb)),
        _probe("build tools", build_tool_paths),
        _probe("keytool", lambda: str(find_keytools()[0])),
        _probe("UnityPy", master_import),
        _probe("Il2CppDumper", il2cpp_dumper),
        _probe("disassembler", disassembler),
        _probe("APK", local_apk),
        _probe("resources", resources),
        _probe("port", free_port),
        # Not required: --prepare-only builds the APK with nothing attached, and
        # a tester who has not started the emulator yet still wants the rest of
        # this list rather than one line about adb.
        _probe("device", ready_device, required=False),
    ]


def report_preflight(checks: Sequence[Check], width: int = 78) -> int:
    """Print the checklist and return the exit status it implies.

    A failing check's detail is the whole instruction for fixing it, which is a
    sentence or three rather than a value, so it is wrapped under its own row
    instead of running off the edge of the terminal.
    """
    print("Checking the local tester environment; nothing is modified.\n")
    label = max(len(check.name) for check in checks)
    for check in checks:
        row = f"  {check.marker}  {check.name.ljust(label)}  "
        if check.ok:
            print(f"{row}{check.detail}")
            continue
        wrapped = textwrap.wrap(check.detail, width=max(20, width - len(row))) or [""]
        print(f"{row}{wrapped[0]}")
        for line in wrapped[1:]:
            print(f"{' ' * len(row)}{line}")
    failed = [check for check in checks if not check.ok and check.required]
    warned = [check for check in checks if not check.ok and not check.required]
    if failed:
        print(f"\n{len(failed)} required check(s) failed. Fix the lines marked FAIL, then run this again.")
        return 1
    if warned:
        print("\nEverything required is ready. The warn line(s) above only matter when you install.")
    else:
        print("\nEverything is ready. Run the same command without --check to build and install.")
    return 0


def run_server(arguments: Sequence[str]) -> None:
    """Run the local server in the foreground with platform-safe argument quoting."""
    subprocess.run(arguments, check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apk", type=Path, default=DEFAULT_APK)
    parser.add_argument("--resource-root", type=Path, default=DEFAULT_RESOURCES)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--device", "--emulator", dest="device",
        help="adb serial of the emulator, phone, or tablet; required only when more than one device is ready",
    )
    parser.add_argument(
        "--device-host", default=EMULATOR_LOOPBACK_HOST,
        help=(
            "address this client should use to reach the server. Leave unset for an emulator. "
            "For a physical phone or tablet, pass this machine's LAN address, for example 192.168.1.10"
        ),
    )
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--build-tools", type=Path, help="Android SDK Build Tools version directory")
    parser.add_argument(
        "--dummy-dll-dir", type=Path, default=DEFAULT_DUMMY_DLL,
        help=(
            "local Il2CppDumper DummyDll directory; required for the complete guided "
            f"setup (default: {DEFAULT_DUMMY_DLL})"
        ),
    )
    parser.add_argument("--event-catalog", type=Path, help="optional user-local event-stage catalog; requires --dummy-dll-dir")
    parser.add_argument("--dump-cs", type=Path, help="Il2CppDumper dump.cs; defaults to the file beside --dummy-dll-dir")
    parser.add_argument("--no-configure", dest="configure", action="store_false", help="skip interactive local-server options and use the standard defaults")
    parser.set_defaults(configure=True)
    parser.add_argument(
        "--check", action="store_true",
        help="report whether this machine has everything setup needs, then exit without changing anything",
    )
    parser.add_argument(
        "--prompt-key-password", dest="prompt_key_password", action="store_true",
        help="choose the local test-key password yourself instead of having one generated",
    )
    parser.add_argument("--prepare-only", action="store_true", help="build the APK but do not install it or start the server")
    parser.add_argument(
        "--replace-existing", action="store_true",
        help=(
            "uninstall an already installed build signed with a different local key before installing. "
            "This clears that app's local data on the device"
        ),
    )
    return parser.parse_args()


def report_existing_accounts(data_directory: Path) -> None:
    """Say which saved account the client will land on, before the server starts.

    An account is keyed by the client's device UUID, so clearing app data or
    reinstalling signs the client into a brand new account while the previous
    save sits in the same file, complete and unreachable. That reads as lost
    progress, and nothing in the client says otherwise, so it is worth one line
    here rather than a JSON hunt later.
    """
    state = data_directory / "bootstrap-state.json"
    summary = account_state.summarize(state)
    accounts = summary.get("accounts") or []
    if not summary.get("exists") or not accounts:
        return
    print(f"\nSaved accounts in {state.name}: {len(accounts)}")
    for account in accounts:
        marker = "* " if account["active"] else "  "
        progress = account.get("progressCode")
        where = "not started" if not account.get("played") else _progress_label(progress)
        print(f"  {marker}{account['accountId']}  {where}")
    if len(accounts) > 1:
        print("  (* is the account the client is currently signed into.)")


def offer_account_switch(data_directory: Path, ask: Callable[[str], str] = input) -> None:
    """Offer to put the client on a different saved account before launching.

    Reinstalling gives the client a new device UUID, so it signs into a fresh
    account while the previous save sits in the same file. Choosing between
    them is a local bookkeeping change, and the swap `switch` performs is
    reversible, so this can be offered rather than left to a manual command.
    """
    state = data_directory / "bootstrap-state.json"
    summary = account_state.summarize(state)
    accounts = summary.get("accounts") or []
    if len(accounts) < 2 or not any(value["active"] for value in accounts):
        return
    active = next(value for value in accounts if value["active"])
    others = [value for value in accounts if not value["active"] and value.get("played")]
    if not any((value.get("progressCode") or 0) > (active.get("progressCode") or 0) for value in others):
        return
    print("\nAnother saved account has more progress than the one the client is on.")
    for index, account in enumerate(others, start=1):
        print(f"  {index}) {account['accountId']}  {_progress_label(account.get('progressCode'))}")
    print("  0) keep the current account")
    raw = ask("Play a different account? Enter a number [0]: ").strip() or "0"
    if not raw.isdecimal() or not 1 <= int(raw) <= len(others):
        print("Keeping the current account.")
        return
    chosen = others[int(raw) - 1]
    result = account_state.switch(state, chosen["accountId"], confirmed=True)
    print(f"Now playing {_progress_label(chosen.get('progressCode'))}.")
    print(f"The previous save is kept and can be switched back to. Backup: {result['preservedPrimary']}")


def _progress_label(progress: object) -> str:
    """Render a stored progressCode as the chapter and section it unlocks."""
    if type(progress) is not int or progress <= 0:
        return "no recorded progress"
    low = progress & 0xFFFF
    return f"unlocked chapter {low >> 6}-{low & 0x3F}"


def main() -> int:
    args = parse_args()
    if args.check:
        # Deliberately ahead of every prompt and every check that can raise: the
        # point of this mode is to answer "is this machine ready" without asking
        # the operator for anything or writing a single file.
        return report_preflight(preflight_checks(
            args.apk, args.resource_root, args.dummy_dll_dir, args.port,
            args.adb, args.device, args.build_tools,
        ))
    try:
        options = (
            choose_local_server_options(args.event_catalog)
            if args.configure and sys.stdin.isatty()
            else LocalServerOptions(event_catalog=args.event_catalog)
        )
        # Chosen before the APK is built so an ambiguous target, or an address
        # the target cannot reach, is reported in seconds rather than after the
        # resource inventory and signing have already run.
        device, adb = None, args.adb
        if not args.prepare_only:
            adb = resolve_adb(args.adb)
            device = select_device(adb, args.device)
            check_device_host_suits_device(device, args.device_host)
        signed = prepare_local_tester(
            args.apk, args.resource_root, args.data_dir, args.port, args.build_tools,
            args.dummy_dll_dir, options.event_catalog, args.device_host,
            dump_cs=args.dump_cs, prompt_for_key_password=args.prompt_key_password,
        )
        if device is None:
            return 0
        install_apk(adb, device, signed, replace_existing=args.replace_existing)
        report_existing_accounts(args.data_dir)
        if args.configure and sys.stdin.isatty():
            offer_account_switch(args.data_dir)
        print(f"\nInstalled on {device}. Starting the local server; press Control-C when finished.")
        run_server(server_arguments(
            args.resource_root.resolve(), args.data_dir, args.port, options.event_catalog,
            options.core_story, options.drop_eligibility, options.achievements, options.summon_skills, options.pacts, options.hunting, options.jobs, options.rebirth, options.status_items, options.companion_draw, options.companion_sale,
            options.companion_strengthen, options.companion_evolution, options.trading_post,
        ))
    except (TesterSetupError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"tester setup failed: {error}") from error
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
