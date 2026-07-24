"""Validate a source-free, operator-local event-character membership catalog."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any


class EventCharacterCatalogError(ValueError):
    """An operator-local event-character catalog is unsafe or inconsistent."""


@dataclass(frozen=True)
class EventCharacterCatalog:
    event_characters: dict[str, frozenset[int]]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_event_character_catalog(path: Path, character_catalog_path: Path) -> EventCharacterCatalog:
    """Load local memberships only when every ID exists in the local APK catalog."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        characters = json.loads(character_catalog_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EventCharacterCatalogError("could not read local event or character catalog JSON") from error
    required = {"schema_version", "provenance", "character_catalog_sha256", "events"}
    if not isinstance(document, dict) or set(document) != required or document.get("schema_version") != 1 or document.get("provenance") != "user-supplied":
        raise EventCharacterCatalogError("event-character catalog has an invalid schema or provenance")
    if document["character_catalog_sha256"] != sha256_file(character_catalog_path):
        raise EventCharacterCatalogError("event-character catalog does not match the local character catalog")
    if not isinstance(characters, dict) or characters.get("schema_version") != 1 or characters.get("provenance") != "user-derived" or not isinstance(characters.get("characters"), list):
        raise EventCharacterCatalogError("local character catalog has an invalid schema or provenance")
    local_ids = {record.get("character_id") for record in characters["characters"] if isinstance(record, dict)}
    if not local_ids or any(type(value) is not int or value <= 0 for value in local_ids):
        raise EventCharacterCatalogError("local character catalog has invalid character IDs")
    events = document["events"]
    if not isinstance(events, list) or not events:
        raise EventCharacterCatalogError("events must be a nonempty array")
    memberships: dict[str, frozenset[int]] = {}
    claimed: set[int] = set()
    for event in events:
        if not isinstance(event, dict) or set(event) != {"event_id", "character_ids"}:
            raise EventCharacterCatalogError("each event requires event_id and character_ids")
        event_id, character_ids = event["event_id"], event["character_ids"]
        if not isinstance(event_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", event_id) or event_id in memberships:
            raise EventCharacterCatalogError("event IDs must be unique lowercase identifiers")
        if not isinstance(character_ids, list) or not character_ids or any(type(value) is not int or value <= 0 for value in character_ids):
            raise EventCharacterCatalogError("event character IDs must be a nonempty positive-integer array")
        if character_ids != sorted(character_ids) or len(character_ids) != len(set(character_ids)):
            raise EventCharacterCatalogError("event character IDs must be ordered and unique")
        identifiers = frozenset(character_ids)
        if not identifiers <= local_ids:
            raise EventCharacterCatalogError("event character IDs are absent from the local character catalog")
        if claimed & identifiers:
            raise EventCharacterCatalogError("event character IDs cannot belong to multiple local events")
        memberships[event_id] = identifiers
        claimed.update(identifiers)
    return EventCharacterCatalog(memberships)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-catalog", required=True, type=Path)
    parser.add_argument("--character-catalog", required=True, type=Path)
    args = parser.parse_args()
    try:
        catalog = load_event_character_catalog(args.event_catalog, args.character_catalog)
    except EventCharacterCatalogError as error:
        raise SystemExit(f"event-character catalog validation failed: {error}") from error
    print(f"validated {len(catalog.event_characters)} local event membership entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
