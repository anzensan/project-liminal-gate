from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from liminal_gate.native_encounter_importer import (
    Method,
    NativeEncounterImportError,
    arm64_spawn_targets,
    build_document,
    instructions,
    main,
    parse_enemies_enum,
    parse_methods,
    resolve_symbol,
    stage_identity,
    verify_calibration,
    verify_disassembly,
    write_document,
)
from liminal_gate import native_encounter_importer


DUMP = """
public enum Enemies // TypeDefIndex: 3803
{
\t// Fields
\tpublic int value__; // 0x0
\tpublic const Enemies NONE = 0;
\tpublic const Enemies CH8_BMAKER = 95;
\tpublic const Enemies CH8_L_TICK2 = 92;
\tpublic const Enemies CH15_I_CELL = 190;
}

// Namespace:
public class ChapterBase : MonoBehaviour // TypeDefIndex: 15000
{
\t// Methods

\t// RVA: 0x1000 Offset: 0x1000 VA: 0x1000 Slot: 70
\tprotected void CreateEnemy(int id, int x, int y) { }

\t// RVA: 0x1100 Offset: 0x1100 VA: 0x1100 Slot: 12
\tpublic virtual void Title() { }
}

public class Chapter8 : ChapterBase // TypeDefIndex: 15432
{
\t// Fields
\tpublic Vector2[] targetPosTbl; // 0x118

\t// Methods

\t// RVA: 0x1200 Offset: 0x1200 VA: 0x1200
\tpublic void .ctor() { }

\t// RVA: 0x1300 Offset: 0x1300 VA: 0x1300 Slot: 66
\tpublic void Init_CH8_BMAKER(int x, int y) { }

\t// RVA: 0x1400 Offset: 0x1400 VA: 0x1400 Slot: 67
\tpublic void Init_CH8_L_TICK2(int x, int y) { }
}
"""


def _listing(rows: list[str]) -> str:
    return "\n".join(f" {address:x}: 00000000     \t{row}" for address, row in enumerate(rows, start=0x2000))


def _gnu_listing(rows: list[str]) -> str:
    """The same listing as GNU binutils prints it.

    Two differences from `_listing`, which is LLVM's: the columns are tabbed
    rather than spaced, and -- the one that matters -- an indexed load's offset
    is printed in decimal.  Every fixture in this file was LLVM's until a tester
    whose PATH had no `llvm-objdump` ran the guided setup and had the reviewed
    library reported back to them as miscalibrated.
    """
    return "\n".join(f"  {address:x}:\t00000000 \t{row}" for address, row in enumerate(rows, start=0x2000))


def _byte_column_listing(rows: list[str]) -> str:
    """The listing an older LLVM prints: the encoding as four separate bytes.

    Read together with `_gnu_listing`, this is the tester's case rather than a
    hypothetical one -- an Xcode-13 `objdump`, same name and vendor as a machine
    where the import works, printing both an unwordded encoding and a decimal
    offset.  The bytes are not the real encoding of these rows; what is under
    test is the column, which a pattern reading it loosely mistakes for the
    mnemonic.
    """
    return "\n".join(f" {address:x}: 09 99 42 f9  \t{row}" for address, row in enumerate(rows, start=0x2000))


class ParseDumpTest(unittest.TestCase):
    def test_reads_methods_with_owner_rva_and_slot(self) -> None:
        methods = parse_methods(DUMP)
        self.assertEqual(
            [
                Method("ChapterBase", "CreateEnemy", 0x1000, 70),
                Method("ChapterBase", "Title", 0x1100, 12),
                Method("Chapter8", ".ctor", 0x1200, None),
                Method("Chapter8", "Init_CH8_BMAKER", 0x1300, 66),
                Method("Chapter8", "Init_CH8_L_TICK2", 0x1400, 67),
            ],
            methods,
        )

    def test_rejects_a_dump_with_no_methods(self) -> None:
        with self.assertRaisesRegex(NativeEncounterImportError, "no method definitions"):
            parse_methods("public class Empty // TypeDefIndex: 1\n{\n}\n")

    def test_reads_the_enemies_enum_and_stops_at_its_close(self) -> None:
        self.assertEqual({"NONE": 0, "CH8_BMAKER": 95, "CH8_L_TICK2": 92, "CH15_I_CELL": 190}, parse_enemies_enum(DUMP))

    def test_rejects_a_dump_with_no_enemies_enum(self) -> None:
        with self.assertRaisesRegex(NativeEncounterImportError, "no Enemies enum"):
            parse_enemies_enum("public enum Other // TypeDefIndex: 1\n{\n\tpublic const Other A = 1;\n}\n")


class ResolveSymbolTest(unittest.TestCase):
    def setUp(self) -> None:
        self.enemies = {"CH8_BMAKER": 95, "CH15_I_CELL": 190, "CH31_LEAD": 700, "CH15_CELL": 191}

    def test_an_enum_member_resolves_exactly(self) -> None:
        self.assertEqual((95, True), resolve_symbol("CH8_BMAKER", self.enemies))

    def test_a_variant_resolves_to_its_base_and_is_never_exact(self) -> None:
        for symbol in ("CH15_I_CELL_MA", "CH15_I_CELL_FNM", "CH15_I_CELL_TANM", "CH15_I_CELL_WB"):
            with self.subTest(symbol=symbol):
                self.assertEqual((190, False), resolve_symbol(symbol, self.enemies))

    def test_a_run_of_suffixes_is_stripped_together(self) -> None:
        self.assertEqual((700, False), resolve_symbol("CH31_LEAD_S_WITH_PARENT", self.enemies))

    def test_longest_suffix_wins_so_a_digit_is_not_left_behind(self) -> None:
        # `_MA1` must not be read as `_MA` plus a stray `1`, which would leave
        # `CH15_CELL1` and resolve to nothing.
        self.assertEqual((191, False), resolve_symbol("CH15_CELL_MA1", self.enemies))

    def test_the_variant_forms_the_widened_chapter_range_introduced(self) -> None:
        # Each of these stood between a real spawn and a real member in the
        # census of what the event, side-world and Eidolon programs could not
        # resolve. All are variants of their base and none may read as exact.
        enemies = {
            "MS_IceA": 1, "SP103_LIZARD": 2, "SP_BASHE1": 3,
            "SP114_BODY": 4, "SP1_Zanna_B": 5, "SP101_DOLL_B": 6,
        }
        for symbol, expected in (
            ("MS_IceA_Up", 1), ("MS_IceA_Down", 1),
            ("SP103_LIZARD_last", 2), ("SP101_DOLL_B_first", 6),
            ("SP_BASHE1_A", 3), ("SP_BASHE1_B", 3),
            ("SP114_BODY_BOSS", 4), ("SP1_Zanna_B_DANGER", 5),
        ):
            with self.subTest(symbol=symbol):
                self.assertEqual((expected, False), resolve_symbol(symbol, enemies))

    def test_a_widened_suffix_never_overrides_a_real_member(self) -> None:
        # `_A` and `_B` are common enough as endings that peeling them must stay
        # subordinate to exact membership, or a real enemy would be read as a
        # variant of something else.
        enemies = {"SP_BASHE1": 3, "SP_BASHE1_A": 9}
        self.assertEqual((9, True), resolve_symbol("SP_BASHE1_A", enemies))

    def test_an_unknown_symbol_resolves_to_nothing(self) -> None:
        self.assertEqual((None, False), resolve_symbol("CH21_WHITE1", self.enemies))

    def test_a_base_that_is_not_an_enum_member_resolves_to_nothing(self) -> None:
        self.assertEqual((None, False), resolve_symbol("CH99_UNKNOWN_NM", self.enemies))


class Arm64SpawnTargetTest(unittest.TestCase):
    def setUp(self) -> None:
        self.slots = {
            66: Method("Chapter8", "Init_CH8_BMAKER", 0x1300, 66),
            67: Method("Chapter8", "Init_CH8_L_TICK2", 0x1400, 67),
            70: Method("ChapterBase", "CreateEnemy", 0x1000, 70),
            12: Method("ChapterBase", "Title", 0x1100, 12),
        }

    def test_reads_instruction_addresses_mnemonics_and_operands(self) -> None:
        self.assertEqual(
            [(0x2000, "ldr", "x9, [x8, #0x530]"), (0x2001, "blr", "x9")],
            instructions(_listing(["ldr\tx9, [x8, #0x530]", "blr\tx9"])),
        )

    def test_resolves_a_vtable_call_to_its_managed_slot(self) -> None:
        # 0x530 is 0x110 + 66 * 16, so this is Chapter8::Init_CH8_BMAKER.
        listing = _listing(["ldr\tx8, [x20]", "ldr\tx9, [x8, #0x530]", "mov\tx0, x20", "blr\tx9"])
        self.assertEqual(["Init_CH8_BMAKER"], arm64_spawn_targets(listing, self.slots))

    def test_records_every_spawn_in_order_with_repeats(self) -> None:
        listing = _listing([
            "ldr\tx9, [x8, #0x530]", "blr\tx9",
            "ldr\tx9, [x8, #0x540]", "blr\tx9",
            "ldr\tx9, [x8, #0x530]", "blr\tx9",
        ])
        self.assertEqual(
            ["Init_CH8_BMAKER", "Init_CH8_L_TICK2", "Init_CH8_BMAKER"],
            arm64_spawn_targets(listing, self.slots),
        )

    def test_the_shared_placement_helper_also_counts(self) -> None:
        # 0x110 + 70 * 16 = 0x570.
        self.assertEqual(["CreateEnemy"], arm64_spawn_targets(_listing(["ldr\tx9, [x8, #0x570]", "blr\tx9"]), self.slots))

    def test_a_direct_call_between_load_and_branch_invalidates_the_register(self) -> None:
        listing = _listing(["ldr\tx9, [x8, #0x530]", "bl\t0xbef9e8 <_ZNSs12_S_constructI>", "blr\tx9"])
        self.assertEqual([], arm64_spawn_targets(listing, self.slots))

    def test_an_offset_off_the_vtable_stride_is_not_a_managed_call(self) -> None:
        self.assertEqual([], arm64_spawn_targets(_listing(["ldr\tx9, [x8, #0x538]", "blr\tx9"]), self.slots))

    def test_an_offset_inside_the_class_header_is_not_a_managed_call(self) -> None:
        self.assertEqual([], arm64_spawn_targets(_listing(["ldr\tx9, [x8, #0x20]", "blr\tx9"]), self.slots))

    def test_a_slot_holding_something_other_than_a_spawn_is_ignored(self) -> None:
        # 0x110 + 12 * 16 = 0x1D0, ChapterBase::Title.
        self.assertEqual([], arm64_spawn_targets(_listing(["ldr\tx9, [x8, #0x1d0]", "blr\tx9"]), self.slots))

    def test_a_branch_through_an_untracked_register_is_ignored(self) -> None:
        self.assertEqual([], arm64_spawn_targets(_listing(["ldr\tx9, [x8, #0x530]", "blr\tx11"]), self.slots))

    def test_an_unmapped_slot_is_ignored(self) -> None:
        self.assertEqual([], arm64_spawn_targets(_listing(["ldr\tx9, [x8, #0x1110]", "blr\tx9"]), self.slots))

    def test_gnu_decimal_offsets_read_as_the_same_instruction(self) -> None:
        # 0x530 printed in decimal.  Whichever disassembler was selected, the
        # library holds one instruction and it names one slot.
        self.assertEqual(
            [(0x2000, "ldr", "x9, [x8, #1328]"), (0x2001, "blr", "x9")],
            instructions(_gnu_listing(["ldr\tx9, [x8, #1328]", "blr\tx9"])),
        )
        self.assertEqual(
            arm64_spawn_targets(_listing(["ldr\tx9, [x8, #0x530]", "blr\tx9"]), self.slots),
            arm64_spawn_targets(_gnu_listing(["ldr\tx9, [x8, #1328]", "blr\tx9"]), self.slots),
        )

    def test_gnu_output_rejects_the_same_offsets_llvm_output_does(self) -> None:
        # A decimal reading must not turn a non-call into a call: 0x538 is off
        # the stride and 0x1D0 is a slot holding something that is not a spawn.
        self.assertEqual([], arm64_spawn_targets(_gnu_listing(["ldr\tx9, [x8, #1336]", "blr\tx9"]), self.slots))
        self.assertEqual([], arm64_spawn_targets(_gnu_listing(["ldr\tx9, [x8, #464]", "blr\tx9"]), self.slots))

    def test_a_byte_column_encoding_is_not_read_as_the_instruction(self) -> None:
        # The whole tester case at once: bytes rather than a word, and the
        # offset in decimal. The second byte must not become the mnemonic.
        self.assertEqual(
            [(0x2000, "ldr", "x9, [x8, #1328]"), (0x2001, "blr", "x9")],
            instructions(_byte_column_listing(["ldr\tx9, [x8, #1328]", "blr\tx9"])),
        )
        self.assertEqual(
            ["Init_CH8_BMAKER"],
            arm64_spawn_targets(_byte_column_listing(["ldr\tx9, [x8, #1328]", "blr\tx9"]), self.slots),
        )

    def test_a_column_that_is_neither_rendering_is_refused(self) -> None:
        # Three bytes is not an AArch64 encoding, and a row that cannot be read
        # has to be no row rather than a guess assembled from its pieces.
        self.assertEqual([], instructions(" 2000: 09 99 42  \tldr\tx9, [x8, #1328]"))

    def test_gnu_output_records_every_spawn_in_order_with_repeats(self) -> None:
        listing = _gnu_listing([
            "ldr\tx9, [x8, #1328]", "blr\tx9",
            "ldr\tx9, [x8, #1344]", "blr\tx9",
            "ldr\tx9, [x8, #1328]", "blr\tx9",
        ])
        self.assertEqual(
            ["Init_CH8_BMAKER", "Init_CH8_L_TICK2", "Init_CH8_BMAKER"],
            arm64_spawn_targets(listing, self.slots),
        )


class StageIdentityTest(unittest.TestCase):
    def test_reads_chapter_and_section_from_a_generator_type(self) -> None:
        self.assertEqual((8, 1), stage_identity("Chapter8.$Battle1_1$25037.$"))
        self.assertEqual((37, 10), stage_identity("Chapter37.$Battle10_3$41200.$"))

    def test_chapter_20_battles_are_folded_two_to_a_section(self) -> None:
        # One continuous twenty-battle program backs ten two-battle sections.
        self.assertEqual((20, 1), stage_identity("Chapter20.$Battle1_1$1$"))
        self.assertEqual((20, 1), stage_identity("Chapter20.$Battle1_2$1$"))
        self.assertEqual((20, 2), stage_identity("Chapter20.$Battle1_3$1$"))
        self.assertEqual((20, 10), stage_identity("Chapter20.$Battle1_20$1$"))

    def test_reads_every_chapter_the_binary_compiles_not_a_fixed_range(self) -> None:
        # The core-story range was a scope decision, not a property of the data.
        # Event, side-world, Descent and Tower chapters compile the same
        # generator types and must read identically.
        for name, identity in (
            ("Chapter110.$Battle1_1$1$", (110, 1)),
            ("Chapter2000.$Battle3_1$1$", (2000, 3)),
            ("Chapter8000.$Battle1_1$1$", (8000, 1)),
            ("Chapter9102.$Battle2_1$1$", (9102, 2)),
        ):
            with self.subTest(name=name):
                self.assertEqual(identity, stage_identity(name))

    def test_rejects_types_that_are_not_a_chapter_generator(self) -> None:
        # A chapter with no battle, a non-chapter type, and a type whose name
        # merely ends in a chapter name must all stay unread.
        for name in ("Chapter8", "BattleManager", "MyChapter8.$Battle1_1$1$"):
            with self.subTest(name=name):
                self.assertIsNone(stage_identity(name))

    def test_reads_the_world_map_specials_quest_named_generators(self) -> None:
        # Chapter 1100 names its generators after the quest and carries no
        # section number at all.  BattleData's section titles put tier 1 at
        # section 4 and section 9, so both groups run backwards; reading them
        # in ascending order would file every tier under the wrong stage.
        for name, identity in (
            ("Chapter1100.$Battle_Shinen_1$9197.$", (1100, 4)),
            ("Chapter1100.$Battle_Shinen_4$9207.$", (1100, 1)),
            ("Chapter1100.$Battle_Mutou_1$9211.$", (1100, 9)),
            ("Chapter1100.$Battle_Mutou_4$9224.$", (1100, 6)),
            ("Chapter1100.$$Battle_Mutou_2$closure$984$9252.$", (1100, 8)),
        ):
            with self.subTest(name=name):
                self.assertEqual(identity, stage_identity(name))

    def test_a_numbered_generator_still_wins_over_the_quest_named_form(self) -> None:
        # Several chapters suffix a numbered generator (`Battle2_3_A`).  Those
        # carry their own section number and must never reach the named table.
        self.assertEqual((8008, 2), stage_identity("Chapter8008.$Battle2_3_A$1$"))
        self.assertEqual((9100, 15), stage_identity("Chapter9100.$Battle15_5_Normal$1$"))

    def test_reads_the_lower_case_alternative_bodies_of_one_battle(self) -> None:
        # `battle1_3a` is a second encounter for the same battle as `Battle1_3`.
        # The section number is in the name; only the capital B was ever missing.
        # Chapter 2003 read 14 of its 63 generator bodies before this.
        for name, identity in (
            ("Chapter2003.$$battle1_3a$closure$1$", (2003, 1)),
            ("Chapter2003.$$battle1_10c$closure$1$", (2003, 1)),
            ("Chapter2004.$$battle1_5d$closure$1$", (2004, 1)),
            ("Chapter2005.$$battle1_7b$closure$1$", (2005, 1)),
        ):
            with self.subTest(name=name):
                self.assertEqual(identity, stage_identity(name))

    def test_a_body_numbered_from_the_battle_needs_a_sole_playable_section(self) -> None:
        # `battle_2a` carries no section at all.  Chapter 2003 declares exactly
        # one playable section, so there is nowhere else it could belong.
        self.assertEqual((2003, 1), stage_identity("Chapter2003.$$battle_2a$closure$1$"))

    def test_a_chapter_with_no_playable_section_reads_none_of_them(self) -> None:
        # Chapter 2014 compiles twenty-six of these against a single slot whose
        # battleCnt is 0.  Reading them would invent a stage that does not exist.
        for name in ("Chapter2014.$$battle_10b$closure$1$", "Chapter2014.$$battle_2_common$closure$1$"):
            with self.subTest(name=name):
                self.assertIsNone(stage_identity(name))

    def test_a_name_that_is_not_a_quest_generator_stays_unread(self) -> None:
        # `BattleExp_1`, `BattleCommon` and `Battle_Toad2` are neither numbered
        # nor of the `Battle_<quest>_<tier>` shape, so they must not be mistaken
        # for one.  Each sits in a chapter whose BattleData cannot say which of
        # its sections would receive the spawns.
        for name in (
            "Chapter1000.$BattleExp_1$1$", "Chapter2015.$Battle_Toad2$1$",
            "Chapter2014.$Battle_1$1$", "Chapter1003.$BattleCommon$1$",
            "Chapter3003.$BattleCommon$1$",
        ):
            with self.subTest(name=name):
                self.assertIsNone(stage_identity(name))

    def test_an_unrecovered_quest_fails_visibly_rather_than_reading_as_absent(self) -> None:
        # Returning None here is how the World Map Specials went unread: an
        # unnumbered generator looks exactly like a chapter with no program.
        with self.assertRaises(NativeEncounterImportError) as caught:
            stage_identity("Chapter1101.$Battle_Kraken_1$1$")
        self.assertEqual(
            "chapter 1101 compiles an unrecognised quest-named generator 'Kraken';"
            " its section mapping must be recovered from BattleData before it can be read",
            str(caught.exception),
        )

    def test_a_tier_outside_the_recovered_mapping_fails_visibly(self) -> None:
        # Tier 5 of each World Map Special quest compiles no generator on the
        # reviewed build.  A build that compiles one is a shape this table has
        # not been checked against.
        with self.assertRaises(NativeEncounterImportError) as caught:
            stage_identity("Chapter1100.$Battle_Shinen_5$1$")
        self.assertEqual(
            "chapter 1100 compiles Shinen tier 5, which the recovered section mapping does not cover",
            str(caught.exception),
        )


class BuildDocumentTest(unittest.TestCase):
    def setUp(self) -> None:
        self.enemies = {"CH8_BMAKER": 95, "CH8_L_TICK": 91, "CH38_RUKU": 1800}
        self.source = {"profile": "p", "abi": "arm64", "apk_sha256": "a" * 64, "dump_cs_sha256": "b" * 64, "libil2cpp_sha256": "c" * 64, "objdump": "objdump 1.0", "vtable_calibration": "verified"}

    def test_counts_multiplicity_and_marks_a_fully_exact_stage(self) -> None:
        document = build_document({(8, 1): ["Init_CH8_BMAKER", "Init_CH8_L_TICK", "Init_CH8_BMAKER"]}, self.enemies, self.source)
        self.assertEqual("user-derived", document["provenance"])
        stage = document["stages"][0]
        self.assertEqual((8, 1, True, True), (stage["chapter"], stage["section"], stage["resolved"], stage["exact"]))
        self.assertEqual(
            [
                {"symbol": "CH8_BMAKER", "enemy_id": 95, "exact": True, "count": 2},
                {"symbol": "CH8_L_TICK", "enemy_id": 91, "exact": True, "count": 1},
            ],
            stage["spawns"],
        )

    def test_a_variant_keeps_the_stage_resolved_but_not_exact(self) -> None:
        stage = build_document({(8, 2): ["Init_CH8_BMAKER_NM"]}, self.enemies, self.source)["stages"][0]
        self.assertEqual((True, False), (stage["resolved"], stage["exact"]))
        self.assertEqual([{"symbol": "CH8_BMAKER_NM", "enemy_id": 95, "exact": False, "count": 1}], stage["spawns"])

    def test_an_unresolved_symbol_is_reported_rather_than_dropped(self) -> None:
        document = build_document({(8, 3): ["Init_CH21_WHITE1", "Init_CH21_WHITE1", "Init_CH8_BMAKER"]}, self.enemies, self.source)
        stage = document["stages"][0]
        self.assertEqual((False, False), (stage["resolved"], stage["exact"]))
        self.assertEqual([{"symbol": "CH21_WHITE1", "count": 2}], document["unresolved_symbols"])
        self.assertEqual(1, document["summary"]["distinct_unresolved_symbols"])

    def test_stages_are_ordered_and_summarised(self) -> None:
        document = build_document(
            {(9, 2): ["Init_CH8_BMAKER"], (8, 10): ["Init_CH8_BMAKER_NM"], (8, 2): ["Init_CH21_WHITE1"]},
            self.enemies,
            self.source,
        )
        self.assertEqual([(8, 2), (8, 10), (9, 2)], [(stage["chapter"], stage["section"]) for stage in document["stages"]])
        self.assertEqual({"stages": 3, "stages_resolved": 2, "stages_exact": 1, "distinct_unresolved_symbols": 1}, document["summary"])

    def test_a_helper_call_with_no_symbol_prefix_is_kept_verbatim(self) -> None:
        stage = build_document({(8, 4): ["CreateEnemy"]}, self.enemies, self.source)["stages"][0]
        self.assertEqual([{"symbol": "CreateEnemy", "enemy_id": None, "exact": False, "count": 1}], stage["spawns"])

    def test_rejects_an_empty_extraction(self) -> None:
        with self.assertRaisesRegex(NativeEncounterImportError, "no chapter generator"):
            build_document({}, self.enemies, self.source)


def _calibration_methods() -> list[Method]:
    """A dump.cs placing every calibration fixture exactly where it expects."""
    return [
        Method(type_name, member, rva, None)
        for type_name, member, rva, _stop, _site, _offset in native_encounter_importer._CALIBRATION
    ]


def _calibration_disassembler(radix: str = "hex", offsets: dict[int, int] | None = None):
    """Replay the reviewed library's calibration sites in one syntax or the other.

    `offsets` overrides what a site loads, which is how a genuinely miscalibrated
    library is told apart here from a disassembler that merely spells the right
    answer differently.
    """
    sites = {
        rva: (site, (offsets or {}).get(site, offset))
        for _type, _member, rva, _stop, site, offset in native_encounter_importer._CALIBRATION
    }

    def disassemble(_objdump: str, _library: Path, start: int, _stop: int) -> str:
        site, offset = sites[start]
        operand = f"#0x{offset:x}" if radix == "hex" else f"#{offset}"
        row = f"ldr\tx9, [x8, {operand}]"
        return f"  {site:x}:\tf9429909 \t{row}" if radix == "decimal" else f" {site:x}: f9429909     \t{row}"

    return disassemble


class CalibrationTest(unittest.TestCase):
    def test_llvm_and_gnu_syntax_calibrate_the_same_library(self) -> None:
        # The whole of the reported failure: the reviewed build, read by a
        # disassembler printing #1328 where the fixture was written as #0x530.
        for radix in ("hex", "decimal"):
            with self.subTest(radix=radix), \
                    patch.object(native_encounter_importer, "disassemble", _calibration_disassembler(radix)):
                verify_calibration(_calibration_methods(), "objdump", Path("/nonexistent/libil2cpp.so"))

    def test_a_site_that_holds_no_vtable_load_says_so(self) -> None:
        def disassemble(_objdump, _library, _start, _stop):
            return _listing(["mov\tx0, x20", "blr\tx9"])

        with patch.object(native_encounter_importer, "disassemble", disassemble):
            with self.assertRaisesRegex(NativeEncounterImportError, "holds no vtable load at 0x1A384D8"):
                verify_calibration(_calibration_methods(), "objdump", Path("/nonexistent/libil2cpp.so"))

    def test_a_site_loading_a_different_offset_names_both_offsets(self) -> None:
        # A library whose layout really has moved, in either syntax: the message
        # has to say what was found, not only what was wanted.
        for radix in ("hex", "decimal"):
            with self.subTest(radix=radix), patch.object(
                native_encounter_importer, "disassemble",
                _calibration_disassembler(radix, offsets={0x1A384D8: 0x540}),
            ):
                with self.assertRaisesRegex(NativeEncounterImportError, r"loads 0x540 at 0x1A384D8, not 0x530"):
                    verify_calibration(_calibration_methods(), "objdump", Path("/nonexistent/libil2cpp.so"))

    def test_a_dump_whose_fixture_method_moved_fails_before_running_objdump(self) -> None:
        methods = [Method("Chapter8.$Battle1_1$25037.$", "MoveNext", 0xDEAD, 1)]
        with self.assertRaisesRegex(NativeEncounterImportError, "vtable calibration failed"):
            verify_calibration(methods, "/nonexistent/objdump", Path("/nonexistent/libil2cpp.so"))

    def test_a_dump_missing_the_fixture_method_fails(self) -> None:
        with self.assertRaisesRegex(NativeEncounterImportError, "vtable calibration failed"):
            verify_calibration([], "/nonexistent/objdump", Path("/nonexistent/libil2cpp.so"))


class DisassemblyProbeTest(unittest.TestCase):
    """One readable instruction, asked for before the thousands of calls.

    Calibration only runs on the reviewed library, so it cannot be what tells a
    tester on any other build that their disassembler is unreadable here. This
    probe holds for every build and costs one invocation.
    """

    def setUp(self) -> None:
        self.methods = parse_methods(DUMP)

    def test_either_syntax_satisfies_the_probe(self) -> None:
        for name, listing in (("llvm", _listing), ("gnu", _gnu_listing)):
            with self.subTest(syntax=name), patch.object(
                native_encounter_importer, "disassemble",
                lambda *_args, **_kwargs: listing(["ldr\tx9, [x8, #0x530]", "ret"]),
            ):
                verify_disassembly(self.methods, "objdump", Path("/nonexistent/libil2cpp.so"))

    def test_output_holding_no_instruction_names_the_tool_and_what_it_printed(self) -> None:
        with patch.object(
            native_encounter_importer, "disassemble",
            lambda *_args, **_kwargs: "\nlibil2cpp.so:     file format elf64-little\n",
        ):
            with self.assertRaisesRegex(NativeEncounterImportError, r"gobjdump printed no instruction.*elf64-little"):
                verify_disassembly(self.methods, "gobjdump", Path("/nonexistent/libil2cpp.so"))

    def test_it_gives_up_after_a_few_bodies_rather_than_reading_the_library(self) -> None:
        calls: list[int] = []

        def disassemble(_objdump, _library, start, _stop):
            calls.append(start)
            return ""

        with patch.object(native_encounter_importer, "disassemble", disassemble):
            with self.assertRaises(NativeEncounterImportError):
                verify_disassembly(self.methods, "objdump", Path("/nonexistent/libil2cpp.so"))
        self.assertEqual([0x1000, 0x1100, 0x1200], calls)

    def test_a_body_holding_nothing_readable_is_not_the_verdict(self) -> None:
        # One method can legitimately disassemble into nothing this parses; the
        # probe is about the tool, so it moves on to the next body.
        def disassemble(_objdump, _library, start, _stop):
            return "" if start == 0x1000 else _gnu_listing(["ret"])

        with patch.object(native_encounter_importer, "disassemble", disassemble):
            verify_disassembly(self.methods, "objdump", Path("/nonexistent/libil2cpp.so"))


class WriteDocumentTest(unittest.TestCase):
    def test_writes_atomically_and_leaves_no_temporary_behind(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "derived" / "native-encounters.json"
            write_document(path, {"schema_version": 1})
            self.assertEqual('{\n  "schema_version": 1\n}\n', path.read_text(encoding="utf-8"))
            self.assertEqual([path.name], [entry.name for entry in path.parent.iterdir()])


class MainOverwriteGuardTest(unittest.TestCase):
    def test_refuses_to_overwrite_an_existing_output_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "native-encounters.json"
            output.write_text("{}", encoding="utf-8")
            arguments = ["importer", "--apk", "a.apk", "--dump-cs", "d.cs", "--output", str(output)]
            with patch.object(sys, "argv", arguments), self.assertRaisesRegex(SystemExit, "without --force"):
                main()
            self.assertEqual("{}", output.read_text(encoding="utf-8"))
