"""Validate a user-local Hunting stage catalog.

Hunting battles are executed entirely by the client.  The server's whole job is
to authorise an entry, charge its cost, and accept a settlement that stays
inside bounds the operator declared -- so this catalog carries stage identity,
entry cost, unlock policy, and result ceilings, and deliberately carries no
enemy, encounter, reward, or resource data.

Everything here is supplied by the tester from their own local inputs.  Nothing
is bundled: an empty or absent catalog means Hunting is simply unavailable,
which is the correct behaviour for a stage whose bounds nobody has established.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


class HuntingCatalogError(ValueError):
    """A user-local Hunting catalog is malformed."""


@dataclass(frozen=True)
class HuntingStage:
    family: str
    chapter: int
    section: int
    stamina: int
    coins: int
    entry_item_id: int
    entry_item_count: int
    unlock_progress_code: int
    max_coins: int
    max_exp: int
    item_maxima: dict[int, int]

    def entry_items(self) -> dict[int, int]:
        return {self.entry_item_id: self.entry_item_count} if self.entry_item_id else {}


@dataclass(frozen=True)
class HuntingCatalog:
    stages: tuple[HuntingStage, ...]
    item_slots: int
    max_stack: int

    def by_identity(self) -> dict[tuple[int, int], HuntingStage]:
        return {(stage.chapter, stage.section): stage for stage in self.stages}


_STAGE_FIELDS = {
    "family", "chapter", "section", "stamina", "coins", "entry_item_id",
    "entry_item_count", "unlock_progress_code", "max_coins", "max_exp", "item_maxima",
}


def load_hunting_catalog(path: Path) -> HuntingCatalog:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HuntingCatalogError("could not read local hunting catalog JSON") from error
    if (
        not isinstance(document, dict)
        or set(document) != {"schema_version", "provenance", "item_slots", "max_stack", "stages"}
        or document["schema_version"] != 1
        or document["provenance"] != "user-supplied"
        or any(type(document[name]) is not int or document[name] < 1 for name in ("item_slots", "max_stack"))
        or not isinstance(document["stages"], list)
    ):
        raise HuntingCatalogError("hunting catalog has an invalid schema or provenance")
    stages = tuple(_parse_stage(raw, document["item_slots"], document["max_stack"]) for raw in document["stages"])
    identities = [(stage.chapter, stage.section) for stage in stages]
    if not stages or len(set(identities)) != len(identities):
        raise HuntingCatalogError("hunting stages must be nonempty and unique")
    return HuntingCatalog(stages, document["item_slots"], document["max_stack"])


def _parse_stage(raw: object, item_slots: int, max_stack: int) -> HuntingStage:
    if not isinstance(raw, dict) or set(raw) != _STAGE_FIELDS:
        raise HuntingCatalogError("each hunting stage has an invalid schema")
    integers = _STAGE_FIELDS - {"family", "item_maxima"}
    if not isinstance(raw["family"], str) or not raw["family"]:
        raise HuntingCatalogError("hunting stage family must be a nonempty string")
    if any(type(raw[name]) is not int or raw[name] < 0 for name in integers):
        raise HuntingCatalogError("hunting stage values must be nonnegative integers")
    if raw["chapter"] < 1 or raw["section"] < 1:
        raise HuntingCatalogError("hunting stage identity must be positive")
    # An entry item is all-or-nothing: a count without an item, or an item
    # without a count, would charge something the operator did not declare.
    if bool(raw["entry_item_id"]) != bool(raw["entry_item_count"]):
        raise HuntingCatalogError("hunting entry item and count must be declared together")
    if raw["entry_item_id"] > item_slots:
        raise HuntingCatalogError("hunting entry item is outside the declared item slots")
    maxima = _parse_maxima(raw["item_maxima"], item_slots, max_stack)
    return HuntingStage(
        family=raw["family"], chapter=raw["chapter"], section=raw["section"],
        stamina=raw["stamina"], coins=raw["coins"],
        entry_item_id=raw["entry_item_id"], entry_item_count=raw["entry_item_count"],
        unlock_progress_code=raw["unlock_progress_code"],
        max_coins=raw["max_coins"], max_exp=raw["max_exp"], item_maxima=maxima,
    )


def _parse_maxima(raw: object, item_slots: int, max_stack: int) -> dict[int, int]:
    """Parse an item-id to maximum-count map, keyed by decimal strings in JSON."""
    if not isinstance(raw, dict):
        raise HuntingCatalogError("hunting item maxima must be an object")
    maxima: dict[int, int] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not key.isdecimal() or type(value) is not int:
            raise HuntingCatalogError("hunting item maxima must map decimal item IDs to integers")
        item_id = int(key)
        if not 1 <= item_id <= item_slots or not 1 <= value <= max_stack:
            raise HuntingCatalogError("hunting item maxima are outside the declared bounds")
        maxima[item_id] = value
    return maxima


def hunting_settlement_within_bounds(stage: HuntingStage, result: dict[str, Any]) -> bool:
    """Whether a client-reported battle result stays inside the declared ceilings.

    Only the families whose results this catalog can bound are accepted.  A
    result carrying Companions or Battle Summons is refused rather than settled
    generously: those need their own recovered bounds, and a success response
    that accepts an unbounded claim is worse than a visible refusal.
    """
    if result["coins"] > stage.max_coins or result["exp"] > stage.max_exp:
        return False
    if result["buddies"] or result["summons"] or result["monsters"]:
        return False
    gained = {int(item_id): count for item_id, count in result["items"].items()}
    return all(item_id in stage.item_maxima and count <= stage.item_maxima[item_id] for item_id, count in gained.items())
