"""Strict user-local inputs for the status-up item compatibility route.

The public source deliberately includes no item effects, character species, or
Luck-cap rows.  An operator supplies those values locally, with provenance,
before the server enables ``POST /gd/use_statusup_item``.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from liminal_gate.statusup_character_data import STATUSUP_CHARACTER_ROWS
from liminal_gate.save_validation import ITEM_SLOTS


class StatusupCatalogError(ValueError):
    """A user-local status-up catalog is invalid."""


@dataclass(frozen=True)
class StatusupItem:
    item_id: int
    level: int
    skill_boost: int
    luck: int
    species: int | None


@dataclass(frozen=True)
class StatusupCharacter:
    character_id: int
    species: int
    luck_cap: int


@dataclass(frozen=True)
class StatusupCatalog:
    item_slots: int
    level_cap: int
    skill_boost_cap: int
    items: dict[int, StatusupItem]
    characters: dict[int, StatusupCharacter]


def load_statusup_catalog(path: Path) -> StatusupCatalog:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise StatusupCatalogError("could not read status-up catalog JSON") from error
    required = {"schema_version", "provenance", "item_slots", "level_cap", "skill_boost_cap", "items", "characters"}
    if not isinstance(document, dict) or set(document) != required:
        raise StatusupCatalogError("status-up catalog has an invalid schema")
    if document["schema_version"] != 1 or document["provenance"] != "user-supplied":
        raise StatusupCatalogError("status-up catalog requires schema version 1 and user-supplied provenance")
    counts = (document["item_slots"], document["level_cap"], document["skill_boost_cap"])
    if any(type(value) is not int or value <= 0 for value in counts):
        raise StatusupCatalogError("slot and cap values must be positive integers")
    items = _items(document["items"])
    characters = _characters(document["characters"])
    return StatusupCatalog(*counts, items, characters)


def _items(value: object) -> dict[int, StatusupItem]:
    if not isinstance(value, list) or not value:
        raise StatusupCatalogError("items must be a nonempty array")
    required = {"item_id", "level", "skill_boost", "luck", "species"}
    parsed: list[StatusupItem] = []
    for item in value:
        if not isinstance(item, dict) or set(item) != required:
            raise StatusupCatalogError("each item must have the required fields")
        if any(type(item[name]) is not int for name in ("item_id", "level", "skill_boost", "luck")):
            raise StatusupCatalogError("status-up item numbers must be integers")
        species = item["species"]
        if species is not None and (type(species) is not int or species <= 0):
            raise StatusupCatalogError("item species must be a positive integer or null")
        if item["item_id"] <= 0 or min(item["level"], item["skill_boost"], item["luck"]) < 0:
            raise StatusupCatalogError("status-up item values are outside range")
        if item["level"] + item["skill_boost"] + item["luck"] <= 0:
            raise StatusupCatalogError("each status-up item must have an effect")
        parsed.append(StatusupItem(item["item_id"], item["level"], item["skill_boost"], item["luck"], species))
    ids = [item.item_id for item in parsed]
    if ids != sorted(ids) or len(ids) != len(set(ids)):
        raise StatusupCatalogError("items must be ordered and unique by item_id")
    return {item.item_id: item for item in parsed}


def _characters(value: object) -> dict[int, StatusupCharacter]:
    if not isinstance(value, list) or not value:
        raise StatusupCatalogError("characters must be a nonempty array")
    required = {"character_id", "species", "luck_cap"}
    parsed: list[StatusupCharacter] = []
    for character in value:
        if not isinstance(character, dict) or set(character) != required:
            raise StatusupCatalogError("each character must have the required fields")
        if any(type(character[name]) is not int or character[name] <= 0 for name in required):
            raise StatusupCatalogError("character values must be positive integers")
        parsed.append(StatusupCharacter(character["character_id"], character["species"], character["luck_cap"]))
    ids = [character.character_id for character in parsed]
    if ids != sorted(ids) or len(ids) != len(set(ids)):
        raise StatusupCatalogError("characters must be ordered and unique by character_id")
    return {character.character_id: character for character in parsed}


# The client's own inventory shape and caps: Skill Boost stops at 100.0 percent
# in tenths, job levels at 90.
BUNDLED_ITEM_SLOTS = ITEM_SLOTS
BUNDLED_LEVEL_CAP = 90
BUNDLED_SKILL_BOOST_CAP = 1000
# The final client's `statusUpItems` rows: level, displayed Skill Boost,
# displayed Luck, and the species a Machine-only item is gated on.  Displayed
# points are stored in tenths, which the server applies.
_BUNDLED_ITEMS: tuple[tuple[int, int, int, int, int | None], ...] = (
    (161, 1, 0, 0, None),
    (162, 0, 1, 0, None),
    (163, 0, 0, 1, None),
    (168, 0, 1, 0, 8),
    (175, 3, 0, 0, None),
    (176, 0, 3, 0, None),
    (177, 0, 0, 3, None),
)


def client_status_up_items(catalog: StatusupCatalog) -> dict[str, list[int]]:
    """Project one catalog into the client's own `statusUpItems` block.

    This is not decoration: it is the whole gate on whether a candy item can be
    used at all.  `UIChrSelectWindow.GetFilteredList` (ARM64 `0xEF4BEC`) keeps a
    character in the item-use list only when `CalcMaxUseNum` (`0xEF82BC`)
    returns at least one, and that method's first act is
    `UserData.statusUpItems.Contains(itemID.ToString())` -- a miss returns zero
    immediately.  `UserData.SetServerConstants` (`0x19D2A74`) fills that static
    from this key and substitutes an *empty* `JsonData` when the key is absent,
    so a server that never sends it leaves every candy item usable on nobody,
    with no error to explain it.

    The four values are read positionally: job levels, displayed Skill Boost
    percent, displayed Luck percent, and the species a Machine-only item is
    gated on, zero meaning no gate.  All four are required, because
    `IsStatusUpItemsDesignatedSpeciesImplemented` (`0x19D7348`) compares both
    advertised client versions against 4.99 and the status route advertises
    5.57; a three-value row makes the client read the species as 1000 and
    refuse every character.  They are also read through LitJson's *int*
    accessor, which throws on a JSON double -- the same trap `jobLevels` carries
    in the other direction.
    """
    return {
        str(item.item_id): [item.level, item.skill_boost, item.luck, item.species or 0]
        for item in catalog.items.values()
    }


def build_bundled_statusup_policy() -> StatusupCatalog:
    """Return the guided-path local status-up item policy.

    Item effects, the species gate, the level and Skill Boost caps, and the
    per-character Luck ceilings are recovered from the final client and are
    Confirmed.  Nothing here concerns how an item is obtained.
    """
    items = {
        item_id: StatusupItem(item_id, level, skill_boost, luck, species)
        for item_id, level, skill_boost, luck, species in _BUNDLED_ITEMS
    }
    characters = {
        character_id: StatusupCharacter(character_id, species, luck_cap)
        for character_id, species, luck_cap in STATUSUP_CHARACTER_ROWS
    }
    return StatusupCatalog(BUNDLED_ITEM_SLOTS, BUNDLED_LEVEL_CAP, BUNDLED_SKILL_BOOST_CAP, items, characters)
