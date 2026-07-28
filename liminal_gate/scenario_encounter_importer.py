"""Recover the Chapter 2--7 encounter map from the client's MoonSharp scripts.

`liminal_gate.native_encounter_importer` reads chapter battle programs out of
the compiled library.  Chapters 2--7 have none: their encounters are placed by
Lua scripts the client runs on an embedded MoonSharp VM, shipped as Unity
`TextAsset` objects.  Without this import those fifty stages reach the
story-outcome generator with nothing joined, so their item and character
ceilings stay empty and the Companions their *enemies* drop -- as opposed to the
ones the section allowlist names -- are invisible.

Output is the stage schema `story_outcome_generator --scenario-encounters`
accepts, identical to the native map's.  Provenance is validated separately, so
a scenario-derived row can never claim it came from a disassembled chapter
program.

Format (Confirmed): the payload is exactly `Processor.Dump`/`Processor.Undump`
from MoonSharp `Execution/VM/Processor_BinaryDump.cs`, using
`BinDumpBinaryReader` for compressed integers and a de-duplicated string table.
Every chapter asset opens with the 8-byte magic ``1D 4D 4F 4F 4E 23 0D 1A``
(ASCII ``.MOON#\\r\\n``).  Twelve declare compressed int32 version ``0x150``
(336), the value used by MoonSharp v2.0.0.0; the four ``Chapter7000-*`` assets
declare ``0x902`` (2306), the `DUMP_CHUNK_VERSION` at MoonSharp tag 0.9.2.  The
old format is identical except that opcode 21 is named `FuncMeta` and
serializes only ``NumVal | Name``; v2 renamed it `Meta` and added
``NumVal2 | Value``.

`OpCode` is byte-identical between v2.0.0.0 and current MoonSharp master, but
`InstructionFieldUsage.GetFieldUsage()` is **not**: `NewTable` and `Closure`
moved groups.  The v2.0.0.0 tables are used here; a decoder built against
current master silently misparses those two.

Sources:
https://github.com/moonsharp-devs/moonsharp/blob/v2.0.0.0/src/MoonSharp.Interpreter/Execution/VM/Processor/Processor_BinaryDump.cs
https://github.com/moonsharp-devs/moonsharp/blob/0.9.2/src/MoonSharp.Interpreter/Execution/VM/Processor/Processor_BinaryDump.cs

There is no container, compression, or encryption around the payload; the
client loads the asset whole and hands it to `Script.LoadStream`.

What is read out of the decoded program
---------------------------------------

`Meta` instructions delimit every function and give its name and length, so the
program's structure is recoverable without executing it.  A stage is a
``Section{N}`` function; the ``Battle{N}_{M}`` functions it names in order are
its waves; and each ``Init_*`` a wave calls places one named enemy, whose
`Enemies` enum member the initializer itself references.

Only *direct* calls count.  A call made inside a nested closure or behind a
conditional jump has no statically knowable per-clear count, and understating a
ceiling refuses a legitimate clear, so any section carrying one is dropped whole
and reported rather than guessed at.

Every emitted spawn is ``exact: false``.  The enemy identity is exact -- it is
the enum member the script names -- but placement is read from a static decode
rather than observed at runtime, so it stays Strongly inferred.

Usage::

    python3 -m liminal_gate.scenario_encounter_importer \\
        --apk local-input/terra-battle-5.5.7-170.apk \\
        --dump-cs /path/to/il2cpp-output/dump.cs \\
        --output user-data/derived/scenario-encounters.json
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import tempfile
from typing import Any
import zipfile

from liminal_gate.character_catalog_importer import APK_DATA_MEMBER
from liminal_gate.native_encounter_importer import SOURCE_PROFILE, parse_enemies_enum, sha256_file


class ScenarioEncounterImportError(ValueError):
    """The reviewed APK or dump.cs cannot produce a scenario encounter map."""


DUMP_CHUNK_MAGIC = 0x1A0D234E4F4F4D1D
DUMP_CHUNK_VERSION_V0_9_2 = 0x902
DUMP_CHUNK_VERSION_V2_0_0_0 = 0x150
SUPPORTED_DUMP_CHUNK_VERSIONS = frozenset({DUMP_CHUNK_VERSION_V0_9_2, DUMP_CHUNK_VERSION_V2_0_0_0})

#: BattleData numbers ordinary story chapters from 2; Chapter 1 is the tutorial
#: and is settled by its own scripted path, not by a story-outcome rule.
ORDINARY_CHAPTERS = tuple(range(2, 8))

#: `OpCode` enum order, MoonSharp v2.0.0.0, `Execution/VM/OpCode.cs`.
OPCODES = (
    "Nop", "Debug", "Pop", "Copy", "Swap", "Literal", "Closure", "NewTable",
    "TblInitN", "TblInitI", "StoreLcl", "Local", "StoreUpv", "Upvalue",
    "IndexSet", "Index", "IndexSetN", "IndexN", "IndexSetL", "IndexL",
    "Clean", "Meta", "BeginFn", "Args", "Call", "ThisCall", "Ret", "Jump",
    "Jf", "JNil", "JFor", "JtOrPop", "JfOrPop", "Concat", "LessEq", "Less",
    "Eq", "Add", "Sub", "Mul", "Div", "Mod", "Not", "Len", "Neg", "Power",
    "CNot", "MkTuple", "Scalar", "Incr", "ToNum", "ToBool", "ExpTuple",
    "IterPrep", "IterUpd", "Invalid",
)
OPCODES_V0_9_2 = tuple("FuncMeta" if opcode == "Meta" else opcode for opcode in OPCODES)

# `InstructionFieldUsage` flags, `Execution/InstructionFieldUsage.cs`.
F_NONE, F_SYMBOL, F_SYMBOLLIST, F_NAME = 0x0, 0x1, 0x2, 0x4
F_VALUE, F_NUMVAL, F_NUMVAL2 = 0x8, 0x10, 0x20
F_NUMVAL_AS_CODE_ADDR = 0x8010

# `GetFieldUsage()` switch, MoonSharp v2.0.0.0.
_NONE_OPS = frozenset({
    "TblInitN", "Scalar", "IterUpd", "IterPrep", "NewTable", "Concat",
    "LessEq", "Less", "Eq", "Add", "Sub", "Mul", "Div", "Mod", "Not", "Len",
    "Neg", "Power", "CNot", "ToBool",
})
_NUMVAL_OPS = frozenset({"Pop", "Copy", "TblInitI", "ExpTuple", "Incr", "ToNum", "Ret", "MkTuple"})
_CODEADDR_OPS = frozenset({"Jump", "Jf", "JNil", "JFor", "JtOrPop", "JfOrPop"})
_NUMVAL_NUMVAL2_OPS = frozenset({"Swap", "Clean"})
_SYMBOL_OPS = frozenset({"Local", "Upvalue"})
_SYM_VAL_NUM_NUM2_OPS = frozenset({"IndexSet", "IndexSetN", "IndexSetL"})
_SYM_NUM_NUM2_OPS = frozenset({"StoreLcl", "StoreUpv"})
_VALUE_OPS = frozenset({"Index", "IndexL", "IndexN", "Literal"})
_NAME_OPS = frozenset({"Nop", "Debug", "Invalid"})
_NUMVAL_NAME_OPS = frozenset({"Call", "ThisCall"})

DATA_TYPES = (
    "Nil", "Void", "Boolean", "Number", "String", "Function", "Table",
    "Tuple", "UserData", "Thread", "ClrFunction", "TailCallRequest", "YieldRequest",
)
SYMBOL_REF_TYPES = ("Local", "Upvalue", "Global", "DefaultEnv")

#: Functions the encounter walk cares about.
_SECTION_RE = re.compile(r"^Section(\d+)$")
_WAVE_RE = re.compile(r"^Battle\d+_\d+$")
_INITIALIZER_PREFIX = "Init_"
#: A string constant is read from these two opcodes; both are how the compiled
#: program names a sibling function or an `Enemies` member.
_STRING_REF_OPS = frozenset({"Index", "IndexN"})
#: Conditional jumps.  A call reached only past one of these is not a
#: deterministic placement.  `JtOrPop` is included for completeness; the
#: recovered chapters never reach an initializer through one.
_BRANCH_OPS = frozenset({"Jf", "JNil", "JfOrPop", "JtOrPop"})


def field_usage(opcode: str) -> int:
    if opcode in _NONE_OPS:
        return F_NONE
    if opcode in _NUMVAL_OPS:
        return F_NUMVAL
    if opcode in _CODEADDR_OPS:
        return F_NUMVAL_AS_CODE_ADDR
    if opcode in _NUMVAL_NUMVAL2_OPS:
        return F_NUMVAL | F_NUMVAL2
    if opcode in _SYMBOL_OPS:
        return F_SYMBOL
    if opcode in _SYM_VAL_NUM_NUM2_OPS:
        return F_SYMBOL | F_VALUE | F_NUMVAL | F_NUMVAL2
    if opcode in _SYM_NUM_NUM2_OPS:
        return F_SYMBOL | F_NUMVAL | F_NUMVAL2
    if opcode in _VALUE_OPS:
        return F_VALUE
    if opcode == "Args":
        return F_SYMBOLLIST
    if opcode == "BeginFn":
        return F_SYMBOLLIST | F_NUMVAL | F_NUMVAL2
    if opcode == "Closure":
        # v2.0.0.0: a plain NumVal, not a code address. This is one of the two
        # opcodes whose field usage differs in current MoonSharp master.
        return F_SYMBOLLIST | F_NUMVAL
    if opcode in _NAME_OPS:
        return F_NAME
    if opcode in _NUMVAL_NAME_OPS:
        return F_NUMVAL | F_NAME
    if opcode == "FuncMeta":
        return F_NUMVAL | F_NAME
    if opcode == "Meta":
        return F_NUMVAL | F_NUMVAL2 | F_VALUE | F_NAME
    raise ScenarioEncounterImportError(f"unhandled opcode for field usage: {opcode}")


class BinDumpReader:
    """MoonSharp's `BinDumpBinaryReader`: compressed int32 plus a write-once
    string table shared across the whole stream."""

    def __init__(self, data: bytes) -> None:
        self.buffer = data
        self.position = 0
        self.strings: list[str] = []

    def read_bytes(self, count: int) -> bytes:
        chunk = self.buffer[self.position:self.position + count]
        if len(chunk) != count:
            raise ScenarioEncounterImportError(
                f"expected {count} bytes at offset {self.position}, got {len(chunk)}"
            )
        self.position += count
        return chunk

    def read_byte(self) -> int:
        return self.read_bytes(1)[0]

    def read_bool(self) -> bool:
        return self.read_byte() != 0

    def read_uint64(self) -> int:
        return struct.unpack("<Q", self.read_bytes(8))[0]

    def read_double(self) -> float:
        return struct.unpack("<d", self.read_bytes(8))[0]

    def read_int32(self) -> int:
        """`ReadInt32` override: an sbyte marker, `0x7F` -> int16, `0x7E` ->
        raw int32, otherwise the sbyte value itself."""
        marker = struct.unpack("<b", self.read_bytes(1))[0]
        if marker == 0x7F:
            return struct.unpack("<h", self.read_bytes(2))[0]
        if marker == 0x7E:
            return struct.unpack("<i", self.read_bytes(4))[0]
        return marker

    def read_net_string(self) -> str:
        """`BinaryReader.ReadString()`: 7-bit-encoded length then UTF-8."""
        result, shift = 0, 0
        while True:
            byte = self.read_byte()
            result |= (byte & 0x7F) << shift
            if not byte & 0x80:
                break
            shift += 7
        try:
            return self.read_bytes(result).decode("utf-8")
        except UnicodeDecodeError as error:
            raise ScenarioEncounterImportError("chapter string table is not valid UTF-8") from error

    def read_string(self) -> str:
        """`ReadString` override: a compressed index into the string table; a
        new string is read raw and appended when the index equals its length."""
        index = self.read_int32()
        if index < len(self.strings):
            return self.strings[index]
        if index == len(self.strings):
            value = self.read_net_string()
            self.strings.append(value)
            return value
        raise ScenarioEncounterImportError(
            f"string table index {index} out of range ({len(self.strings)})"
        )


@dataclass
class SymbolRef:
    kind: str
    index: int
    name: str

    @staticmethod
    def read(reader: BinDumpReader) -> "SymbolRef":
        kind = SYMBOL_REF_TYPES[reader.read_byte()]
        return SymbolRef(kind, reader.read_int32(), reader.read_string())


@dataclass
class Instruction:
    index: int
    opcode: str
    num_val: int = 0
    name: str | None = None
    string_value: str | None = None


def _read_value(reader: BinDumpReader) -> str | None:
    """Read a `DynValue`, returning its text when it is a string constant."""
    if not reader.read_bool():
        return None
    data_type = DATA_TYPES[reader.read_byte()]
    if data_type in ("Nil", "Void"):
        return None
    if data_type == "Boolean":
        reader.read_bool()
        return None
    if data_type == "Number":
        reader.read_double()
        return None
    if data_type == "String":
        return reader.read_string()
    if data_type == "Table":
        return None
    raise ScenarioEncounterImportError(f"unsupported DynValue type in chunk dump: {data_type}")


def _read_instruction(reader: BinDumpReader, index: int, symbols: list[SymbolRef], version: int) -> Instruction:
    opcodes = OPCODES_V0_9_2 if version == DUMP_CHUNK_VERSION_V0_9_2 else OPCODES
    opcode = opcodes[reader.read_byte()]
    usage = field_usage(opcode)
    instruction = Instruction(index=index, opcode=opcode)
    if usage & F_NUMVAL:
        instruction.num_val = reader.read_int32()
    if usage & F_NUMVAL2:
        reader.read_int32()
    if usage & F_NAME:
        instruction.name = reader.read_string()
    if usage & F_VALUE:
        instruction.string_value = _read_value(reader)
    if usage & F_SYMBOL:
        reader.read_int32()
    if usage & F_SYMBOLLIST:
        for _ in range(reader.read_int32()):
            reader.read_int32()
    return instruction


def decode_chapter(data: bytes) -> list[Instruction]:
    """Decode one chapter asset into its instruction stream."""
    reader = BinDumpReader(data)
    if reader.read_uint64() != DUMP_CHUNK_MAGIC:
        raise ScenarioEncounterImportError("asset is not a MoonSharp dump chunk")
    version = reader.read_int32()
    if version not in SUPPORTED_DUMP_CHUNK_VERSIONS:
        raise ScenarioEncounterImportError(f"unexpected DUMP_CHUNK_VERSION {version:#x}")
    reader.read_bool()  # has_upvalues
    length = reader.read_int32()
    symbols = [SymbolRef.read(reader) for _ in range(reader.read_int32())]
    for _ in symbols:
        reader.read_int32()  # environment back-reference
    instructions = [_read_instruction(reader, index, symbols, version) for index in range(length + 1)]
    trailing = len(data) - reader.position
    if trailing:
        # A clean parse consumes the asset exactly. Anything left over means the
        # field-usage tables disagree with this build, and every offset after
        # the disagreement is untrustworthy.
        raise ScenarioEncounterImportError(f"{trailing} trailing unparsed byte(s) after the instruction stream")
    return instructions


def function_ranges(instructions: list[Instruction]) -> list[tuple[int, int, str]]:
    """Return ``(start, end, name)`` for every function the program declares."""
    ranges = []
    for instruction in instructions:
        if instruction.opcode in ("Meta", "FuncMeta") and instruction.name:
            ranges.append((instruction.index, instruction.index + instruction.num_val - 1, instruction.name))
    if not ranges:
        raise ScenarioEncounterImportError("chapter program declares no functions")
    return ranges


def _string_refs(instructions: list[Instruction], start: int, end: int):
    for index in range(start, min(end, len(instructions) - 1) + 1):
        instruction = instructions[index]
        if instruction.opcode in _STRING_REF_OPS and instruction.string_value:
            yield index, instruction.string_value


def _reached_conditionally(instructions: list[Instruction], start: int, target: int) -> bool:
    """Whether a conditional jump before ``target`` can skip past it."""
    for index in range(start, target):
        instruction = instructions[index]
        if instruction.opcode in _BRANCH_OPS and instruction.num_val > target:
            return True
    return False


def chapter_stages(instructions: list[Instruction], chapter: int, enemies: dict[str, int]) -> tuple[list[dict[str, Any]], list[int]]:
    """Return ``(stages, skipped_sections)`` for one decoded chapter."""
    ranges = function_ranges(instructions)
    named = {name: (start, end) for start, end, name in ranges}
    initializer_enemy: dict[str, str] = {}
    for name, (start, end) in named.items():
        if not name.startswith(_INITIALIZER_PREFIX):
            continue
        for _index, value in _string_refs(instructions, start, end):
            if value in enemies:
                # The first member an initializer names is the enemy it places.
                initializer_enemy[name] = value
                break

    stages: list[dict[str, Any]] = []
    skipped: list[int] = []
    for name, (start, end) in sorted(named.items()):
        section = _SECTION_RE.match(name)
        if not section:
            continue
        waves: list[str] = []
        for _index, value in _string_refs(instructions, start, end):
            if _WAVE_RE.match(value) and value in named and value not in waves:
                waves.append(value)
        if not waves:
            continue
        counts: dict[str, int] = {}
        dynamic = False
        for wave in waves:
            wave_start, wave_end = named[wave]
            nested = [
                (a, b) for a, b, _n in ranges if a > wave_start and b <= wave_end
            ]
            for index, value in _string_refs(instructions, wave_start, wave_end):
                symbol = initializer_enemy.get(value)
                if symbol is None:
                    continue
                enclosed = any(a <= index <= b for a, b in nested)
                if enclosed or _reached_conditionally(instructions, wave_start, index):
                    dynamic = True
                    continue
                counts[symbol] = counts.get(symbol, 0) + 1
        number = int(section.group(1))
        if dynamic or not counts:
            # Understating a ceiling refuses a legitimate clear, so a section
            # with any non-deterministic placement is left out entirely.
            if dynamic:
                skipped.append(number)
            continue
        stages.append({
            "chapter": chapter, "section": number, "resolved": True, "exact": False,
            "spawns": [
                {"symbol": symbol, "enemy_id": enemies[symbol], "exact": False, "count": counts[symbol]}
                for symbol in sorted(counts)
            ],
        })
    return stages, skipped


def read_chapter_assets(apk: Path) -> dict[int, bytes]:
    """Extract the ordinary story chapters' MoonSharp assets from the APK."""
    try:
        import UnityPy
    except ImportError as error:
        raise ScenarioEncounterImportError(
            "scenario encounter import requires UnityPy==1.25.2; "
            "install the master-import optional dependency"
        ) from error
    try:
        with zipfile.ZipFile(apk) as archive:
            payload = archive.read(APK_DATA_MEMBER)
    except (OSError, KeyError, zipfile.BadZipFile) as error:
        raise ScenarioEncounterImportError("APK does not contain the reviewed data.unity3d member") from error
    wanted = {f"Chapter{number}": number for number in ORDINARY_CHAPTERS}
    assets: dict[int, bytes] = {}
    try:
        with tempfile.TemporaryDirectory() as directory:
            data_file = Path(directory) / "data.unity3d"
            data_file.write_bytes(payload)
            for obj in UnityPy.load(str(data_file)).objects:
                if obj.type.name != "TextAsset":
                    continue
                data = obj.read()
                name = getattr(data, "m_Name", "") or ""
                if name not in wanted:
                    continue
                raw = getattr(data, "m_Script", None)
                if raw is None:
                    raw = getattr(data, "script", b"")
                if isinstance(raw, str):
                    # UnityPy surfaces the payload as latin-1-ish text when it
                    # is not valid UTF-8; these assets are binary either way.
                    raw = raw.encode("utf-8", "surrogateescape")
                assets[wanted[name]] = bytes(raw)
    except ScenarioEncounterImportError:
        raise
    except Exception as error:
        raise ScenarioEncounterImportError("could not read chapter TextAssets from the APK") from error
    missing = [number for number in ORDINARY_CHAPTERS if number not in assets]
    if missing:
        raise ScenarioEncounterImportError(
            "APK is missing chapter script asset(s): " + ", ".join(str(value) for value in missing)
        )
    return assets


def import_encounters(apk: Path, dump_cs: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return ``(document, report)`` for one reviewed APK."""
    enemies = parse_enemies_enum(dump_cs.read_text(encoding="utf-8", errors="replace"))
    assets = read_chapter_assets(apk)
    stages: list[dict[str, Any]] = []
    skipped: dict[str, list[int]] = {}
    chapter_sha256: dict[str, str] = {}
    for chapter in ORDINARY_CHAPTERS:
        payload = assets[chapter]
        chapter_sha256[str(chapter)] = hashlib.sha256(payload).hexdigest()
        chapter_stages_, chapter_skipped = chapter_stages(decode_chapter(payload), chapter, enemies)
        stages.extend(chapter_stages_)
        if chapter_skipped:
            skipped[str(chapter)] = sorted(chapter_skipped)
    if not stages:
        raise ScenarioEncounterImportError("no chapter section resolved a single enemy placement")
    stages.sort(key=lambda stage: (stage["chapter"], stage["section"]))
    document = {
        "schema_version": 1,
        "provenance": "user-derived",
        "source": {
            "profile": SOURCE_PROFILE,
            "apk_sha256": sha256_file(apk),
            "format": "moonsharp-binary-dump",
            "decoder": "liminal_gate.scenario_encounter_importer",
            "chapter_sha256": chapter_sha256,
        },
        "stages": stages,
    }
    report = {
        "chapters": list(ORDINARY_CHAPTERS),
        "stages_written": len(stages),
        "spawns": sum(len(stage["spawns"]) for stage in stages),
        "sections_skipped_dynamic": skipped,
    }
    return document, report


def write_document(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(document, indent=1, sort_keys=True) + "\n").encode("utf-8")
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apk", required=True, type=Path, help="your own reviewed APK")
    parser.add_argument("--dump-cs", required=True, type=Path, help="dump.cs from the run that produced DummyDll")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--force", action="store_true", help="overwrite an existing output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.output.exists() and not args.force:
        raise SystemExit(f"refusing to overwrite {args.output} without --force")
    try:
        document, report = import_encounters(args.apk.resolve(strict=True), args.dump_cs.resolve(strict=True))
        write_document(args.output, document)
    except (OSError, ScenarioEncounterImportError) as error:
        raise SystemExit(f"scenario encounter import failed: {error}") from error
    print(f"wrote local MoonSharp scenario encounter map: {args.output}")
    print(
        f"  {report['stages_written']} stage(s) across chapters"
        f" {report['chapters'][0]}-{report['chapters'][-1]}, {report['spawns']} enemy placement(s)"
    )
    if report["sections_skipped_dynamic"]:
        detail = ", ".join(
            f"{chapter}-{section}"
            for chapter, sections in sorted(report["sections_skipped_dynamic"].items())
            for section in sections
        )
        print(f"  skipped for non-deterministic placement: {detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
