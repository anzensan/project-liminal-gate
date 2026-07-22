"""User-local identity and reward constraints for generic-story settlement."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


class SettlementCatalogError(ValueError):
    """A local settlement catalog is invalid."""


@dataclass(frozen=True)
class SettlementRule:
    chapter: int
    section: int
    character_rewards: frozenset[int]
    item_rewards: dict[int, int]
    summon_rewards: dict[int, int]
    clear_coins: int | None


@dataclass(frozen=True)
class SettlementCatalog:
    character_ids: frozenset[int]
    item_slots: int
    summon_slots: int
    max_stack: int
    rules: dict[tuple[int, int], SettlementRule]


def load_settlement_catalog(path: Path) -> SettlementCatalog:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SettlementCatalogError("could not read settlement catalog JSON") from error
    required = {"schema_version", "provenance", "character_ids", "item_slots", "summon_slots", "max_stack", "stages"}
    if not isinstance(value, dict) or set(value) != required or value.get("schema_version") != 1 or value.get("provenance") != "user-supplied":
        raise SettlementCatalogError("settlement catalog has an invalid schema or provenance")
    ids = value["character_ids"]
    if not isinstance(ids, list) or not ids or ids != sorted(ids) or len(ids) != len(set(ids)) or any(type(item) is not int or item <= 0 for item in ids):
        raise SettlementCatalogError("character_ids must be ordered, unique, positive integers")
    counts = (value["item_slots"], value["summon_slots"], value["max_stack"])
    if any(type(count) is not int or count <= 0 for count in counts):
        raise SettlementCatalogError("slot and stack counts must be positive integers")
    raw_rules = value["stages"]
    if not isinstance(raw_rules, list) or not raw_rules:
        raise SettlementCatalogError("stages must be a nonempty array")
    rules = tuple(_rule(raw) for raw in raw_rules)
    identities = [(rule.chapter, rule.section) for rule in rules]
    if identities != sorted(identities) or len(identities) != len(set(identities)):
        raise SettlementCatalogError("stages must be ordered and unique")
    return SettlementCatalog(frozenset(ids), *counts, {identity: rule for identity, rule in zip(identities, rules)})


def _rule(value: object) -> SettlementRule:
    required = {"chapter", "section", "character_rewards", "item_rewards", "summon_rewards"}
    if not isinstance(value, dict) or (set(value) != required and set(value) != required | {"clear_coins"}) or type(value["chapter"]) is not int or type(value["section"]) is not int or value["chapter"] < 2 or value["section"] < 1:
        raise SettlementCatalogError("each stage has invalid identity")
    characters = value["character_rewards"]
    if not isinstance(characters, list) or len(characters) != len(set(characters)) or any(type(item) is not int or item <= 0 for item in characters):
        raise SettlementCatalogError("character_rewards must be unique positive integers")
    clear_coins = value.get("clear_coins")
    if clear_coins is not None and (type(clear_coins) is not int or clear_coins < 0):
        raise SettlementCatalogError("clear_coins must be a nonnegative integer")
    return SettlementRule(value["chapter"], value["section"], frozenset(characters), _rewards(value["item_rewards"]), _rewards(value["summon_rewards"]), clear_coins)


def _rewards(value: object) -> dict[int, int]:
    if not isinstance(value, dict):
        raise SettlementCatalogError("reward maps must be objects")
    result: dict[int, int] = {}
    for raw_id, count in value.items():
        if not isinstance(raw_id, str) or not raw_id.isdecimal() or raw_id != str(int(raw_id)) or int(raw_id) <= 0 or type(count) is not int or count < 0:
            raise SettlementCatalogError("reward maps require positive decimal IDs and nonnegative counts")
        result[int(raw_id)] = count
    return result
