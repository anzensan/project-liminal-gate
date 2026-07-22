from __future__ import annotations

import unittest

from liminal_gate.story_progression_importer import StoryProgressionImportError, build_story_progression, progress_low_bits


def _metadata() -> dict[str, object]:
    stages = []
    for chapter in range(2, 43):
        count = 5 if chapter in {2, 3} else 3 if chapter == 42 else 10
        for section in range(1, count + 1):
            stages.append({"chapter": chapter, "section": section, "stamina": 5, "coins": 0, "battle_count": 1, "has_battle": True})
    return {"schema_version": 1, "provenance": "user-derived", "source": {"profile": "terra-battle-android-5.5.7-170"}, "stages": stages}


class StoryProgressionImporterTest(unittest.TestCase):
    def test_derives_successors_and_chapter_transition_flags(self) -> None:
        document = build_story_progression(_metadata())
        self.assertEqual(393, len(document["stages"]))
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
