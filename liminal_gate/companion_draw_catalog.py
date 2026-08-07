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
# 114 of its 497 records, grouped here by the `BuddyData.rarity` each record
# carries.  Both fields are recovered from the same master object, and grouping
# the roster by class rather than listing it flat is what makes the two-way
# check structural: the per-class counts below are the counts the community
# record states for the pool, so a transcription error in either the membership
# or the rarity shows up as a group of the wrong size.
#
# `Rarity` is the same enum the character side uses -- D 2, C 3, B 4, A 5,
# S 6, SS 7, Z 8 -- so these keys mean the classes the client displays.
_RARE_SLOT_CLASSES: dict[str, tuple[int, ...]] = {
    "z": (
        303, 304, 305, 306, 307, 371, 372, 373, 374, 377, 378, 379,
        380, 410, 411, 412, 413, 414, 415,
    ),
    "ss": (
        3, 5, 13, 19, 25, 31, 45, 46, 47, 79, 80, 81, 82,
    ),
    "s": (
        4, 10, 16, 22, 28, 42, 43, 44, 49, 59, 60, 61, 62, 63, 64, 65,
        66, 67, 78, 89, 113, 122, 123, 124, 125, 127, 150, 158, 159,
        160, 161, 198, 199, 200, 201, 202, 203, 204, 205, 206, 229,
        230, 231, 232, 246, 247, 248, 249, 253, 259,
    ),
    "a": (
        2, 7, 11, 12, 17, 18, 23, 24, 29, 30, 32, 33, 34, 35, 48, 84,
        85, 86, 100, 102, 104, 106, 112, 114, 115, 116, 117, 126, 167,
        252,
    ),
    "b": (
        1, 6,
    ),
}
_RARE_SLOT_IDS = tuple(sorted(
    companion_id for companion_ids in _RARE_SLOT_CLASSES.values() for companion_id in companion_ids
))

# Rare-pool class shares, in parts per million of one pull.  These are the base
# rates the service displayed in-game from 2018-02-28, as the community record
# transcribes them on the Companions of Truth page: Z 3%, SS 8%, S 10%, A 30%,
# B 49%.  Same evidence class as the Pact of Truth shares in
# :mod:`liminal_gate.pact_draw_catalog` -- community record of a displayed
# figure, with no APK table to cross-validate, because the retired server owned
# pool selection entirely.  The client's only rate-related symbol for this pool
# is the Energy cost this bundle already sends.
#
# What the display had that this table does not is a per-Companion rate.
# Splitting a class's share evenly across its own members is the only reading
# the source supports, and it is the same choice the Pact shares document.
#
# Weighting matters more here than the flat weight it replaces suggests: the
# pool is lopsided the opposite way from the rates.  Half its members are S and
# only two are B, so a uniform draw returns Z at 16.7% against a displayed 3%
# and B at 1.8% against a displayed 49% -- inverting the two commonest outcomes.
_RARE_CLASS_SHARE_PPM = {
    "z": 30_000,
    "ss": 80_000,
    "s": 100_000,
    "a": 300_000,
    "b": 490_000,
}
_WEIGHT_SCALE = 1_000_000


# `SlotKind.Normal` (`kind == 1`) members of the same BuddyDatabase: 81 of its
# 497 records, split 41 C and 40 D on the rarity scale the Rare groups above
# use.  This is the pool the Coin-priced Companion draw and its Fellowship
# Ticket variant pull from; membership is recovered, and this pool stays
# uniform deliberately.  No displayed-rate record was found for it -- the
# Companions of Truth page documents the Rare pool only -- and a two-class pool
# that a uniform draw already splits near evenly is not worth inventing a table
# for.  Weighting Rare and not Normal is the same asymmetry the Pact policy
# carries between Truth and Fellowship, for the same reason.
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


def _rare_weights() -> dict[int, int]:
    """Split each Rare class's displayed share evenly across its own members.

    The scale factor keeps the smallest share an integer with room to spare:
    the narrowest split, Z across nineteen members, still lands near 1.6e9, so
    the floor division loses parts per billion rather than anything a draw
    could observe.
    """
    weights: dict[int, int] = {}
    for name, companion_ids in _RARE_SLOT_CLASSES.items():
        share = _RARE_CLASS_SHARE_PPM[name] * _WEIGHT_SCALE // len(companion_ids)
        for companion_id in companion_ids:
            weights[companion_id] = max(share, 1)
    return weights


def build_bundled_companion_draw_policy() -> BundledCompanionDrawPolicy:
    """Return the guided-path local Companion draw policy.

    Pool membership, per-Companion rarity, both ticket items, the displayed
    three-Energy fallback, the Coin price, and the Companion box ceiling are
    recovered from the final client.  Rare-pool selection follows the displayed
    class shares documented above; the even split within a class, and the
    Normal pool's uniform selection, are local policy rather than claims about
    retired odds.
    """
    rare_weights = _rare_weights()
    return BundledCompanionDrawPolicy(
        BUNDLED_ITEM_SLOTS, BUNDLED_TICKET_ITEM_ID, BUNDLED_NORMAL_TICKET_ITEM_ID,
        BUNDLED_COIN_COST, BUNDLED_ENERGY_COST, BUNDLED_MAX_OWNED,
        tuple(CompanionDraw(companion_id, 1) for companion_id in _NORMAL_SLOT_IDS),
        tuple(CompanionDraw(companion_id, rare_weights[companion_id]) for companion_id in _RARE_SLOT_IDS),
    )
