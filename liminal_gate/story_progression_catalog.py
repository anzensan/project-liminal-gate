"""Load the strict local core-story progression projection."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


class StoryProgressionCatalogError(ValueError):
    pass


@dataclass(frozen=True)
class StoryProgressionStage:
    chapter: int
    section: int
    stamina: int
    coins: int
    successor_chapter: int
    successor_section: int
    successor_low_progress: int
    chapter_boundary: bool


@dataclass(frozen=True)
class StoryProgressionCatalog:
    stages: tuple[StoryProgressionStage, ...]

    def by_identity(self) -> dict[tuple[int, int], StoryProgressionStage]:
        return {(stage.chapter, stage.section): stage for stage in self.stages}

    def index_by_identity(self) -> dict[tuple[int, int], int]:
        return {(stage.chapter, stage.section): index for index, stage in enumerate(self.stages)}

    def expected_clear_progress(self, current_progress: int, identity: tuple[int, int]) -> int | None:
        """Return the only accepted clear progress, including a permitted replay."""
        current_identity = ((current_progress & 0xFFFF) >> 6, current_progress & 0x3F)
        indexes = self.index_by_identity()
        stage_index = indexes.get(identity)
        unlocked_index = indexes.get(current_identity)
        if stage_index is None or unlocked_index is None or stage_index > unlocked_index:
            return None
        if stage_index < unlocked_index:
            return current_progress
        stage = self.by_identity()[identity]
        progress = (current_progress & ~0xFFFF) | stage.successor_low_progress
        return progress | 0x03000000 if stage.chapter_boundary else progress

    @staticmethod
    def expected_reveal_progress(current_progress: int) -> int | None:
        """Accept only the client map write that clears the show-progress bit."""
        return current_progress & ~0x02000000 if current_progress & 0x03000000 == 0x03000000 else None


def load_story_progression_catalog(path: Path) -> StoryProgressionCatalog:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise StoryProgressionCatalogError("could not read story progression JSON") from error
    source = document.get("source") if isinstance(document, dict) else None
    if (
        not isinstance(document, dict)
        or document.get("schema_version") != 1
        or document.get("provenance") != "user-derived"
        or not isinstance(source, dict)
        or source.get("profile") != "terra-battle-android-5.5.7-170"
        or source.get("kind") != "battledata-core-story-progression"
        or not isinstance(document.get("stages"), list)
    ):
        raise StoryProgressionCatalogError("story progression catalog has an invalid schema")
    stages = tuple(_parse_stage(value) for value in document["stages"])
    identities = [(stage.chapter, stage.section) for stage in stages]
    if len(stages) != 393 or identities != sorted(identities) or len(set(identities)) != len(identities):
        raise StoryProgressionCatalogError("story progression catalog must contain the ordered 393-stage core story")
    for index, stage in enumerate(stages):
        successor = (43, 1) if index + 1 == len(stages) else (stages[index + 1].chapter, stages[index + 1].section)
        if (stage.successor_chapter, stage.successor_section) != successor or stage.successor_low_progress != (successor[0] << 6) | successor[1] or stage.chapter_boundary != (successor[0] != stage.chapter):
            raise StoryProgressionCatalogError("story progression successor metadata is inconsistent")
    return StoryProgressionCatalog(stages)


def _parse_stage(value: object) -> StoryProgressionStage:
    required = {"chapter", "section", "stamina", "coins", "successor_chapter", "successor_section", "successor_low_progress", "chapter_boundary"}
    if not isinstance(value, dict) or set(value) != required:
        raise StoryProgressionCatalogError("story progression stage has an invalid schema")
    integer = required - {"chapter_boundary"}
    if any(type(value[name]) is not int for name in integer) or type(value["chapter_boundary"]) is not bool:
        raise StoryProgressionCatalogError("story progression stage has invalid field types")
    stage = StoryProgressionStage(**value)
    if stage.chapter < 2 or stage.chapter > 42 or stage.section < 1 or stage.stamina < 0 or stage.coins < 0:
        raise StoryProgressionCatalogError("story progression stage is outside the core-story range")
    return stage
