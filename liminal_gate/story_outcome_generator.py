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

Item and character ceilings
---------------------------

``StoryOutcomeRule`` also carries ``item_maxima`` and ``character_maxima``, and
an empty ceiling *forbids* the outcome rather than permitting it.  Both are
therefore derived here rather than left empty, from the same per-enemy records
the Companion ceiling already reads:

* **Items** come from ``EnemyParams.items``, a four-slot ``ItemCode`` array in
  which ``code >> 8`` is the item and ``code & 0xFF`` the count.  845 of the
  recovered enemy records carry at least one.  There is no per-item ratio, so
  every item an enemy names contributes a ceiling.
* **Characters** come from ``EnemyParams.DropJobID``, which names a
  ``ChrJobParams`` row whose ``chrID`` is the character the client actually
  recruits -- the monster drop ``AddDropMon`` records.  A zero ``DropRatio``
  never rolls and contributes nothing, matching how the Companion ceiling reads
  its own ratio.

A stage the native map cannot join still has no item or character evidence, and
its ceilings stay empty.  The run report counts those stages so an operator
opting into strict validation can see exactly where a clear reporting an item or
a recruited monster would be refused, and ``--baseline`` carries an
operator-authored catalog through unchanged while the recovered ceilings are
unioned on top.

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

from liminal_gate.character_catalog_importer import CharacterCatalogImportError, SOURCE_PROFILE, load_master_trees, sha256_file
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


def _valid_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _native_source(source: object) -> dict[str, str]:
    required = {
        "profile",
        "abi",
        "apk_sha256",
        "dump_cs_sha256",
        "libil2cpp_sha256",
        "objdump",
        "vtable_calibration",
    }
    if (
        not isinstance(source, dict)
        or set(source) != required
        or source.get("profile") != SOURCE_PROFILE
        or source.get("abi") != "arm64"
        or not all(
            _valid_sha256(source.get(field))
            for field in ("apk_sha256", "dump_cs_sha256", "libil2cpp_sha256")
        )
        or not isinstance(source.get("objdump"), str)
        or not source["objdump"]
        or source.get("vtable_calibration") not in {"verified", "unverified"}
    ):
        raise StoryOutcomeGeneratorError(
            "input must be a user-derived ARM64 native encounter map with complete source provenance"
        )
    return {field: source[field] for field in sorted(required)}


def _scenario_source(source: object) -> dict[str, Any]:
    """Validate a MoonSharp scenario encounter map's provenance.

    Deliberately not `_native_source` with fields relaxed.  A scenario map is
    derived from the client's embedded ``Chapter{N}`` MoonSharp binary dumps, so
    it has no ABI, no ``libil2cpp`` hash, and no vtable calibration to report,
    and inventing those fields to satisfy one shared validator would make a
    scenario row indistinguishable from a disassembled one.  What it must
    account for instead is which chapter assets it read: ``chapter_sha256`` maps
    each chapter number to the hash of the decoded listing it came from.
    """
    required = {"profile", "apk_sha256", "format", "decoder", "chapter_sha256"}
    if (
        not isinstance(source, dict)
        or set(source) != required
        or source.get("profile") != SOURCE_PROFILE
        or not _valid_sha256(source.get("apk_sha256"))
        or source.get("format") != "moonsharp-binary-dump"
        or not isinstance(source.get("decoder"), str)
        or not source["decoder"]
        or not isinstance(source.get("chapter_sha256"), dict)
        or not source["chapter_sha256"]
        or not all(
            isinstance(chapter, str) and chapter.isdecimal() and _valid_sha256(digest)
            for chapter, digest in source["chapter_sha256"].items()
        )
    ):
        raise StoryOutcomeGeneratorError(
            "input must be a user-derived MoonSharp scenario encounter map with complete source provenance"
        )
    return {
        "profile": source["profile"],
        "apk_sha256": source["apk_sha256"],
        "format": source["format"],
        "decoder": source["decoder"],
        "chapter_sha256": {key: source["chapter_sha256"][key] for key in sorted(source["chapter_sha256"])},
    }


def build_derivation_source(
    encounters: dict[str, Any],
    characters: dict[str, Any],
    apk_sha256: str,
    native_encounters_sha256: str,
    character_catalog_sha256: str,
    baseline_sha256: str | None = None,
    scenario: dict[str, Any] | None = None,
    scenario_encounters_sha256: str | None = None,
) -> dict[str, Any]:
    """Validate that all derived inputs belong to one APK and retain their hashes."""
    native = _native_source(encounters.get("source"))
    character_source = characters.get("source")
    if (
        not _valid_sha256(apk_sha256)
        or not _valid_sha256(native_encounters_sha256)
        or not _valid_sha256(character_catalog_sha256)
        or (
            baseline_sha256 is not None
            and not _valid_sha256(baseline_sha256)
        )
        or not isinstance(character_source, dict)
        or set(character_source) != {"profile", "apk_sha256"}
        or character_source.get("profile") != SOURCE_PROFILE
        or not _valid_sha256(character_source.get("apk_sha256"))
    ):
        raise StoryOutcomeGeneratorError(
            "story-outcome inputs have incomplete or invalid source provenance"
        )
    if native["apk_sha256"] != apk_sha256:
        raise StoryOutcomeGeneratorError(
            "native encounter map was derived from a different APK"
        )
    if character_source["apk_sha256"] != apk_sha256:
        raise StoryOutcomeGeneratorError(
            "character catalog was derived from a different APK"
        )
    result: dict[str, Any] = {
        "profile": SOURCE_PROFILE,
        "apk_sha256": apk_sha256,
        "native_encounters_sha256": native_encounters_sha256,
        "character_catalog_sha256": character_catalog_sha256,
        "native_encounters": native,
    }
    if baseline_sha256 is not None:
        result["baseline_sha256"] = baseline_sha256
    if scenario is not None:
        scenario_source = _scenario_source(scenario.get("source"))
        if scenario_source["apk_sha256"] != apk_sha256:
            raise StoryOutcomeGeneratorError(
                "scenario encounter map was derived from a different APK"
            )
        if not _valid_sha256(scenario_encounters_sha256):
            raise StoryOutcomeGeneratorError(
                "story-outcome inputs have incomplete or invalid source provenance"
            )
        result["scenario_encounters_sha256"] = scenario_encounters_sha256
        result["scenario_encounters"] = scenario_source
    return result


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


def item_drops_by_enemy(tree: dict[str, Any]) -> dict[int, dict[int, int]]:
    """Map each enemy record ID to the items it can drop.

    ``EnemyParams.items`` is a four-slot ``ItemCode`` array where ``code >> 8``
    is the item and a zero code is an empty slot.

    The low byte is a **drop rate, not a stack count**.  Across the recovered
    table it takes 24 distinct values spanning 0 to 100, including 100 itself 21
    times and 80, 57, and 52 in between; no enemy carries a hundred copies of an
    item, and 100 is a guaranteed drop.  Reading it as a count multiplied every
    ceiling by the drop rate, which produced numbers that permitted far more than
    the stage could yield.  It is read here the same way `DropBuddyRatio` is: a
    rate above zero means the enemy can drop the item, and each such enemy
    contributes one to the ceiling.
    """
    rows = tree.get("data")
    if not isinstance(rows, list) or not rows:
        raise StoryOutcomeGeneratorError("EnemyData must contain a nonempty data array")
    drops: dict[int, dict[int, int]] = {}
    for row in rows:
        if not isinstance(row, dict) or type(row.get("ID")) is not int:
            raise StoryOutcomeGeneratorError("EnemyData record has missing required fields")
        slots = row.get("items")
        if not isinstance(slots, list):
            raise StoryOutcomeGeneratorError("EnemyData record has an invalid items array")
        carried: dict[int, int] = {}
        for slot in slots:
            if not isinstance(slot, dict) or type(slot.get("code")) is not int or slot["code"] < 0:
                raise StoryOutcomeGeneratorError("EnemyData item slot has an invalid code")
            code = slot["code"]
            if not code:
                continue
            item_id, rate = code >> 8, code & 0xFF
            if item_id <= 0 or rate <= 0:
                # A zero rate never rolls, exactly as a zero `DropBuddyRatio`
                # contributes no Companion ceiling.
                continue
            carried[item_id] = 1
        drops[row["ID"]] = carried
    return drops


def character_drops_by_enemy(enemy_tree: dict[str, Any], chr_tree: dict[str, Any]) -> dict[int, int]:
    """Map each enemy record ID to the character it can be recruited as.

    ``EnemyParams.DropJobID`` names a ``ChrJobParams`` row, and that row's
    ``chrID`` is the character the client actually adds -- the monster-recruit
    drop that `AddDropMon` records.  A zero ``DropRatio`` never rolls, matching
    how the Companion ceiling already reads its own ratio.
    """
    jobs = chr_tree.get("data")
    if not isinstance(jobs, list) or not jobs:
        raise StoryOutcomeGeneratorError("ChrDatabase must contain a nonempty data array")
    character_by_job: dict[int, int] = {}
    for job in jobs:
        if not isinstance(job, dict) or type(job.get("ID")) is not int or type(job.get("chrID")) is not int:
            raise StoryOutcomeGeneratorError("ChrJobParams row has an invalid ID or chrID")
        character_by_job[job["ID"]] = job["chrID"]

    rows = enemy_tree.get("data")
    if not isinstance(rows, list) or not rows:
        raise StoryOutcomeGeneratorError("EnemyData must contain a nonempty data array")
    drops: dict[int, int] = {}
    for row in rows:
        fields = ("ID", "DropJobID", "DropRatio")
        if not isinstance(row, dict) or any(field not in row for field in fields):
            raise StoryOutcomeGeneratorError("EnemyData record has missing required fields")
        if type(row["DropJobID"]) is not int or not isinstance(row["DropRatio"], (int, float)):
            raise StoryOutcomeGeneratorError("EnemyData record has invalid Job drop fields")
        job_id = row["DropJobID"]
        drops[row["ID"]] = character_by_job.get(job_id, 0) if job_id > 0 and row["DropRatio"] > 0 else 0
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


def native_stage_maxima(
    encounters: dict[str, Any],
    enemy_drops: dict[int, int],
    enemy_items: dict[int, dict[int, int]],
    enemy_characters: dict[int, int],
    exact_only: bool,
) -> tuple[dict[tuple[int, int], dict[str, dict[int, int]]], dict[str, Any]]:
    """Join the native encounter map to the per-enemy Companion, item, and character drops."""
    if (
        encounters.get("schema_version") != 1
        or encounters.get("provenance") != "user-derived"
        or not isinstance(encounters.get("stages"), list)
        or not encounters["stages"]
    ):
        raise StoryOutcomeGeneratorError("input must be a user-derived ARM64 native encounter map")
    _native_source(encounters.get("source"))
    return _stage_maxima(encounters["stages"], enemy_drops, enemy_items, enemy_characters, exact_only)


def scenario_stage_maxima(
    encounters: dict[str, Any],
    enemy_drops: dict[int, int],
    enemy_items: dict[int, dict[int, int]],
    enemy_characters: dict[int, int],
    exact_only: bool,
) -> tuple[dict[tuple[int, int], dict[str, dict[int, int]]], dict[str, Any]]:
    """Join the MoonSharp scenario encounter map to the same per-enemy drops.

    Chapters 2--7 have no compiled chapter battle program at all: their
    encounters are placed by the scenario scripts the client runs on its
    embedded MoonSharp VM, so the native import cannot see them and every one of
    their stages ends up with an empty item and character ceiling.  This is the
    same join against a map derived from those scripts instead.

    The stage schema is deliberately identical to the native map's.  What
    differs is provenance, which is why the two are separate inputs rather than
    one file an operator concatenates: a scenario-derived row must not be able
    to claim it came from a disassembled chapter program.
    """
    if (
        encounters.get("schema_version") != 1
        or encounters.get("provenance") != "user-derived"
        or not isinstance(encounters.get("stages"), list)
        or not encounters["stages"]
    ):
        raise StoryOutcomeGeneratorError("input must be a user-derived MoonSharp scenario encounter map")
    _scenario_source(encounters.get("source"))
    return _stage_maxima(encounters["stages"], enemy_drops, enemy_items, enemy_characters, exact_only)


def _stage_maxima(
    stages_input: list[Any],
    enemy_drops: dict[int, int],
    enemy_items: dict[int, dict[int, int]],
    enemy_characters: dict[int, int],
    exact_only: bool,
) -> tuple[dict[tuple[int, int], dict[str, dict[int, int]]], dict[str, Any]]:
    """Join one encounter map's stages to the per-enemy drop records.

    A stage contributes only when *every* one of its spawns resolves to an
    enemy record.  A partly-joined stage would understate its own ceiling, and
    understating a ceiling refuses a legitimate clear, so it is left to the
    section allowlist instead.
    """
    encounters = {"stages": stages_input}
    maxima: dict[tuple[int, int], dict[str, dict[int, int]]] = {}
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
        item_counts: dict[int, int] = {}
        character_counts: dict[int, int] = {}
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
            for item_id in enemy_items.get(enemy_id, {}):
                # One per enemy able to drop it, the same rule the Companion
                # ceiling uses. The recovered table states a rate, not a count.
                item_counts[item_id] = item_counts.get(item_id, 0) + spawn["count"]
            character_id = enemy_characters.get(enemy_id, 0)
            if character_id:
                character_counts[character_id] = character_counts.get(character_id, 0) + spawn["count"]
        if not complete:
            unresolved_stages.add(identity)
            continue
        maxima[identity] = {"companions": counts, "items": item_counts, "characters": character_counts}
        if inferred and (counts or item_counts or character_counts):
            inferred_stages.add(identity)
    report = {
        "stages_in_map": len(encounters["stages"]),
        "stages_joined": len(maxima),
        "stages_with_item_ceiling": sum(1 for value in maxima.values() if value["items"]),
        "stages_with_character_ceiling": sum(1 for value in maxima.values() if value["characters"]),
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
    chr_database: dict[str, Any],
    characters: dict[str, Any],
    baseline: dict[str, Any] | None = None,
    exact_only: bool = False,
    source: dict[str, Any] | None = None,
    scenario: dict[str, Any] | None = None,
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
    companion_drops = companion_drops_by_enemy(enemy_data)
    item_drops = item_drops_by_enemy(enemy_data)
    character_drops = character_drops_by_enemy(enemy_data, chr_database)
    native_maxima, report = native_stage_maxima(
        encounters, companion_drops, item_drops, character_drops, exact_only,
    )
    if scenario is None:
        report["scenario_stages_joined"] = 0
        report["scenario_chapters"] = []
    else:
        scenario_maxima, scenario_report = scenario_stage_maxima(
            scenario, companion_drops, item_drops, character_drops, exact_only,
        )
        # The scenario map covers chapters the native map does not reach at all,
        # so the two never disagree about a stage in practice.  Merge by the
        # larger ceiling anyway, which is the rule every other source pair here
        # already follows: a ceiling permits, so taking the smaller one would
        # refuse a clear one of the two sources says is legitimate.
        for identity, value in scenario_maxima.items():
            existing = native_maxima.get(identity)
            if existing is None:
                native_maxima[identity] = value
                continue
            for kind in ("companions", "items", "characters"):
                merged = dict(existing[kind])
                for key, cap in value[kind].items():
                    merged[key] = max(merged.get(key, 0), cap)
                existing[kind] = merged
        report["scenario_stages_joined"] = len(scenario_maxima)
        report["scenario_chapters"] = sorted({chapter for chapter, _ in scenario_maxima})
        report["stages_with_item_ceiling"] = sum(1 for value in native_maxima.values() if value["items"])
        report["stages_with_character_ceiling"] = sum(1 for value in native_maxima.values() if value["characters"])

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
    unknown_characters: set[int] = set()
    used_items: set[int] = set()
    used_characters: set[int] = set()
    unevidenced: set[tuple[int, int]] = set()
    known_characters = set(character_ids)
    stages: list[dict[str, Any]] = []
    used_companions: set[int] = set()
    for identity in sorted(section_maxima):
        native_rule = native_maxima.get(identity, {})
        merged: dict[int, int] = {}
        for companion_source in (
            section_maxima[identity],
            native_rule.get("companions", {}),
        ):
            for companion_id, cap in companion_source.items():
                if companion_id not in recovered_companions:
                    unknown_companions.add(companion_id)
                    continue
                merged[companion_id] = max(merged.get(companion_id, 0), cap)
        baseline_rule = baseline_rules.get(identity, {})
        for companion_id, cap in _maxima(baseline_rule.get("companion_maxima", {})).items():
            merged[companion_id] = max(merged.get(companion_id, 0), cap)
        used_companions |= set(merged)

        # A ceiling permits; an empty one forbids. Both of these are unioned
        # from the recovered per-enemy drop data rather than left empty, so a
        # clear that legitimately reports an item or a recruited monster is
        # accepted instead of refused.
        merged_items: dict[int, int] = dict(native_rule.get("items", {}))
        # Baseline values are operator-authored, so an out-of-range ID there is
        # a mistake worth refusing; recovered values are filtered with a note.
        for key, cap in _maxima_document(baseline_rule.get("item_maxima", {}), capacities["item_slots"]).items():
            item_id = int(key)
            merged_items[item_id] = max(merged_items.get(item_id, 0), cap)
        merged_items = {
            item_id: min(cap, capacities["max_stack"])
            for item_id, cap in merged_items.items()
            if 1 <= item_id <= capacities["item_slots"]
        }
        used_items.update(merged_items)

        merged_characters: dict[int, int] = {}
        for character_id, cap in native_rule.get("characters", {}).items():
            if character_id in known_characters:
                merged_characters[character_id] = cap
            else:
                unknown_characters.add(character_id)
        for key, cap in _maxima_document(baseline_rule.get("character_maxima", {}), None, known_characters).items():
            character_id = int(key)
            merged_characters[character_id] = max(merged_characters.get(character_id, 0), cap)
        used_characters.update(merged_characters)

        # Whether anything could speak to this stage at all, which is a different
        # question from what it said.  A joined stage whose enemies carry no
        # items has a *real* empty ceiling; an unjoinable stage has none.  Both
        # are an empty dict, so the distinction has to be recorded separately or
        # the second one silently forbids ordinary play.
        joined = identity in native_maxima
        item_evidence = joined or bool(_maxima(baseline_rule.get("item_maxima", {})))
        character_evidence = joined or bool(_maxima(baseline_rule.get("character_maxima", {})))
        if not item_evidence and not character_evidence:
            unevidenced.add(identity)
        evidence = [
            name for name, present in (("items", item_evidence), ("characters", character_evidence)) if present
        ]
        stages.append({
            "chapter": identity[0],
            "section": identity[1],
            "evidence": evidence,
            "item_maxima": {str(key): merged_items[key] for key in sorted(merged_items)},
            "character_maxima": {str(key): merged_characters[key] for key in sorted(merged_characters)},
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
    if source is not None:
        catalog["source"] = source
    calibration = encounters["source"]["vtable_calibration"]
    report["vtable_calibration"] = calibration
    if calibration != "verified":
        notes.append(
            "native encounter vtable calibration is unverified for this APK; "
            "the label is retained in catalog source provenance"
        )
    report["stages_written"] = len(stages)
    report["stages_without_outcome_evidence"] = len(unevidenced)
    report["chapters_without_outcome_evidence"] = sorted({chapter for chapter, _ in unevidenced})
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
        if not isinstance(raw_id, str) or not raw_id.isdecimal() or raw_id != str(int(raw_id)) or int(raw_id) <= 0 or type(count) is not int or count < 1:
            raise StoryOutcomeGeneratorError("baseline maxima require positive decimal IDs and counts")
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
    parser.add_argument("--scenario-encounters", type=Path, help="MoonSharp scenario encounter map covering the chapters with no compiled battle program")
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
        apk = args.apk.resolve(strict=True)
        native_encounters_path = args.native_encounters.resolve(strict=True)
        character_catalog_path = args.character_catalog.resolve(strict=True)
        baseline_path = None if args.baseline is None else args.baseline.resolve(strict=True)
        scenario_path = None if args.scenario_encounters is None else args.scenario_encounters.resolve(strict=True)
        encounters = _read(native_encounters_path, "native encounter map")
        characters = _read(character_catalog_path, "character catalog")
        scenario = None if scenario_path is None else _read(scenario_path, "scenario encounter map")
        source = build_derivation_source(
            encounters,
            characters,
            sha256_file(apk),
            sha256_file(native_encounters_path),
            sha256_file(character_catalog_path),
            None if baseline_path is None else sha256_file(baseline_path),
            scenario,
            None if scenario_path is None else sha256_file(scenario_path),
        )
        trees = load_master_trees(apk, args.dummy_dll_dir, ("BattleData", "EnemyData", "ChrDatabase"))
        catalog, report, notes = build_catalog(
            encounters,
            trees["BattleData"],
            trees["EnemyData"],
            trees["ChrDatabase"],
            characters,
            None if baseline_path is None else _read(baseline_path, "baseline story-outcome catalog"),
            args.exact_only,
            source,
            scenario,
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
    if report["scenario_stages_joined"]:
        print(
            f"  scenario map: {report['scenario_stages_joined']} stage(s) joined from the MoonSharp"
            f" chapter scripts (chapters {_chapters(report['scenario_chapters'])})"
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
    print(
        f"  {report['stages_with_item_ceiling']} stage(s) carry an item ceiling and"
        f" {report['stages_with_character_ceiling']} a character ceiling, from the per-enemy drop records"
    )
    if report["stages_without_outcome_evidence"]:
        print(
            f"  {report['stages_without_outcome_evidence']} stage(s) have no item or character"
            f" evidence (chapters {_chapters(report['chapters_without_outcome_evidence'])})."
        )
        print(
            "    Each is marked unevidenced rather than left to read as a ceiling of zero, so the"
            " server leaves their reported items and recruited monsters unconstrained instead of"
            " refusing them. Pass --baseline with hand-authored maxima to bound them."
        )
        if not report["scenario_stages_joined"]:
            print(
                "    Chapters 2-7 are scripted in MoonSharp rather than natively, so the native"
                " encounter import cannot see them. Pass --scenario-encounters to cover them."
            )
    for note in notes:
        print(f"  note: {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
