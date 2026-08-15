"""Compose a local Archive, Tower, and Eidolon catalog from BattleData.

Guided setup runs this composition automatically because event character grants
are checked against the user's own recovered character catalog rather than
asserted by this repository.  That boundary remains deliberate: the generator
reads the user's BattleData import for section economics and their character
catalog for grant validation, and contributes only the recovered manifest
identities from :mod:`liminal_gate.event_manifest_data`. The command-line form
remains available for inspection and explicit catalog overrides.

The event chapters sit in BattleData alongside the main story, and
`battledata_importer` reads their entry stamina, Coins, and required items
exactly as it does ordinary stages. Only banner-backed Eidolon sections with
actual battles are projected. Older co-op reward records are not moved onto
those solo stages without a matching result-path capture.

Usage:

    python3 -m liminal_gate.event_catalog_generator \\
        --battledata user-data/battledata.json \\
        --character-catalog user-data/character-catalog.json \\
        --output user-data/event-catalog.json

The output is written for `--event-catalog` and is validated by
`load_event_catalog` on the way in, so a catalog this produces either loads or
tells you why it does not.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from liminal_gate.event_catalog import EventCatalogError, load_event_catalog
from liminal_gate.event_flag_data import event_flags_for
from liminal_gate.event_manifest_data import (
    ARCHIVE_SECTION_ALLOWLIST,
    EIDOLON_MANIFEST_ROWS,
    EIDOLON_PLAYABLE_SECTIONS,
    EVENT_CLEAR_COINS,
    EVENT_MANIFEST_ROWS,
    MELTING_POT_MANIFEST_ROWS,
    MELTING_POT_SECTIONS,
    FOLDED_ARCHIVE_CHAPTERS,
    SECTION_FLAGGED_FOLDED_CHAPTERS,
    STANDING_SPECIAL_MANIFEST_ROWS,
    STANDING_SPECIAL_SECTION_ALLOWLIST,
    TOWER_MANIFEST_ROWS,
    folded_card_chapter,
)
from liminal_gate.atomic_json import write_json_document


class EventCatalogGeneratorError(ValueError):
    """The supplied local inputs cannot produce an event catalog."""


def _read(path: Path, what: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EventCatalogGeneratorError(f"could not read {what}: {path}") from error


def build_catalog(battledata: dict[str, Any], characters: dict[str, Any], character_catalog_path: Path) -> tuple[dict[str, Any], list[str]]:
    """Return (catalog document, human-readable notes about what was omitted)."""
    stages_by_chapter: dict[int, list[dict[str, Any]]] = {}
    for stage in battledata.get("stages", []) if isinstance(battledata.get("stages"), list) else []:
        if isinstance(stage, dict) and type(stage.get("chapter")) is int:
            stages_by_chapter.setdefault(stage["chapter"], []).append(stage)
    if not stages_by_chapter:
        raise EventCatalogGeneratorError("BattleData import contains no stages")

    known_ids = {
        entry.get("character_id")
        for entry in characters.get("characters", [])
        if isinstance(entry, dict)
    }

    notes: list[str] = []
    rows: list[dict[str, Any]] = []

    def row(event_id: str, flag: str, chapter: int, unlock_after: int, section: dict[str, Any], **extra: Any) -> dict[str, Any]:
        """One stage row: the shared economics plus each family's own fields.

        The flag check lives here so no family can emit a row whose recovered
        flag cannot gate its stage.
        """
        number = section["section"]
        if flag not in event_flags_for(chapter, number):
            raise EventCatalogGeneratorError(
                f"{event_id}: recovered flag {flag!r} cannot gate {chapter}-{number}"
            )
        entry_item_id = section.get("entry_item_id", 0)
        entry_item_count = section.get("entry_item_count", 0)
        if (
            type(entry_item_id) is not int
            or type(entry_item_count) is not int
            or entry_item_id < 0
            or entry_item_count < 0
        ):
            raise EventCatalogGeneratorError(
                f"{event_id}: invalid entry item for {chapter}-{number}"
            )
        if bool(entry_item_id) != bool(entry_item_count):
            raise EventCatalogGeneratorError(
                f"{event_id}: incomplete entry item for {chapter}-{number}"
            )
        entry_item = (
            {
                "entry_item_id": entry_item_id,
                "entry_item_count": entry_item_count,
            }
            if entry_item_id
            else {}
        )
        return {
            "event_id": event_id,
            "flag": flag,
            "chapter": chapter,
            "section": number,
            "stamina": int(section.get("stamina", 0)),
            "coins": int(section.get("coins", 0)),
            "clear_coins": EVENT_CLEAR_COINS,
            "unlock_after_chapter": unlock_after,
            **entry_item,
            **extra,
        }

    for event_id, flag, chapter, unlock_after, character_ids in EVENT_MANIFEST_ROWS:
        sections = sorted(stages_by_chapter.get(chapter, []), key=lambda value: value["section"])
        allowed_sections = ARCHIVE_SECTION_ALLOWLIST.get(chapter)
        if allowed_sections is not None:
            sections = [
                section for section in sections
                if section["section"] in allowed_sections
            ]
        if not sections:
            notes.append(f"{event_id}: chapter {chapter} absent from the BattleData import; skipped")
            continue

        granted = [value for value in character_ids if value in known_ids]
        missing = [value for value in character_ids if value not in known_ids]
        if missing:
            notes.append(
                f"{event_id}: character {', '.join(str(value) for value in missing)} "
                "not in the local character catalog; grant omitted"
            )

        card_chapter = folded_card_chapter(chapter)
        for section in sections:
            number = section["section"]
            rows.append(row(
                event_id,
                # A chapter that folds while withholding sections carries its
                # own section flag, never the chapter flag that would also open
                # what it withholds. See `SECTION_FLAGGED_FOLDED_CHAPTERS`.
                event_flags_for(chapter, number)[1]
                if chapter in SECTION_FLAGGED_FOLDED_CHAPTERS
                else flag,
                chapter, unlock_after, section,
                # The permanent archive cadence declared beside the recovered
                # identities, not a recovered historical schedule.
                selector_id=(
                    str(card_chapter)
                    if card_chapter != chapter or chapter in FOLDED_ARCHIVE_CHAPTERS
                    else f"{chapter}-{number}"
                ),
                # Grants ride the first section only; repeating them per section
                # would grant the character once per stage rather than once.
                character_ids=granted if number == sections[0]["section"] else [],
            ))

    for event_id, flag, chapter, unlock_after in TOWER_MANIFEST_ROWS:
        sections = sorted(stages_by_chapter.get(chapter, []), key=lambda value: value["section"])
        if not sections:
            notes.append(f"{event_id}: chapter {chapter} absent from the BattleData import; skipped")
            continue
        for section in sections:
            # A row per tier, not one card per boss. The client has no
            # `sectionNumOfFoldedQuests` entry for 9000--9003, so a folded card
            # here would expand into a single tier and strand the two above it;
            # see `client_folded_section_count`.
            rows.append(row(event_id, flag, chapter, unlock_after, section, character_ids=[]))

    for event_id, chapter, unlock_after in STANDING_SPECIAL_MANIFEST_ROWS:
        sections = sorted(stages_by_chapter.get(chapter, []), key=lambda value: value["section"])
        allowed = STANDING_SPECIAL_SECTION_ALLOWLIST.get(chapter)
        if allowed is not None:
            sections = [section for section in sections if section["section"] in allowed]
        if not sections:
            notes.append(f"{event_id}: chapter {chapter} absent from the BattleData import; skipped")
            continue
        for section in sections:
            number = section["section"]
            rows.append(row(
                # The exact section flag, not the chapter fallback. These are
                # advertised as one card per section, and a chapter-level flag
                # would also open the sections this manifest deliberately
                # withholds for want of a retained banner.
                event_id, f"sp_ch_{chapter}-{number}", chapter, unlock_after, section,
                character_ids=[],
            ))

    for event_id, flag, chapter, unlock_after in MELTING_POT_MANIFEST_ROWS:
        sections = sorted(stages_by_chapter.get(chapter, []), key=lambda value: value["section"])
        if not sections:
            notes.append(f"{event_id}: chapter {chapter} absent from the BattleData import; skipped")
            continue
        if len(sections) != MELTING_POT_SECTIONS:
            raise EventCatalogGeneratorError(
                f"{event_id}: expected {MELTING_POT_SECTIONS} BattleData sections in chapter "
                f"{chapter}, found {len(sections)}"
            )
        for section in sections:
            rows.append(row(
                event_id, flag, chapter, unlock_after, section,
                character_ids=[],
                # One folded card per chapter: the client already knows these
                # chapters hold fifteen sections and expands them itself.
                selector_id=str(chapter),
            ))

    for event_id, flag, chapter, unlock_after, drops in EIDOLON_MANIFEST_ROWS:
        imported = sorted(stages_by_chapter.get(chapter, []), key=lambda value: value["section"])
        if not imported:
            notes.append(f"{event_id}: chapter {chapter} absent from the BattleData import; skipped")
            continue
        expected_section = EIDOLON_PLAYABLE_SECTIONS[chapter]
        battle_sections = {
            section["section"]
            for section in imported
            if section.get("has_battle") is True
        }
        if battle_sections != {expected_section}:
            raise EventCatalogGeneratorError(
                f"{event_id}: expected playable BattleData section "
                f"{chapter}-{expected_section}, found "
                f"{', '.join(f'{chapter}-{value}' for value in sorted(battle_sections)) or 'none'}"
            )
        sections = [
            section for section in imported
            if section["section"] == expected_section
        ]
        drops_by_section = dict(drops)
        for section in sections:
            number = section["section"]
            rows.append(row(
                event_id, flag, chapter, unlock_after, section,
                character_ids=[],
                summon_ids=[drops_by_section[number]] if number in drops_by_section else [],
            ))

    if not rows:
        raise EventCatalogGeneratorError("no event chapter in the manifest set is present in this BattleData import")

    return {
        "schema_version": 1,
        "provenance": "user-supplied",
        "character_catalog_sha256": hashlib.sha256(character_catalog_path.read_bytes()).hexdigest(),
        "stages": rows,
    }, notes


def write_catalog(path: Path, document: dict[str, Any]) -> None:
    """Atomically write a generated catalog beside the other local projections."""
    write_json_document(path, document, indent=1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--battledata", type=Path, required=True, help="battledata_importer output")
    parser.add_argument("--character-catalog", type=Path, required=True, help="local character catalog")
    parser.add_argument("--output", type=Path, required=True, help="event catalog to write")
    parser.add_argument("--force", action="store_true", help="overwrite an existing output")
    args = parser.parse_args()

    if args.output.exists() and not args.force:
        raise SystemExit(f"refusing to overwrite {args.output} without --force")
    try:
        catalog, notes = build_catalog(
            _read(args.battledata, "BattleData import"),
            _read(args.character_catalog, "character catalog"),
            args.character_catalog,
        )
    except EventCatalogGeneratorError as error:
        raise SystemExit(f"event catalog generation failed: {error}") from error

    write_catalog(args.output, catalog)
    try:
        load_event_catalog(args.output, args.character_catalog)
    except (EventCatalogError, OSError) as error:
        raise SystemExit(f"event catalog generation failed: {error}") from error
    events = len({row["event_id"] for row in catalog["stages"]})
    print(f"wrote {len(catalog['stages'])} stages across {events} event(s) -> {args.output}")
    for note in notes:
        print(f"  note: {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
