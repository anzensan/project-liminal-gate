"""Validate a user-local Hunting stage catalog.

Hunting battles are executed entirely by the client.  The server's whole job is
to authorise an entry, charge its cost, and accept a settlement that stays
inside bounds the operator declared -- so this catalog carries stage identity,
entry cost, unlock policy, and result ceilings, and deliberately carries no
enemy, encounter, reward, or resource data.

A stage may come from an operator's own catalog file, or from the bundled
policy below, which follows the same split the Pact and core-story policies
already use: recovered structure and observed costs are bundled, while anything
that would be a claim about the retired service's tuning -- odds, rotations,
schedules -- is an explicit local policy instead.
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
    unlock_chapter: int
    unlock_section: int
    max_coins: int
    max_exp: int
    max_items_total: int
    item_maxima: dict[int, int]

    def unlocked_at(self, progress_code: int) -> bool:
        """Whether an account's story progress has reached this stage.

        Compared on the decoded chapter/section rather than the raw
        `progressCode`, whose high bits carry unrelated show-progress flags
        that would otherwise make an earlier chapter compare as later.
        """
        return ((progress_code & 0xFFFF) >> 6, progress_code & 0x3F) >= (self.unlock_chapter, self.unlock_section)

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
    "entry_item_count", "unlock_chapter", "unlock_section", "max_coins",
    "max_exp", "max_items_total", "item_maxima",
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
    if raw["chapter"] < 1 or raw["section"] < 1 or raw["unlock_chapter"] < 1 or raw["unlock_section"] < 1:
        raise HuntingCatalogError("hunting stage identity and unlock must be positive")
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
        unlock_chapter=raw["unlock_chapter"], unlock_section=raw["unlock_section"],
        max_coins=raw["max_coins"], max_exp=raw["max_exp"],
        max_items_total=raw["max_items_total"], item_maxima=maxima,
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
    if sum(gained.values()) > stage.max_items_total:
        return False
    return all(item_id in stage.item_maxima and count <= stage.item_maxima[item_id] for item_id, count in gained.items())


# The client's own inventory shape: 181 item counts, stacking to 999.
BUNDLED_ITEM_SLOTS = 181
BUNDLED_MAX_STACK = 999
# Availability is a preservation policy, not a recovered schedule: the retired
# rotations were never captured, so each tier simply becomes permanent once the
# story has passed the chapter recorded here.
_UNLOCK_AFTER_CHAPTER = {1: 3, 2: 9, 3: 18}


def _tier(section: int) -> tuple[int, int]:
    return _UNLOCK_AFTER_CHAPTER[section] + 1, 1


def _span(first: int, last: int, maximum: int) -> dict[int, int]:
    return {item_id: maximum for item_id in range(first, last + 1)}


def build_bundled_hunting_policy() -> HuntingCatalog:
    """Return the guided-path local Hunting policy.

    Stage identities, entry stamina, and the population-derived item ceilings
    are recovered from the final client and are Confirmed.  Two things are
    deliberately *not* claims about the original service: the availability
    thresholds above, and Puppet Show's aggregate of 60 -- its real-time board
    refills without any cumulative spawn counter, so no exact finite cap exists
    to recover and 60 is retained as conservative anti-inflation policy.

    Metal Zone (Chapters 1000/3000) is absent on purpose.  Its results carry
    EXP and Companion drops, which this catalog cannot bound, and a settlement
    carrying Companions is refused rather than accepted generously.
    """
    stamina = {1: 5, 2: 8, 3: 10}
    pudding_items = _span(13, 17, 21) | {46: 21} | _span(26, 29, 20) | {122: 19, 123: 19, 164: 19, 165: 19}
    stages: list[HuntingStage] = []
    for section in (1, 2, 3):
        unlock_chapter, unlock_section = _tier(section)
        common = {
            "section": section, "coins": 0, "entry_item_id": 0, "entry_item_count": 0,
            "unlock_chapter": unlock_chapter, "unlock_section": unlock_section, "max_exp": 0,
        }
        stages.append(HuntingStage(
            family="pudding_time", chapter=1001, stamina=stamina[section],
            max_coins=0, max_items_total=79, item_maxima=dict(pudding_items), **common,
        ))
        # Tin's first zone alone caps items 22-25 at a single boss slot.
        tin_items = _span(9, 12, 32) | (_span(18, 21, 31) | _span(22, 25, 1) if section == 1 else _span(18, 25, 31))
        stages.append(HuntingStage(
            family="tin_parade", chapter=1002, stamina=stamina[section],
            max_coins=0, max_items_total=63 if section == 1 else 93, item_maxima=tin_items, **common,
        ))
        stages.append(HuntingStage(
            family="coin_creeps", chapter=1003, stamina={1: 10, 2: 15, 3: 20}[section],
            max_coins={1: 1500, 2: 5000, 3: 11000}[section], max_items_total=0, item_maxima={}, **common,
        ))
        puppet_items = _span(1, 8, 60) if section < 3 else ({1: 60, 3: 60, 5: 60, 7: 60} | {2: 2, 4: 2, 6: 2, 8: 2})
        stages.append(HuntingStage(
            family="puppet_show", chapter=1004, stamina=stamina[section],
            max_coins=0, max_items_total=60, item_maxima=puppet_items | _span(22, 29, 1), **common,
        ))
    return HuntingCatalog(tuple(stages), BUNDLED_ITEM_SLOTS, BUNDLED_MAX_STACK)
