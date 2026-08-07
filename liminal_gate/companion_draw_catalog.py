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

    def draws_for_kind(self, kind: int) -> tuple[CompanionDraw, ...]:
        """Return the pool this wire kind draws from.

        A user-supplied catalog carries one pool, the Energy-priced Rare one,
        so the Coin-priced Normal pool and its ticket variant stay unsupported
        rather than silently drawing from the wrong pool.
        """
        return self.draws if kind in {1, 21} else ()

    def cost_for_kind(self, kind: int) -> tuple[str, int] | None:
        return ("energy", self.energy_cost) if kind in {1, 21} else None

    def ticket_item_for_kind(self, kind: int) -> int | None:
        """Return the item that pays for this pool ahead of its currency."""
        return self.ticket_item_id if kind in {1, 21} else None


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
# `UIBarSlot.NormalSlotItemId`: the Fellowship Ticket pays for the Coin-priced
# Normal pool on both the character and the Companion page, while Item 112
# above pays only for the Companion Rare pool.  The Coin price is the same
# `NormalBuddySlotCoins` this bundle already sends in the constants block.
BUNDLED_NORMAL_TICKET_ITEM_ID = 81
BUNDLED_COIN_COST = 3000
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


# `SlotKind.Normal` (`kind == 1`) members of the same BuddyDatabase: 81 of its
# 497 records, split 41 C and 40 D on the rarity scale the Rare split above
# uses.  This is the pool the Coin-priced Companion draw and its Fellowship
# Ticket variant pull from; membership is recovered, the uniform weight is not
# a claim about retired odds.
_NORMAL_SLOT_IDS = (
    8, 14, 20, 26, 36, 37, 38, 68, 69, 70, 71, 83, 87, 88, 108, 109, 110,
    111, 131, 132, 133, 134, 135, 136, 137, 138, 139, 151, 152, 153, 154,
    155, 156, 157, 162, 163, 164, 165, 168, 169, 170, 171, 180, 181, 182,
    183, 184, 185, 186, 187, 188, 189, 190, 191, 192, 193, 194, 195, 196,
    197, 207, 208, 209, 210, 211, 212, 213, 214, 215, 225, 226, 227, 228,
    233, 234, 235, 236, 237, 238, 239, 240,
)


@dataclass(frozen=True)
class BundledCompanionDrawPolicy:
    """Local Companion draw policy used by the guided tester path.

    The client's Companion page offers both pools the retired service did: a
    Coin-priced Normal pull that the Fellowship Ticket also pays for, and an
    Energy-priced Rare pull that the Companion Ticket also pays for.  A
    user-supplied :class:`CompanionDrawCatalog` describes only the second, so
    the two shapes answer the same three questions and the route treats them
    alike.
    """

    item_slots: int
    ticket_item_id: int
    normal_ticket_item_id: int
    coin_cost: int
    energy_cost: int
    max_owned: int
    normal_draws: tuple[CompanionDraw, ...]
    rare_draws: tuple[CompanionDraw, ...]

    def draws_for_kind(self, kind: int) -> tuple[CompanionDraw, ...]:
        return self.normal_draws if kind in {0, 20} else self.rare_draws if kind in {1, 21} else ()

    def cost_for_kind(self, kind: int) -> tuple[str, int] | None:
        if kind in {0, 20}:
            return ("coins", self.coin_cost)
        return ("energy", self.energy_cost) if kind in {1, 21} else None

    def ticket_item_for_kind(self, kind: int) -> int | None:
        """Return the item that pays for this pool ahead of its currency."""
        if kind in {0, 20}:
            return self.normal_ticket_item_id
        return self.ticket_item_id if kind in {1, 21} else None


def build_bundled_companion_draw_policy() -> BundledCompanionDrawPolicy:
    """Return the guided-path local Companion draw policy.

    Pool membership, both ticket items, the displayed three-Energy fallback,
    the Coin price, and the Companion box ceiling are recovered from the final
    client.  Selection is uniform across each pool as an explicit local policy.
    The community record (Companions of Truth, terrabattle.fandom.com)
    transcribes the officially displayed base rates as Z 3%, SS 8%, S 10%,
    A 30%, B 49%, and the Rare pool's per-rarity counts above are known -- but
    the public bundle does not store which of the 114 IDs belongs to which
    class, so applying that table here would mean bundling an unrecovered
    membership map.  An operator who imports per-Companion rarity from their
    own BuddyDatabase can supply a weighted catalog through
    ``load_companion_draw_catalog`` instead; until then the uniform weight
    stays, deliberately not a claim about retired odds.
    """
    return BundledCompanionDrawPolicy(
        BUNDLED_ITEM_SLOTS, BUNDLED_TICKET_ITEM_ID, BUNDLED_NORMAL_TICKET_ITEM_ID,
        BUNDLED_COIN_COST, BUNDLED_ENERGY_COST, BUNDLED_MAX_OWNED,
        tuple(CompanionDraw(companion_id, 1) for companion_id in _NORMAL_SLOT_IDS),
        tuple(CompanionDraw(companion_id, 1) for companion_id in _RARE_SLOT_IDS),
    )
