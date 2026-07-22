"""Strict user-local Rebirth recipe input for a future atomic mutation route."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


class RebirthCatalogError(ValueError):
    """A user-local Rebirth catalog is invalid."""


@dataclass(frozen=True)
class RebirthRecipe:
    recipe_id: int
    source_character_id: int
    destination_character_id: int
    coins: int
    items: dict[int, int]
    materials: tuple[tuple[int, int], tuple[int, int]]


@dataclass(frozen=True)
class RebirthCatalog:
    item_slots: int
    joker_character_id: int
    recipes: dict[int, RebirthRecipe]


def load_rebirth_catalog(path: Path) -> RebirthCatalog:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RebirthCatalogError("could not read Rebirth catalog JSON") from error
    required = {"schema_version", "provenance", "item_slots", "joker_character_id", "recipes"}
    if not isinstance(document, dict) or set(document) != required:
        raise RebirthCatalogError("Rebirth catalog has an invalid schema")
    if document["schema_version"] != 1 or document["provenance"] != "user-supplied":
        raise RebirthCatalogError("Rebirth catalog requires schema version 1 and user-supplied provenance")
    if type(document["item_slots"]) is not int or document["item_slots"] <= 0:
        raise RebirthCatalogError("item_slots must be a positive integer")
    if type(document["joker_character_id"]) is not int or document["joker_character_id"] <= 0:
        raise RebirthCatalogError("joker_character_id must be a positive integer")
    raw = document["recipes"]
    if not isinstance(raw, list) or not raw:
        raise RebirthCatalogError("recipes must be a nonempty array")
    recipes = tuple(_recipe(value) for value in raw)
    ids = [recipe.recipe_id for recipe in recipes]
    if ids != sorted(ids) or len(ids) != len(set(ids)):
        raise RebirthCatalogError("recipes must be ordered and unique by recipe_id")
    return RebirthCatalog(document["item_slots"], document["joker_character_id"], {recipe.recipe_id: recipe for recipe in recipes})


def _recipe(value: object) -> RebirthRecipe:
    required = {"recipe_id", "source_character_id", "destination_character_id", "coins", "items", "materials"}
    if not isinstance(value, dict) or set(value) != required:
        raise RebirthCatalogError("each recipe must have the required fields")
    numeric = ("recipe_id", "source_character_id", "destination_character_id", "coins")
    if any(type(value[name]) is not int for name in numeric) or any(value[name] <= 0 for name in numeric[:3]) or value["coins"] < 0:
        raise RebirthCatalogError("recipe numeric fields are outside range")
    items = _counts(value["items"], "items")
    materials_raw = value["materials"]
    if not isinstance(materials_raw, list) or len(materials_raw) != 2:
        raise RebirthCatalogError("materials must contain exactly two requirements")
    materials: list[tuple[int, int]] = []
    for material in materials_raw:
        if not isinstance(material, dict) or set(material) != {"character_id", "level"} or type(material["character_id"]) is not int or type(material["level"]) is not int or material["character_id"] <= 0 or material["level"] <= 0:
            raise RebirthCatalogError("each material requires positive character_id and level")
        materials.append((material["character_id"], material["level"]))
    return RebirthRecipe(value["recipe_id"], value["source_character_id"], value["destination_character_id"], value["coins"], items, (materials[0], materials[1]))


def _counts(value: object, label: str) -> dict[int, int]:
    if not isinstance(value, dict):
        raise RebirthCatalogError(f"{label} must be an object")
    parsed: dict[int, int] = {}
    for raw_id, count in value.items():
        if not isinstance(raw_id, str) or not raw_id.isdecimal() or raw_id != str(int(raw_id)) or int(raw_id) <= 0 or type(count) is not int or count < 0:
            raise RebirthCatalogError(f"{label} require positive decimal IDs and nonnegative counts")
        parsed[int(raw_id)] = count
    return parsed
