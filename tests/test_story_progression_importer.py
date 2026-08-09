from __future__ import annotations

import unittest

from liminal_gate.story_progression_catalog import build_core_story_policy
from liminal_gate.story_progression_importer import StoryProgressionImportError, build_story_progression, progress_low_bits


def _metadata() -> dict[str, object]:
    """The slot layout BattleData actually ships, padding included.

    Chapter 20 reserves ten sections and fills one. Every other core chapter
    uses every slot it reserves, so this is the single place the two counts
    differ -- and the reason the importer has to read `has_battle` rather than
    trust the run length.
    """
    stages = []
    for chapter in range(2, 43):
        slots = 5 if chapter in {2, 3} else 3 if chapter == 42 else 10
        playable = 1 if chapter == 20 else slots
        for section in range(1, slots + 1):
            has_battle = section <= playable
            stages.append({
                "chapter": chapter,
                "section": section,
                "stamina": 5,
                "coins": 0,
                "battle_count": 1 if has_battle else 0,
                "has_battle": has_battle,
            })
    return {"schema_version": 1, "provenance": "user-derived", "source": {"profile": "terra-battle-android-5.5.7-170"}, "stages": stages}


class StoryProgressionImporterTest(unittest.TestCase):
    def test_derives_successors_and_chapter_transition_flags(self) -> None:
        document = build_story_progression(_metadata())
        self.assertEqual(384, len(document["stages"]))
        chapter_two_last = document["stages"][4]
        self.assertEqual((3, 1), (chapter_two_last["successor_chapter"], chapter_two_last["successor_section"]))
        self.assertTrue(chapter_two_last["chapter_boundary"])
        self.assertEqual(progress_low_bits(3, 1), chapter_two_last["successor_low_progress"])
        terminal = document["stages"][-1]
        self.assertEqual((43, 1), (terminal["successor_chapter"], terminal["successor_section"]))
        self.assertTrue(terminal["chapter_boundary"])

    def test_rejects_missing_core_section(self) -> None:
        metadata = _metadata()
        metadata["stages"].pop()
        with self.assertRaisesRegex(StoryProgressionImportError, "section counts"):
            build_story_progression(metadata)

    def test_built_in_policy_contains_only_ordered_progression(self) -> None:
        policy = build_core_story_policy()
        stages = policy.by_identity()
        self.assertEqual(384, len(stages))
        self.assertEqual((3, 1), (stages[(2, 5)].successor_chapter, stages[(2, 5)].successor_section))
        self.assertIsNone(stages[(2, 2)].stamina)
        self.assertIsNone(stages[(2, 2)].coins)

    def test_a_reserved_section_without_battles_is_not_a_stage(self) -> None:
        """Chapter 20 ships ten slots and one battle; nine are padding."""
        document = build_story_progression(_metadata())
        chapter_twenty = [row for row in document["stages"] if row["chapter"] == 20]
        self.assertEqual([1], [row["section"] for row in chapter_twenty])

    def test_the_single_chapter_twenty_stage_ends_its_chapter(self) -> None:
        """The regression. Treating 20-1 as mid-chapter strands the account.

        With the padded slots carried through, 20-1's successor was the phantom
        20-2 and the server demanded a progress code the client cannot send:
        having finished the chapter, it reports 21-1 with the boundary flags. The
        clear was refused and the save stayed pinned on 20-1 forever.
        """
        stage = build_core_story_policy().by_identity()[(20, 1)]
        self.assertEqual((21, 1), (stage.successor_chapter, stage.successor_section))
        self.assertTrue(stage.chapter_boundary)
        self.assertEqual(progress_low_bits(21, 1), stage.successor_low_progress)

    def test_the_clear_a_finished_chapter_twenty_reports_is_the_accepted_one(self) -> None:
        after_chapter_nineteen = 0x01000000 | progress_low_bits(20, 1)
        self.assertEqual(
            0x03000000 | progress_low_bits(21, 1),
            build_core_story_policy().expected_clear_progress(after_chapter_nineteen, (20, 1)),
        )

    def test_rejects_playable_sections_that_do_not_start_at_one(self) -> None:
        """Right count, wrong place. Dropping padding must not leave a hole.

        Chapter 20's one battle moved off section 1 keeps the count this importer
        checks, so only the ordering rule catches it. A layout like that needs a
        decision about which stage the chapter starts on rather than a filter.
        """
        metadata = _metadata()
        for row in metadata["stages"]:
            if row["chapter"] == 20:
                playable = row["section"] == 2
                row["battle_count"], row["has_battle"] = int(playable), playable
        with self.assertRaisesRegex(StoryProgressionImportError, "without a gap"):
            build_story_progression(metadata)
