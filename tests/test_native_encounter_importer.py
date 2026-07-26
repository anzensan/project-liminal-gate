from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from liminal_gate.native_encounter_importer import (
    Method,
    NativeEncounterImportError,
    arm64_spawn_targets,
    build_document,
    instructions,
    parse_enemies_enum,
    parse_methods,
    resolve_symbol,
    stage_identity,
    verify_calibration,
    write_document,
)


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

    def test_rejects_types_outside_the_supported_range(self) -> None:
        for name in ("Chapter7.$Battle1_1$1$", "Chapter43.$Battle1_1$1$", "Chapter8", "BattleManager", "MyChapter8.$Battle1_1$1$"):
            with self.subTest(name=name):
                self.assertIsNone(stage_identity(name))


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
        with self.assertRaisesRegex(NativeEncounterImportError, "no Chapter 8-42 generator"):
            build_document({}, self.enemies, self.source)


class CalibrationTest(unittest.TestCase):
    def test_a_dump_whose_fixture_method_moved_fails_before_running_objdump(self) -> None:
        methods = [Method("Chapter8.$Battle1_1$25037.$", "MoveNext", 0xDEAD, 1)]
        with self.assertRaisesRegex(NativeEncounterImportError, "vtable calibration failed"):
            verify_calibration(methods, "/nonexistent/objdump", Path("/nonexistent/libil2cpp.so"))

    def test_a_dump_missing_the_fixture_method_fails(self) -> None:
        with self.assertRaisesRegex(NativeEncounterImportError, "vtable calibration failed"):
            verify_calibration([], "/nonexistent/objdump", Path("/nonexistent/libil2cpp.so"))


class WriteDocumentTest(unittest.TestCase):
    def test_writes_atomically_and_leaves_no_temporary_behind(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "derived" / "native-encounters.json"
            write_document(path, {"schema_version": 1})
            self.assertEqual('{\n  "schema_version": 1\n}\n', path.read_text(encoding="utf-8"))
            self.assertEqual([path.name], [entry.name for entry in path.parent.iterdir()])
