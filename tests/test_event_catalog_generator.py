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
    ARCHIVE_SECTION_ALLOWLIST,
    EIDOLON_MANIFEST_ROWS,
    EIDOLON_PLAYABLE_SECTIONS,
    EVENT_CLEAR_COINS,
    EVENT_MANIFEST_ROWS,
    FOLDED_ARCHIVE_CHAPTERS,
    MELTING_POT_MANIFEST_ROWS,
    MELTING_POT_SECTIONS,
    STANDING_SPECIAL_MANIFEST_ROWS,
    STANDING_SPECIAL_SECTION_ALLOWLIST,
    TOWER_MANIFEST_ROWS,
)


def _battledata(*chapters: int) -> dict:
    stages = []
    for chapter in chapters:
        # Melting Pot is the one family whose section count the client itself
        # fixes, and the generator checks the import against it.
        sections = (
            range(1, MELTING_POT_SECTIONS + 1)
            if any(chapter == row[2] for row in MELTING_POT_MANIFEST_ROWS)
            else (1, 2)
        )
        for section in sections:
            stages.append({
                "chapter": chapter, "section": section, "stamina": 15,
                "coins": 0, "entry_item_id": 0, "entry_item_count": 0,
                "battle_count": 5, "has_battle": True,
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
        lists = loaded.client_lists(progress_after_chapter_4)
        self.assertEqual(["2004-1", "2004-2"], lists["specialQuestList"])
        # 2000 is a Third Descent and rides the Arena -> Descent Quests menu,
        # not Special Quests; the cadence it unlocks on is the same either way.
        self.assertEqual(["2000"], lists["descentQuestList"])

    def test_curated_archive_uses_folded_and_explicit_selector_rows(self) -> None:
        chapters = (2000, 2003, 2005, 2007, 2008, 2009, 2010, 2011, 2014, 2015, 2016, 2017, 2018)
        battledata = _battledata(*chapters)
        # The real Chapter 2015 import also contains three empty placeholders.
        battledata["stages"].extend({
            "chapter": 2015, "section": section, "stamina": 25,
            "coins": 0, "battle_count": 0, "has_battle": False,
        } for section in (4, 5, 6))
        _, _, loaded = self._generate(
            battledata,
            (148, 596, 597, 736, 805, 1080, 1288),
        )
        after_story = 0x01000000 | (43 << 6) | 1
        lists = loaded.client_lists(after_story)
        self.assertEqual(
            [
                "2003-1", "2003-2", "2005-1", "2005-2",
                "2007", "2008", "2014-1", "2014-2",
                # 2015 stays per-section although the client folds it: the
                # placeholders below are what a folded card would advertise.
                "2015-1", "2015-2",
                # 2017 folds, which is how the client names it and what keeps
                # `specialQuestList` inside the length it can draw.
                "2017",
                "2018-1", "2018-2",
            ],
            lists["specialQuestList"],
        )
        # The Third Descents, the Dragon King and the Royal Rings are drawn by
        # a different Arena menu, and each keeps the folded or per-section
        # identity it had while it was miscarried on the Special list: 2000,
        # 2009 and 2016 fold, 2010 and 2011 do not.
        self.assertEqual(
            ["2000", "2009", "2010-1", "2010-2", "2011-1", "2011-2", "2016"],
            lists["descentQuestList"],
        )
        # The client names 2015 bare too, and that literal is deliberately not
        # honoured: a folded card offers a tier per section its flag answers
        # for, and three of 2015's six are the placeholders below.
        self.assertIn(2017, FOLDED_ARCHIVE_CHAPTERS)
        self.assertIn(2016, FOLDED_ARCHIVE_CHAPTERS)
        self.assertNotIn(2015, FOLDED_ARCHIVE_CHAPTERS)
        self.assertEqual((1, 2, 3), ARCHIVE_SECTION_ALLOWLIST[2015])
        self.assertFalse(
            {(2015, 4), (2015, 5), (2015, 6)} & set(loaded.by_identity())
        )
        self.assertEqual((596, 597), loaded.by_identity()[(2003, 1)].character_ids)
        self.assertEqual((736,), loaded.by_identity()[(2005, 1)].character_ids)
        self.assertEqual((805,), loaded.by_identity()[(2008, 1)].character_ids)
        self.assertEqual((1080,), loaded.by_identity()[(2015, 1)].character_ids)
        self.assertEqual((1288,), loaded.by_identity()[(2018, 1)].character_ids)
        self.assertEqual((), loaded.by_identity()[(2017, 1)].character_ids)
        self.assertTrue({2000, 2007, 2008, 2009} <= FOLDED_ARCHIVE_CHAPTERS)

    def test_the_fifth_strikes_back_section_is_withheld(self) -> None:
        """BattleData carries it; the retained archive cannot draw it.

        Chapters 8000--8007 each have five sections with real battles, so a
        generator reading BattleData alone offers all five. The retired service
        shipped `sp<chapter>-1` through `-4` and no fifth, and the client has no
        name for one either -- it renders the literal placeholder `text` under a
        black card, which is what a tester's selector showed. `flags` keys these
        families per section, so dropping the stage drops the row with it.
        """
        battledata = {
            "schema_version": 1, "provenance": "user-derived",
            "source": {"profile": "p", "apk_sha256": "0" * 64},
            "stages": [
                {"chapter": 8002, "section": section, "stamina": 15,
                 "coins": 0, "battle_count": 1, "has_battle": True}
                for section in range(1, 6)
            ],
        }
        _, _, loaded = self._generate(battledata, ())
        self.assertEqual((1, 2, 3, 4), ARCHIVE_SECTION_ALLOWLIST[8002])
        self.assertEqual(
            [1, 2, 3, 4],
            sorted(stage.section for stage in loaded.stages if stage.chapter == 8002),
        )
        self.assertNotIn((8002, 5), loaded.by_identity())
        # The row is what actually goes: an unbacked section defers to its flag,
        # and there is no longer a `-5` key to answer for it.
        self.assertNotIn("sp_ch_8002-5", loaded.flags(None))

    def test_a_folded_chapter_never_withholds_one_of_its_own_sections(self) -> None:
        """The property that makes folding safe, and the 2015 trap in one line.

        A folded card offers a tier per section its chapter flag answers for --
        `CheckQuestFlag` retries an unset `sp_ch_<chapter>-<section>` as
        `sp_ch_<chapter>` -- so the client will offer every section BattleData
        carries, not just the ones this server serves. A chapter that withholds
        any of its own sections therefore must not be folded, or it advertises
        tiers this archive cannot draw and this server refuses to start.
        """
        self.assertEqual(
            set(),
            FOLDED_ARCHIVE_CHAPTERS & set(ARCHIVE_SECTION_ALLOWLIST),
            "a chapter cannot both be folded and have sections withheld",
        )

    def test_grant_rides_the_first_section_only(self) -> None:
        # Repeating it per section would grant the character once per stage.
        _, _, loaded = self._generate(_battledata(2000), (148,))
        by_section = {stage.section: stage.character_ids for stage in loaded.stages}
        self.assertEqual((148,), by_section[1])
        self.assertEqual((), by_section[2])

    def test_lucia_entry_keys_are_projected_from_battledata(self) -> None:
        battledata = _battledata(2006)
        second = next(
            stage for stage in battledata["stages"] if stage["section"] == 2
        )
        second["stamina"] = 35
        second["entry_item_id"] = 110
        second["entry_item_count"] = 1
        document, _, loaded = self._generate(battledata, ())
        raw = next(
            stage for stage in document["stages"]
            if (stage["chapter"], stage["section"]) == (2006, 2)
        )
        self.assertEqual((110, 1), (
            raw["entry_item_id"], raw["entry_item_count"],
        ))
        stage = loaded.by_identity()[(2006, 2)]
        self.assertEqual((35, 110, 1), (
            stage.stamina, stage.entry_item_id, stage.entry_item_count,
        ))

    def test_tower_and_melting_pot_are_separate_selectors(self) -> None:
        # 9000--9003 and 9100--9102 are client chapter ranges with
        # different selectors: the dedicated Tower list, and the ordinary
        # Special list as one folded card per race.
        battledata = _battledata(9000, 9001, 9002, 9003, 9100, 9101, 9102)
        _, _, loaded = self._generate(battledata, ())
        self.assertEqual(
            [
                (chapter, section)
                for chapter in (9000, 9001, 9002, 9003)
                for section in (1, 2)
            ]
            + [
                (chapter, section)
                for chapter in (9100, 9101, 9102)
                for section in range(1, MELTING_POT_SECTIONS + 1)
            ],
            sorted(loaded.by_identity()),
        )
        before = 0x01000000 | (3 << 6) | 1
        after = 0x01000000 | (4 << 6) | 1
        self.assertEqual([], loaded.client_lists(before)["towerQuestList"])
        self.assertEqual(
            [
                f"{chapter}-{section}"
                for chapter in (9000, 9001, 9002, 9003)
                for section in (1, 2)
            ],
            loaded.client_lists(after)["towerQuestList"],
        )
        stage = loaded.by_identity()[(9000, 1)]
        self.assertEqual(15, stage.stamina)
        self.assertEqual("tower", stage.selector)
        self.assertEqual(TOWER_MANIFEST_ROWS[0][3], stage.unlock_after_chapter)
        # Melting Pot rides the Special list as one card per chapter, and
        # settles from the client's own reported drops.
        self.assertEqual(
            ["9100", "9101", "9102"],
            [
                row for row in loaded.client_lists(after)["specialQuestList"]
                if row.startswith("91")
            ],
        )
        melting_pot = loaded.by_identity()[(9100, 1)]
        self.assertEqual("special", melting_pot.selector)
        self.assertTrue(melting_pot.projected_rewards)
        self.assertEqual(
            MELTING_POT_MANIFEST_ROWS[0][3], melting_pot.unlock_after_chapter,
        )

    def test_only_banner_backed_battle_eidolon_sections_are_projected(self) -> None:
        battledata = _battledata(*range(4100, 4112))
        for stage in battledata["stages"]:
            expected = EIDOLON_PLAYABLE_SECTIONS[stage["chapter"]]
            stage["section"] = expected
        # Deduplicate chapters whose helper-produced rows now share the exact
        # one playable section from the final BattleData import.
        battledata["stages"] = list({
            (stage["chapter"], stage["section"]): stage
            for stage in battledata["stages"]
        }.values())
        _, _, loaded = self._generate(battledata, ())
        before = 0x01000000 | (3 << 6) | 1
        after = 0x01000000 | (4 << 6) | 1
        self.assertEqual([], loaded.client_lists(before)["eidolonQuestList"])
        self.assertEqual(
            [
                f"{chapter}-{EIDOLON_PLAYABLE_SECTIONS[chapter]}"
                for chapter in range(4100, 4112)
            ],
            loaded.client_lists(after)["eidolonQuestList"],
        )
        self.assertEqual(12, len(loaded.stages))
        self.assertTrue(all(not stage.summon_ids for stage in loaded.stages))
        self.assertTrue(
            all(stage.selector == "eidolon" for stage in loaded.stages)
        )

    def test_eidolon_battledata_shape_drift_is_refused(self) -> None:
        with self.assertRaisesRegex(
            EventCatalogGeneratorError,
            "expected playable BattleData section 4100-3",
        ):
            self._generate(_battledata(4100), ())

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
            + tuple(row[2] for row in MELTING_POT_MANIFEST_ROWS)
            + tuple(row[2] for row in EIDOLON_MANIFEST_ROWS)
            # The standing Special rows carry their chapter in position 1: they
            # build their flag per section rather than naming one per chapter.
            + tuple(row[1] for row in STANDING_SPECIAL_MANIFEST_ROWS)
        )
        battledata = _battledata(*chapters)
        for stage in battledata["stages"]:
            if stage["chapter"] in EIDOLON_PLAYABLE_SECTIONS:
                stage["section"] = EIDOLON_PLAYABLE_SECTIONS[stage["chapter"]]
        battledata["stages"] = list({
            (stage["chapter"], stage["section"]): stage
            for stage in battledata["stages"]
        }.values())
        _, notes, loaded = self._generate(battledata, ())
        self.assertEqual(set(chapters), {stage.chapter for stage in loaded.stages})
        self.assertEqual(
            len(EVENT_MANIFEST_ROWS)
            + len(TOWER_MANIFEST_ROWS)
            + len(MELTING_POT_MANIFEST_ROWS)
            + len(EIDOLON_MANIFEST_ROWS)
            + len(STANDING_SPECIAL_MANIFEST_ROWS),
            len({stage.event_id for stage in loaded.stages}),
        )
        self.assertFalse([note for note in notes if "skipped" in note])

    def test_standing_specials_ride_sectioned_rows_and_per_section_flags(self) -> None:
        chapters = tuple(row[1] for row in STANDING_SPECIAL_MANIFEST_ROWS)
        _, _, loaded = self._generate(_battledata(*chapters), ())
        after_gate = 0x01000000 | (4 << 6) | 1
        # Every row is sectioned. The client's section-title lookup is 1-based,
        # so a bare chapter here would index -1 and abort the selector.
        rows = [
            row for row in loaded.client_lists(after_gate)["specialQuestList"]
            if row.startswith(("3001", "3100", "32", "3300"))
        ]
        self.assertTrue(all("-" in row for row in rows))
        self.assertIn("3200-1", rows)
        stage = loaded.by_identity()[(3200, 1)]
        self.assertEqual("special", stage.selector)
        self.assertEqual("sp_ch_3200-1", stage.flag)
        # No reward table for these survived, so a clear settles from the
        # client's own reported drops, as Counter Descent and Melting Pot do.
        self.assertTrue(stage.projected_rewards)

    def test_unbannered_standing_special_sections_are_withheld(self) -> None:
        # Chapter 3001 has three BattleData sections but only two retained
        # banner bundles; the third must not reach the selector.
        battledata = _battledata(3001)
        battledata["stages"].append({
            "chapter": 3001, "section": 3, "stamina": 20,
            "coins": 0, "battle_count": 1, "has_battle": True,
        })
        _, _, loaded = self._generate(battledata, ())
        self.assertEqual(
            STANDING_SPECIAL_SECTION_ALLOWLIST[3001],
            tuple(sorted(section for _chapter, section in loaded.by_identity())),
        )

    def test_event_catalog_adds_no_unsupported_fixed_clear_increment(self) -> None:
        _, _, loaded = self._generate(_battledata(2004, 8000), (673,))
        self.assertTrue(
            all(
                stage.clear_coins == EVENT_CLEAR_COINS
                for stage in loaded.stages
            )
        )
        self.assertEqual(0, EVENT_CLEAR_COINS)

    def test_late_counter_descents_retain_the_bundled_projected_selector(self) -> None:
        chapters = tuple(range(8012, 8018))
        _, _, loaded = self._generate(_battledata(*chapters), ())
        progress_after_chapter_18 = 0x01000000 | (19 << 6) | 1
        self.assertEqual(
            [str(chapter) for chapter in chapters],
            loaded.client_lists(progress_after_chapter_18)[
                "descentHuntingList"
            ],
        )
        self.assertTrue(all(stage.projected_rewards for stage in loaded.stages))
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
