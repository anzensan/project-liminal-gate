"""Fetch the external tools guided setup needs, into ignored local storage.

Nothing here is a Terra Battle asset.  Every download is a general-purpose
development tool published by its own vendor -- a JDK from Adoptium, the Android
command line tools and NDK from Google, the .NET runtime from Microsoft,
Il2CppDumper from its GitHub release -- and each lands beneath the tester's
ignored data directory rather than anywhere Git can see.  The project's own
inputs are still supplied by the operator and are still never downloaded.

Two pinning strategies are used, deliberately:

* Google's command line tools, the side-by-side NDK package, and Il2CppDumper
  are pinned to an exact build. Direct-archive checksums are written here;
  `sdkmanager` resolves and verifies the NDK through Google's repository
  metadata. These are versioned artefacts whose contents this project reasons
  about -- the dumper's version is already named in `tester_setup`, whose
  workaround for its exit behaviour is specific to it -- so a silent upgrade
  is a change worth refusing.
* The JDK and the .NET runtime are resolved through their vendor's own release
  API, and the checksum is the one that API publishes over the same HTTPS
  connection.  Both ship security updates on their own schedule, both are
  interchangeable within a major version, and pinning a patch release here
  would mean shipping a knowingly outdated runtime between releases.

A checksum from a vendor API is weaker than one reviewed in source: it attests
that the bytes are the ones the vendor's own index names, not that anyone here
has seen them.  It is recorded as such rather than presented as a stronger
guarantee than it is.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import stat
import subprocess
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from liminal_gate.setup_progress import ProgressLine, format_bytes


class ToolInstallError(RuntimeError):
    """A tool could not be fetched or unpacked, and setup must not pretend it was."""


#: Where every download lands, relative to `--data-dir`.
TOOLCHAIN_DIRECTORY = "toolchain"

#: Long enough for a slow link to start a 180 MB transfer, short enough that a
#: black-holed connection fails within a coffee break rather than never.
NETWORK_TIMEOUT_SECONDS = 120

#: GitHub refuses requests without one, and a truthful name is more useful to
#: the services being asked than a browser string would be.
USER_AGENT = "project-liminal-gate-doctor"

_CHUNK_BYTES = 256 * 1024


@dataclass(frozen=True)
class Checksum:
    algorithm: str
    hexdigest: str

    def verify(self, path: Path) -> None:
        digest = hashlib.new(self.algorithm)
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(_CHUNK_BYTES), b""):
                digest.update(block)
        actual = digest.hexdigest()
        if actual.lower() != self.hexdigest.lower():
            raise ToolInstallError(
                f"{path.name} does not match its published {self.algorithm} checksum "
                f"(expected {self.hexdigest}, got {actual}). The download was not used. "
                "Retry; if it keeps failing, fetch the tool yourself and record its "
                "location instead of letting this command download it."
            )


@dataclass(frozen=True)
class Host:
    """The operating system and processor, in the words each vendor uses."""

    system: str
    architecture: str

    @property
    def is_windows(self) -> bool:
        return self.system == "windows"

    @property
    def executable_suffix(self) -> str:
        return ".exe" if self.is_windows else ""


_SYSTEMS = {"Darwin": "mac", "Linux": "linux", "Windows": "windows"}
_ARCHITECTURES = {
    "x86_64": "x64", "AMD64": "x64", "amd64": "x64",
    "arm64": "aarch64", "aarch64": "aarch64", "ARM64": "aarch64",
}


def detect_host() -> Host:
    system = _SYSTEMS.get(platform.system())
    architecture = _ARCHITECTURES.get(platform.machine())
    if system is None or architecture is None:
        raise ToolInstallError(
            f"automatic tool installation does not cover {platform.system()} on "
            f"{platform.machine()}. Install the tools by hand as described in "
            "docs/install-tools.md; everything else in setup still works."
        )
    return Host(system, architecture)


def _request(url: str) -> urllib.request.Request:
    return urllib.request.Request(url, headers={"User-Agent": USER_AGENT})


def read_json(url: str) -> object:
    """Read one vendor index, turning every network failure into one message."""
    try:
        with urllib.request.urlopen(_request(url), timeout=NETWORK_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise ToolInstallError(f"{url} returned HTTP {error.code} {error.reason}") from error
    except (urllib.error.URLError, OSError) as error:
        raise ToolInstallError(f"could not reach {url}: {error}") from error
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ToolInstallError(f"{url} did not return the JSON index expected: {error}") from error


def download(url: str, destination: Path, label: str, checksum: Checksum | None = None) -> Path:
    """Fetch one archive, verify it, and only then let it occupy its final name.

    The transfer runs into a neighbouring `.part` file that is renamed after the
    checksum passes.  A run interrupted halfway therefore leaves nothing that a
    later run could mistake for a complete download, which matters here because
    the next thing that happens to these files is that they are unpacked and
    executed.
    """
    if destination.is_file() and checksum is not None:
        try:
            checksum.verify(destination)
        except ToolInstallError:
            destination.unlink()
        else:
            print(f"  {label}: already downloaded ({format_bytes(destination.stat().st_size)})")
            return destination

    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part")
    progress = ProgressLine(label)
    received = 0
    try:
        with urllib.request.urlopen(_request(url), timeout=NETWORK_TIMEOUT_SECONDS) as response:
            total = int(response.headers.get("Content-Length") or 0)
            with partial.open("wb") as stream:
                while block := response.read(_CHUNK_BYTES):
                    stream.write(block)
                    received += len(block)
                    progress.advance(received, total, format_bytes(received))
    except urllib.error.HTTPError as error:
        partial.unlink(missing_ok=True)
        raise ToolInstallError(f"{url} returned HTTP {error.code} {error.reason}") from error
    except (urllib.error.URLError, OSError) as error:
        partial.unlink(missing_ok=True)
        raise ToolInstallError(f"could not download {url}: {error}") from error

    if checksum is not None:
        try:
            checksum.verify(partial)
        except ToolInstallError:
            partial.unlink(missing_ok=True)
            raise
    partial.replace(destination)
    progress.done(f"{format_bytes(received)} downloaded and verified")
    return destination


def _reject_unsafe(names: Sequence[str], root: Path) -> None:
    """Refuse an archive that would write outside the directory it unpacks into."""
    resolved_root = root.resolve()
    for name in names:
        target = (resolved_root / name).resolve()
        if target != resolved_root and resolved_root not in target.parents:
            raise ToolInstallError(f"archive member would be written outside {root}: {name}")


def _restore_zip_modes(archive: zipfile.ZipFile, root: Path) -> None:
    """Put the executable bit back on files that had one.

    `zipfile` discards Unix permissions, so a command line tools archive
    unpacked with it yields an `sdkmanager` that cannot be run.  The original
    mode is in the high half of `external_attr` whenever the archive was built
    on a Unix host.
    """
    if os.name == "nt":
        return
    for member in archive.infolist():
        mode = member.external_attr >> 16
        if not mode or member.is_dir():
            continue
        target = root / member.filename
        if target.is_file():
            target.chmod(stat.S_IMODE(mode))


def long_path(path: Path) -> Path:
    r"""Return `path` in the form Windows accepts beyond its 260 character limit.

    Win32 refuses a longer path with `ENOENT`, which surfaces from an unpack as
    the baffling claim that a file being *created* does not exist.  The `\\?\`
    prefix opts individual calls out of that limit.  Google's command line tools
    very nearly reach it unaided: under `cmdline-tools/lib/external/com/google/
    guava/` the archive names both a directory and the jar inside it
    `listenablefuture-9999.0-empty-to-avoid-conflict-with-guava`, spending 165
    characters before the destination contributes any.  A checkout under
    `Documents\GitHub` is then enough to go over.

    The prefix also suppresses all path normalisation, so what it is given must
    be absolute and separator-clean already -- hence `resolve()`.  Archive
    members are still vetted against the unprefixed root before extraction, so
    this widens nothing an archive is permitted to write.
    """
    if os.name != "nt":
        return path
    resolved = path.resolve()
    text = str(resolved)
    if text.startswith("\\\\?\\"):
        return resolved
    # A UNC path spells the prefix differently: \\server\share becomes
    # \\?\UNC\server\share rather than growing a second pair of backslashes.
    if text.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + text[2:])
    return Path("\\\\?\\" + text)


def extract(archive: Path, root: Path) -> Path:
    """Unpack one `.zip` or `.tar.gz` beneath `root`, refusing unsafe members.

    Returns the root the members were written under, which on Windows carries
    the long-path prefix.  A caller that goes on to read, move, or delete what
    was unpacked should use the returned path rather than the one it passed, so
    that a deep archive stays reachable to those calls too.
    """
    destination = long_path(root)
    destination.mkdir(parents=True, exist_ok=True)
    try:
        if archive.name.endswith(".zip"):
            with zipfile.ZipFile(archive) as source:
                _reject_unsafe(source.namelist(), root)
                source.extractall(destination)
                _restore_zip_modes(source, destination)
        elif archive.name.endswith((".tar.gz", ".tgz")):
            with tarfile.open(archive, "r:gz") as source:
                _reject_unsafe(source.getnames(), root)
                # `data` drops device nodes, setuid bits, and absolute links.
                # None of the archives here carry any, so filtering costs
                # nothing and removes a class of surprise from the ones that do.
                # The parameter arrived during 3.11, so the earliest supported
                # interpreters fall back to the member check just performed.
                try:
                    source.extractall(destination, filter="data")
                except TypeError:
                    source.extractall(destination, members=_safe_tar_members(source, root))
        else:
            raise ToolInstallError(f"unsupported archive type: {archive.name}")
    except (OSError, zipfile.BadZipFile, tarfile.TarError) as error:
        raise ToolInstallError(f"could not unpack {archive.name}: {error}") from error
    return destination


def _safe_tar_members(source: tarfile.TarFile, root: Path) -> list[tarfile.TarInfo]:
    """Backport the relevant ``data`` filter checks for early Python 3.11.

    The project's minimum interpreter predates the portable extraction filter
    on some patch releases. Archive paths alone are not enough: a relative
    symlink can point outside the destination, and device nodes or set-id modes
    do not belong in a private toolchain directory.
    """
    members = source.getmembers()
    for member in members:
        if member.isdev() or member.isfifo():
            raise ToolInstallError(f"archive contains an unsupported special file: {member.name}")
        if member.issym() or member.islnk():
            link = Path(member.linkname)
            target = (
                link
                if link.is_absolute() or member.islnk()
                else Path(member.name).parent / link
            )
            _reject_unsafe((str(target),), root)
        member.mode &= 0o755
    return members


def _make_executable(path: Path) -> None:
    if os.name == "nt":
        return
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


# --------------------------------------------------------------------------
# A JDK, for keytool and for Gradle
# --------------------------------------------------------------------------

#: Java 17.  `keytool` is content with any JDK, but the on-device path hands
#: this same runtime to pinned Gradle, which accepts 17 through 23, and 17 is
#: the long-term release inside that window.
JDK_FEATURE_VERSION = 17

ADOPTIUM_LATEST = (
    "https://api.adoptium.net/v3/assets/latest/{feature}/hotspot"
    "?os={system}&architecture={architecture}&image_type=jdk"
)


def _java_home_within(root: Path) -> Path:
    """Find the unpacked JDK's home, which differs by platform.

    A macOS archive nests it under `Contents/Home`; every other platform puts
    it directly in the versioned top-level directory.  Rather than encode both
    layouts, the home is defined as the shallowest directory holding `bin/java`.
    """
    name = "java.exe" if os.name == "nt" else "java"
    # `parent.parent` because the match is the launcher itself: its parent is
    # the JDK's `bin`, and the home is the directory holding that.
    candidates = [path.parent.parent for path in root.rglob(f"bin/{name}") if path.is_file()]
    if not candidates:
        raise ToolInstallError(f"the unpacked JDK beneath {root} contains no bin/{name}")
    return min(candidates, key=lambda path: len(path.parts))


def install_jdk(root: Path, host: Host) -> Path:
    """Install a Temurin JDK and return its home."""
    url = ADOPTIUM_LATEST.format(
        feature=JDK_FEATURE_VERSION, system=host.system, architecture=host.architecture,
    )
    assets = read_json(url)
    if not isinstance(assets, list) or not assets:
        raise ToolInstallError(
            f"Adoptium lists no Java {JDK_FEATURE_VERSION} build for {host.system}/{host.architecture}"
        )
    try:
        package = assets[0]["binary"]["package"]
        link, name = str(package["link"]), str(package["name"])
        checksum = Checksum("sha256", str(package["checksum"]))
        release = str(assets[0].get("release_name", "unknown"))
    except (KeyError, TypeError, IndexError) as error:
        raise ToolInstallError(f"Adoptium returned an index this build cannot read: {error}") from error

    print(f"Installing {release} from Adoptium.")
    destination = root / "downloads" / name
    download(link, destination, "JDK", checksum)
    unpacked = root / "jdk"
    if unpacked.exists():
        shutil.rmtree(long_path(unpacked), ignore_errors=True)
    extract(destination, unpacked)
    # Deliberately the unprefixed root: this path becomes `JAVA_HOME` and is
    # handed to Gradle, and a `\\?\` prefix means nothing to a JVM launcher.
    # The JDK's own layout is shallow, so it does not need the escape hatch.
    java_home = _java_home_within(unpacked)
    print(f"  JDK ready: {java_home}")
    return java_home


# --------------------------------------------------------------------------
# The Android SDK
# --------------------------------------------------------------------------

ANDROID_REPOSITORY = "https://dl.google.com/android/repository/"

#: Command line tools 22.0, build 15859902, with the SHA-1 Google publishes for
#: each host in `repository2-3.xml`.  SHA-1 is what that index carries; it is
#: recorded because it is the vendor's own published value, and it is doing its
#: work on top of an HTTPS transfer rather than instead of one.
ANDROID_CMDLINE_TOOLS_REVISION = "22.0"
_CMDLINE_TOOLS = {
    ("linux", "x64"): ("commandlinetools-linux-15859902_latest.zip", "040d3996a65543d22ec4bf73e4c37aa37a8d4af4"),
    ("mac", "x64"): ("commandlinetools-mac_x86_64-15859902_latest.zip", "1a79e61677b99cb0ce622792713cbea7ff2dc5de"),
    ("mac", "aarch64"): ("commandlinetools-mac_arm64-15859902_latest.zip", "c4e0dbc53f1a4ce04fc2b11d4e2c4675001a95af"),
    ("windows", "x64"): ("commandlinetools-win-15859902_latest.zip", "b9862337a13e2809a5159dc3a08d058091bd59f6"),
}

#: What guided setup actually consumes: `adb` from platform-tools, and
#: `zipalign` with `apksigner` from build-tools.  The build-tools version is not
#: special -- `find_build_tools` takes the highest installed -- so this is
#: simply a current stable one, overridable from the command line.
ANDROID_PLATFORM_API = 35
ANDROID_PACKAGES = (
    "platform-tools",
    "build-tools;36.1.0",
    f"platforms;android-{ANDROID_PLATFORM_API}",
)

#: The latest long-term-support NDK at the time this installer was reviewed.
#: Guided setup does not build native code with it: the package is Google's
#: cross-platform, side-by-side distribution of LLVM, and its `llvm-objdump`
#: is the one private AArch64 disassembler the doctor needs.  Installing it
#: through `sdkmanager` keeps Google's package checksum/licence handling and
#: avoids a separate platform-specific LLVM installer.
ANDROID_NDK_VERSION = "27.3.13750724"
ANDROID_NDK_PACKAGE = f"ndk;{ANDROID_NDK_VERSION}"

#: Google retains the x86_64-looking Darwin tag for compatibility, but its NDK
#: binaries are universal and run natively on Apple silicon too.
_ANDROID_NDK_HOST_TAGS = {
    ("mac", "x64"): "darwin-x86_64",
    ("mac", "aarch64"): "darwin-x86_64",
    ("linux", "x64"): "linux-x86_64",
    ("windows", "x64"): "windows-x86_64",
}

#: Where accepting these licences commits the operator, named so the doctor can
#: print it before asking.
ANDROID_LICENCE_URL = "https://developer.android.com/studio/terms"


def command_line_tools_home(sdk_root: Path) -> Path:
    """The one directory `sdkmanager` accepts being installed in."""
    return sdk_root / "cmdline-tools" / "latest"


def sdkmanager_path(sdk_root: Path) -> Path:
    suffix = ".bat" if os.name == "nt" else ""
    return command_line_tools_home(sdk_root) / "bin" / f"sdkmanager{suffix}"


def install_command_line_tools(sdk_root: Path, root: Path, host: Host) -> Path:
    """Place Google's command line tools where `sdkmanager` expects to live.

    The archive unpacks to a plain `cmdline-tools` directory, but `sdkmanager`
    refuses to manage an SDK unless it is installed at `cmdline-tools/latest`,
    reporting the confusing complaint that it could not determine its own
    location.  The move below is that requirement, not a preference.
    """
    manager = sdkmanager_path(sdk_root)
    if manager.is_file():
        return manager
    try:
        name, digest = _CMDLINE_TOOLS[(host.system, host.architecture)]
    except KeyError as error:
        raise ToolInstallError(
            f"Google publishes no command line tools for {host.system}/{host.architecture}"
        ) from error

    print(f"Installing Android command line tools {ANDROID_CMDLINE_TOOLS_REVISION} from Google.")
    archive = download(
        ANDROID_REPOSITORY + name, root / "downloads" / name, "command line tools",
        Checksum("sha1", digest),
    )
    home = command_line_tools_home(sdk_root)
    # Every character spent on the staging directory is a character the deepest
    # archive member cannot afford, so the usual `tmp` prefix and an `unpacked`
    # subdirectory are both dropped: the archive's own `cmdline-tools` top level
    # already separates it from anything else here.  `TemporaryDirectory` is not
    # used because it cleans up through the unprefixed path, which on Windows
    # cannot delete what a long-path extraction wrote.
    staging = Path(tempfile.mkdtemp(dir=root, prefix=""))
    try:
        unpacked = extract(archive, staging)
        source = unpacked / "cmdline-tools"
        if not source.is_dir():
            raise ToolInstallError("the command line tools archive did not contain a cmdline-tools directory")
        home.parent.mkdir(parents=True, exist_ok=True)
        # `shutil.move` into an existing directory nests rather than replaces,
        # which would bury `bin/sdkmanager` one level deeper than it belongs, so
        # the destination has to be absent before the move.
        if home.exists():
            shutil.rmtree(long_path(home), ignore_errors=True)
        shutil.move(str(source), str(home))
    finally:
        shutil.rmtree(long_path(staging), ignore_errors=True)
    if not manager.is_file():
        raise ToolInstallError(f"the command line tools archive did not provide {manager}")
    _make_executable(manager)
    return manager


def require_supported_android_sdk_host(host: Host) -> None:
    """Fail before downloads when Google does not publish this host toolchain."""
    if (host.system, host.architecture) not in _CMDLINE_TOOLS:
        raise ToolInstallError(
            f"Google does not publish a supported Android SDK toolchain for "
            f"{host.system}/{host.architecture}. Use an x64 Windows/Linux host or an "
            "Intel/Apple-silicon Mac for the APK build."
        )


def _sdkmanager_environment(java_home: Path | None) -> dict[str, str]:
    environment = dict(os.environ)
    if java_home is not None:
        environment["JAVA_HOME"] = str(java_home)
        environment["PATH"] = os.pathsep.join((str(java_home / "bin"), environment.get("PATH", "")))
    return environment


def _run_sdkmanager(
    manager: Path, sdk_root: Path, arguments: Sequence[str], java_home: Path | None,
    stdin_text: str | None = None, timeout: float = 1800,
) -> None:
    command = (str(manager), f"--sdk_root={sdk_root}", *arguments)
    try:
        result = subprocess.run(
            command, text=True, capture_output=True, timeout=timeout,
            env=_sdkmanager_environment(java_home),
            input=stdin_text if stdin_text is not None else "",
        )
    except subprocess.TimeoutExpired as error:
        raise ToolInstallError(f"sdkmanager did not finish within {timeout:.0f}s: {' '.join(arguments)}") from error
    except OSError as error:
        raise ToolInstallError(f"could not run sdkmanager at {manager}: {error}") from error
    if result.returncode != 0:
        reported = (result.stderr or result.stdout or "").strip()
        raise ToolInstallError(
            f"sdkmanager failed ({' '.join(arguments)}): {reported or f'exit {result.returncode}'}"
        )


def accept_android_licences(sdk_root: Path, root: Path, host: Host, java_home: Path | None) -> None:
    """Record the operator's acceptance of Google's SDK licences.

    Only ever reached from an explicit choice made by the operator: agreeing to
    someone else's licence terms on their behalf is not a default this command
    is entitled to take. The caller is responsible for having asked.
    """
    manager = install_command_line_tools(sdk_root, root, host)
    # sdkmanager asks once per unaccepted licence and reads a line each time.
    _run_sdkmanager(manager, sdk_root, ("--licenses",), java_home, stdin_text="y\n" * 50)


def install_android_packages(
    sdk_root: Path, root: Path, host: Host, java_home: Path | None,
    packages: Sequence[str] = ANDROID_PACKAGES,
) -> Path:
    """Install the SDK packages guided setup consumes and return the SDK root."""
    manager = install_command_line_tools(sdk_root, root, host)
    print(f"Installing Android SDK packages: {', '.join(packages)}.")
    _run_sdkmanager(manager, sdk_root, tuple(packages), java_home, stdin_text="y\n" * 50)
    print(f"  Android SDK ready: {sdk_root}")
    return sdk_root


def android_ndk_objdump(sdk_root: Path, host: Host) -> Path:
    """Return the pinned NDK's exact LLVM disassembler or fail explicitly."""
    try:
        host_tag = _ANDROID_NDK_HOST_TAGS[(host.system, host.architecture)]
    except KeyError as error:
        raise ToolInstallError(
            f"Google publishes no supported Android NDK toolchain for "
            f"{host.system}/{host.architecture}"
        ) from error
    executable = (
        sdk_root / "ndk" / ANDROID_NDK_VERSION / "toolchains" / "llvm" /
        "prebuilt" / host_tag / "bin" / f"llvm-objdump{host.executable_suffix}"
    )
    if not executable.is_file():
        raise ToolInstallError(
            f"the installed {ANDROID_NDK_PACKAGE} package did not provide {executable}. "
            "The SDK installation was kept; rerun the doctor to repair the package."
        )
    _make_executable(executable)
    return executable


# --------------------------------------------------------------------------
# Il2CppDumper
# --------------------------------------------------------------------------

#: Pinned exactly.  `tester_setup` documents a workaround for the way this
#: release ends its run, derived from reading this version's behaviour, so
#: quietly moving to another one would invalidate a documented finding.
IL2CPP_DUMPER_VERSION = "v6.7.46"
IL2CPP_DUMPER_RELEASE = (
    f"https://github.com/Perfare/Il2CppDumper/releases/download/{IL2CPP_DUMPER_VERSION}/"
)

#: Windows gets the self-contained build, which needs no runtime at all.  Every
#: other platform gets the portable managed build, which does.  The Windows
#: archive also ships an `Il2CppDumper.exe` *launcher* beside the managed
#: assembly, so the exact file is recorded rather than the directory: pointing
#: at the directory on macOS selects a Windows executable that cannot run.
_IL2CPP_DUMPER_ASSETS = {
    "windows": (
        "Il2CppDumper-win-v6.7.46.zip",
        "f5fc60dfc5c034c1ff3fc651514416ebd47658a63493207734537fd25fa2dea2",
        "Il2CppDumper.exe",
    ),
    "mac": (
        "Il2CppDumper-net7-v6.7.46.zip",
        "c7f365347ce6bd816cdf774830e44ac46aea59c391c94f388605667394d6aba2",
        "Il2CppDumper.dll",
    ),
    "linux": (
        "Il2CppDumper-net7-v6.7.46.zip",
        "c7f365347ce6bd816cdf774830e44ac46aea59c391c94f388605667394d6aba2",
        "Il2CppDumper.dll",
    ),
}


def _silence_dumper_keypress(directory: Path) -> None:
    """Turn off the "press any key to exit" this release ships enabled.

    Guided setup captures the dumper's output to show progress, so its standard
    input is never a console, and .NET refuses the keypress read outright.  The
    dump completes and the process then exits non-zero anyway -- a failure
    `tester_setup` already recognises and steps over.  Since this command
    unpacked the tool, the setting can simply be corrected at the source.
    """
    config = directory / "config.json"
    try:
        document = json.loads(config.read_text(encoding="utf-8"))
        if not isinstance(document, dict) or document.get("RequireAnyKey") is not True:
            return
        document["RequireAnyKey"] = False
        config.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    except (OSError, json.JSONDecodeError) as error:
        # Cosmetic only: leaving it enabled costs a recognised non-zero exit,
        # not a failed dump, so this must not stop the install.
        print(f"  Could not disable Il2CppDumper's exit keypress ({error}); setup handles it anyway.")
        return
    print("  Disabled Il2CppDumper's exit keypress, which a captured run cannot answer.")


def install_il2cpp_dumper(root: Path, host: Host) -> Path:
    """Install Il2CppDumper and return the exact file that should be run."""
    try:
        name, digest, member = _IL2CPP_DUMPER_ASSETS[host.system]
    except KeyError as error:
        raise ToolInstallError(f"no Il2CppDumper build is published for {host.system}") from error

    print(f"Installing Il2CppDumper {IL2CPP_DUMPER_VERSION}.")
    archive = download(
        IL2CPP_DUMPER_RELEASE + name, root / "downloads" / name, "Il2CppDumper",
        Checksum("sha256", digest),
    )
    unpacked = root / "il2cpp-dumper"
    if unpacked.exists():
        shutil.rmtree(long_path(unpacked), ignore_errors=True)
    extract(archive, unpacked)
    executable = unpacked / member
    if not executable.is_file():
        raise ToolInstallError(f"the Il2CppDumper archive did not contain {member}")
    if not member.endswith(".dll"):
        _make_executable(executable)
    _silence_dumper_keypress(unpacked)
    print(f"  Il2CppDumper ready: {executable}")
    return executable


# --------------------------------------------------------------------------
# The .NET runtime, only where the managed dumper needs one
# --------------------------------------------------------------------------

#: The current long-term-support channel.  The dumper build above targets .NET
#: 7, which is out of support; `toolchain` sets `DOTNET_ROLL_FORWARD` so this
#: runtime hosts it rather than installing an unsupported one to match.
DOTNET_CHANNEL = "8.0"
DOTNET_RELEASES = (
    f"https://builds.dotnet.microsoft.com/dotnet/release-metadata/{DOTNET_CHANNEL}/releases.json"
)

_DOTNET_PLATFORMS = {"mac": "osx", "linux": "linux", "windows": "win"}
_DOTNET_ARCHITECTURES = {"x64": "x64", "aarch64": "arm64"}


def _dotnet_runtime_file(index: object, host: Host) -> tuple[str, Checksum, str]:
    """Pick the archive for this host out of Microsoft's channel index."""
    if not isinstance(index, dict):
        raise ToolInstallError("the .NET release index was not the object expected")
    rid = f"{_DOTNET_PLATFORMS[host.system]}-{_DOTNET_ARCHITECTURES[host.architecture]}"
    wanted = ".zip" if host.is_windows else ".tar.gz"
    latest = index.get("latest-runtime")
    for release in index.get("releases", []):
        runtime = (release or {}).get("runtime") or {}
        if latest is not None and runtime.get("version") != latest:
            continue
        for entry in runtime.get("files", []):
            if entry.get("rid") != rid or not str(entry.get("name", "")).endswith(wanted):
                continue
            # Microsoft publishes SHA-512 here; the length is checked rather
            # than assumed so a change of algorithm fails loudly.
            digest = str(entry.get("hash", ""))
            algorithm = {128: "sha512", 64: "sha256"}.get(len(digest))
            if algorithm is None:
                raise ToolInstallError(f"the .NET index carries a checksum of unknown type for {rid}")
            return str(entry["url"]), Checksum(algorithm, digest), str(runtime.get("version", "unknown"))
    raise ToolInstallError(f"the .NET {DOTNET_CHANNEL} index lists no runtime archive for {rid}")


def install_dotnet_runtime(root: Path, host: Host) -> Path:
    """Install a private .NET runtime and return the directory holding `dotnet`."""
    url, checksum, version = _dotnet_runtime_file(read_json(DOTNET_RELEASES), host)
    print(f"Installing the .NET {version} runtime, which the Il2CppDumper build for this platform needs.")
    destination = root / "downloads" / url.rsplit("/", 1)[-1]
    download(url, destination, ".NET runtime", checksum)
    unpacked = root / "dotnet"
    if unpacked.exists():
        shutil.rmtree(long_path(unpacked), ignore_errors=True)
    extract(destination, unpacked)
    launcher = unpacked / f"dotnet{host.executable_suffix}"
    if not launcher.is_file():
        raise ToolInstallError(f"the .NET runtime archive did not contain {launcher.name}")
    _make_executable(launcher)
    print(f"  .NET runtime ready: {launcher}")
    return unpacked
