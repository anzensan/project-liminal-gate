"""Strict user-local clear-chapter achievement claim catalog."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import tomllib


class AchievementCatalogError(ValueError):
    """A user-local achievement catalog is invalid."""


@dataclass(frozen=True)
class Achievement:
    achievement_id: int
    required_chapter: int
    free_energy: int
    coins: int
    items: dict[int, int]


@dataclass(frozen=True)
class AchievementCatalog:
    item_slots: int
    max_free_energy: int
    max_coins: int
    max_stack: int
    achievements: dict[int, Achievement]


def load_achievement_catalog(path: Path) -> AchievementCatalog:
    try:
        document = tomllib.loads(path.read_text(encoding="utf-8")) if path.suffix.lower() == ".toml" else json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, tomllib.TOMLDecodeError) as error:
        raise AchievementCatalogError("could not read achievement catalog JSON or TOML") from error
    required = {"schema_version", "provenance", "item_slots", "max_free_energy", "max_coins", "max_stack", "achievements"}
    if not isinstance(document, dict) or set(document) != required:
        raise AchievementCatalogError("achievement catalog has an invalid schema")
    if document["schema_version"] != 1 or document["provenance"] != "user-supplied":
        raise AchievementCatalogError("achievement catalog requires schema version 1 and user-supplied provenance")
    limits = ("item_slots", "max_free_energy", "max_coins", "max_stack")
    if any(type(document[key]) is not int or document[key] < 1 for key in limits):
        raise AchievementCatalogError("achievement catalog limits must be positive integers")
    raw = document["achievements"]
    if not isinstance(raw, list) or not raw:
        raise AchievementCatalogError("achievements must be a nonempty array")
    achievements = tuple(_achievement(value, document["item_slots"]) for value in raw)
    ids = [achievement.achievement_id for achievement in achievements]
    if ids != sorted(ids) or len(ids) != len(set(ids)):
        raise AchievementCatalogError("achievements must be ordered and unique by achievement_id")
    return AchievementCatalog(*(document[key] for key in limits), {achievement.achievement_id: achievement for achievement in achievements})


def _achievement(value: object, item_slots: int) -> Achievement:
    required = {"achievement_id", "required_chapter", "free_energy", "coins", "items"}
    if not isinstance(value, dict) or set(value) != required:
        raise AchievementCatalogError("each achievement has an invalid schema")
    numeric = ("achievement_id", "required_chapter", "free_energy", "coins")
    if any(type(value[key]) is not int or value[key] < 0 for key in numeric) or value["achievement_id"] < 1 or value["required_chapter"] < 1:
        raise AchievementCatalogError("achievement numeric values are outside range")
    items = value["items"]
    if not isinstance(items, dict):
        raise AchievementCatalogError("achievement items must be an object")
    parsed: dict[int, int] = {}
    for raw_id, count in items.items():
        if not isinstance(raw_id, str) or not raw_id.isdecimal() or raw_id != str(int(raw_id)) or not 1 <= int(raw_id) <= item_slots or type(count) is not int or count < 1:
            raise AchievementCatalogError("achievement items require in-range decimal IDs and positive counts")
        parsed[int(raw_id)] = count
    return Achievement(value["achievement_id"], value["required_chapter"], value["free_energy"], value["coins"], parsed)
