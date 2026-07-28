"""Decode the client's MoonSharp chapter scripts without executing them.

Chapters 2--7 place their encounters from Lua the client runs on an embedded
MoonSharp VM rather than from a compiled battle program, so the native encounter
import cannot see them at all. These cover the two halves of reading them: the
`BinDumpBinaryReader` wire format, and the walk over the decoded program that
decides which placements are deterministic enough to become a ceiling.
"""

from __future__ import annotations

import struct
import unittest

from liminal_gate.scenario_encounter_importer import (
    DUMP_CHUNK_MAGIC,
    DUMP_CHUNK_VERSION_V0_9_2,
    DUMP_CHUNK_VERSION_V2_0_0_0,
    OPCODES,
    OPCODES_V0_9_2,
    BinDumpReader,
    Instruction,
    ScenarioEncounterImportError,
    chapter_stages,
    decode_chapter,
    field_usage,
    function_ranges,
)


ENEMIES = {"CH2_BAKUROU": 7, "CH2_KERORAN": 11, "CH2_RARE": 12}


def _meta(index: int, size: int, name: str) -> Instruction:
    return Instruction(index=index, opcode="Meta", num_val=size, name=name)


def _ref(index: int, value: str) -> Instruction:
    return Instruction(index=index, opcode="Index", string_value=value)


def _branch(index: int, target: int) -> Instruction:
    return Instruction(index=index, opcode="Jf", num_val=target)


def _pad(count: int, start: int) -> list[Instruction]:
    return [Instruction(index=start + offset, opcode="Nop") for offset in range(count)]


class BinDumpReaderTest(unittest.TestCase):
    def test_compressed_int32_uses_the_marker_byte_widths(self) -> None:
        reader = BinDumpReader(
            bytes([5]) + bytes([0xFB])                      # positive and negative sbyte
            + bytes([0x7F]) + struct.pack("<h", 4660)       # int16 escape
            + bytes([0x7E]) + struct.pack("<i", 123456)     # int32 escape
        )
        self.assertEqual([5, -5, 4660, 123456], [reader.read_int32() for _ in range(4)])

    def test_the_string_table_is_written_once_and_then_referenced(self) -> None:
        payload = bytes([0]) + bytes([5]) + b"Init_" + bytes([0])
        reader = BinDumpReader(payload)
        self.assertEqual("Init_", reader.read_string())
        # The second read is an index into the table, not another raw string.
        self.assertEqual("Init_", reader.read_string())

    def test_a_string_index_past_the_table_is_refused(self) -> None:
        with self.assertRaisesRegex(ScenarioEncounterImportError, "string table index"):
            BinDumpReader(bytes([9])).read_string()

    def test_a_truncated_read_is_refused(self) -> None:
        with self.assertRaisesRegex(ScenarioEncounterImportError, "expected 8 bytes"):
            BinDumpReader(b"\x00").read_uint64()


class FieldUsageTest(unittest.TestCase):
    def test_every_opcode_in_both_versions_has_a_field_usage(self) -> None:
        for opcode in set(OPCODES) | set(OPCODES_V0_9_2):
            with self.subTest(opcode=opcode):
                self.assertIsInstance(field_usage(opcode), int)

    def test_an_unknown_opcode_is_refused_rather_than_guessed(self) -> None:
        with self.assertRaisesRegex(ScenarioEncounterImportError, "unhandled opcode"):
            field_usage("NotAnOpcode")


class DecodeChapterTest(unittest.TestCase):
    def test_a_foreign_payload_is_refused(self) -> None:
        with self.assertRaisesRegex(ScenarioEncounterImportError, "not a MoonSharp dump chunk"):
            decode_chapter(struct.pack("<Q", 0x1122334455667788))

    def test_an_unsupported_dump_version_is_refused(self) -> None:
        payload = struct.pack("<Q", DUMP_CHUNK_MAGIC) + bytes([0x7F]) + struct.pack("<h", 0x999)
        with self.assertRaisesRegex(ScenarioEncounterImportError, "DUMP_CHUNK_VERSION"):
            decode_chapter(payload)

    def test_both_recovered_dump_versions_are_accepted(self) -> None:
        for version in (DUMP_CHUNK_VERSION_V2_0_0_0, DUMP_CHUNK_VERSION_V0_9_2):
            with self.subTest(version=version):
                payload = (
                    struct.pack("<Q", DUMP_CHUNK_MAGIC)
                    + bytes([0x7F]) + struct.pack("<h", version)
                    + bytes([0])          # has_upvalues
                    + bytes([0])          # length: one instruction follows
                    + bytes([0])          # no symbols
                    + bytes([OPCODES.index("Nop")]) + bytes([0]) + bytes([3]) + b"nop"
                )
                self.assertEqual(1, len(decode_chapter(payload)))

    def test_trailing_bytes_are_refused_rather_than_ignored(self) -> None:
        payload = (
            struct.pack("<Q", DUMP_CHUNK_MAGIC)
            + bytes([0x7F]) + struct.pack("<h", DUMP_CHUNK_VERSION_V2_0_0_0)
            + bytes([0]) + bytes([0]) + bytes([0])
            + bytes([OPCODES.index("Nop")]) + bytes([0]) + bytes([3]) + b"nop"
            + b"\x00\x00"
        )
        # A clean parse consumes the asset exactly; leftovers mean the field
        # usage tables disagree with this build and every later offset is junk.
        with self.assertRaisesRegex(ScenarioEncounterImportError, "trailing unparsed"):
            decode_chapter(payload)


class ChapterStagesTest(unittest.TestCase):
    """The walk from `Section{N}` to a per-enemy count."""

    def _program(self, *, conditional: bool = False) -> list[Instruction]:
        # Section1 names one wave; Battle1_1 places two enemies, one of them
        # twice. Instruction indices are contiguous so the ranges line up.
        program: list[Instruction] = []
        program.append(_meta(0, 4, "Section1"))
        program.append(_ref(1, "Battle1_1"))
        program += _pad(2, 2)

        program.append(_meta(4, 8, "Battle1_1"))
        program.append(_ref(5, "Init_A"))
        program.append(_ref(6, "Init_A"))
        if conditional:
            # A jump landing past the call makes the placement conditional.
            program.append(_branch(7, 20))
        else:
            program.append(Instruction(index=7, opcode="Nop"))
        program.append(_ref(8, "Init_B"))
        program += _pad(3, 9)

        program.append(_meta(12, 3, "Init_A"))
        program.append(_ref(13, "CH2_BAKUROU"))
        program += _pad(1, 14)

        program.append(_meta(15, 3, "Init_B"))
        program.append(_ref(16, "CH2_KERORAN"))
        program += _pad(1, 17)
        return program

    def test_counts_each_direct_placement(self) -> None:
        stages, skipped = chapter_stages(self._program(), 2, ENEMIES)
        self.assertEqual([], skipped)
        self.assertEqual(1, len(stages))
        stage = stages[0]
        self.assertEqual((2, 1, True, False), (stage["chapter"], stage["section"], stage["resolved"], stage["exact"]))
        self.assertEqual(
            [{"symbol": "CH2_BAKUROU", "enemy_id": 7, "exact": False, "count": 2},
             {"symbol": "CH2_KERORAN", "enemy_id": 11, "exact": False, "count": 1}],
            stage["spawns"],
        )

    def test_every_spawn_stays_inferred(self) -> None:
        # The enemy identity is exact -- the script names the enum member -- but
        # the placement is read from a static decode, never observed running.
        stage = chapter_stages(self._program(), 2, ENEMIES)[0][0]
        self.assertFalse(stage["exact"])
        self.assertTrue(all(not spawn["exact"] for spawn in stage["spawns"]))

    def test_a_conditional_placement_drops_the_whole_section(self) -> None:
        stages, skipped = chapter_stages(self._program(conditional=True), 2, ENEMIES)
        # Understating a ceiling refuses a legitimate clear, so the section is
        # left out and reported rather than emitted with a partial count.
        self.assertEqual(([], [1]), (stages, skipped))

    def test_a_placement_inside_a_nested_closure_drops_the_section(self) -> None:
        program = [
            _meta(0, 3, "Section1"), _ref(1, "Battle1_1"), Instruction(index=2, opcode="Nop"),
            _meta(3, 4, "Battle1_1"), _ref(4, "Init_A"),
            # A closure declared inside the wave; its call is not the wave's own.
            _meta(5, 2, "anonymous"), _ref(6, "Init_A"),
            _meta(7, 2, "Init_A"), _ref(8, "CH2_BAKUROU"),
        ]
        self.assertEqual(([], [1]), chapter_stages(program, 2, ENEMIES))

    def test_an_initializer_naming_no_known_enemy_places_nothing(self) -> None:
        stages, _skipped = chapter_stages(self._program(), 2, {"CH2_BAKUROU": 7})
        self.assertEqual(
            [{"symbol": "CH2_BAKUROU", "enemy_id": 7, "exact": False, "count": 2}],
            stages[0]["spawns"],
        )

    def test_a_section_naming_no_wave_is_not_a_stage(self) -> None:
        program = [_meta(0, 2, "Section1"), Instruction(index=1, opcode="Nop")]
        self.assertEqual(([], []), chapter_stages(program, 2, ENEMIES))

    def test_a_program_declaring_no_function_is_refused(self) -> None:
        with self.assertRaisesRegex(ScenarioEncounterImportError, "declares no functions"):
            function_ranges([Instruction(index=0, opcode="Nop")])


if __name__ == "__main__":
    unittest.main()
