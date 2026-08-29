from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from liminal_gate.hunting_catalog import BUNDLED_ITEM_SLOTS, BUNDLED_MAX_STACK
from liminal_gate.story_outcome_catalog import load_story_outcome_catalog
from liminal_gate.story_outcome_generator import (
    DEFAULT_COMPANION_DROP_LEVEL,
    MAX_COMPANIONS,
    StoryOutcomeGeneratorError,
    build_catalog,
    build_derivation_source,
    companion_drops_by_enemy,
    native_stage_maxima,
    section_companion_maxima,
    write_catalog,
)


# Companion IDs used below are real entries in the bundled Companion master
# table, because the generator omits any Companion this release does not know.
BOMBORG, ELECTROTICK, TEKSURA = 95, 92, 94
COMPANION_A, COMPANION_B = 111, 226
#: Spinetrich Kino ΟⅡ, one of the 51 that drop at 30 rather than 1.
OMICRON_TWO_COMPANION = 317
UNKNOWN_COMPANION = 60000
APK_SHA256 = "a" * 64


def _code(companion_id: int, cap: int) -> dict[str, int]:
    return {"code": (companion_id << 8) | cap}


def _enemy(
    record_id: int, companion_id: int = 0, ratio: float = 0.0,
    items: tuple[tuple[int, int], ...] = (), job_id: int = 0, job_ratio: float = 0.0,
) -> dict[str, object]:
    slots = [{"code": (item << 8) | count} for item, count in items]
    slots += [{"code": 0}] * (4 - len(slots))
    return {
        "ID": record_id, "DropBuddyID": companion_id, "DropBuddyRatio": ratio,
        "items": slots, "DropJobID": job_id, "DropRatio": job_ratio,
    }


def _encounters(stages: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schema_version": 1, "provenance": "user-derived",
        "source": {
            "profile": "terra-battle-android-5.5.7-170",
            "abi": "arm64",
            "apk_sha256": APK_SHA256,
            "dump_cs_sha256": "b" * 64,
            "libil2cpp_sha256": "c" * 64,
            "objdump": "GNU objdump 2.44",
            "vtable_calibration": "verified",
        },
        "stages": stages,
    }


def _stage(chapter: int, section: int, spawns: list[tuple[str, int | None, bool, int]]) -> dict[str, object]:
    rows = [{"symbol": symbol, "enemy_id": enemy_id, "exact": exact, "count": count} for symbol, enemy_id, exact, count in spawns]
    return {
        "chapter": chapter, "section": section,
        "resolved": all(row["enemy_id"] is not None for row in rows),
        "exact": all(row["enemy_id"] is not None and row["exact"] for row in rows),
        "spawns": rows,
    }


class CompanionDropsByEnemyTest(unittest.TestCase):
    def test_reads_the_companion_each_enemy_can_drop(self) -> None:
        tree = {"data": [_enemy(BOMBORG, COMPANION_A, 20.0), _enemy(TEKSURA, COMPANION_B, 13.0)]}
        self.assertEqual({BOMBORG: COMPANION_A, TEKSURA: COMPANION_B}, companion_drops_by_enemy(tree))

    def test_a_zero_ratio_record_contributes_no_ceiling(self) -> None:
        # The clone records carry a Companion ID at ratio 0.0, which never rolls.
        tree = {"data": [_enemy(ELECTROTICK, COMPANION_A, 0.0), _enemy(BOMBORG)]}
        self.assertEqual({ELECTROTICK: 0, BOMBORG: 0}, companion_drops_by_enemy(tree))

    def test_rejects_malformed_enemy_data(self) -> None:
        for tree, message in (
            ({"data": []}, "nonempty data array"),
            ({"data": [{"ID": 1, "DropBuddyID": 2}]}, "missing required fields"),
            ({"data": [{"ID": "1", "DropBuddyID": 2, "DropBuddyRatio": 1.0}]}, "invalid drop fields"),
            ({"data": [_enemy(1, 2, 1.0), _enemy(1, 3, 1.0)]}, "must be unique"),
        ):
            with self.subTest(message=message), self.assertRaisesRegex(StoryOutcomeGeneratorError, message):
                companion_drops_by_enemy(tree)


class SectionCompanionMaximaTest(unittest.TestCase):
    def test_unpacks_the_companion_and_cap_from_each_code(self) -> None:
        tree = {"chapters": [{"chapterNo": 8, "sections": [
            {"dropBuddies": [_code(COMPANION_A, 1), _code(COMPANION_B, 3)]},
            {"dropBuddies": []},
        ]}]}
        self.assertEqual({(8, 1): {COMPANION_A: 1, COMPANION_B: 3}, (8, 2): {}}, section_companion_maxima(tree))

    def test_keeps_the_larger_cap_when_a_companion_is_listed_twice(self) -> None:
        tree = {"chapters": [{"chapterNo": 8, "sections": [{"dropBuddies": [_code(COMPANION_A, 1), _code(COMPANION_A, 4)]}]}]}
        self.assertEqual({(8, 1): {COMPANION_A: 4}}, section_companion_maxima(tree))

    def test_skips_the_tutorial_chapter_the_schema_excludes(self) -> None:
        tree = {"chapters": [
            {"chapterNo": 1, "sections": [{"dropBuddies": [_code(COMPANION_A, 1)]}]},
            {"chapterNo": 2, "sections": [{"dropBuddies": []}]},
        ]}
        self.assertEqual({(2, 1)}, set(section_companion_maxima(tree)))

    def test_a_section_with_no_droplist_is_still_a_stage(self) -> None:
        self.assertEqual({(2, 1): {}}, section_companion_maxima({"chapters": [{"chapterNo": 2, "sections": [{}]}]}))

    def test_rejects_malformed_battledata(self) -> None:
        for tree, message in (
            ({"chapters": []}, "nonempty chapters array"),
            ({"chapters": [{"chapterNo": "2", "sections": []}]}, "chapter is invalid"),
            ({"chapters": [{"chapterNo": 2, "sections": [{"dropBuddies": 5}]}]}, "invalid dropBuddies"),
            ({"chapters": [{"chapterNo": 2, "sections": [{"dropBuddies": [{"code": -1}]}]}]}, "dropBuddies entry is invalid"),
            ({"chapters": [{"chapterNo": 1, "sections": [{}]}]}, "no chapter at or above 2"),
        ):
            with self.subTest(message=message), self.assertRaisesRegex(StoryOutcomeGeneratorError, message):
                section_companion_maxima(tree)


class NativeCompanionMaximaTest(unittest.TestCase):
    def setUp(self) -> None:
        self.drops = {BOMBORG: COMPANION_A, ELECTROTICK: 0, TEKSURA: COMPANION_B}

    def test_a_stage_ceiling_is_how_many_droppers_it_spawns(self) -> None:
        encounters = _encounters([_stage(8, 1, [("CH8_BMAKER", BOMBORG, True, 4), ("CH8_L_TICK", ELECTROTICK, True, 6)])])
        maxima, report = native_stage_maxima(encounters, self.drops, {}, {}, exact_only=False)
        self.assertEqual({COMPANION_A: 4}, maxima[(8, 1)]["companions"])
        self.assertEqual((1, 0, 0), (report["stages_joined"], report["stages_unjoinable"], report["stages_with_inferred_ceiling"]))

    def test_two_droppers_of_the_same_companion_add_up(self) -> None:
        drops = {BOMBORG: COMPANION_A, TEKSURA: COMPANION_A}
        encounters = _encounters([_stage(8, 1, [("CH8_BMAKER", BOMBORG, True, 2), ("CH8_TECHSURA", TEKSURA, True, 3)])])
        self.assertEqual({COMPANION_A: 5}, native_stage_maxima(encounters, drops, {}, {}, exact_only=False)[0][(8, 1)]["companions"])

    def test_an_inferred_variant_contributes_but_is_counted_separately(self) -> None:
        encounters = _encounters([_stage(8, 2, [("CH8_BMAKER_NM", BOMBORG, False, 2)])])
        maxima, report = native_stage_maxima(encounters, self.drops, {}, {}, exact_only=False)
        self.assertEqual({COMPANION_A: 2}, maxima[(8, 2)]["companions"])
        self.assertEqual(1, report["stages_with_inferred_ceiling"])

    def test_exact_only_drops_a_stage_that_rests_on_a_variant(self) -> None:
        encounters = _encounters([_stage(8, 2, [("CH8_BMAKER_NM", BOMBORG, False, 2)])])
        maxima, report = native_stage_maxima(encounters, self.drops, {}, {}, exact_only=True)
        self.assertEqual(({}, 1, 0), (maxima, report["stages_unjoinable"], report["stages_with_inferred_ceiling"]))

    def test_a_stage_missing_one_enemy_record_contributes_nothing(self) -> None:
        # Understating a ceiling refuses a legitimate clear, so a partly-joined
        # stage is left to its own BattleData allowlist instead.
        encounters = _encounters([_stage(38, 1, [("CH8_BMAKER", BOMBORG, True, 2), ("CH38_RUKU", 1800, True, 3)])])
        maxima, report = native_stage_maxima(encounters, self.drops, {}, {}, exact_only=False)
        self.assertEqual({}, maxima)
        self.assertEqual((1, 1, 3, [38]), (
            report["stages_unjoinable"], report["symbols_without_enemy_record"],
            report["spawns_without_enemy_record"], report["chapters_without_enemy_record"],
        ))

    def test_a_permanently_absent_record_is_reported_apart_from_an_unknown_name(self) -> None:
        encounters = _encounters([
            _stage(38, 1, [("CH38_RUKU", 1800, True, 3)]),
            _stage(21, 4, [("CH21_WHITE1", None, False, 1)]),
        ])
        report = native_stage_maxima(encounters, self.drops, {}, {}, exact_only=False)[1]
        self.assertEqual((1, 3, 1, 1), (
            report["symbols_without_enemy_record"], report["spawns_without_enemy_record"],
            report["unrecognised_symbols"], report["spawns_from_unrecognised_symbols"],
        ))
        self.assertEqual(([38], 2), (report["chapters_without_enemy_record"], report["stages_unjoinable"]))

    def test_rejects_a_map_that_is_not_a_user_derived_arm64_import(self) -> None:
        for document in (
            {**_encounters([_stage(8, 1, [])]), "provenance": "user-supplied"},
            {**_encounters([_stage(8, 1, [])]), "schema_version": 2},
            {
                **_encounters([_stage(8, 1, [])]),
                "source": {
                    **_encounters([])["source"],
                    "abi": "armv7",
                },
            },
            {**_encounters([]), "stages": []},
        ):
            with self.subTest(document=document), self.assertRaisesRegex(StoryOutcomeGeneratorError, "user-derived ARM64"):
                native_stage_maxima(document, self.drops, {}, {}, exact_only=False)

    def test_rejects_a_malformed_stage_or_spawn(self) -> None:
        with self.assertRaisesRegex(StoryOutcomeGeneratorError, "invalid stage"):
            native_stage_maxima(_encounters([{"chapter": 8}]), self.drops, {}, {}, exact_only=False)
        broken = _stage(8, 1, [("CH8_BMAKER", BOMBORG, True, 1)])
        broken["spawns"] = [{"symbol": "CH8_BMAKER", "enemy_id": 95, "exact": "yes", "count": 1}]
        with self.assertRaisesRegex(StoryOutcomeGeneratorError, "invalid spawn"):
            native_stage_maxima(_encounters([broken]), self.drops, {}, {}, exact_only=False)


class BuildCatalogTest(unittest.TestCase):
    def setUp(self) -> None:
        self.characters = {
            "source": {
                "profile": "terra-battle-android-5.5.7-170",
                "apk_sha256": APK_SHA256,
            },
            "characters": [{"character_id": 9002}, {"character_id": 9001}],
        }
        self.enemy_data = {"data": [
            _enemy(BOMBORG, COMPANION_A, 20.0, items=((5, 2),), job_id=700, job_ratio=5.0),
            _enemy(TEKSURA, COMPANION_B, 13.0, items=((5, 1), (9, 3))),
            # Job drop with a zero ratio never rolls, so it contributes nothing.
            _enemy(ELECTROTICK, COMPANION_A, 0.0, job_id=701, job_ratio=0.0),
        ]}
        self.chr_database = {"data": [
            {"ID": 700, "chrID": 9001},
            {"ID": 701, "chrID": 9002},
        ]}
        self.battledata = {"chapters": [{"chapterNo": 8, "sections": [
            {"dropBuddies": [_code(COMPANION_A, 1)]},
            {"dropBuddies": [_code(COMPANION_B, 2)]},
            {"dropBuddies": []},
        ]}]}
        self.encounters = _encounters([
            _stage(8, 1, [("CH8_BMAKER", BOMBORG, True, 4)]),
            _stage(8, 2, [("CH8_TECHSURA", TEKSURA, True, 1)]),
            _stage(8, 3, [("CH8_L_TICK", ELECTROTICK, True, 6)]),
        ])

    def _build(self, **kwargs: object) -> tuple[dict[str, object], dict[str, object], list[str]]:
        return build_catalog(self.encounters, self.battledata, self.enemy_data, self.chr_database, self.characters, **kwargs)  # type: ignore[arg-type]

    def _rules(self, catalog: dict[str, object]) -> dict[tuple[int, int], dict[str, object]]:
        return {(rule["chapter"], rule["section"]): rule for rule in catalog["stages"]}  # type: ignore[index,union-attr]

    def test_the_union_takes_the_larger_of_the_two_sources(self) -> None:
        rules = self._rules(self._build()[0])
        # 8-1: the native map counts four droppers, the section list allows one.
        self.assertEqual({str(COMPANION_A): 4}, rules[(8, 1)]["companion_maxima"])
        # 8-2: the section list allows two, the native map finds one dropper.
        self.assertEqual({str(COMPANION_B): 2}, rules[(8, 2)]["companion_maxima"])
        # 8-3: neither source offers anything, and the stage is still written.
        self.assertEqual({}, rules[(8, 3)]["companion_maxima"])

    def test_item_and_character_ceilings_come_from_the_recovered_drop_data(self) -> None:
        # A ceiling permits and an empty one forbids, so these have to be
        # derived: leaving them empty refuses a clear that legitimately reports
        # an item or a recruited monster.
        rules = self._rules(self._build()[0])
        # One per enemy able to drop it. The low byte of an `ItemCode` is a drop
        # rate, not a stack count -- the recovered table runs to 100 -- so
        # Bomborg's rate of 2 over four spawns is a ceiling of four, not eight.
        self.assertEqual({"5": 4}, rules[(8, 1)]["item_maxima"])
        self.assertEqual({"9001": 4}, rules[(8, 1)]["character_maxima"])
        self.assertEqual({"5": 1, "9": 1}, rules[(8, 2)]["item_maxima"])

    def test_a_zero_rate_item_contributes_no_ceiling(self) -> None:
        # Same reading the Companion and Job ceilings apply to their own ratios.
        enemy_data = {"data": [_enemy(BOMBORG, COMPANION_A, 20.0, items=((5, 0), (9, 4)))]}
        catalog, _report, _notes = build_catalog(
            _encounters([_stage(8, 1, [("CH8_BMAKER", BOMBORG, True, 3)])]),
            {"chapters": [{"chapterNo": 8, "sections": [{"dropBuddies": [_code(COMPANION_A, 1)]}]}]},
            enemy_data, self.chr_database, self.characters,
        )
        self.assertEqual({"9": 3}, catalog["stages"][0]["item_maxima"])

    def test_a_zero_ratio_job_drop_contributes_no_character_ceiling(self) -> None:
        # Same reading the Companion ceiling already applies to its own ratio.
        self.assertEqual({}, self._rules(self._build()[0])[(8, 3)]["character_maxima"])

    def test_declares_every_used_companion_at_the_recovered_drop_level(self) -> None:
        catalog = self._build()[0]
        self.assertEqual(
            [
                {"companion_id": COMPANION_A, "drop_level": DEFAULT_COMPANION_DROP_LEVEL},
                {"companion_id": COMPANION_B, "drop_level": DEFAULT_COMPANION_DROP_LEVEL},
            ],
            catalog["companion_masters"],
        )

    def test_an_omicron_two_dropper_is_declared_at_thirty(self) -> None:
        """The half of the ΟⅡ recovery that reaches a player through a
        generated file rather than through code.

        `COMPANION_A` and `COMPANION_B` are both level 1 droppers, so this
        generator's ΟⅡ path had no coverage, and a catalog generated before
        the recovery keeps declaring 30 of them at 1 until it is regenerated --
        which is how issue 77's level 1 Companions outlived the fix.
        """
        self.battledata["chapters"][0]["sections"][2]["dropBuddies"] = [  # type: ignore[index]
            _code(OMICRON_TWO_COMPANION, 1)
        ]
        catalog = self._build()[0]
        self.assertIn(
            {"companion_id": OMICRON_TWO_COMPANION, "drop_level": 30},
            catalog["companion_masters"],
        )

    def test_carries_the_client_capacities_and_sorted_character_ids(self) -> None:
        catalog = self._build()[0]
        self.assertEqual(
            (BUNDLED_ITEM_SLOTS, BUNDLED_MAX_STACK, MAX_COMPANIONS, [9001, 9002], "user-supplied"),
            (catalog["item_slots"], catalog["max_stack"], catalog["max_companions"], catalog["character_ids"], catalog["provenance"]),
        )

    def test_omits_a_companion_this_release_does_not_know_and_says_so(self) -> None:
        self.battledata["chapters"][0]["sections"][2]["dropBuddies"] = [_code(UNKNOWN_COMPANION, 1)]  # type: ignore[index]
        catalog, _report, notes = self._build()
        self.assertEqual({}, self._rules(catalog)[(8, 3)]["companion_maxima"])
        self.assertTrue(any("Companion master table" in note for note in notes))

    def test_a_baseline_is_widened_rather_than_replaced(self) -> None:
        baseline = {
            "item_slots": 4, "max_stack": 9, "max_companions": 7,
            "companion_masters": [{"companion_id": COMPANION_A, "drop_level": 5}],
            "stages": [{"chapter": 8, "section": 3, "item_maxima": {"2": 3}, "character_maxima": {"9001": 1}, "companion_maxima": {str(COMPANION_B): 9}}],
        }
        catalog, _report, _notes = self._build(baseline=baseline)
        rules = self._rules(catalog)
        self.assertEqual((4, 9, 7), (catalog["item_slots"], catalog["max_stack"], catalog["max_companions"]))
        self.assertEqual(({"2": 3}, {"9001": 1}, {str(COMPANION_B): 9}), (rules[(8, 3)]["item_maxima"], rules[(8, 3)]["character_maxima"], rules[(8, 3)]["companion_maxima"]))
        self.assertEqual({str(COMPANION_A): 4}, rules[(8, 1)]["companion_maxima"])
        self.assertIn({"companion_id": COMPANION_A, "drop_level": 5}, catalog["companion_masters"])

    def test_a_baseline_never_lowers_a_recovered_ceiling(self) -> None:
        baseline = {"stages": [{"chapter": 8, "section": 1, "item_maxima": {}, "character_maxima": {}, "companion_maxima": {str(COMPANION_A): 1}}]}
        self.assertEqual({str(COMPANION_A): 4}, self._rules(self._build(baseline=baseline)[0])[(8, 1)]["companion_maxima"])

    def test_rejects_a_baseline_id_the_catalog_loader_would_refuse(self) -> None:
        for raw_id in ("07", "0", "-1"):
            baseline = {"stages": [{"chapter": 8, "section": 1, "item_maxima": {raw_id: 1}, "character_maxima": {}, "companion_maxima": {}}]}
            with self.subTest(raw_id=raw_id), self.assertRaisesRegex(StoryOutcomeGeneratorError, "positive decimal IDs"):
                self._build(baseline=baseline)

    def test_rejects_a_baseline_naming_an_unknown_character_or_item(self) -> None:
        for maxima, field in (({"7777": 1}, "character_maxima"), ({str(BUNDLED_ITEM_SLOTS + 1): 1}, "item_maxima")):
            baseline = {"stages": [{"chapter": 8, "section": 1, "item_maxima": {}, "character_maxima": {}, field: maxima}]}
            with self.subTest(field=field), self.assertRaisesRegex(StoryOutcomeGeneratorError, "out-of-range ID"):
                self._build(baseline=baseline)

    def test_rejects_inputs_that_resolve_no_companion_at_all(self) -> None:
        self.battledata["chapters"][0]["sections"] = [{"dropBuddies": []}]  # type: ignore[index]
        self.encounters = _encounters([_stage(8, 1, [("CH8_L_TICK", ELECTROTICK, True, 6)])])
        with self.assertRaisesRegex(StoryOutcomeGeneratorError, "no stage resolved a single Companion"):
            self._build()

    def test_rejects_a_character_catalog_with_no_characters(self) -> None:
        self.characters = {"characters": []}
        with self.assertRaisesRegex(StoryOutcomeGeneratorError, "no character IDs"):
            self._build()

    def test_the_result_loads_through_the_real_catalog_loader(self) -> None:
        catalog, report, _notes = self._build()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "derived" / "story-outcomes.json"
            write_catalog(path, catalog)
            loaded = load_story_outcome_catalog(path)
        self.assertEqual(4, loaded.rules[(8, 1)].companion_maxima[COMPANION_A])
        self.assertEqual(DEFAULT_COMPANION_DROP_LEVEL, loaded.companion_masters[COMPANION_A].drop_level)
        self.assertEqual((3, 2, 3), (report["stages_written"], report["distinct_companions"], report["core_stages_with_companion_ceiling"] + 1))

    def test_rejects_native_or_character_inputs_from_a_different_apk(self) -> None:
        for field in ("native", "character"):
            encounters = self.encounters
            characters = self.characters
            if field == "native":
                encounters = {
                    **self.encounters,
                    "source": {
                        **self.encounters["source"],
                        "apk_sha256": "f" * 64,
                    },
                }
            else:
                characters = {
                    **self.characters,
                    "source": {
                        **self.characters["source"],
                        "apk_sha256": "f" * 64,
                    },
                }
            with self.subTest(field=field), self.assertRaisesRegex(
                StoryOutcomeGeneratorError,
                "different APK",
            ):
                build_derivation_source(
                    encounters,
                    characters,
                    APK_SHA256,
                    "d" * 64,
                    "e" * 64,
                )

    def test_generated_catalog_retains_input_hashes_and_calibration(self) -> None:
        source = build_derivation_source(
            self.encounters,
            self.characters,
            APK_SHA256,
            "d" * 64,
            "e" * 64,
            "f" * 64,
        )
        catalog = self._build(source=source)[0]
        self.assertEqual(source, catalog["source"])
        self.assertEqual(
            "verified",
            catalog["source"]["native_encounters"]["vtable_calibration"],
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "story-outcomes.json"
            write_catalog(path, catalog)
            load_story_outcome_catalog(path)

    def test_unverified_native_calibration_stays_explicit(self) -> None:
        self.encounters["source"]["vtable_calibration"] = "unverified"
        _catalog, report, notes = self._build()
        self.assertEqual("unverified", report["vtable_calibration"])
        self.assertTrue(any("unverified" in note for note in notes))

    def test_written_catalogs_are_json_and_leave_no_temporary_behind(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "story-outcomes.json"
            write_catalog(path, self._build()[0])
            self.assertEqual(1, json.loads(path.read_text(encoding="utf-8"))["schema_version"])
            self.assertEqual([path.name], [entry.name for entry in path.parent.iterdir()])


class UnevidencedStageReportTest(unittest.TestCase):
    """A stage nobody could recover evidence for must be counted and marked.

    "This stage drops nothing" and "nobody knows what this stage drops" are both
    an empty ceiling, and an empty ceiling forbids. Conflating them refuses
    ordinary play on every stage the encounter join could not reach, so the two
    are separated here and the second is recorded on the stage itself.
    """

    def test_counts_only_the_stages_no_source_could_reach(self) -> None:
        characters = {"characters": [{"character_id": 9001}]}
        enemy_data = {"data": [
            _enemy(BOMBORG, COMPANION_A, 20.0, items=((5, 2),), job_id=700, job_ratio=5.0),
            _enemy(TEKSURA, COMPANION_B, 13.0),
        ]}
        chr_database = {"data": [{"ID": 700, "chrID": 9001}]}
        battledata = {"chapters": [{"chapterNo": 8, "sections": [
            {"dropBuddies": [_code(COMPANION_A, 1)]},
            {"dropBuddies": [_code(COMPANION_B, 1)]},
            {"dropBuddies": [_code(COMPANION_A, 1)]},
        ]}]}
        encounters = _encounters([
            _stage(8, 1, [("CH8_BMAKER", BOMBORG, True, 1)]),
            _stage(8, 2, [("CH8_TECHSURA", TEKSURA, True, 1)]),
            # No EnemyData row for this spawn, so the stage cannot be joined and
            # nothing can be said about its item or character outcome.
            _stage(8, 3, [("CH8_UNKNOWN", 4242, True, 1)]),
        ])
        catalog, report, _notes = build_catalog(
            encounters, battledata, enemy_data, chr_database, characters,
        )
        self.assertEqual(1, report["stages_without_outcome_evidence"])
        self.assertEqual([8], report["chapters_without_outcome_evidence"])
        self.assertEqual(1, report["stages_with_item_ceiling"])
        self.assertEqual(1, report["stages_with_character_ceiling"])
        by_section = {stage["section"]: stage for stage in catalog["stages"]}
        # 8-1 joined and drops both. 8-2 joined and drops neither, which is a
        # statement, so it stays evidenced and keeps forbidding. 8-3 could not be
        # joined, which is an admission, so it is marked and stops forbidding.
        self.assertEqual(["items", "characters"], by_section[1]["evidence"])
        self.assertEqual(["items", "characters"], by_section[2]["evidence"])
        self.assertEqual([], by_section[3]["evidence"])
        self.assertEqual({}, by_section[2]["item_maxima"])
