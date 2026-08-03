"""Report which build tools this machine has, and optionally fetch the rest.

This answers the question `docs/install-tools.md` used to answer with three
pages of per-shell `export` lines: *is this machine ready, and if not, what
would make it ready*.  Run with `--install-missing` it also does the fetching,
into the ignored data directory, and records where everything landed so no
shell variable has to be set in this terminal or any later one.

What it deliberately does not do:

* touch a shell profile, the registry, or anything outside `--data-dir`;
* accept Google's SDK licences without being told to;
* download Android Studio, an emulator system image, or any game material.

The tester still supplies their own APK and resources, and still needs a device
or emulator to install onto.  This command is about the toolchain around that,
which is the part that can be automated honestly.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from liminal_gate import tester_setup, tool_install, toolchain as toolchain_module
from liminal_gate.tool_install import Host, ToolInstallError, detect_host
from liminal_gate.toolchain import Toolchain, ToolchainError


DEFAULT_DATA = tester_setup.DEFAULT_DATA

#: Where an `objdump` that can read AArch64 tends to be when it is installed but
#: not on `PATH`.  Checked so the common case on macOS -- the Command Line Tools
#: are present and provide one -- does not send the operator to install LLVM
#: they already effectively have.  Nothing here is downloaded; a candidate is
#: only recorded once it has confirmed AArch64 support for itself.
_OBJDUMP_LOCATIONS = {
    "mac": (
        "/Library/Developer/CommandLineTools/usr/bin/objdump",
        "/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/llvm-objdump",
        "/opt/homebrew/opt/llvm/bin/llvm-objdump",
        "/usr/local/opt/llvm/bin/llvm-objdump",
    ),
    "linux": (
        "/usr/bin/llvm-objdump",
        "/usr/lib/llvm/bin/llvm-objdump",
    ),
    "windows": (
        r"C:\Program Files\LLVM\bin\llvm-objdump.exe",
        r"C:\Program Files (x86)\LLVM\bin\llvm-objdump.exe",
    ),
}

#: Manual fallback when Google's supported SDK/NDK toolchain does not cover the
#: host.  Normal `--install-missing` uses the pinned side-by-side NDK and never
#: invokes a system package manager.
_DISASSEMBLER_ADVICE = {
    "mac": "install it with: xcode-select --install   (or: brew install llvm)",
    "linux": "install it with your package manager, for example: sudo apt install llvm binutils-multiarch",
    "windows": "install LLVM from https://github.com/llvm/llvm-project/releases (choose the win64 installer)",
}


@dataclass(frozen=True)
class ToolStatus:
    """One tool, as the operator has to think about it."""

    name: str
    ok: bool
    detail: str
    #: Whether `--install-missing` can do anything about this one.
    fixable: bool = True

    @property
    def marker(self) -> str:
        return "ok" if self.ok else "MISSING"


def _probe(name: str, resolve: Callable[[], str], fixable: bool = True) -> ToolStatus:
    """Run one resolver, turning its own refusal message into the reported detail."""
    try:
        return ToolStatus(name, True, resolve(), fixable)
    except (tester_setup.TesterSetupError, OSError) as error:
        return ToolStatus(name, False, str(error), fixable)


def find_objdump(host: Host) -> Path | None:
    """Return an AArch64-capable disassembler found off `PATH`, if there is one."""
    for location in _OBJDUMP_LOCATIONS.get(host.system, ()):
        candidate = Path(location)
        if not candidate.is_file():
            continue
        # Asked to prove it reads AArch64 by the same test setup uses, because
        # a stock objdump on an x86 host frequently cannot.
        if tester_setup.find_aarch64_objdump((str(candidate),)) is not None:
            return candidate
    return None


def survey(host: Host) -> list[ToolStatus]:
    """Report every tool guided setup needs, in the order they would be fixed."""
    def java() -> str:
        return f"keytool at {tester_setup.find_keytools()[0]}"

    def android_platform_tools() -> str:
        return f"adb at {tester_setup.resolve_adb('adb')}"

    def android_build_tools() -> str:
        zipalign, _ = tester_setup.find_build_tools(None)
        return str(zipalign.parent)

    def master_import() -> str:
        missing = tester_setup.find_missing_master_import()
        if missing:
            raise tester_setup.TesterSetupError(tester_setup.describe_missing_master_import(missing))
        return ", ".join(tester_setup.MASTER_IMPORT_DISTRIBUTIONS)

    def il2cpp_dumper() -> str:
        command = tester_setup.find_il2cpp_dumper()
        if command is None:
            raise tester_setup.TesterSetupError(tester_setup.describe_missing_il2cpp_dumper())
        return " ".join(command)

    def disassembler() -> str:
        found = tester_setup.find_aarch64_objdump()
        if found is None:
            raise tester_setup.TesterSetupError(
                "no objdump on this machine reports AArch64 support, and the encounter map for "
                "chapters 8-42 only exists as compiled code inside your APK. "
                f"--install-missing installs Google's pinned {tool_install.ANDROID_NDK_PACKAGE} "
                "LLVM toolchain privately; manual fallback: "
                f"{_DISASSEMBLER_ADVICE.get(host.system, 'install LLVM')}"
            )
        return str(found)

    return [
        ToolStatus(
            "python",
            sys.version_info >= (3, 11),
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
            if sys.version_info >= (3, 11)
            else "Python 3.11 or newer is required",
            fixable=False,
        ),
        _probe("java", java),
        _probe("platform tools", android_platform_tools),
        _probe("build tools", android_build_tools),
        _probe("UnityPy", master_import),
        _probe("Il2CppDumper", il2cpp_dumper),
        _probe("disassembler", disassembler),
    ]


def report(statuses: Sequence[ToolStatus], width: int = 78) -> None:
    """Print the survey, wrapping each instruction under the row it belongs to."""
    label = max(len(status.name) for status in statuses)
    marker = max(len(status.marker) for status in statuses)
    for status in statuses:
        row = f"  {status.marker.ljust(marker)}  {status.name.ljust(label)}  "
        if status.ok:
            print(f"{row}{status.detail}")
            continue
        wrapped = textwrap.wrap(status.detail, width=max(20, width - len(row))) or [""]
        print(f"{row}{wrapped[0]}")
        for line in wrapped[1:]:
            print(f"{' ' * len(row)}{line}")


def _missing(statuses: Sequence[ToolStatus], name: str) -> bool:
    return any(status.name == name and not status.ok for status in statuses)


def install_master_import() -> None:
    """Install the APK-reading dependencies into the running interpreter.

    Run through this interpreter rather than a bare `pip`, so the packages land
    in the environment setup will import them from rather than whichever one a
    `pip` on `PATH` happens to target.

    The project's own `master-import` extra is installed rather than the two
    distributions by name: `pyproject.toml` pins their versions, and repeating
    those pins here would create a second place to forget to update.
    """
    root = Path(__file__).resolve().parent.parent
    if not (root / "pyproject.toml").is_file():
        raise ToolInstallError(
            "the master-import dependencies are declared by this project's pyproject.toml, which "
            f"is not beside the installed package at {root}. Install them yourself with: "
            f'{sys.executable} -m pip install "UnityPy" "TypeTreeGeneratorAPI"'
        )
    print("Installing the master-import dependencies with pip.")
    command = (sys.executable, "-m", "pip", "install", f"{root}[master-import]")
    try:
        result = subprocess.run(command, text=True, capture_output=True, timeout=1800)
    except (OSError, subprocess.SubprocessError) as error:
        raise ToolInstallError(f"could not run pip: {error}") from error
    if result.returncode != 0:
        raise ToolInstallError(
            f"pip could not install the master-import dependencies: "
            f"{(result.stderr or result.stdout or '').strip() or f'exit {result.returncode}'}"
        )
    print("  master-import dependencies ready.")


def confirm_android_licences(ask: Callable[[str], str] = input) -> bool:
    """Ask the operator to accept Google's SDK licences, in their own words."""
    print(
        "\nThe Android SDK packages are covered by the Android Software Development Kit\n"
        f"Licence Agreement: {tool_install.ANDROID_LICENCE_URL}\n"
        "Accepting is your decision, so this command will not answer for you."
    )
    try:
        answer = ask("Accept the Android SDK licences and continue? [y/N]: ").strip().lower()
    except EOFError:
        return False
    return answer in {"y", "yes"}


def install_missing(
    statuses: Sequence[ToolStatus], data_directory: Path, host: Host,
    recorded: Toolchain, accept_licences: bool, packages: Sequence[str],
) -> Toolchain:
    """Fetch what is absent, in dependency order, recording each success.

    Ordered rather than independent: `sdkmanager` is a Java program, so a
    machine missing both a JDK and the SDK has to gain them in that sequence.
    Each success is saved as it happens, so a run that fails partway leaves the
    tools it did install recorded rather than orphaned in the data directory.
    """
    root = data_directory / tool_install.TOOLCHAIN_DIRECTORY
    updated = recorded

    def keep(**found: Path | None) -> None:
        nonlocal updated
        updated = updated.with_updates(**found)
        toolchain_module.save(data_directory, updated)
        toolchain_module.apply(updated, override=True)

    needs_sdk = any(
        _missing(statuses, name)
        for name in ("platform tools", "build tools", "disassembler")
    )
    if needs_sdk:
        tool_install.require_supported_android_sdk_host(host)
    if needs_sdk and not accept_licences:
        # Refused here rather than at the SDK step below, because that step is
        # reached only after a JDK has been fetched for it. Declining the
        # licences should not cost a 180 MB download first.
        raise ToolInstallError(
            "the Android SDK packages cannot be installed without accepting Google's SDK "
            "licences. Re-run with --accept-android-sdk-licenses, or install the SDK through "
            "Android Studio as described in docs/install-tools.md."
        )
    # A JDK is also fetched for the SDK's sake, because `sdkmanager` is itself a
    # Java program. That second condition tests for `java` specifically: the
    # `keytool` found above can belong to a runtime that is not on PATH, which
    # satisfies signing and still leaves sdkmanager with nothing to launch.
    if _missing(statuses, "java") or (needs_sdk and shutil.which("java") is None):
        keep(java_home=tool_install.install_jdk(root, host))

    if needs_sdk:
        sdk_root = updated.sdk_root or (root / "android-sdk")
        tool_install.accept_android_licences(sdk_root, root, host, updated.java_home)
        selected_packages = list(packages)
        if (
            _missing(statuses, "disassembler")
            and tool_install.ANDROID_NDK_PACKAGE not in selected_packages
        ):
            selected_packages.append(tool_install.ANDROID_NDK_PACKAGE)
        keep(sdk_root=tool_install.install_android_packages(
            sdk_root, root, host, updated.java_home, tuple(selected_packages),
        ))
        if _missing(statuses, "disassembler"):
            objdump = tool_install.android_ndk_objdump(updated.sdk_root, host)
            if tester_setup.find_aarch64_objdump((str(objdump),)) is None:
                raise ToolInstallError(
                    f"the installed disassembler at {objdump} does not report AArch64 support"
                )
            keep(objdump=objdump)

    if _missing(statuses, "UnityPy"):
        install_master_import()

    if _missing(statuses, "Il2CppDumper"):
        dumper = tool_install.install_il2cpp_dumper(root, host)
        keep(il2cpp_dumper=dumper)
        if dumper.suffix.lower() == ".dll" and tester_setup.find_il2cpp_dumper() is None:
            # The managed build is the only one published for this platform and
            # it has no runtime to run on, so the dumper is not actually usable
            # yet however successfully it unpacked.
            keep(dotnet_root=tool_install.install_dotnet_runtime(root, host))

    return updated


def record_discoveries(data_directory: Path, recorded: Toolchain, host: Host) -> Toolchain:
    """Record tools that are installed but unreachable, before judging the machine.

    Run ahead of the survey so its verdict matches what setup would actually
    find. Without this the common macOS case reads as a missing disassembler on
    a machine whose Command Line Tools have been providing one all along, and
    the advice printed alongside would be to install what is already there.
    """
    if tester_setup.find_aarch64_objdump() is not None:
        return recorded
    found = find_objdump(host)
    if found is None:
        return recorded
    updated = recorded.with_updates(objdump=found)
    toolchain_module.save(data_directory, updated)
    toolchain_module.apply(updated, override=True)
    print(f"Recorded a disassembler that was installed but not on PATH: {found}\n")
    return updated


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument(
        "--install-missing", action="store_true",
        help="download and record the tools this machine is missing; without it nothing is fetched",
    )
    parser.add_argument(
        "--accept-android-sdk-licenses", dest="accept_licences", action="store_true",
        help=f"accept the Android SDK licences ({tool_install.ANDROID_LICENCE_URL}) without being asked",
    )
    parser.add_argument(
        "--android-package", dest="packages", action="append", metavar="PACKAGE",
        help=(
            "sdkmanager package to install instead of the defaults "
            f"({', '.join(tool_install.ANDROID_PACKAGES)}); repeatable. The pinned "
            f"{tool_install.ANDROID_NDK_PACKAGE} package is still added when the "
            "AArch64 disassembler is missing"
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        host = detect_host()
    except ToolInstallError as error:
        print(f"tool doctor: {error}")
        return 1

    print(
        "Checking the tools guided setup needs. Where they are is recorded under "
        f"{args.data_dir}; nothing is installed unless --install-missing is given.\n"
    )
    recorded = toolchain_module.load_and_apply(args.data_dir)
    if not recorded.is_empty():
        print(f"Using the tool locations recorded in {toolchain_module.toolchain_path(args.data_dir)}.\n")
    try:
        recorded = record_discoveries(args.data_dir, recorded, host)
    except ToolchainError as error:
        print(f"tool doctor failed: {error}")
        return 1

    statuses = survey(host)
    report(statuses)

    if args.install_missing and any(not status.ok and status.fixable for status in statuses):
        accept = args.accept_licences
        needs_sdk = any(
            _missing(statuses, name)
            for name in ("platform tools", "build tools", "disassembler")
        )
        if needs_sdk and not accept and sys.stdin.isatty():
            accept = confirm_android_licences()
        print()
        try:
            install_missing(
                statuses, args.data_dir, host, recorded, accept,
                tuple(args.packages) if args.packages else tool_install.ANDROID_PACKAGES,
            )
        except (ToolInstallError, ToolchainError) as error:
            print(f"\ntool doctor failed: {error}")
            return 1
        print("\nRe-checking after installation.\n")
        statuses = survey(host)
        report(statuses)

    outstanding = [status for status in statuses if not status.ok]
    if not outstanding:
        print(
            f"\nEverything is ready, and its location is recorded in "
            f"{toolchain_module.toolchain_path(args.data_dir)}.\n"
            "You do not need to set PATH or JAVA_HOME; setup reads that file."
        )
        return 0
    if args.install_missing:
        unfixable = [status.name for status in outstanding if not status.fixable]
        print(
            f"\n{len(outstanding)} tool(s) still missing"
            + (f"; {', '.join(unfixable)} cannot be installed by this command." if unfixable else ".")
        )
    else:
        print(
            f"\n{len(outstanding)} tool(s) missing. Run this again with --install-missing to fetch "
            "the ones it can, or follow docs/install-tools.md to install them yourself."
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
