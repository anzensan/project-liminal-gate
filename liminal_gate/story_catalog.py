"""Validate a user-local normalized main-story stage catalog.

The catalog is deliberately an input contract, not bundled game data.  It
contains only the stage identity and local-server validation values required by
the future generic-story boundary; users create and retain it locally.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path


STORY_CATALOG_SCHEMA_VERSION = 1


class StoryCatalogError(ValueError):
    """A user-local story catalog does not meet the narrow input contract."""


@dataclass(frozen=True)
class StoryStage:
    chapter: int
    section: int
    stamina: int
    coins: int
    clear_progress_code: int
    clear_coins: int


@dataclass(frozen=True)
class StoryCatalog:
    stages: tuple[StoryStage, ...]

    def by_identity(self) -> dict[tuple[int, int], StoryStage]:
        return {(stage.chapter, stage.section): stage for stage in self.stages}


def load_story_catalog(path: Path) -> StoryCatalog:
    """Load a strict user-local generic-story catalog without resolving paths."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise StoryCatalogError("could not read story catalog JSON") from error
    if not isinstance(document, dict) or document.get("schema_version") != STORY_CATALOG_SCHEMA_VERSION:
        raise StoryCatalogError(f"schema_version must be {STORY_CATALOG_SCHEMA_VERSION}")
    if document.get("provenance") != "user-supplied":
        raise StoryCatalogError("provenance must be user-supplied")
    raw_stages = document.get("stages")
    if not isinstance(raw_stages, list) or not raw_stages:
        raise StoryCatalogError("stages must be a nonempty array")
    stages = tuple(_parse_stage(raw) for raw in raw_stages)
    identities = [(stage.chapter, stage.section) for stage in stages]
    if identities != sorted(identities) or len(identities) != len(set(identities)):
        raise StoryCatalogError("stages must be strictly ordered and unique by chapter and section")
    return StoryCatalog(stages)


def _parse_stage(value: object) -> StoryStage:
    required = {"chapter", "section", "stamina", "coins", "clear_progress_code", "clear_coins"}
    if not isinstance(value, dict) or set(value) != required:
        raise StoryCatalogError("each stage must contain only the required numeric fields")
    if any(type(value[name]) is not int for name in required):
        raise StoryCatalogError("every stage field must be an integer")
    stage = StoryStage(**{name: value[name] for name in required})
    if stage.chapter < 2 or stage.section < 1 or stage.stamina < 0 or stage.coins < 0:
        raise StoryCatalogError("chapter/section/stamina/coins are outside the generic-story range")
    if stage.clear_progress_code < 0 or stage.clear_coins < 0:
        raise StoryCatalogError("clear values must be nonnegative")
    return stage


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--story-catalog", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        catalog = load_story_catalog(args.story_catalog)
    except StoryCatalogError as error:
        raise SystemExit(f"story catalog validation failed: {error}") from error
    first, last = catalog.stages[0], catalog.stages[-1]
    print(
        f"validated {len(catalog.stages)} user-supplied story stages: "
        f"{first.chapter}-{first.section} through {last.chapter}-{last.section}"
    )
    return 0
