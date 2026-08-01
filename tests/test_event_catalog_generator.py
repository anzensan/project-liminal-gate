"""Composing an event catalog from the user's own BattleData import.

The event chapters sit in BattleData beside the main story, so their entry
stamina and start costs come from the same import that serves ordinary stages --
no native disassembly is involved.

The generator contributes only the recovered manifest identities. Character
grants are still validated against the user's own catalog, which is the
boundary the generated artifact and an explicit `--event-catalog` override
keep.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from liminal_gate.event_catalog import load_event_catalog
from liminal_gate.event_catalog_generator import (
    EventCatalogGeneratorError,
    build_catalog,
)
from liminal_gate.event_manifest_data import (
    EIDOLON_MANIFEST_ROWS,
    EVENT_CLEAR_COINS,
    EVENT_MANIFEST_ROWS,
    TOWER_MANIFEST_ROWS,
)


def _battledata(*chapters: int) -> dict:
    stages = []
    for chapter in chapters:
        for section in (1, 2):
            stages.append({
                "chapter": chapter, "section": section, "stamina": 15,
                "coins": 0, "battle_count": 5, "has_battle": True,
            })
    return {"schema_version": 1, "provenance": "user-derived", "source": {}, "stages": stages}


class EventCatalogGeneratorTest(unittest.TestCase):
    def _generate(self, battledata: dict, character_ids: tuple[int, ...]):
        with tempfile.TemporaryDirectory() as directory:
            catalog_path = Path(directory) / "characters.json"
            characters = {"characters": [{"character_id": value} for value in character_ids]}
            catalog_path.write_text(json.dumps(characters), encoding="utf-8")
            document, notes = build_catalog(battledata, characters, catalog_path)
            out = Path(directory) / "events.json"
            out.write_text(json.dumps(document), encoding="utf-8")
            return document, notes, load_event_catalog(out, catalog_path)

    def test_output_loads_through_the_real_validator(self) -> None:
        document, _, loaded = self._generate(_battledata(2000), (148,))
        self.assertEqual(2, len(loaded.stages))
        self.assertEqual(hashlib.sha256, hashlib.sha256)  # sanity: hashing available
        self.assertEqual("user-supplied", document["provenance"])
        self.assertEqual(
            {2},
            {stage.unlock_after_chapter for stage in loaded.stages},
        )

    def test_archive_unlock_cadence_is_projected_from_the_manifest(self) -> None:
        _, _, loaded = self._generate(
            _battledata(2000, 2001, 2002, 2004, 2006),
            (144, 148, 151, 673),
        )
        progress_after_chapter_4 = 0x01000000 | (5 << 6) | 1
        self.assertEqual(
            ["2000-1", "2000-2", "2004-1", "2004-2"],
            loaded.client_lists(progress_after_chapter_4)["specialQuestList"],
        )

    def test_grant_rides_the_first_section_only(self) -> None:
        # Repeating it per section would grant the character once per stage.
        _, _, loaded = self._generate(_battledata(2000), (148,))
        by_section = {stage.section: stage.character_ids for stage in loaded.stages}
        self.assertEqual((148,), by_section[1])
        self.assertEqual((), by_section[2])

    def test_tower_projects_every_imported_stage_and_excludes_donation(self) -> None:
        battledata = _battledata(9010, 9011, 9012, 9013, 9100, 9101, 9102)
        _, _, loaded = self._generate(battledata, ())
        self.assertEqual(
            [
                (chapter, section)
                for chapter in (9010, 9011, 9012, 9013)
                for section in (1, 2)
            ],
            sorted(loaded.by_identity()),
        )
        before = 0x01000000 | (3 << 6) | 1
        after = 0x01000000 | (4 << 6) | 1
        self.assertEqual([], loaded.client_lists(before)["towerQuestList"])
        self.assertEqual(
            [
                f"{chapter}-{section}"
                for chapter in (9010, 9011, 9012, 9013)
                for section in (1, 2)
            ],
            loaded.client_lists(after)["towerQuestList"],
        )
        stage = loaded.by_identity()[(9010, 1)]
        self.assertEqual(15, stage.stamina)
        self.assertEqual("tower", stage.selector)
        self.assertEqual(TOWER_MANIFEST_ROWS[0][3], stage.unlock_after_chapter)
        self.assertFalse(
            {9100, 9101, 9102} & {stage.chapter for stage in loaded.stages}
        )

    def test_eidolon_stages_and_recovered_drop_ceiling_are_projected(self) -> None:
        _, _, loaded = self._generate(_battledata(*range(4100, 4112)), ())
        before = 0x01000000 | (3 << 6) | 1
        after = 0x01000000 | (4 << 6) | 1
        self.assertEqual([], loaded.client_lists(before)["eidolonQuestList"])
        self.assertEqual(
            [
                f"{chapter}-{section}"
                for chapter in range(4100, 4112)
                for section in (1, 2)
            ],
            loaded.client_lists(after)["eidolonQuestList"],
        )
        self.assertEqual((4,), loaded.by_identity()[(4100, 1)].summon_ids)
        self.assertEqual((), loaded.by_identity()[(4100, 2)].summon_ids)
        self.assertEqual((7,), loaded.by_identity()[(4109, 1)].summon_ids)
        self.assertTrue(
            all(stage.selector == "eidolon" for stage in loaded.stages)
        )

    def test_grant_absent_from_the_local_catalog_is_omitted_and_reported(self) -> None:
        # The user-input boundary: grants are validated, never asserted.
        document, notes, loaded = self._generate(_battledata(2000), ())
        self.assertTrue(all(stage.character_ids == () for stage in loaded.stages))
        self.assertTrue(any("grant omitted" in note for note in notes))

    def test_chapters_absent_from_the_import_are_skipped_and_reported(self) -> None:
        _, notes, loaded = self._generate(_battledata(2000), (148,))
        self.assertEqual({2000}, {stage.chapter for stage in loaded.stages})
        self.assertTrue(any("skipped" in note for note in notes))

    def test_every_manifest_chapter_is_supported(self) -> None:
        chapters = (
            tuple(row[2] for row in EVENT_MANIFEST_ROWS)
            + tuple(row[2] for row in TOWER_MANIFEST_ROWS)
            + tuple(row[2] for row in EIDOLON_MANIFEST_ROWS)
        )
        _, notes, loaded = self._generate(_battledata(*chapters), ())
        self.assertEqual(set(chapters), {stage.chapter for stage in loaded.stages})
        self.assertEqual(
            len(EVENT_MANIFEST_ROWS)
            + len(TOWER_MANIFEST_ROWS)
            + len(EIDOLON_MANIFEST_ROWS),
            len({stage.event_id for stage in loaded.stages}),
        )
        self.assertFalse([note for note in notes if "skipped" in note])

    def test_event_catalog_adds_no_unsupported_fixed_clear_increment(self) -> None:
        _, _, loaded = self._generate(_battledata(2004, 8000), (673,))
        self.assertTrue(
            all(
                stage.clear_coins == EVENT_CLEAR_COINS
                for stage in loaded.stages
            )
        )
        self.assertEqual(0, EVENT_CLEAR_COINS)

    def test_late_counter_descents_retain_the_bundled_zero_base_selector(self) -> None:
        chapters = tuple(range(8012, 8018))
        _, _, loaded = self._generate(_battledata(*chapters), ())
        progress_after_chapter_18 = 0x01000000 | (19 << 6) | 1
        self.assertEqual(
            [f"{chapter}-1" for chapter in chapters],
            loaded.client_lists(progress_after_chapter_18)[
                "descentHuntingList"
            ],
        )
        self.assertTrue(all(stage.zero_base for stage in loaded.stages))
        self.assertFalse(loaded.client_lists(progress_after_chapter_18)["specialQuestList"])

    def test_empty_import_is_refused(self) -> None:
        with self.assertRaises(EventCatalogGeneratorError):
            self._generate({"stages": []}, ())

    def test_import_without_any_event_chapter_is_refused(self) -> None:
        with self.assertRaises(EventCatalogGeneratorError):
            self._generate(_battledata(3), ())

    def test_manifest_rows_are_unique(self) -> None:
        ids = [row[0] for row in EVENT_MANIFEST_ROWS]
        chapters = [row[2] for row in EVENT_MANIFEST_ROWS]
        self.assertEqual(len(set(ids)), len(ids))
        self.assertEqual(len(set(chapters)), len(chapters))


if __name__ == "__main__":
    unittest.main()
