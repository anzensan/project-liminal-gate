"""User-local Companion draw pool and local-cost policy."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import tomllib

from liminal_gate.save_validation import ITEM_SLOTS


class CompanionDrawCatalogError(ValueError):
    """A user-local Companion-draw catalog is invalid."""


@dataclass(frozen=True)
class CompanionDraw:
    companion_id: int
    weight: int


@dataclass(frozen=True)
class CompanionDrawCatalog:
    item_slots: int
    ticket_item_id: int
    energy_cost: int
    max_owned: int
    draws: tuple[CompanionDraw, ...]


def load_companion_draw_catalog(path: Path) -> CompanionDrawCatalog:
    try:
        document = tomllib.loads(path.read_text(encoding="utf-8")) if path.suffix.lower() == ".toml" else json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, tomllib.TOMLDecodeError) as error:
        raise CompanionDrawCatalogError("could not read Companion-draw catalog JSON or TOML") from error
    required = {"schema_version", "provenance", "item_slots", "ticket_item_id", "energy_cost", "max_owned", "draws"}
    if not isinstance(document, dict) or set(document) != required:
        raise CompanionDrawCatalogError("Companion-draw catalog has an invalid schema")
    if document["schema_version"] != 1 or document["provenance"] != "user-supplied":
        raise CompanionDrawCatalogError("Companion-draw catalog requires schema version 1 and user-supplied provenance")
    numeric = ("item_slots", "ticket_item_id", "energy_cost", "max_owned")
    if any(type(document[name]) is not int for name in numeric) or document["item_slots"] <= 0 or not 1 <= document["ticket_item_id"] <= document["item_slots"] or document["energy_cost"] <= 0 or document["max_owned"] <= 0:
        raise CompanionDrawCatalogError("Companion-draw numeric values are outside range")
    raw_draws = document["draws"]
    if not isinstance(raw_draws, list) or not raw_draws:
        raise CompanionDrawCatalogError("draws must be a nonempty array")
    draws = tuple(_draw(value) for value in raw_draws)
    ids = [draw.companion_id for draw in draws]
    if ids != sorted(ids) or len(ids) != len(set(ids)):
        raise CompanionDrawCatalogError("draws must be ordered and unique by companion_id")
    return CompanionDrawCatalog(document["item_slots"], document["ticket_item_id"], document["energy_cost"], document["max_owned"], draws)


def _draw(value: object) -> CompanionDraw:
    if not isinstance(value, dict) or set(value) != {"companion_id", "weight"} or type(value["companion_id"]) is not int or type(value["weight"]) is not int or value["companion_id"] <= 0 or value["weight"] <= 0:
        raise CompanionDrawCatalogError("each draw requires a positive companion_id and weight")
    return CompanionDraw(value["companion_id"], value["weight"])


# The client's inventory shape, its Companion Ticket master item, the displayed
# Energy fallback, and the Companion box ceiling.
BUNDLED_ITEM_SLOTS = ITEM_SLOTS
BUNDLED_TICKET_ITEM_ID = 112
BUNDLED_ENERGY_COST = 3
BUNDLED_MAX_OWNED = 1000
# `SlotKind.Rare` (`kind == 2`) members of the final client's BuddyDatabase:
# 114 of its 497 records, split 19 Z, 13 SS, 50 S, 30 A, 2 B.  Membership is
# recovered; the uniform weight below is not a claim about retired odds.
_RARE_SLOT_IDS = (
    1, 2, 3, 4, 5, 6, 7, 10, 11, 12, 13, 16, 17, 18, 19, 22, 23, 24, 25, 28,
    29, 30, 31, 32, 33, 34, 35, 42, 43, 44, 45, 46, 47, 48, 49, 59, 60, 61,
    62, 63, 64, 65, 66, 67, 78, 79, 80, 81, 82, 84, 85, 86, 89, 100, 102,
    104, 106, 112, 113, 114, 115, 116, 117, 122, 123, 124, 125, 126, 127,
    150, 158, 159, 160, 161, 167, 198, 199, 200, 201, 202, 203, 204, 205,
    206, 229, 230, 231, 232, 246, 247, 248, 249, 252, 253, 259, 303, 304,
    305, 306, 307, 371, 372, 373, 374, 377, 378, 379, 380, 410, 411, 412,
    413, 414, 415,
)


def build_bundled_companion_draw_policy() -> CompanionDrawCatalog:
    """Return the guided-path local Companion draw policy.

    Pool membership, the ticket item, the displayed three-Energy fallback, and
    the Companion box ceiling are recovered from the final client.  Selection
    is uniform across the pool as an explicit local policy.  The community
    record (Companions of Truth, terrabattle.fandom.com) transcribes the
    officially displayed base rates as Z 3%, SS 8%, S 10%, A 30%, B 49%, and
    the pool's per-rarity counts above are known -- but the public bundle does
    not store which of the 114 IDs belongs to which class, so applying that
    table here would mean bundling an unrecovered membership map.  An operator
    who imports per-Companion rarity from their own BuddyDatabase can supply a
    weighted catalog through ``load_companion_draw_catalog`` instead; until
    then the uniform weight stays, deliberately not a claim about retired odds.
    """
    return CompanionDrawCatalog(
        BUNDLED_ITEM_SLOTS, BUNDLED_TICKET_ITEM_ID, BUNDLED_ENERGY_COST, BUNDLED_MAX_OWNED,
        tuple(CompanionDraw(companion_id, 1) for companion_id in _RARE_SLOT_IDS),
    )
