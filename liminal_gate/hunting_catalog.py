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

from collections import Counter
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any


class HuntingCatalogError(ValueError):
    """A user-local Hunting catalog is malformed."""


#: Which client selector advertises a stage.  `UISpecialSelect` mode 7 reads
#: `huntingHuntingList` and mode 6 reads `metalHuntingList`; `hidden` is for a
#: stage the server will honour if asked but does not advertise, which is how a
#: duplicate stage identity stays startable without appearing twice.
SELECTORS = ("hunting", "metal", "hidden")


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
    selector: str = "hunting"
    #: When true the entry item is an *alternative* to stamina rather than an
    #: additional charge: the Metal Zone ticket is spent when one is held, and
    #: the stamina cost applies only when it is not.  Holding no ticket is
    #: therefore not an error, which is why this cannot reuse `entry_item_id`
    #: alone -- that one charges both.
    ticket_optional: bool = False
    #: Companion id to the most copies one settlement may report.
    companion_maxima: dict[int, int] = field(default_factory=dict)
    #: Companion id to the level a dropped copy arrives at.
    companion_drop_levels: dict[int, int] = field(default_factory=dict)

    def identity_label(self) -> str:
        """The `chapter-section` string the client's selector lists expect."""
        return f"{self.chapter}-{self.section}"

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
    #: The client's Companion box capacity; a settlement may not push an
    #: account past it.
    max_companions: int = 1000

    def by_identity(self) -> dict[tuple[int, int], HuntingStage]:
        return {(stage.chapter, stage.section): stage for stage in self.stages}

    def client_lists(self, progress_code: int) -> dict[str, list[str]]:
        """Return the zone lists the client's Huntland selectors read.

        The client hard-codes no thresholds of its own, so a zone the server
        does not name here simply does not exist to it.  Deriving both lists
        from the same stages that authorise a start is deliberate: a zone can
        never be advertised without also being startable, which would turn a
        locked card into a failed request.
        """
        return {
            f"{selector}HuntingList": [
                stage.identity_label() for stage in self.stages
                if stage.selector == selector and stage.unlocked_at(progress_code)
            ]
            for selector in ("metal", "hunting")
        }


_STAGE_FIELDS = {
    "family", "chapter", "section", "stamina", "coins", "entry_item_id",
    "entry_item_count", "unlock_chapter", "unlock_section", "max_coins",
    "max_exp", "max_items_total", "item_maxima",
}
# Optional so that catalogs written before the client-facing zone lists existed
# still load; omitting it advertises the stage on the ordinary Hunting selector,
# which is what every such catalog described.
_OPTIONAL_STAGE_FIELDS = {"selector", "ticket_optional", "companion_maxima", "companion_drop_levels"}


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
    if not isinstance(raw, dict) or set(raw) - _OPTIONAL_STAGE_FIELDS != _STAGE_FIELDS:
        raise HuntingCatalogError("each hunting stage has an invalid schema")
    if raw.get("selector", "hunting") not in SELECTORS:
        raise HuntingCatalogError(f"hunting stage selector must be one of {', '.join(SELECTORS)}")
    if type(raw.get("ticket_optional", False)) is not bool:
        raise HuntingCatalogError("hunting stage ticket_optional must be true or false")
    if raw.get("ticket_optional") and not raw.get("entry_item_id"):
        raise HuntingCatalogError("a ticket alternative needs the entry item it replaces stamina with")
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
    companions = _parse_companion_counts(raw.get("companion_maxima", {}), "companion_maxima")
    levels = _parse_companion_counts(raw.get("companion_drop_levels", {}), "companion_drop_levels")
    # A declared drop needs a level to arrive at, or the settlement could not
    # say what it granted.
    if set(companions) - set(levels):
        raise HuntingCatalogError("every companion in companion_maxima needs a companion_drop_levels entry")
    return HuntingStage(
        family=raw["family"], chapter=raw["chapter"], section=raw["section"],
        stamina=raw["stamina"], coins=raw["coins"],
        entry_item_id=raw["entry_item_id"], entry_item_count=raw["entry_item_count"],
        unlock_chapter=raw["unlock_chapter"], unlock_section=raw["unlock_section"],
        max_coins=raw["max_coins"], max_exp=raw["max_exp"],
        max_items_total=raw["max_items_total"], item_maxima=maxima,
        selector=raw.get("selector", "hunting"),
        ticket_optional=raw.get("ticket_optional", False),
        companion_maxima=companions, companion_drop_levels=levels,
    )


def _parse_companion_counts(raw: object, label: str) -> dict[int, int]:
    """Parse a companion-id to positive-integer map, keyed by decimal strings."""
    if not isinstance(raw, dict):
        raise HuntingCatalogError(f"hunting {label} must be an object")
    parsed: dict[int, int] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not key.isdecimal() or type(value) is not int or value < 1:
            raise HuntingCatalogError(f"hunting {label} must map decimal companion IDs to positive integers")
        parsed[int(key)] = value
    return parsed


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

    Every reward channel is bounded by the stage, and anything the stage does
    not declare is refused rather than settled generously: a success response
    that accepts an unbounded claim is worse than a visible refusal.  Metal Zone
    declares Companion drops and an EXP ceiling; the Hunting families declare
    items or Coins; Dragon and Machine Road declare nothing at all and so must
    settle at zero.  Battle Summons and recruited monsters are refused
    everywhere: no Huntland family grants either.
    """
    if result["coins"] > stage.max_coins or result["exp"] > stage.max_exp:
        return False
    if result["summons"] or result["monsters"]:
        return False
    companions = Counter(result["buddies"])
    if any(count > stage.companion_maxima.get(companion_id, 0) for companion_id, count in companions.items()):
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
# Metal Zone, Chapter 3000.  Entry cost, the Item 50 ticket contract, and the
# Companion drop manifests are recovered from the final client's BattleData and
# BuddyDatabase.  The availability thresholds are the same category of
# preservation policy as the Hunting tiers above.
_METAL_UNLOCK_AFTER_CHAPTER = (3, 8, 12, 17, 21, 26, 30)
_METAL_STAMINA = (5, 8, 10, 13, 15, 18, 20)
# Zone to Companion id and the most copies one clear may report.  Zones 3 to 7
# share one manifest.  Both Companions arrive at level 1.
_METAL_COMPANION_MAXIMA = ({128: 1}, {128: 2}) + ({128: 3, 129: 2},) * 5
_METAL_COMPANION_DROP_LEVELS = {128: 1, 129: 1}
# Conservative per-zone EXP ceilings carried over from the reference server:
# twenty copies of the strongest documented enemy at the zone's upper eligible
# party level.  The original service's validation is lost, so these are labeled
# local policy -- they exist to stop an arbitrary client-authored EXP claim, not
# to reproduce a recovered rule.
_METAL_EXP_CEILING = (750_000, 920_000, 1_560_000, 2_270_000, 2_550_000, 4_400_000, 7_720_000)
# The Metal Zone ticket.  Held tickets are spent instead of stamina.
METAL_TICKET_ITEM_ID = 50
# Dragon Road and Machine Road are ordinary entries in the client's Metal
# selector, not the Chapter 1300 time-attack family.  BattleData gives them no
# Coins, items, EXP, or Companion drops, so they settle at zero until a real
# clear proves otherwise.  Their historical availability gate is not preserved;
# they appear with Metal Zone 1.
_ROAD_CHAPTERS = (1200, 1201)
_ROAD_STAMINA = 15


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

    Metal Zone and the two Roads are included, with their recovered entry costs
    and Companion manifests.  Two things about them are local policy and are
    labeled as such beside the tables: the availability thresholds, and the
    per-zone EXP ceilings, which bound an unbounded client claim rather than
    reproduce a recovered service rule.

    Chapter 3000 carries each zone twice, at sections 1-7 and again at 11-17.
    Only the ticket-aware 11-17 range is advertised, matching the reference
    server; the 1-7 duplicates stay startable but hidden so the selector does
    not list every zone twice.
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
    stages.extend(_bundled_metal_stages())
    stages.extend(_bundled_road_stages())
    return HuntingCatalog(tuple(stages), BUNDLED_ITEM_SLOTS, BUNDLED_MAX_STACK)


def _bundled_metal_stages() -> list[HuntingStage]:
    """Return Chapter 3000's seven zones, each at its two recovered sections."""
    stages: list[HuntingStage] = []
    for zone in range(1, 8):
        for section, selector in ((zone, "hidden"), (zone + 10, "metal")):
            stages.append(HuntingStage(
                family="metal_zone", chapter=3000, section=section,
                stamina=_METAL_STAMINA[zone - 1], coins=0,
                entry_item_id=METAL_TICKET_ITEM_ID, entry_item_count=1, ticket_optional=True,
                unlock_chapter=_METAL_UNLOCK_AFTER_CHAPTER[zone - 1] + 1, unlock_section=1,
                max_coins=0, max_exp=_METAL_EXP_CEILING[zone - 1],
                # Metal settles EXP and Companions only: no Coins, no items.
                max_items_total=0, item_maxima={}, selector=selector,
                companion_maxima=dict(_METAL_COMPANION_MAXIMA[zone - 1]),
                companion_drop_levels=dict(_METAL_COMPANION_DROP_LEVELS),
            ))
    return stages


def _bundled_road_stages() -> list[HuntingStage]:
    """Return Dragon and Machine Road, which reward nothing that is recovered."""
    return [
        HuntingStage(
            family="road", chapter=chapter, section=1, stamina=_ROAD_STAMINA, coins=0,
            entry_item_id=0, entry_item_count=0,
            unlock_chapter=_METAL_UNLOCK_AFTER_CHAPTER[0] + 1, unlock_section=1,
            max_coins=0, max_exp=0, max_items_total=0, item_maxima={}, selector="metal",
        )
        for chapter in _ROAD_CHAPTERS
    ]
