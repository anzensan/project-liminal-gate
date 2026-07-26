"""Compose a local story-outcome catalog from the user's own recovered drops.

``--story-outcome-catalog`` is the option that lets a story clear mint a
Companion.  Without one, ``clear_quest`` writes no ``buddyInfo`` at all, so a
self-hosted instance can play the whole story and never see a Companion drop
even though the client rolled one.  Authoring that catalog by hand means
writing a per-stage Companion ceiling for every ordinary stage, which nobody
will do.  This composes it from data the user already has.

Two sources, unioned
--------------------

1. ``BattleData.Section.dropBuddies`` -- the curated per-section allowlist the
   client itself carries.  Each entry packs one Companion and its per-clear cap
   into a single integer (``code >> 8`` is the Companion, ``code & 0xFF`` the
   cap).  Read straight out of the reviewed APK.
2. The native encounter map from :mod:`liminal_gate.native_encounter_importer`,
   joined to ``EnemyData``.  Each spawn resolves to an enemy record, and that
   record's ``DropBuddyID``/``DropBuddyRatio`` say which Companion that enemy
   can drop.  A stage's ceiling for a Companion is then simply how many enemies
   able to drop it the stage spawns.

Neither source subsumes the other.  The section allowlist covers stages the
native map cannot resolve; the native map covers Companions the section list
omits.  The ceiling taken is the larger of the two, which is what a ceiling
means: it permits a roll the client legitimately made and invents nothing.

What this deliberately does not know
------------------------------------

``StoryOutcomeRule`` also carries ``item_maxima`` and ``character_maxima``.
Nothing in this project has recovered a per-stage item or character drop table
for the ordinary story -- ``EnemyData`` carries a Job drop, not an item, and
carries no character drop at all -- so both are emitted **empty**, and an empty
ceiling *forbids* the outcome rather than permitting it.

Read that plainly before using this: a generated catalog makes Companion drops
work and refuses any clear whose battle result reports an item or a character.
That is the correct reading of a ceiling built from what is known, not a claim
that the original game dropped neither.  If your client reports those outcomes,
pass an operator-authored catalog as ``--baseline``; its capacities, its
``item_maxima``/``character_maxima``, and its Companion drop levels are carried
through unchanged and only the Companion ceilings are widened.

Inferred variants
-----------------

A chapter program may spawn a *variant* initializer -- a base enemy with a
behavioural modifier -- which resolves to the base enemy's record with
``exact: false`` in the encounter import.  Those rows are Strongly inferred, not
Confirmed, and are never relabelled here: the summary counts the stages whose
ceiling depends on one, and ``--exact-only`` drops them entirely.

Usage::

    python3 -m liminal_gate.story_outcome_generator \\
        --apk local-input/terra-battle-5.5.7-170.apk \\
        --dummy-dll-dir /path/to/il2cpp-output/DummyDll \\
        --native-encounters user-data/derived/native-encounters.json \\
        --character-catalog user-data/character-catalog.json \\
        --output user-data/derived/story-outcomes.json

The result is validated by ``load_story_outcome_catalog`` before it is written,
so a catalog this produces either loads or says why it does not.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from liminal_gate.character_catalog_importer import CharacterCatalogImportError, load_master_trees
from liminal_gate.companion_master_data import COMPANION_MASTER_ROWS
from liminal_gate.hunting_catalog import BUNDLED_ITEM_SLOTS, BUNDLED_MAX_STACK
from liminal_gate.server_constants import build_server_constants
from liminal_gate.story_outcome_catalog import StoryOutcomeCatalogError, load_story_outcome_catalog


SCHEMA_VERSION = 1

#: The Companion box the local server advertises.  Taken from the same constant
#: block the client is sent so the catalog's capacity and the client's agree.
MAX_COMPANIONS = int(build_server_constants()["maxBuddyBoxCount"])

#: The level a dropped Companion arrives at.  ``EnemyData`` records which
#: Companion an enemy drops and at what rate, and no level, so this follows the
#: one recovered drop manifest that does state it -- Metal Zone's two
#: Companions, both level 1 (:mod:`liminal_gate.hunting_catalog`).  Strongly
#: inferred; a ``--baseline`` entry overrides it per Companion.
DEFAULT_COMPANION_DROP_LEVEL = 1

#: Ordinary story chapters.  Anything else BattleData carries -- archived
#: events, Hunting -- is emitted too, so an operator running this catalog
#: alongside an event catalog does not have every event clear refused for want
#: of a rule.  Only these chapters are counted in the summary.
CORE_CHAPTERS = range(2, 43)


class StoryOutcomeGeneratorError(ValueError):
    """The supplied local inputs cannot produce a story-outcome catalog."""


def _read(path: Path, what: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise StoryOutcomeGeneratorError(f"could not read {what}: {path}") from error


def companion_drops_by_enemy(tree: dict[str, Any]) -> dict[int, int]:
    """Map each enemy record ID to the Companion it can drop, if any.

    A record with ``DropBuddyRatio`` of zero never rolls its Companion, so it
    contributes no ceiling -- the same reading the recovered table's many
    zero-ratio clone records already require.
    """
    rows = tree.get("data")
    if not isinstance(rows, list) or not rows:
        raise StoryOutcomeGeneratorError("EnemyData must contain a nonempty data array")
    drops: dict[int, int] = {}
    for row in rows:
        fields = ("ID", "DropBuddyID", "DropBuddyRatio")
        if not isinstance(row, dict) or any(field not in row for field in fields):
            raise StoryOutcomeGeneratorError("EnemyData record has missing required fields")
        if type(row["ID"]) is not int or type(row["DropBuddyID"]) is not int or not isinstance(row["DropBuddyRatio"], (int, float)):
            raise StoryOutcomeGeneratorError("EnemyData record has invalid drop fields")
        if row["ID"] in drops:
            raise StoryOutcomeGeneratorError("EnemyData record IDs must be unique")
        drops[row["ID"]] = row["DropBuddyID"] if row["DropBuddyID"] > 0 and row["DropBuddyRatio"] > 0 else 0
    return drops


def section_companion_maxima(tree: dict[str, Any]) -> dict[tuple[int, int], dict[int, int]]:
    """Read every stage's own ``dropBuddies`` allowlist out of BattleData."""
    chapters = tree.get("chapters")
    if not isinstance(chapters, list) or not chapters:
        raise StoryOutcomeGeneratorError("BattleData must contain a nonempty chapters array")
    maxima: dict[tuple[int, int], dict[int, int]] = {}
    for chapter in chapters:
        if not isinstance(chapter, dict) or type(chapter.get("chapterNo")) is not int or not isinstance(chapter.get("sections"), list):
            raise StoryOutcomeGeneratorError("BattleData chapter is invalid")
        if chapter["chapterNo"] < 2:
            continue
        for number, section in enumerate(chapter["sections"], start=1):
            if not isinstance(section, dict):
                raise StoryOutcomeGeneratorError("BattleData section must be an object")
            entries = section.get("dropBuddies", [])
            if not isinstance(entries, list):
                raise StoryOutcomeGeneratorError("BattleData section has an invalid dropBuddies list")
            allowed: dict[int, int] = {}
            for entry in entries:
                code = entry.get("code") if isinstance(entry, dict) else entry
                if type(code) is not int or code <= 0:
                    raise StoryOutcomeGeneratorError("BattleData dropBuddies entry is invalid")
                companion_id, cap = code >> 8, code & 0xFF
                if companion_id > 0 and cap > 0:
                    allowed[companion_id] = max(allowed.get(companion_id, 0), cap)
            maxima[(chapter["chapterNo"], number)] = allowed
    if not maxima:
        raise StoryOutcomeGeneratorError("BattleData carries no chapter at or above 2")
    return maxima


def native_companion_maxima(
    encounters: dict[str, Any], enemy_drops: dict[int, int], exact_only: bool,
) -> tuple[dict[tuple[int, int], dict[int, int]], dict[str, Any]]:
    """Join the native encounter map to the per-enemy Companion drops.

    A stage contributes only when *every* one of its spawns resolves to an
    enemy record.  A partly-joined stage would understate its own ceiling, and
    understating a ceiling refuses a legitimate clear, so it is left to the
    section allowlist instead.
    """
    if (
        encounters.get("schema_version") != 1
        or encounters.get("provenance") != "user-derived"
        or not isinstance(encounters.get("source"), dict)
        or encounters["source"].get("abi") != "arm64"
        or not isinstance(encounters.get("stages"), list)
        or not encounters["stages"]
    ):
        raise StoryOutcomeGeneratorError("input must be a user-derived ARM64 native encounter map")
    maxima: dict[tuple[int, int], dict[int, int]] = {}
    inferred_stages: set[tuple[int, int]] = set()
    # Two different failures, kept apart because they mean different things.
    # A symbol with no enemy record is the permanent Chapter 38-42 gap: the
    # client shipped those chapters' scripts but not their EnemyData rows, so
    # no amount of further work recovers them from this APK.  A symbol that
    # resolved to nothing at all is an unrecognised variant name, which a wider
    # suffix census could still resolve.
    missing_records: dict[str, int] = {}
    unresolved_symbols: dict[str, int] = {}
    unresolved_stages: set[tuple[int, int]] = set()
    missing_record_chapters: set[int] = set()
    for stage in encounters["stages"]:
        required = {"chapter", "section", "resolved", "exact", "spawns"}
        if not isinstance(stage, dict) or not required <= set(stage) or type(stage["chapter"]) is not int or type(stage["section"]) is not int:
            raise StoryOutcomeGeneratorError("native encounter map has an invalid stage")
        identity = (stage["chapter"], stage["section"])
        counts: dict[int, int] = {}
        inferred = False
        complete = True
        for spawn in stage["spawns"]:
            if not isinstance(spawn, dict) or type(spawn.get("count")) is not int or type(spawn.get("exact")) is not bool or not isinstance(spawn.get("symbol"), str):
                raise StoryOutcomeGeneratorError("native encounter map has an invalid spawn")
            enemy_id = spawn.get("enemy_id")
            if type(enemy_id) is not int:
                complete = False
                unresolved_symbols[spawn["symbol"]] = unresolved_symbols.get(spawn["symbol"], 0) + spawn["count"]
                continue
            if enemy_id not in enemy_drops:
                complete = False
                missing_records[spawn["symbol"]] = missing_records.get(spawn["symbol"], 0) + spawn["count"]
                missing_record_chapters.add(identity[0])
                continue
            if not spawn["exact"]:
                if exact_only:
                    complete = False
                    continue
                inferred = True
            companion_id = enemy_drops[enemy_id]
            if companion_id:
                counts[companion_id] = counts.get(companion_id, 0) + spawn["count"]
        if not complete:
            unresolved_stages.add(identity)
            continue
        maxima[identity] = counts
        if inferred and counts:
            inferred_stages.add(identity)
    report = {
        "stages_in_map": len(encounters["stages"]),
        "stages_joined": len(maxima),
        "stages_unjoinable": len(unresolved_stages),
        "stages_with_inferred_ceiling": len(inferred_stages),
        "symbols_without_enemy_record": len(missing_records),
        "spawns_without_enemy_record": sum(missing_records.values()),
        "chapters_without_enemy_record": sorted(missing_record_chapters),
        "unrecognised_symbols": len(unresolved_symbols),
        "spawns_from_unrecognised_symbols": sum(unresolved_symbols.values()),
        "chapters_unjoinable": sorted({chapter for chapter, _ in unresolved_stages}),
    }
    return maxima, report


def build_catalog(
    encounters: dict[str, Any],
    battledata: dict[str, Any],
    enemy_data: dict[str, Any],
    characters: dict[str, Any],
    baseline: dict[str, Any] | None = None,
    exact_only: bool = False,
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    """Return ``(catalog, join report, notes)`` for the supplied local inputs."""
    character_ids = sorted({
        entry["character_id"]
        for entry in characters.get("characters", []) if isinstance(entry, dict) and type(entry.get("character_id")) is int and entry["character_id"] > 0
    })
    if not character_ids:
        raise StoryOutcomeGeneratorError("character catalog contains no character IDs")
    recovered_companions = {row[0] for row in COMPANION_MASTER_ROWS}

    section_maxima = section_companion_maxima(battledata)
    native_maxima, report = native_companion_maxima(encounters, companion_drops_by_enemy(enemy_data), exact_only)

    baseline_rules: dict[tuple[int, int], dict[str, Any]] = {}
    baseline_levels: dict[int, int] = {}
    capacities = {"item_slots": BUNDLED_ITEM_SLOTS, "max_stack": BUNDLED_MAX_STACK, "max_companions": MAX_COMPANIONS}
    if baseline is not None:
        for rule in baseline.get("stages", []) if isinstance(baseline.get("stages"), list) else []:
            if isinstance(rule, dict) and type(rule.get("chapter")) is int and type(rule.get("section")) is int:
                baseline_rules[(rule["chapter"], rule["section"])] = rule
        for master in baseline.get("companion_masters", []) if isinstance(baseline.get("companion_masters"), list) else []:
            if isinstance(master, dict) and type(master.get("companion_id")) is int and type(master.get("drop_level")) is int:
                baseline_levels[master["companion_id"]] = master["drop_level"]
        for name in capacities:
            if type(baseline.get(name)) is int and baseline[name] > 0:
                capacities[name] = baseline[name]

    notes: list[str] = []
    unknown_companions: set[int] = set()
    stages: list[dict[str, Any]] = []
    used_companions: set[int] = set()
    for identity in sorted(section_maxima):
        merged: dict[int, int] = {}
        for source in (section_maxima[identity], native_maxima.get(identity, {})):
            for companion_id, cap in source.items():
                if companion_id not in recovered_companions:
                    unknown_companions.add(companion_id)
                    continue
                merged[companion_id] = max(merged.get(companion_id, 0), cap)
        baseline_rule = baseline_rules.get(identity, {})
        for companion_id, cap in _maxima(baseline_rule.get("companion_maxima", {})).items():
            merged[companion_id] = max(merged.get(companion_id, 0), cap)
        used_companions |= set(merged)
        stages.append({
            "chapter": identity[0],
            "section": identity[1],
            "item_maxima": _maxima_document(baseline_rule.get("item_maxima", {}), capacities["item_slots"]),
            "character_maxima": _maxima_document(baseline_rule.get("character_maxima", {}), None, set(character_ids)),
            "companion_maxima": {str(key): merged[key] for key in sorted(merged)},
        })
    if unknown_companions:
        notes.append(
            f"{len(unknown_companions)} Companion ID(s) in the recovered drop data are absent from this "
            "release's Companion master table and were omitted from every ceiling"
        )
    if not used_companions:
        raise StoryOutcomeGeneratorError("no stage resolved a single Companion drop; check the inputs")

    catalog = {
        "schema_version": SCHEMA_VERSION,
        "provenance": "user-supplied",
        "character_ids": character_ids,
        **capacities,
        "companion_masters": [
            {"companion_id": companion_id, "drop_level": baseline_levels.get(companion_id, DEFAULT_COMPANION_DROP_LEVEL)}
            for companion_id in sorted(used_companions | set(baseline_levels))
        ],
        "stages": stages,
    }
    report["stages_written"] = len(stages)
    report["core_stages_with_companion_ceiling"] = sum(
        1 for stage in stages if stage["companion_maxima"] and stage["chapter"] in CORE_CHAPTERS
    )
    report["companion_ceiling_pairs"] = sum(len(stage["companion_maxima"]) for stage in stages)
    report["distinct_companions"] = len(used_companions)
    return catalog, report, notes


def _maxima(value: object) -> dict[int, int]:
    if not isinstance(value, dict):
        raise StoryOutcomeGeneratorError("baseline maxima must be objects")
    result: dict[int, int] = {}
    for raw_id, count in value.items():
        if not isinstance(raw_id, str) or not raw_id.isdecimal() or type(count) is not int or count < 1:
            raise StoryOutcomeGeneratorError("baseline maxima require decimal IDs and positive counts")
        result[int(raw_id)] = count
    return result


def _maxima_document(value: object, ceiling: int | None, allowed: set[int] | None = None) -> dict[str, int]:
    parsed = _maxima(value)
    for key in parsed:
        if key <= 0 or (ceiling is not None and key > ceiling) or (allowed is not None and key not in allowed):
            raise StoryOutcomeGeneratorError(f"baseline maxima reference an out-of-range ID: {key}")
    return {str(key): parsed[key] for key in sorted(parsed)}


def write_catalog(path: Path, document: dict[str, Any]) -> None:
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


def _chapters(values: list[int]) -> str:
    return ", ".join(str(value) for value in values) if values else "none"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apk", required=True, type=Path, help="your own reviewed APK")
    parser.add_argument("--dummy-dll-dir", required=True, type=Path, help="locally generated DummyDll directory")
    parser.add_argument("--native-encounters", required=True, type=Path, help="native_encounter_importer output")
    parser.add_argument("--character-catalog", required=True, type=Path, help="local character catalog")
    parser.add_argument("--baseline", type=Path, help="operator-authored story-outcome catalog to widen")
    parser.add_argument("--exact-only", action="store_true", help="drop ceilings that rest on an inferred variant")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--force", action="store_true", help="overwrite an existing output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.output.exists() and not args.force:
        raise SystemExit(f"refusing to overwrite {args.output} without --force")
    try:
        trees = load_master_trees(args.apk.resolve(strict=True), args.dummy_dll_dir, ("BattleData", "EnemyData"))
        catalog, report, notes = build_catalog(
            _read(args.native_encounters, "native encounter map"),
            trees["BattleData"],
            trees["EnemyData"],
            _read(args.character_catalog, "character catalog"),
            None if args.baseline is None else _read(args.baseline, "baseline story-outcome catalog"),
            args.exact_only,
        )
        write_catalog(args.output, catalog)
        load_story_outcome_catalog(args.output)
    except (CharacterCatalogImportError, StoryOutcomeGeneratorError, StoryOutcomeCatalogError, OSError) as error:
        raise SystemExit(f"story-outcome catalog generation failed: {error}") from error
    print(f"wrote {report['stages_written']} stage rule(s) -> {args.output}")
    print(
        f"  {report['core_stages_with_companion_ceiling']} ordinary story stage(s) can now mint a Companion:"
        f" {report['companion_ceiling_pairs']} stage/Companion pair(s), {report['distinct_companions']} distinct Companion(s)"
    )
    print(
        f"  native map: {report['stages_joined']}/{report['stages_in_map']} stages joined,"
        f" {report['stages_with_inferred_ceiling']} of those resting on an inferred variant"
    )
    if report["stages_unjoinable"]:
        print(
            f"  {report['stages_unjoinable']} stage(s) could not be joined and keep only their own"
            f" BattleData allowlist (chapters {_chapters(report['chapters_unjoinable'])}):"
        )
        print(
            f"    {report['symbols_without_enemy_record']} symbol(s) covering"
            f" {report['spawns_without_enemy_record']} spawn(s) have no EnemyData record at all"
            f" (chapters {_chapters(report['chapters_without_enemy_record'])}) -- the client shipped"
            " those chapters' scripts without their enemy rows, so this is permanent, not a fault here"
        )
        print(
            f"    {report['unrecognised_symbols']} symbol(s) covering"
            f" {report['spawns_from_unrecognised_symbols']} spawn(s) are variant names with no"
            " recognised base enemy"
        )
    print("  item_maxima and character_maxima are empty: no per-stage item or character drop table is recovered.")
    for note in notes:
        print(f"  note: {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
