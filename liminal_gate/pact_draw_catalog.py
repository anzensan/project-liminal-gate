"""User-local ordinary Pact pool, rates, and duplicate policy."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import tomllib


class PactDrawCatalogError(ValueError):
    """A user-local ordinary-Pact catalog is invalid."""


@dataclass(frozen=True)
class PactDraw:
    character_id: int
    weight: int
    duplicate_level_added: int
    duplicate_skill_boost: int


@dataclass(frozen=True)
class PactDrawCatalog:
    coin_cost: int
    new_level: int
    max_level: int
    max_skill_boost: int
    draws: tuple[PactDraw, ...]


def load_pact_draw_catalog(path: Path) -> PactDrawCatalog:
    try:
        document = tomllib.loads(path.read_text(encoding="utf-8")) if path.suffix.lower() == ".toml" else json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, tomllib.TOMLDecodeError) as error:
        raise PactDrawCatalogError("could not read ordinary-Pact catalog JSON or TOML") from error
    required = {"schema_version", "provenance", "coin_cost", "new_level", "max_level", "max_skill_boost", "draws"}
    if not isinstance(document, dict) or set(document) != required:
        raise PactDrawCatalogError("ordinary-Pact catalog has an invalid schema")
    if document["schema_version"] != 1 or document["provenance"] != "user-supplied":
        raise PactDrawCatalogError("ordinary-Pact catalog requires schema version 1 and user-supplied provenance")
    numeric = ("coin_cost", "new_level", "max_level", "max_skill_boost")
    if any(type(document[name]) is not int for name in numeric) or document["coin_cost"] <= 0 or document["new_level"] < 1 or document["max_level"] < document["new_level"] or document["max_skill_boost"] < 1:
        raise PactDrawCatalogError("ordinary-Pact numeric values are outside range")
    if not isinstance(document["draws"], list) or not document["draws"]:
        raise PactDrawCatalogError("draws must be a nonempty array")
    draws = tuple(_draw(value) for value in document["draws"])
    ids = [draw.character_id for draw in draws]
    if ids != sorted(ids) or len(ids) != len(set(ids)):
        raise PactDrawCatalogError("draws must be ordered and unique by character_id")
    return PactDrawCatalog(*(document[name] for name in numeric), draws)


def _draw(value: object) -> PactDraw:
    fields = {"character_id", "weight", "duplicate_level_added", "duplicate_skill_boost"}
    if not isinstance(value, dict) or set(value) != fields or any(type(value[name]) is not int for name in fields) or any(value[name] <= 0 for name in fields):
        raise PactDrawCatalogError("each draw requires positive character_id, weight, and duplicate gains")
    return PactDraw(value["character_id"], value["weight"], value["duplicate_level_added"], value["duplicate_skill_boost"])
