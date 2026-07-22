"""User-local bounds for client-reported generic story outcomes."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
import tomllib


class StoryOutcomeCatalogError(ValueError):
    """A user-local story-outcome catalog is invalid."""


@dataclass(frozen=True)
class CompanionDropMaster:
    companion_id: int
    drop_level: int


@dataclass(frozen=True)
class StoryOutcomeRule:
    chapter: int
    section: int
    item_maxima: dict[int, int]
    character_maxima: dict[int, int]
    companion_maxima: dict[int, int]


@dataclass(frozen=True)
class StoryOutcomeCatalog:
    character_ids: frozenset[int]
    item_slots: int
    max_stack: int
    max_companions: int
    companion_masters: dict[int, CompanionDropMaster]
    rules: dict[tuple[int, int], StoryOutcomeRule]


def load_story_outcome_catalog(path: Path) -> StoryOutcomeCatalog:
    try:
        value = tomllib.loads(path.read_text(encoding="utf-8")) if path.suffix.lower() == ".toml" else json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, tomllib.TOMLDecodeError) as error:
        raise StoryOutcomeCatalogError("could not read story-outcome catalog JSON or TOML") from error
    required = {"schema_version", "provenance", "character_ids", "item_slots", "max_stack", "max_companions", "companion_masters", "stages"}
    if not isinstance(value, dict) or set(value) != required or value.get("schema_version") != 1 or value.get("provenance") != "user-supplied":
        raise StoryOutcomeCatalogError("story-outcome catalog has an invalid schema or provenance")
    character_ids = _ids(value["character_ids"], "character_ids")
    numeric = ("item_slots", "max_stack", "max_companions")
    if any(type(value[name]) is not int or value[name] <= 0 for name in numeric):
        raise StoryOutcomeCatalogError("story-outcome catalog capacities must be positive integers")
    if not isinstance(value["companion_masters"], list):
        raise StoryOutcomeCatalogError("companion_masters must be an array")
    if not isinstance(value["stages"], list) or not value["stages"]:
        raise StoryOutcomeCatalogError("stages must be a nonempty array")
    masters = tuple(_master(item) for item in value["companion_masters"])
    master_ids = [master.companion_id for master in masters]
    if master_ids != sorted(master_ids) or len(master_ids) != len(set(master_ids)):
        raise StoryOutcomeCatalogError("companion_masters must be ordered and unique")
    rules = tuple(_rule(item) for item in value["stages"])
    identities = [(rule.chapter, rule.section) for rule in rules]
    if identities != sorted(identities) or len(identities) != len(set(identities)):
        raise StoryOutcomeCatalogError("stages must be ordered and unique")
    masters_by_id = {master.companion_id: master for master in masters}
    if any(any(companion_id not in masters_by_id for companion_id in rule.companion_maxima) or any(character_id not in character_ids for character_id in rule.character_maxima) or any(item_id > value["item_slots"] for item_id in rule.item_maxima) for rule in rules):
        raise StoryOutcomeCatalogError("stage maxima reference an undeclared ID")
    return StoryOutcomeCatalog(frozenset(character_ids), *(value[name] for name in numeric), masters_by_id, {identity: rule for identity, rule in zip(identities, rules)})


def _ids(value: object, name: str) -> list[int]:
    if not isinstance(value, list) or not value or value != sorted(value) or len(value) != len(set(value)) or any(type(item) is not int or item <= 0 for item in value):
        raise StoryOutcomeCatalogError(f"{name} must be ordered unique positive integers")
    return value


def _master(value: object) -> CompanionDropMaster:
    if not isinstance(value, dict) or set(value) != {"companion_id", "drop_level"} or any(type(value[name]) is not int or value[name] <= 0 for name in ("companion_id", "drop_level")):
        raise StoryOutcomeCatalogError("each companion master requires positive ID and drop level")
    return CompanionDropMaster(value["companion_id"], value["drop_level"])


def _rule(value: object) -> StoryOutcomeRule:
    required = {"chapter", "section", "item_maxima", "character_maxima", "companion_maxima"}
    if not isinstance(value, dict) or set(value) != required or type(value["chapter"]) is not int or type(value["section"]) is not int or value["chapter"] < 2 or value["section"] < 1:
        raise StoryOutcomeCatalogError("each stage has an invalid identity")
    return StoryOutcomeRule(value["chapter"], value["section"], _maxima(value["item_maxima"]), _maxima(value["character_maxima"]), _maxima(value["companion_maxima"]))


def _maxima(value: object) -> dict[int, int]:
    if not isinstance(value, dict):
        raise StoryOutcomeCatalogError("outcome maxima must be objects")
    result: dict[int, int] = {}
    for raw_id, maximum in value.items():
        if not isinstance(raw_id, str) or not raw_id.isdecimal() or raw_id != str(int(raw_id)) or int(raw_id) <= 0 or type(maximum) is not int or maximum < 1:
            raise StoryOutcomeCatalogError("outcome maxima require positive decimal IDs and counts")
        result[int(raw_id)] = maximum
    return result


def allowed(counter: Counter[int], maxima: dict[int, int]) -> bool:
    return all(value <= maxima.get(key, 0) for key, value in counter.items())
