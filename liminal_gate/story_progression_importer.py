"""Derive ordered core-story progression metadata from local BattleData output."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile
from typing import Any


SCHEMA_VERSION = 1
SOURCE_PROFILE = "terra-battle-android-5.5.7-170"
CORE_CHAPTERS = range(2, 43)
_EXPECTED_SECTIONS = {
    chapter: (5 if chapter == 2 or chapter == 3 else 3 if chapter == 42 else 10)
    for chapter in CORE_CHAPTERS
}


class StoryProgressionImportError(ValueError):
    """Local BattleData metadata cannot prove the required ordered core story."""


def progress_low_bits(chapter: int, section: int) -> int:
    if chapter < 1 or section < 1 or section > 63:
        raise StoryProgressionImportError("story identity cannot be encoded in progress low bits")
    return (chapter << 6) | section


def build_story_progression(document: dict[str, Any]) -> dict[str, object]:
    """Project local BattleData metadata into successor-only core-story state."""
    if (
        document.get("schema_version") != 1
        or document.get("provenance") != "user-derived"
        or not isinstance(document.get("source"), dict)
        or document["source"].get("profile") != SOURCE_PROFILE
        or not isinstance(document.get("stages"), list)
    ):
        raise StoryProgressionImportError("input must be reviewed user-derived BattleData stage metadata")
    stages: list[dict[str, int]] = []
    for row in document["stages"]:
        required = {"chapter", "section", "stamina", "coins", "battle_count", "has_battle"}
        if not isinstance(row, dict) or set(row) != required:
            raise StoryProgressionImportError("BattleData stage metadata has an invalid schema")
        if any(type(row[name]) is not int for name in ("chapter", "section", "stamina", "coins", "battle_count")) or type(row["has_battle"]) is not bool:
            raise StoryProgressionImportError("BattleData stage metadata has invalid field types")
        if row["chapter"] in CORE_CHAPTERS:
            stages.append({name: row[name] for name in ("chapter", "section", "stamina", "coins")})
    identities = [(row["chapter"], row["section"]) for row in stages]
    if identities != sorted(identities) or len(identities) != len(set(identities)):
        raise StoryProgressionImportError("core story stages must be sorted and unique")
    counts = {chapter: sum(row["chapter"] == chapter for row in stages) for chapter in CORE_CHAPTERS}
    if counts != _EXPECTED_SECTIONS:
        raise StoryProgressionImportError("BattleData does not match the reviewed core-story section counts")
    output: list[dict[str, int | bool]] = []
    for index, row in enumerate(stages):
        successor = (43, 1) if index + 1 == len(stages) else (stages[index + 1]["chapter"], stages[index + 1]["section"])
        output.append({
            **row,
            "successor_chapter": successor[0],
            "successor_section": successor[1],
            "successor_low_progress": progress_low_bits(*successor),
            "chapter_boundary": successor[0] != row["chapter"],
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "provenance": "user-derived",
        "source": {"profile": SOURCE_PROFILE, "kind": "battledata-core-story-progression"},
        "stages": output,
    }


def write_story_progression(path: Path, document: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--battledata-stages", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        document = json.loads(args.battledata_stages.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise StoryProgressionImportError("BattleData stage metadata must be an object")
        output = build_story_progression(document)
        write_story_progression(args.output, output)
    except (OSError, json.JSONDecodeError, StoryProgressionImportError) as error:
        raise SystemExit(f"story progression import failed: {error}") from error
    print(f"wrote {len(output['stages'])} local core-story progression stages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
