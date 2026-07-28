"""Derive per-stage story encounter spawns from a user-owned reviewed APK.

Every other importer in this repository reads *serialized data*: a Unity object
inside ``resources.assets`` whose field layout the ``DummyDll`` type trees
recover.  The Chapter 8--42 encounter map is not serialized data.  The final
client compiles each chapter's battle script into IL2CPP generator classes, and
a stage's spawn list only exists as a sequence of virtual calls inside
``libil2cpp.so``.  Reading it therefore needs a disassembler, which is why this
is the one import that cannot be served by UnityPy.

What this reads, and why each input is needed
---------------------------------------------

* ``--apk`` -- your own reviewed APK.  The ARM64 ``libil2cpp.so`` is read out of
  it into a temporary directory and deleted again; nothing is written beside
  the APK and no library bytes reach the output.
* ``--dump-cs`` -- the ``dump.cs`` file produced by the *same* Il2CppDumper run
  that produced your ``DummyDll`` directory (it is that directory's sibling in
  the Il2CppDumper output).  This is an explicit additional input, not a hidden
  assumption: the disassembly alone gives no method names, no managed virtual
  slot numbers, and no ``Enemies`` enum, and all three are required.  See
  "Generating the `DummyDll` directory" in ``docs/advanced-configuration.md``.
* ``--objdump`` -- any ``objdump`` that can disassemble AArch64.  The importer
  records the version string it saw.

How a spawn is recovered
------------------------

A chapter's battle program is a compiler-generated iterator; its body is the
``MoveNext`` method of a type named like ``Chapter8.$Battle1_1$25037.$``.  Spawn
calls in that body are *indirect*: the generator loads the chapter object's
``Il2CppClass`` pointer, indexes the managed vtable, and branches::

    ldr  x8, [x20]              ; Il2CppClass*
    ldr  x9, [x8, #0x530]       ; vtable entry
    blr  x9                     ; -> Chapter8::Init_CH8_BMAKER

The vtable begins ``CLASS_HEADER_BYTES`` into ``Il2CppClass`` and each entry is
``VTABLE_ENTRY_BYTES`` wide, so ``0x530`` is managed slot 66, and ``dump.cs``
names the ``Chapter8`` (or inherited ``ChapterBase``) method occupying slot 66.
Only arguments that are immediate at the call site would be statically known, so
this importer records the *identity* of each spawn and its multiplicity, which
is all a drop ceiling needs, and nothing that would require emulating the
program.

Scope: ARM64 only
-----------------

The APK also ships ``armeabi-v7a``, whose class header is ``0xB4`` and whose
vtable entries are 8 bytes.  Supporting it would need a second register-tracking
pass over a different calling convention for no additional information -- the
two ABIs are compiled from one program.  ARM64 is the ABI every offset in this
project's documentation refers to.  A 32-bit port is possible follow-up work and
is deliberately not attempted here.

Usage::

    python3 -m liminal_gate.native_encounter_importer \\
        --apk local-input/terra-battle-5.5.7-170.apk \\
        --dump-cs /path/to/il2cpp-output/dump.cs \\
        --output user-data/derived/native-encounters.json

The output is an ignored, local, user-derived projection.  It carries stage
identities, enemy record IDs, and spawn counts -- no names, no text, no code.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Callable, Iterable, NamedTuple
import zipfile


ARM64_LIBRARY_MEMBER = "lib/arm64-v8a/libil2cpp.so"
SCHEMA_VERSION = 1
SOURCE_PROFILE = "terra-battle-android-5.5.7-170"
ABI = "arm64"

#: ``Il2CppClass`` layout for this build's ARM64 library: the managed vtable
#: starts here and each entry is this wide.  Both are checked against two
#: fixtures below when the library is the reviewed one.
CLASS_HEADER_BYTES = 0x110
VTABLE_ENTRY_BYTES = 16

#: SHA-256 of ``lib/arm64-v8a/libil2cpp.so`` in the reviewed 5.5.7-170 APK.
#: Advisory only.  A match enables the vtable calibration fixtures below; a
#: mismatch is reported rather than fatal, because a different build can still
#: be read -- its layout simply has not been checked here.
REVIEWED_ARM64_LIBRARY_SHA256 = "ba6fecba562f7ff46305792cadeabcae1879a0c384f7195a5d77872af04c1753"

#: Two calls whose caller offset and callee slot were resolved by hand against
#: the reviewed library.  ``(type, member, rva, stop, site, operand)``: within
#: ``member``'s body, address ``site`` must load the vtable at ``operand``.  The
#: first pins a generator's call into a chapter initializer; the second pins an
#: initializer's own call onward.  Together they fix both constants above.
_CALIBRATION = (
    ("Chapter8.$Battle1_1$25037.$", "MoveNext", 0x1A38400, 0x1A38520, "1a384d8:", "#0x530]"),
    ("Chapter8", "Init_CH8_BMAKER", 0x1A3358C, 0x1A33620, "1a335f0:", "#0x570]"),
)

CHAPTERS = range(8, 43)
_CHAPTER_TYPE_RE = re.compile(r"^Chapter(8|9|[1-3][0-9]|4[0-2])(?:\.|$)")
_BATTLE_TYPE_RE = re.compile(r"Battle(\d+)_(\d+)")
_TYPE_RE = re.compile(
    r"^(?:public|private|internal|protected)?\s*"
    r"(?:sealed\s+|static\s+|abstract\s+)*"
    r"(?:class|struct|interface|enum)\s+(.+?)"
    r"(?:\s*:\s*.*?)?\s*// TypeDefIndex: \d+$"
)
_ADDRESS_RE = re.compile(r"^\s*// RVA: 0x([0-9A-Fa-f]+).*?(?: Slot: (\d+))?$")
_ENEMY_MEMBER_RE = re.compile(r"Enemies\s+(\w+)\s*=\s*(-?\d+)\s*;")
_INSTRUCTION_RE = re.compile(r"^\s*([0-9a-f]+):\s+[0-9a-f]+\s+([.\w]+)\s*(.*?)\s*$", re.I)

#: A chapter program may call a *variant* initializer -- the same enemy with a
#: behavioural modifier applied (no-move, wall-bound, appears-later, a numbered
#: clone).  Those variants are their own native methods but usually not their
#: own ``Enemies`` members, so the symbol is reduced to its base member and the
#: resulting row is marked ``exact: false``.  The variant's rewards follow the
#: base record's: Strongly inferred, never promoted to exact, because a modifier
#: could in principle alter them.  Longest alternatives lead so ``_MA1`` is not
#: read as ``_MA`` plus a stray ``1``.
#:
#: This matches ONE suffix, not a run of them.  `resolve_symbol` peels them one
#: at a time and re-checks membership after each, because the base member can
#: sit partway through the run: ``CH31_LEAD_S_WITH_PARENT`` reduces to the real
#: member ``CH31_LEAD_S``, and stripping the whole run at once overshoots it to
#: ``CH31_LEAD``, which does not exist.  Eight of the ten stages that failed to
#: join at all failed exactly this way.
#:
#: A bare trailing digit is a variant suffix too: numbered clones are written
#: both ways (``CH33_KING2`` beside ``CH21_PLUS3``).  It is tried only after a
#: full-symbol membership check, so a numbered enemy that *is* its own member --
#: ``CH2_BAKUROU2`` -- still resolves to itself, exactly.
_SUFFIX_RE = re.compile(
    r"(_TANM|_TWNM|_2NM|_NM|_WB|_FNM"
    r"|_APPEAR|_ATTACK|_MOVE|_FIRST"
    r"|_MA1|_MA2|_MA|_AS|_CS|_SL"
    r"|_WITH_PARENT|_PARENT|_CLONE"
    r"|_S|_L|_R|_H|_V"
    r"|_2|_3|_4|_5|_6"
    r"|\d)$"
)

#: How many suffixes may be peeled from one symbol before giving up.  A real
#: variant name stacks two or three; a longer chain means the guess has stopped
#: being a reduction and started being a search, so it stops instead.
_MAX_SUFFIX_PEELS = 4

#: Upper bound on one generator body, used when the next method's RVA is too far
#: away to trust (the last method in the library has no successor).
_MAX_BODY_BYTES = 0x20000

#: Callee names worth recording.  ``Init_*`` places a named enemy; ``CreateEnemy``
#: is the shared placement helper the initializers themselves call.
_SPAWN_PREFIX = "Init_"
_SPAWN_INFIX = "CreateEnemy"


class NativeEncounterImportError(ValueError):
    """A local APK, dump, or disassembler cannot produce an encounter map."""


class Method(NamedTuple):
    type_name: str
    member_name: str
    rva: int
    slot: int | None


class Spawn(NamedTuple):
    symbol: str
    enemy_id: int | None
    exact: bool
    count: int


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_methods(text: str) -> list[Method]:
    """Read every ``dump.cs`` method with its RVA and managed virtual slot."""
    current_type = ""
    pending: tuple[int, int | None] | None = None
    methods: list[Method] = []
    for line in text.splitlines():
        if match := _TYPE_RE.match(line):
            current_type = match.group(1)
            pending = None
            continue
        if match := _ADDRESS_RE.match(line):
            pending = (int(match.group(1), 16), int(match.group(2)) if match.group(2) else None)
            continue
        stripped = line.strip()
        if pending is not None and stripped.endswith("{ }") and "(" in stripped:
            member = stripped[:-3].strip().split("(", 1)[0].rsplit(" ", 1)[-1]
            methods.append(Method(current_type, member, pending[0], pending[1]))
            pending = None
    if not methods:
        raise NativeEncounterImportError("dump.cs contains no method definitions")
    return methods


def parse_enemies_enum(text: str) -> dict[str, int]:
    """Map every ``Enemies`` member to its enemy record ID."""
    mapping: dict[str, int] = {}
    inside = False
    for line in text.splitlines():
        if not inside:
            inside = "enum Enemies" in line
            continue
        if line.startswith("}"):
            break
        if match := _ENEMY_MEMBER_RE.search(line):
            mapping[match.group(1)] = int(match.group(2))
    if not mapping:
        raise NativeEncounterImportError("dump.cs contains no Enemies enum")
    return mapping


def resolve_symbol(symbol: str, enemies: dict[str, int]) -> tuple[int | None, bool]:
    """Resolve an initializer symbol to ``(enemy_id, exact)``.

    ``exact`` is true only for a symbol that is itself an ``Enemies`` member.
    A variant symbol reduced to its base member resolves with ``exact`` false
    and must stay distinguishable downstream.

    Suffixes are peeled one at a time and membership is re-checked after each,
    so the *most specific* base wins.  Stripping the whole run at once would
    skip past a real member that carries a suffix of its own.
    """
    if symbol in enemies:
        return enemies[symbol], True
    base = symbol
    for _ in range(_MAX_SUFFIX_PEELS):
        match = _SUFFIX_RE.search(base)
        if match is None or match.start() == 0:
            return None, False
        base = base[: match.start()]
        if base in enemies:
            return enemies[base], False
    return None, False


def instructions(text: str) -> list[tuple[int, str, str]]:
    """Return ``(address, mnemonic, operands)`` for one objdump listing."""
    rows: list[tuple[int, str, str]] = []
    for line in text.splitlines():
        if match := _INSTRUCTION_RE.match(line):
            rows.append((int(match.group(1), 16), match.group(2).lower(), match.group(3).lower()))
    return rows


def arm64_spawn_targets(text: str, slots: dict[int, Method]) -> list[str]:
    """Return each spawn callee named by one ARM64 generator body, in order.

    Only the load-then-branch pair matters here.  Registers are not tracked,
    because the recovered argument vector (grid position, wait counters) is not
    what a drop ceiling reads, and tracking it would add a large amount of
    machinery whose failures would be silent.
    """
    vtable_offsets: dict[int, int] = {}
    targets: list[str] = []
    for _address, mnemonic, operands in instructions(text):
        line = f"{mnemonic} {operands}"
        if match := re.match(r"ldr\s+x(\d+),\s*\[x\d+,\s*#0x([0-9a-f]+)\]", line):
            vtable_offsets[int(match.group(1))] = int(match.group(2), 16)
        elif match := re.match(r"blr\s+x(\d+)", line):
            offset = vtable_offsets.get(int(match.group(1)))
            method = _slot_method(offset, slots)
            if method is not None:
                targets.append(method.member_name)
            vtable_offsets.clear()
        elif mnemonic == "bl":
            vtable_offsets.clear()
    return targets


def _slot_method(offset: int | None, slots: dict[int, Method]) -> Method | None:
    if offset is None or offset < CLASS_HEADER_BYTES or (offset - CLASS_HEADER_BYTES) % VTABLE_ENTRY_BYTES:
        return None
    method = slots.get((offset - CLASS_HEADER_BYTES) // VTABLE_ENTRY_BYTES)
    if method is None or not (method.member_name.startswith(_SPAWN_PREFIX) or _SPAWN_INFIX in method.member_name):
        return None
    return method


def stage_identity(type_name: str) -> tuple[int, int] | None:
    """Map a generator type name to the ``(chapter, section)`` it settles."""
    chapter_match = _CHAPTER_TYPE_RE.match(type_name)
    battle_match = _BATTLE_TYPE_RE.search(type_name)
    if chapter_match is None or battle_match is None:
        return None
    chapter = int(chapter_match.group(1))
    section, battle = int(battle_match.group(1)), int(battle_match.group(2))
    if chapter == 20:
        # Chapter 20 is one continuous twenty-battle program backing ten
        # two-battle sections, so its generator numbering is not the section
        # numbering the client and BattleData use.
        section = (battle + 1) // 2
    return chapter, section


def build_document(
    spawns_by_stage: dict[tuple[int, int], list[str]],
    enemies: dict[str, int],
    source: dict[str, object],
) -> dict[str, object]:
    """Project raw per-stage callee names into the local encounter document."""
    if not spawns_by_stage:
        raise NativeEncounterImportError("no Chapter 8-42 generator produced a spawn call")
    stages: list[dict[str, object]] = []
    unresolved_symbols: dict[str, int] = {}
    for (chapter, section), symbols in sorted(spawns_by_stage.items()):
        counts: dict[str, int] = {}
        for name in symbols:
            symbol = name[len(_SPAWN_PREFIX):] if name.startswith(_SPAWN_PREFIX) else name
            counts[symbol] = counts.get(symbol, 0) + 1
        rows = [Spawn(symbol, *resolve_symbol(symbol, enemies), count) for symbol, count in sorted(counts.items())]
        for row in rows:
            if row.enemy_id is None:
                unresolved_symbols[row.symbol] = unresolved_symbols.get(row.symbol, 0) + row.count
        stages.append({
            "chapter": chapter,
            "section": section,
            "resolved": all(row.enemy_id is not None for row in rows),
            "exact": all(row.enemy_id is not None and row.exact for row in rows),
            "spawns": [
                {"symbol": row.symbol, "enemy_id": row.enemy_id, "exact": row.exact, "count": row.count}
                for row in rows
            ],
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "provenance": "user-derived",
        "source": source,
        "stages": stages,
        "unresolved_symbols": [
            {"symbol": symbol, "count": count} for symbol, count in sorted(unresolved_symbols.items())
        ],
        "summary": {
            "stages": len(stages),
            "stages_resolved": sum(1 for stage in stages if stage["resolved"]),
            "stages_exact": sum(1 for stage in stages if stage["exact"]),
            "distinct_unresolved_symbols": len(unresolved_symbols),
        },
    }


def extract_library(apk: Path, destination: Path) -> Path:
    """Copy the reviewed APK's ARM64 IL2CPP library into a scratch directory."""
    library = destination / "libil2cpp.so"
    try:
        with zipfile.ZipFile(apk) as archive, archive.open(ARM64_LIBRARY_MEMBER) as source, library.open("wb") as stream:
            shutil.copyfileobj(source, stream)
    except (OSError, KeyError, zipfile.BadZipFile) as error:
        raise NativeEncounterImportError("APK does not contain lib/arm64-v8a/libil2cpp.so") from error
    return library


def disassemble(objdump: str, library: Path, start: int, stop: int) -> str:
    try:
        completed = subprocess.run(
            (objdump, "--disassemble", f"--start-address=0x{start:X}", f"--stop-address=0x{stop:X}", str(library)),
            stdin=subprocess.DEVNULL, capture_output=True, text=True, check=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise NativeEncounterImportError(f"objdump failed on 0x{start:X}-0x{stop:X}") from error
    return completed.stdout


def objdump_version(objdump: str) -> str:
    try:
        completed = subprocess.run(
            (objdump, "--version"), stdin=subprocess.DEVNULL, capture_output=True, text=True, check=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise NativeEncounterImportError(f"could not run {objdump!r}") from error
    return completed.stdout.splitlines()[0].strip() if completed.stdout.strip() else "unknown"


def verify_calibration(methods: Iterable[Method], objdump: str, library: Path) -> None:
    """Confirm the two vtable constants against the reviewed library."""
    index = {(method.type_name, method.member_name): method for method in methods}
    for type_name, member, rva, stop, site, operand in _CALIBRATION:
        method = index.get((type_name, member))
        if method is None or method.rva != rva:
            raise NativeEncounterImportError(
                f"vtable calibration failed: {type_name}.{member} is not at 0x{rva:X} in this dump.cs"
            )
        text = disassemble(objdump, library, rva, stop).lower()
        if site not in text or operand not in text:
            raise NativeEncounterImportError(
                f"vtable calibration failed: {type_name}.{member} does not load {operand} at {site}"
            )


def collect_spawns(
    methods: list[Method], objdump: str, library: Path,
    progress: Callable[[int, int], None] | None = None,
) -> dict[tuple[int, int], list[str]]:
    """Disassemble every Chapter 8-42 generator and gather its spawn callees.

    `progress` is called with (done, total) after each generator. There are
    thousands of them and each is a separate disassembler invocation, so a
    caller with a terminal has something to show rather than going silent for
    minutes.
    """
    boundaries = sorted({method.rva for method in methods})
    successor = dict(zip(boundaries, boundaries[1:]))
    inherited = {method.slot: method for method in methods if method.type_name == "ChapterBase" and method.slot is not None}
    slot_maps = {
        chapter: inherited | {
            method.slot: method
            for method in methods
            if method.type_name == f"Chapter{chapter}" and method.slot is not None
        }
        for chapter in CHAPTERS
    }
    generators = [
        (method, identity)
        for method in methods
        if method.member_name == "MoveNext"
        for identity in (stage_identity(method.type_name),)
        if identity is not None
    ]
    spawns: dict[tuple[int, int], list[str]] = {}
    for done, (method, identity) in enumerate(generators, start=1):
        stop = min(successor.get(method.rva, method.rva + _MAX_BODY_BYTES), method.rva + _MAX_BODY_BYTES)
        text = disassemble(objdump, library, method.rva, stop)
        spawns.setdefault(identity, []).extend(arm64_spawn_targets(text, slot_maps[identity[0]]))
        if progress is not None:
            progress(done, len(generators))
    return spawns


def write_document(path: Path, document: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def import_encounters(
    apk: Path, dump_cs: Path, objdump: str,
    progress: Callable[[int, int], None] | None = None,
) -> dict[str, object]:
    """Read one reviewed APK and dump into a local encounter document."""
    try:
        text = dump_cs.read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        raise NativeEncounterImportError("could not read the Il2CppDumper dump.cs") from error
    methods = parse_methods(text)
    enemies = parse_enemies_enum(text)
    version = objdump_version(objdump)
    with tempfile.TemporaryDirectory() as directory:
        library = extract_library(apk, Path(directory))
        library_sha256 = sha256_file(library)
        calibrated = library_sha256 == REVIEWED_ARM64_LIBRARY_SHA256
        if calibrated:
            verify_calibration(methods, objdump, library)
        spawns = collect_spawns(methods, objdump, library, progress)
    return build_document(spawns, enemies, {
        "profile": SOURCE_PROFILE,
        "abi": ABI,
        "apk_sha256": sha256_file(apk),
        "dump_cs_sha256": sha256_file(dump_cs),
        "libil2cpp_sha256": library_sha256,
        "objdump": version,
        "vtable_calibration": "verified" if calibrated else "unverified",
    })


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apk", required=True, type=Path, help="your own reviewed APK")
    parser.add_argument("--dump-cs", required=True, type=Path, help="dump.cs from the run that produced DummyDll")
    parser.add_argument("--objdump", default="objdump", help="an objdump that disassembles AArch64")
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        document = import_encounters(args.apk.resolve(strict=True), args.dump_cs.resolve(strict=True), args.objdump)
        write_document(args.output, document)
    except (NativeEncounterImportError, OSError) as error:
        raise SystemExit(f"native encounter import failed: {error}") from error
    summary = document["summary"]
    source = document["source"]
    assert isinstance(summary, dict) and isinstance(source, dict)
    print(f"wrote local ARM64 story encounter map: {args.output}")
    print(
        f"  {summary['stages_resolved']}/{summary['stages']} stages resolve every spawn"
        f" ({summary['stages_exact']} with no inferred variant),"
        f" {summary['distinct_unresolved_symbols']} distinct unresolved symbol(s)"
    )
    if source["vtable_calibration"] != "verified":
        print("  note: this library is not the reviewed build; the vtable layout was assumed, not checked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
