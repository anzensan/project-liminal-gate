"""Remember where the build tools are, so no shell variable has to be edited.

Every tool guided setup needs is found by the resolvers in `tester_setup`, and
each of them reads the environment: `ANDROID_SDK_ROOT` for the SDK, `JAVA_HOME`
for `keytool`, `PATH` for `adb` and the disassembler, and
`LIMINAL_GATE_IL2CPPDUMPER` for the dumper.  That works, and it is why
`docs/install-tools.md` spends most of its length teaching three different
shells to export the same four variables -- a step that is invisible when it
succeeds, silently undone by opening a new terminal, and the single most common
reason a correctly equipped machine reports missing tools.

So the locations are recorded in one file instead, beneath the ignored data
directory, and replayed into this process's own environment at startup.  The
resolvers are untouched: they still read the environment, and the environment
now says what the last `liminal_gate.doctor` run found.  Nothing outside this
process is modified, so no shell profile is edited and no other program's
configuration changes.

A variable the operator has already set always wins.  Someone who deliberately
exported `JAVA_HOME` is making a choice, and a recorded value from an earlier
run is not entitled to overrule it; the record fills gaps rather than asserting
control.  `PATH` follows the same rule by appending, never prepending.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import Iterator, MutableMapping


#: Where the record lives, relative to `--data-dir`.  That directory is already
#: ignored by Git and already holds the rest of the tester's local state.
TOOLCHAIN_FILE = "toolchain.json"

#: Bumped only when an older file could be misread rather than merely lacking a
#: field.  Unknown keys are ignored, so adding a tool does not need a bump.
DOCUMENT_VERSION = 1


class ToolchainError(RuntimeError):
    """The recorded tool locations cannot be read or written."""


@dataclass(frozen=True)
class Toolchain:
    """Where each externally installed tool was last found.

    Every field is optional.  A tool that the machine already provides on
    `PATH` never needs recording, so an empty record on a well-equipped machine
    is the expected result rather than a failure.
    """

    #: Android SDK root, holding `platform-tools` and `build-tools`.
    sdk_root: Path | None = None
    #: A JDK root.  `keytool` lives in its `bin`, and Gradle is handed the root.
    java_home: Path | None = None
    #: The Il2CppDumper executable or its managed `.dll`.
    il2cpp_dumper: Path | None = None
    #: An `objdump` that can read AArch64.  Recorded as the file, because the
    #: one macOS ships is reached through a directory nothing else needs.
    objdump: Path | None = None
    #: The directory containing a `dotnet` launcher, for a managed dumper.
    dotnet_root: Path | None = None

    def is_empty(self) -> bool:
        return all(getattr(self, field.name) is None for field in fields(self))

    def with_updates(self, **updates: Path | None) -> "Toolchain":
        """Return a copy carrying the given locations, ignoring `None` updates.

        Discovering one tool must never erase another, and every caller here
        learns about tools one at a time, so an update that found nothing is
        dropped rather than written through as an absence.
        """
        return replace(self, **{name: value for name, value in updates.items() if value is not None})


def _document_paths(document: object) -> dict[str, Path]:
    if not isinstance(document, dict):
        raise ToolchainError("recorded tool locations must be a JSON object")
    version = document.get("version", DOCUMENT_VERSION)
    if not isinstance(version, int) or version > DOCUMENT_VERSION:
        raise ToolchainError(
            f"recorded tool locations were written by a newer version ({version!r}); "
            f"this build understands up to {DOCUMENT_VERSION}"
        )
    tools = document.get("tools", {})
    if not isinstance(tools, dict):
        raise ToolchainError("the 'tools' member of the recorded tool locations must be an object")
    known = {field.name for field in fields(Toolchain)}
    resolved: dict[str, Path] = {}
    for name, value in tools.items():
        if name not in known or value is None:
            # Unknown members are ignored on purpose: a record written by a
            # build that knows about one more tool must stay readable here.
            continue
        if not isinstance(value, str) or not value.strip():
            raise ToolchainError(f"recorded location for {name!r} must be a non-empty string")
        resolved[name] = Path(value)
    return resolved


def to_document(toolchain: Toolchain) -> dict[str, object]:
    return {
        "version": DOCUMENT_VERSION,
        "tools": {
            field.name: str(value)
            for field in fields(Toolchain)
            if (value := getattr(toolchain, field.name)) is not None
        },
    }


def toolchain_path(data_directory: Path) -> Path:
    return data_directory / TOOLCHAIN_FILE


def load(data_directory: Path) -> Toolchain:
    """Return the recorded locations, or an empty record if none were written.

    A missing file is the normal state before the first `doctor` run and is not
    an error.  A file that exists but cannot be parsed *is* one: silently
    treating it as empty would send the operator back to hunting for tools the
    record already names.
    """
    path = toolchain_path(data_directory)
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return Toolchain()
    except OSError as error:
        raise ToolchainError(f"could not read recorded tool locations at {path}: {error}") from error
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ToolchainError(
            f"recorded tool locations at {path} are not valid JSON: {error}. "
            "Delete the file and run the doctor again to rebuild it."
        ) from error
    return Toolchain(**_document_paths(document))


def save(data_directory: Path, toolchain: Toolchain) -> Path:
    """Write the record, absolute, so a later run from another directory agrees.

    Paths are resolved here rather than at discovery time because a relative
    path recorded from one working directory names a different place when the
    tester runs setup from another, and the failure that produces reports a
    missing tool on a machine that has it.
    """
    path = toolchain_path(data_directory)
    absolute = Toolchain(**{
        field.name: value.expanduser().resolve()
        for field in fields(Toolchain)
        if (value := getattr(toolchain, field.name)) is not None
    })
    temporary: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        rendered = json.dumps(to_document(absolute), indent=2, sort_keys=True) + "\n"
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(rendered)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    except OSError as error:
        raise ToolchainError(f"could not write recorded tool locations to {path}: {error}") from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return path


def _executable_directories(toolchain: Toolchain) -> Iterator[Path]:
    """Yield the directories that have to be searchable for a tool to be found."""
    if toolchain.java_home is not None:
        yield toolchain.java_home / "bin"
    if toolchain.sdk_root is not None:
        yield toolchain.sdk_root / "platform-tools"
        yield toolchain.sdk_root / "cmdline-tools" / "latest" / "bin"
        yield toolchain.sdk_root / "emulator"
    if toolchain.dotnet_root is not None:
        yield toolchain.dotnet_root
    for tool in (toolchain.objdump, toolchain.il2cpp_dumper):
        if tool is not None:
            yield tool.parent


def _variables(toolchain: Toolchain) -> dict[str, str]:
    """Return the environment each recorded location stands behind."""
    values: dict[str, str] = {}
    if toolchain.sdk_root is not None:
        # Both names are set because the SDK's own tools disagree about which
        # is authoritative, and the resolvers here read either one.
        values["ANDROID_SDK_ROOT"] = str(toolchain.sdk_root)
        values["ANDROID_HOME"] = str(toolchain.sdk_root)
    if toolchain.java_home is not None:
        values["JAVA_HOME"] = str(toolchain.java_home)
    if toolchain.il2cpp_dumper is not None:
        values["LIMINAL_GATE_IL2CPPDUMPER"] = str(toolchain.il2cpp_dumper)
        if toolchain.il2cpp_dumper.suffix.lower() == ".dll":
            # The only Il2CppDumper builds for macOS and Linux are managed
            # assemblies targeting .NET 6 and 7, both of which are out of
            # support and neither of which a current runtime will host unless
            # it is allowed to roll forward across a major version.  Without
            # this the dumper aborts at startup naming a runtime the operator
            # cannot reasonably be asked to install.
            values["DOTNET_ROLL_FORWARD"] = "Major"
    if toolchain.dotnet_root is not None:
        values["DOTNET_ROOT"] = str(toolchain.dotnet_root)
    return values


def apply(
    toolchain: Toolchain,
    environ: MutableMapping[str, str] | None = None,
    override: bool = False,
) -> tuple[str, ...]:
    """Put the recorded locations into an environment and return what was set.

    By default only gaps are filled.  An operator who exported one of these has
    said where their tool is, and a value recorded by an earlier run does not
    get to disagree with a deliberate choice made in the terminal setup is
    running in.

    `override` exists for the one caller that has earned the right to disagree:
    the doctor, immediately after installing a tool.  It only installs one
    because whatever the environment already named failed to provide a working
    tool, so continuing to defer to that value would verify the wrong thing and
    report the install as a failure.
    """
    target = os.environ if environ is None else environ
    changed: list[str] = []
    for name, value in _variables(toolchain).items():
        if target.get(name, "").strip() and not override:
            continue
        target[name] = value
        changed.append(name)

    existing = [entry for entry in target.get("PATH", "").split(os.pathsep) if entry]
    known = {os.path.normcase(entry) for entry in existing}
    added: list[str] = []
    for directory in _executable_directories(toolchain):
        if not directory.is_dir():
            continue
        text = str(directory)
        if os.path.normcase(text) in known:
            continue
        known.add(os.path.normcase(text))
        added.append(text)
    if added:
        # Appended, for the same reason the variables above are only filled in:
        # a tool already on the operator's PATH keeps priority. When overriding,
        # the freshly installed one has to win, so it goes in front instead.
        order = (*added, *existing) if override else (*existing, *added)
        target["PATH"] = os.pathsep.join(order)
        changed.append("PATH")
    return tuple(changed)


def load_and_apply(data_directory: Path) -> Toolchain:
    """Replay any recorded locations before a launcher resolves its tools.

    Called for effect at the top of every entry point that needs an external
    tool.  A missing or unreadable record must not stop a machine that has its
    tools on `PATH` from starting, so failure here is reported and stepped over
    rather than raised: the resolvers run next and say precisely what is absent.
    """
    try:
        toolchain = load(data_directory)
    except ToolchainError as error:
        print(f"Ignoring the recorded tool locations: {error}")
        return Toolchain()
    apply(toolchain)
    return toolchain
