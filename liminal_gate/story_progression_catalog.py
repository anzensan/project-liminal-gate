"""Load the strict local core-story progression projection."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from liminal_gate.reviewed_build import SOURCE_PROFILE


class StoryProgressionCatalogError(ValueError):
    pass


@dataclass(frozen=True)
class StoryProgressionStage:
    chapter: int
    section: int
    stamina: int | None
    coins: int | None
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


#: How many *playable* sections each core-story chapter has.
#:
#: BattleData gives every chapter a fixed run of section slots -- ten for most,
#: five for Chapters 2 and 3, three for Chapter 42 -- but a slot is only a stage
#: when its ``battleCnt`` is nonzero. Chapter 20 is the one chapter in the core
#: story where the two disagree: "Awakening" ships ten slots carrying a single
#: twenty-battle stage, and clearing that one stage completes the chapter.
#:
#: Counting slots rather than battles is not a cosmetic error, which is why this
#: is a table and not an expression. It makes 20-1 an ordinary mid-chapter stage
#: whose successor is the phantom 20-2, so the server demands a progress code the
#: client never sends: having finished the chapter, the client reports 21-1 with
#: the chapter-boundary flags set. The clear is refused, `active_generic_story`
#: stays pinned on 20-1, and every retry fails the same way -- an account that
#: cannot leave Chapter 20 at all, while the server log shows only 200s.
#:
#: Confirmed four ways before it was changed: the reviewed APK's own BattleData
#: (`battleCnt` nonzero for 20-1 alone), the final wiki ("consists of only a
#: single stage"), the client's stage list drawing exactly one row for Chapter
#: 20, and a stuck tester save pinned on 20-1 with no `20-x` clear ever recorded.
CORE_SECTION_COUNTS = {
    chapter: 1 if chapter == 20 else 5 if chapter in {2, 3} else 3 if chapter == 42 else 10
    for chapter in range(2, 43)
}

#: Every playable core-story stage. BattleData reserves 393 section slots; nine
#: of Chapter 20's are empty, so the graph the client walks is nine shorter.
CORE_STORY_STAGE_COUNT = sum(CORE_SECTION_COUNTS.values())


def build_core_story_policy() -> StoryProgressionCatalog:
    """Build the local ordinary-story policy used by the guided tester path.

    This contains only the recovered ordered Chapter 2--42 identities and
    successor progression.  ``None`` start values deliberately mean the
    user's client supplies its own nonnegative stamina/coin fields; this is a
    local compatibility policy, not a bundled reward or cost table.

    Section counts come from :data:`CORE_SECTION_COUNTS`, which counts stages
    the client can actually play rather than the slots BattleData reserves.
    """
    identities = [
        (chapter, section)
        for chapter in range(2, 43)
        for section in range(1, CORE_SECTION_COUNTS[chapter] + 1)
    ]
    stages = tuple(
        StoryProgressionStage(
            chapter=chapter,
            section=section,
            stamina=None,
            coins=None,
            successor_chapter=43 if index + 1 == len(identities) else identities[index + 1][0],
            successor_section=1 if index + 1 == len(identities) else identities[index + 1][1],
            successor_low_progress=(43 << 6) | 1 if index + 1 == len(identities) else (identities[index + 1][0] << 6) | identities[index + 1][1],
            chapter_boundary=index + 1 == len(identities) or identities[index + 1][0] != chapter,
        )
        for index, (chapter, section) in enumerate(identities)
    )
    return StoryProgressionCatalog(stages)


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
        or source.get("profile") != SOURCE_PROFILE
        or source.get("kind") != "battledata-core-story-progression"
        or not isinstance(document.get("stages"), list)
    ):
        raise StoryProgressionCatalogError("story progression catalog has an invalid schema")
    stages = tuple(_parse_stage(value) for value in document["stages"])
    identities = [(stage.chapter, stage.section) for stage in stages]
    if len(stages) != CORE_STORY_STAGE_COUNT or identities != sorted(identities) or len(set(identities)) != len(identities):
        raise StoryProgressionCatalogError(
            f"story progression catalog must contain the ordered {CORE_STORY_STAGE_COUNT}-stage core story"
        )
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
