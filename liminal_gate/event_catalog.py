"""Validate local event stages and provide the bounded Counter Descent policy."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from liminal_gate.event_flag_data import event_flags_for
from liminal_gate.event_manifest_data import EVENT_MANIFEST_ROWS


DEFAULT_EVENT_CATALOG = "event-catalog.json"


class EventCatalogError(ValueError):
    """A user-local event catalog is malformed."""


@dataclass(frozen=True)
class EventStage:
    event_id: str
    flag: str
    chapter: int
    section: int
    stamina: int
    coins: int
    clear_coins: int
    character_ids: tuple[int, ...]
    summon_ids: tuple[int, ...] = ()
    selector: str = "special"
    unlock_after_chapter: int | None = None
    zero_base: bool = False

    def identity_label(self) -> str:
        return f"{self.chapter}-{self.section}"

    def unlocked_at(self, progress_code: int | None) -> bool:
        if self.unlock_after_chapter is None:
            return True
        if progress_code is None:
            return False
        current_chapter = (progress_code & 0xFFFF) >> 6
        completed_chapter = max(0, current_chapter - 1)
        return completed_chapter >= self.unlock_after_chapter


@dataclass(frozen=True)
class EventCatalog:
    stages: tuple[EventStage, ...]

    def by_identity(self) -> dict[tuple[int, int], EventStage]:
        return {(stage.chapter, stage.section): stage for stage in self.stages}

    def flags(self, progress_code: int | None = None) -> dict[str, dict[str, object]]:
        return {
            stage.flag: {"name": stage.flag, "value": True}
            for stage in self.stages
            if stage.unlocked_at(progress_code)
        }

    def client_lists(self, progress_code: int | None) -> dict[str, list[str]]:
        """Project Special, Tower, and folded Strikes Back selector rows."""
        special = [
            stage.identity_label()
            for stage in self.stages
            if stage.selector == "special" and stage.unlocked_at(progress_code)
        ]
        tower = [
            stage.identity_label()
            for stage in self.stages
            if stage.selector == "tower" and stage.unlocked_at(progress_code)
        ]
        eidolon = [
            stage.identity_label()
            for stage in self.stages
            if stage.selector == "eidolon" and stage.unlocked_at(progress_code)
        ]
        descent_chapters: dict[int, None] = {}
        for stage in self.stages:
            if (
                stage.selector == "descent_hunting"
                and stage.unlocked_at(progress_code)
            ):
                descent_chapters.setdefault(stage.chapter, None)
        return {
            "specialQuestList": special,
            "towerQuestList": tower,
            "eidolonQuestList": eidolon,
            # Counter Descent is a folded five-tier card. The selector receives
            # one row; the client expands the chapter's packaged sections.
            "descentHuntingList": [
                f"{chapter}-1" for chapter in descent_chapters
            ],
        }

    def client_list(self) -> list[str]:
        """Compatibility accessor for the normal Special selector."""
        return self.client_lists(None)["specialQuestList"]


_FIVE_TIER_COUNTER_DESCENT_STAMINA = (5, 10, 15, 15, 15)
_THREE_TIER_COUNTER_DESCENT_STAMINA = (5, 10, 15)


def _counter_descent_stamina(chapter: int) -> tuple[int, ...] | None:
    if 8000 <= chapter <= 8007:
        return _FIVE_TIER_COUNTER_DESCENT_STAMINA
    if 8012 <= chapter <= 8017:
        return _THREE_TIER_COUNTER_DESCENT_STAMINA
    return None


def build_bundled_counter_descent_policy() -> EventCatalog:
    """Return the fourteen packaged non-collaboration Strikes Back families.

    Chapter identities, flags, section counts, and stamina are recovered from
    the final client. Permanent Chapter 5--18 unlocks and zero-base settlement
    are explicit preservation policy because the historical schedule and
    retired result service were not captured. Little Noah 8008--8011 and Hime
    Rush 8018 are deliberately excluded because their progression/reward
    contracts are distinct and unrecovered.
    """
    manifests = [
        row
        for row in EVENT_MANIFEST_ROWS
        if _counter_descent_stamina(row[2]) is not None
    ]
    if len(manifests) != 14:
        raise EventCatalogError("bundled Counter Descent manifest is incomplete")
    stages = tuple(
        EventStage(
            event_id=event_id,
            flag=flag,
            chapter=chapter,
            section=section,
            stamina=stamina,
            coins=0,
            clear_coins=0,
            character_ids=(),
            selector="descent_hunting",
            unlock_after_chapter=unlock_after_chapter,
            zero_base=True,
        )
        for event_id, flag, chapter, unlock_after_chapter, _character_ids in manifests
        for section, stamina in enumerate(
            _counter_descent_stamina(chapter) or (), start=1
        )
    )
    return EventCatalog(stages)


def merge_event_catalogs(*catalogs: EventCatalog | None) -> EventCatalog | None:
    """Combine policies while keeping the first owner of an exact stage.

    The standard server's zero-base Counter Descent rows stay authoritative
    when an advanced generated catalog also contains those chapters. All other
    user-local event stages are retained.
    """
    stages: dict[tuple[int, int], EventStage] = {}
    for catalog in catalogs:
        if catalog is None:
            continue
        for stage in catalog.stages:
            stages.setdefault((stage.chapter, stage.section), stage)
    return EventCatalog(tuple(stages.values())) if stages else None


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_event_catalog(path: Path, character_catalog_path: Path) -> EventCatalog:
    try:
        document = json.loads(path.read_text())
        characters = json.loads(character_catalog_path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise EventCatalogError(
            "could not read local event or character catalog JSON"
        ) from error
    if (
        set(document)
        != {"schema_version", "provenance", "character_catalog_sha256", "stages"}
        or document["schema_version"] != 1
        or document["provenance"] != "user-supplied"
    ):
        raise EventCatalogError("event catalog has an invalid schema or provenance")
    if document["character_catalog_sha256"] != _hash(character_catalog_path):
        raise EventCatalogError(
            "event catalog does not match the local character catalog"
        )
    character_ids = {
        row.get("character_id")
        for row in characters.get("characters", [])
        if isinstance(row, dict)
    }
    stages: list[EventStage] = []
    raw_stages = document["stages"] if isinstance(document["stages"], list) else []
    for raw in raw_stages:
        required = {
            "event_id", "flag", "chapter", "section", "stamina", "coins",
            "clear_coins", "character_ids",
        }
        optional = {"unlock_after_chapter", "summon_ids"}
        if (
            not isinstance(raw, dict)
            or not required.issubset(raw)
            or not set(raw).issubset(required | optional)
        ):
            raise EventCatalogError("each event stage has an invalid schema")
        if (
            not isinstance(raw["event_id"], str)
            or not isinstance(raw["flag"], str)
            or any(
                type(raw[field]) is not int or raw[field] < 0
                for field in (
                    "chapter", "section", "stamina", "coins", "clear_coins",
                )
            )
        ):
            raise EventCatalogError("event stage has invalid values")
        unlock_after_chapter = raw.get("unlock_after_chapter")
        if (
            unlock_after_chapter is not None
            and (
                type(unlock_after_chapter) is not int
                or unlock_after_chapter < 0
            )
        ):
            raise EventCatalogError(
                "event stage unlock_after_chapter must be a nonnegative integer"
            )
        # The client constructs this key and looks it up by exact name. Any
        # other flag is inert: the row disappears without a useful error.
        permitted = event_flags_for(raw["chapter"], raw["section"])
        if raw["flag"] not in permitted:
            raise EventCatalogError(
                f"event stage flag {raw['flag']!r} cannot gate stage "
                f"{raw['chapter']}-{raw['section']}; the client only reads "
                f"{permitted[0]!r} or {permitted[1]!r}"
            )
        grants = raw["character_ids"]
        if (
            not isinstance(grants, list)
            or any(
                type(character_id) is not int or character_id not in character_ids
                for character_id in grants
            )
            or grants != sorted(set(grants))
        ):
            raise EventCatalogError(
                "event grants must be ordered local character IDs"
            )
        summon_ids = raw.get("summon_ids", [])
        if (
            not isinstance(summon_ids, list)
            or any(type(summon_id) is not int or not 1 <= summon_id <= 16 for summon_id in summon_ids)
            or summon_ids != sorted(set(summon_ids))
            or summon_ids and not 4100 <= raw["chapter"] <= 4111
        ):
            raise EventCatalogError(
                "event summon grants must be ordered Summon IDs from 1 through 16"
            )
        chapter = raw["chapter"]
        stages.append(
            EventStage(
                raw["event_id"],
                raw["flag"],
                chapter,
                raw["section"],
                raw["stamina"],
                raw["coins"],
                raw["clear_coins"],
                tuple(grants),
                tuple(summon_ids),
                selector=(
                    "descent_hunting"
                    if _counter_descent_stamina(chapter) is not None
                    else "tower"
                    if 9100 <= chapter <= 9102
                    else "eidolon"
                    if 4100 <= chapter <= 4111
                    else "special"
                ),
                unlock_after_chapter=unlock_after_chapter,
                zero_base=_counter_descent_stamina(chapter) is not None,
            )
        )
    if (
        not stages
        or len({(stage.chapter, stage.section) for stage in stages}) != len(stages)
    ):
        raise EventCatalogError("event stages must be nonempty and unique")
    return EventCatalog(tuple(stages))
