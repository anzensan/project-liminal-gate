"""User-local Companion evolution recipes for the public compatibility server."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


class CompanionEvolutionCatalogError(ValueError):
    """A user-local Companion-evolution catalog is invalid."""


@dataclass(frozen=True)
class CompanionEvolution:
    source_companion_id: int
    destination_companion_id: int
    max_level: int
    coins: int
    items: dict[int, int]
    duplicate_source_count: int


@dataclass(frozen=True)
class CompanionEvolutionCatalog:
    item_slots: int
    recipes: dict[int, CompanionEvolution]


def load_companion_evolution_catalog(path: Path) -> CompanionEvolutionCatalog:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CompanionEvolutionCatalogError("could not read Companion-evolution catalog JSON") from error
    required = {"schema_version", "provenance", "item_slots", "recipes"}
    if not isinstance(document, dict) or set(document) != required:
        raise CompanionEvolutionCatalogError("Companion-evolution catalog has an invalid schema")
    if document["schema_version"] != 1 or document["provenance"] != "user-supplied":
        raise CompanionEvolutionCatalogError("Companion-evolution catalog requires schema version 1 and user-supplied provenance")
    if type(document["item_slots"]) is not int or document["item_slots"] <= 0:
        raise CompanionEvolutionCatalogError("item_slots must be a positive integer")
    raw_recipes = document["recipes"]
    if not isinstance(raw_recipes, list) or not raw_recipes:
        raise CompanionEvolutionCatalogError("recipes must be a nonempty array")
    recipes = tuple(_recipe(value) for value in raw_recipes)
    ids = [recipe.source_companion_id for recipe in recipes]
    if ids != sorted(ids) or len(ids) != len(set(ids)):
        raise CompanionEvolutionCatalogError("recipes must be ordered and unique by source_companion_id")
    return CompanionEvolutionCatalog(document["item_slots"], {recipe.source_companion_id: recipe for recipe in recipes})


def _recipe(value: object) -> CompanionEvolution:
    required = {"source_companion_id", "destination_companion_id", "max_level", "coins", "items", "duplicate_source_count"}
    if not isinstance(value, dict) or set(value) != required:
        raise CompanionEvolutionCatalogError("each evolution recipe must have the required fields")
    numeric = ("source_companion_id", "destination_companion_id", "max_level", "coins", "duplicate_source_count")
    if any(type(value[name]) is not int for name in numeric) or value["source_companion_id"] <= 0 or value["destination_companion_id"] <= 0 or value["max_level"] <= 0 or value["coins"] < 0 or value["duplicate_source_count"] < 0:
        raise CompanionEvolutionCatalogError("evolution recipe values are outside range")
    if not isinstance(value["items"], dict):
        raise CompanionEvolutionCatalogError("items must be an object")
    items: dict[int, int] = {}
    for raw_id, count in value["items"].items():
        if not isinstance(raw_id, str) or not raw_id.isdecimal() or raw_id != str(int(raw_id)) or int(raw_id) <= 0 or type(count) is not int or count < 0:
            raise CompanionEvolutionCatalogError("items require positive decimal IDs and nonnegative counts")
        items[int(raw_id)] = count
    return CompanionEvolution(value["source_companion_id"], value["destination_companion_id"], value["max_level"], value["coins"], items, value["duplicate_source_count"])
