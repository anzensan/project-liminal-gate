"""User-local Companion draw pool and local-cost policy."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import tomllib


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
