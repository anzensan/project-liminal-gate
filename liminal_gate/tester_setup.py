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
from dataclasses import dataclass
from typing import Callable, Sequence

from liminal_gate.apk_patcher import PatchPlanError, apply_patch_plan, load_patch_plan
from liminal_gate.apk_signer import ApkSigningError, sign_apk
from liminal_gate.input_importer import ImportError, build_import_manifest, write_import_manifest
from liminal_gate.il2cpp_plan_generator import PlanGenerationError
from liminal_gate.legacy_client_apk_plan import generate_legacy_client_plan, normalize_server_origin
from liminal_gate.resource_catalog import ResourceCatalogError
from liminal_gate.resource_catalog_builder import build_resource_manifest, write_resource_manifest
from liminal_gate.pact_banner_importer import PactBannerImportError, prepare_pact_banners
from liminal_gate.character_catalog_importer import CharacterCatalogImportError, build_character_catalog, load_character_master_tree, sha256_file, write_character_catalog


class TesterSetupError(RuntimeError):
    """The local tester environment is incomplete or ambiguous."""


@dataclass(frozen=True)
class LocalServerOptions:
    """Supported, explicit local policies selected during tester setup."""

    core_story: bool = True
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
    dummy_dll_dir: Path | None = None


DEFAULT_APK = Path("local-input/terra-battle-5.5.7-170.apk")
DEFAULT_RESOURCES = Path("local-input/resources/data_u2017/android")
DEFAULT_DATA = Path("user-data")
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
REQUIRED_RESOURCE_CATEGORIES = ("BG", "BGM", "Banner", "BuddyImages", "BuddyThumbs", "Illust", "Pieces", "SE", "Scenario")


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


def find_keytool() -> Path:
    """Locate keytool on PATH, under JAVA_HOME, or in Android Studio's runtime."""
    on_path = shutil.which("keytool")
    if on_path is not None:
        return Path(on_path)
    java_home = os.environ.get("JAVA_HOME")
    directories = ((Path(java_home) / "bin",) if java_home else ()) + _bundled_java_bin_directories()
    for directory in directories:
        keytool = _find_tool(directory, KEYTOOL_NAMES)
        if keytool is not None:
            print(f"Using the keytool bundled with your JDK: {keytool}")
            return keytool
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


def ensure_keystore(keystore: Path, password_file: Path) -> None:
    if keystore.is_file() and password_file.is_file():
        return
    keytool = find_keytool()
    keystore.parent.mkdir(parents=True, exist_ok=True)
    password = prompt_key_password(confirm=not keystore.exists())
    if not keystore.exists():
        try:
            subprocess.run((
                str(keytool), "-genkeypair", "-v", "-keystore", str(keystore), "-alias", KEY_ALIAS,
                "-keyalg", "RSA", "-keysize", "2048", "-validity", "10000",
                "-dname", "CN=Local Tester, OU=Testing, O=Project Liminal Gate, L=Local, ST=Local, C=US",
                "-storepass", password, "-keypass", password,
            ), check=True, text=True, capture_output=True)
        except subprocess.CalledProcessError as error:
            # keytool's own message is the useful part; without it the failure
            # reads as unexplained.
            reported = (error.stderr or error.stdout or "").strip()
            raise TesterSetupError(f"could not create the local test keystore: {reported or f'keytool exited {error.returncode}'}") from error
        except OSError as error:
            raise TesterSetupError(f"could not run keytool at {keytool}: {error}") from error
        print(f"Created the local test signing key: {keystore}")
    write_password_file(password_file, password)


def prepare_local_tester(
    apk: Path, resource_root: Path, data_directory: Path, port: int, build_tools: Path | None,
    dummy_dll_dir: Path | None = None, event_catalog: Path | None = None,
    device_host: str = EMULATOR_LOOPBACK_HOST,
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
    ensure_keystore(keystore, password_file)
    zipalign, apksigner = find_build_tools(build_tools)
    try:
        imported = build_import_manifest(apk, resource_root, reviewed_android_5_5_7=True)
        write_import_manifest(data_directory / "input-manifest", imported)
        if dummy_dll_dir is not None:
            character_catalog = build_character_catalog(
                load_character_master_tree(apk, dummy_dll_dir), sha256_file(apk),
            )
            write_character_catalog(data_directory / "character-catalog.json", character_catalog)
        manifest = build_resource_manifest(resource_root)
        resource_manifest = data_directory / "resources.json"
        write_resource_manifest(resource_manifest, manifest)
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
    core_story: bool = True, pacts: bool = True, hunting: bool = True, jobs: bool = True, rebirth: bool = True, status_items: bool = True, companion_draw: bool = True, companion_sale: bool = True,
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
    event_catalog: Path | None, dummy_dll_dir: Path | None, ask: Callable[[str], str] = input,
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
        "Do you already have an advanced local event catalog and DummyDll files", event_catalog is not None, ask,
    )
    if not enable_events:
        return LocalServerOptions()
    if event_catalog is None:
        raw = ask("Path to your local event catalog JSON: ").strip()
        if not raw:
            raise TesterSetupError("an event catalog path is required when local events are enabled")
        event_catalog = Path(raw)
    if dummy_dll_dir is None:
        raw = ask("Path to your local Il2CppDumper DummyDll directory: ").strip()
        if not raw:
            raise TesterSetupError("a DummyDll directory is required when local events are enabled")
        dummy_dll_dir = Path(raw)
    return LocalServerOptions(event_catalog=event_catalog, dummy_dll_dir=dummy_dll_dir)


def run_server(arguments: Sequence[str]) -> None:
    """Run the local server in the foreground with platform-safe argument quoting."""
    subprocess.run(arguments, check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apk", type=Path, default=DEFAULT_APK)
    parser.add_argument("--resource-root", type=Path, default=DEFAULT_RESOURCES)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--port", type=int, default=8002)
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
    parser.add_argument("--dummy-dll-dir", type=Path, help="optional local Il2CppDumper DummyDll directory; derives user-data/character-catalog.json")
    parser.add_argument("--event-catalog", type=Path, help="optional user-local event-stage catalog; requires --dummy-dll-dir")
    parser.add_argument("--no-configure", dest="configure", action="store_false", help="skip interactive local-server options and use the standard defaults")
    parser.set_defaults(configure=True)
    parser.add_argument("--prepare-only", action="store_true", help="build the APK but do not install it or start the server")
    parser.add_argument(
        "--replace-existing", action="store_true",
        help=(
            "uninstall an already installed build signed with a different local key before installing. "
            "This clears that app's local data on the device"
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        options = (
            choose_local_server_options(args.event_catalog, args.dummy_dll_dir)
            if args.configure and sys.stdin.isatty()
            else LocalServerOptions(event_catalog=args.event_catalog, dummy_dll_dir=args.dummy_dll_dir)
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
            options.dummy_dll_dir, options.event_catalog, args.device_host,
        )
        if device is None:
            return 0
        install_apk(adb, device, signed, replace_existing=args.replace_existing)
        print(f"Installed on {device}. Starting the local server; press Control-C when finished.")
        run_server(server_arguments(
            args.resource_root.resolve(), args.data_dir, args.port, options.event_catalog,
            options.core_story, options.pacts, options.hunting, options.jobs, options.rebirth, options.status_items, options.companion_draw, options.companion_sale,
            options.companion_strengthen, options.companion_evolution, options.trading_post,
        ))
    except (TesterSetupError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"tester setup failed: {error}") from error
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
