"""Compose a local Archive, Tower, and Eidolon catalog from BattleData.

Guided setup runs this composition automatically because event character grants
are checked against the user's own recovered character catalog rather than
asserted by this repository.  That boundary remains deliberate: the generator
reads the user's BattleData import for section economics and their character
catalog for grant validation, and contributes only the recovered manifest
identities from :mod:`liminal_gate.event_manifest_data`. The command-line form
remains available for inspection and explicit catalog overrides.

The event chapters sit in BattleData alongside the main story, and
`battledata_importer` reads their entry stamina and start costs exactly as it
does ordinary stages. The bounded Eidolon drop identities additionally come
from reviewed native chapter-program and EnemyData analysis recorded beside
the manifest; the generator does not derive or broaden them at setup time.

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
import os
from pathlib import Path
import tempfile
from typing import Any

from liminal_gate.event_flag_data import event_flags_for
from liminal_gate.event_manifest_data import (
    EIDOLON_MANIFEST_ROWS,
    EVENT_CLEAR_COINS,
    EVENT_MANIFEST_ROWS,
    TOWER_MANIFEST_ROWS,
)


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
    for event_id, flag, chapter, unlock_after, character_ids in EVENT_MANIFEST_ROWS:
        sections = sorted(stages_by_chapter.get(chapter, []), key=lambda value: value["section"])
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

        for section in sections:
            number = section["section"]
            permitted = event_flags_for(chapter, number)
            if flag not in permitted:
                raise EventCatalogGeneratorError(
                    f"{event_id}: recovered flag {flag!r} cannot gate {chapter}-{number}"
                )
            rows.append({
                "event_id": event_id,
                "flag": flag,
                "chapter": chapter,
                "section": number,
                "stamina": int(section.get("stamina", 0)),
                "coins": int(section.get("coins", 0)),
                "clear_coins": EVENT_CLEAR_COINS,
                # This is the permanent archive cadence declared beside the
                # recovered identities, not a recovered historical schedule.
                "unlock_after_chapter": unlock_after,
                # Grants ride the first section only; repeating them per section
                # would grant the character once per stage rather than once.
                "character_ids": granted if number == sections[0]["section"] else [],
            })

    for event_id, flag, chapter, unlock_after in TOWER_MANIFEST_ROWS:
        sections = sorted(stages_by_chapter.get(chapter, []), key=lambda value: value["section"])
        if not sections:
            notes.append(f"{event_id}: chapter {chapter} absent from the BattleData import; skipped")
            continue
        for section in sections:
            number = section["section"]
            if flag not in event_flags_for(chapter, number):
                raise EventCatalogGeneratorError(
                    f"{event_id}: recovered flag {flag!r} cannot gate {chapter}-{number}"
                )
            rows.append({
                "event_id": event_id,
                "flag": flag,
                "chapter": chapter,
                "section": number,
                "stamina": int(section.get("stamina", 0)),
                "coins": int(section.get("coins", 0)),
                "clear_coins": EVENT_CLEAR_COINS,
                "unlock_after_chapter": unlock_after,
                "character_ids": [],
            })

    for event_id, flag, chapter, unlock_after, drops in EIDOLON_MANIFEST_ROWS:
        sections = sorted(stages_by_chapter.get(chapter, []), key=lambda value: value["section"])
        if not sections:
            notes.append(f"{event_id}: chapter {chapter} absent from the BattleData import; skipped")
            continue
        drops_by_section = dict(drops)
        for section in sections:
            number = section["section"]
            if flag not in event_flags_for(chapter, number):
                raise EventCatalogGeneratorError(
                    f"{event_id}: recovered flag {flag!r} cannot gate {chapter}-{number}"
                )
            rows.append({
                "event_id": event_id,
                "flag": flag,
                "chapter": chapter,
                "section": number,
                "stamina": int(section.get("stamina", 0)),
                "coins": int(section.get("coins", 0)),
                "clear_coins": EVENT_CLEAR_COINS,
                "unlock_after_chapter": unlock_after,
                "character_ids": [],
                "summon_ids": (
                    [drops_by_section[number]] if number in drops_by_section else []
                ),
            })

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
    events = len({row["event_id"] for row in catalog["stages"]})
    print(f"wrote {len(catalog['stages'])} stages across {events} event(s) -> {args.output}")
    for note in notes:
        print(f"  note: {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
