"""User-local Battle Summon skill-unlock costs for the public server."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from liminal_gate.summon_skill_data import SUMMON_SKILL_ROWS
from liminal_gate.save_validation import ITEM_SLOTS


class SummonSkillCatalogError(ValueError):
    """A user-local Battle Summon skill catalog is invalid."""


@dataclass(frozen=True)
class SummonSkillLevel:
    summon_id: int
    skill_level: int
    coins: int
    materials: dict[int, int]


@dataclass(frozen=True)
class SummonSkillCatalog:
    item_slots: int
    levels: dict[tuple[int, int], SummonSkillLevel]
    level_counts: dict[int, int]


def load_summon_skill_catalog(path: Path) -> SummonSkillCatalog:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SummonSkillCatalogError("could not read Battle Summon skill catalog JSON") from error
    required = {"schema_version", "provenance", "item_slots", "levels"}
    if not isinstance(document, dict) or set(document) != required:
        raise SummonSkillCatalogError("Battle Summon skill catalog has an invalid schema")
    if document["schema_version"] != 1 or document["provenance"] != "user-supplied":
        raise SummonSkillCatalogError("Battle Summon skill catalog requires schema version 1 and user-supplied provenance")
    if type(document["item_slots"]) is not int or document["item_slots"] <= 0:
        raise SummonSkillCatalogError("item_slots must be a positive integer")
    raw_levels = document["levels"]
    if not isinstance(raw_levels, list) or not raw_levels:
        raise SummonSkillCatalogError("levels must be a nonempty array")
    levels = tuple(_level(value) for value in raw_levels)
    identities = [(level.summon_id, level.skill_level) for level in levels]
    if identities != sorted(identities) or len(identities) != len(set(identities)):
        raise SummonSkillCatalogError("levels must be ordered and unique by summon_id/skill_level")
    level_counts: dict[int, int] = {}
    for summon_id in range(1, 17):
        indices = [level.skill_level for level in levels if level.summon_id == summon_id]
        if not indices:
            raise SummonSkillCatalogError("levels must include every Battle Summon ID from 1 through 16")
        if indices != list(range(len(indices))):
            raise SummonSkillCatalogError("each Battle Summon skill level must start at 0 and be consecutive")
        level_counts[summon_id] = len(indices)
    return SummonSkillCatalog(
        document["item_slots"],
        {(level.summon_id, level.skill_level): level for level in levels},
        level_counts,
    )


def _level(value: object) -> SummonSkillLevel:
    required = {"summon_id", "skill_level", "coins", "materials"}
    if not isinstance(value, dict) or set(value) != required:
        raise SummonSkillCatalogError("each level must have the required fields")
    numeric = ("summon_id", "skill_level", "coins")
    if any(type(value[name]) is not int for name in numeric):
        raise SummonSkillCatalogError("level numeric fields must be integers")
    if not 1 <= value["summon_id"] <= 16 or value["skill_level"] < 0 or value["coins"] < 0:
        raise SummonSkillCatalogError("level values are outside range")
    materials = value["materials"]
    if not isinstance(materials, dict):
        raise SummonSkillCatalogError("materials must be an object")
    parsed: dict[int, int] = {}
    for raw_id, count in materials.items():
        if not isinstance(raw_id, str) or not raw_id.isdecimal() or raw_id != str(int(raw_id)) or int(raw_id) <= 0 or type(count) is not int or count < 0:
            raise SummonSkillCatalogError("materials require positive decimal IDs and nonnegative counts")
        parsed[int(raw_id)] = count
    return SummonSkillLevel(value["summon_id"], value["skill_level"], value["coins"], parsed)


# The client's own 181 item slots, matching the other bundled policies.
BUNDLED_ITEM_SLOTS = ITEM_SLOTS


def build_bundled_summon_skill_policy() -> SummonSkillCatalog:
    """Return the archival local Battle Summon skill policy.

    Costs are the recovered `SummonData` -> `ChrJobParams` join; see
    :mod:`liminal_gate.summon_skill_data`. Nothing here concerns how a Summon is
    acquired, which remains unrecovered. Version 5.5.0 retired the enhancement
    UI, so this policy preserves a static transport rather than enabling a
    required final-version solo loop.
    """
    levels = {
        (summon_id, skill_level): SummonSkillLevel(
            summon_id, skill_level, coins, {item: count for item, count in materials}
        )
        for summon_id, skill_level, coins, materials in SUMMON_SKILL_ROWS
    }
    level_counts: dict[int, int] = {}
    for summon_id, skill_level in levels:
        level_counts[summon_id] = max(level_counts.get(summon_id, 0), skill_level + 1)
    return SummonSkillCatalog(BUNDLED_ITEM_SLOTS, levels, level_counts)
