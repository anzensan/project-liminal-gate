"""User-local Companion progression values for a bounded strengthen route."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


class CompanionStrengthenCatalogError(ValueError):
    """A user-local Companion-strengthen catalog is invalid."""


@dataclass(frozen=True)
class CompanionProgressionMaster:
    companion_id: int
    base_exp: int
    max_level: int
    exp_max: int
    exp_coeff: float
    same_bonus_bias: int


@dataclass(frozen=True)
class CompanionStrengthenCatalog:
    masters: dict[int, CompanionProgressionMaster]
    same_companion_multiplier: int
    byebye_companion_id: int | None
    byebye_multiplier_percent: int
    bonus_weights: tuple[tuple[int, int], ...]


def load_companion_strengthen_catalog(path: Path) -> CompanionStrengthenCatalog:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CompanionStrengthenCatalogError("could not read Companion-strengthen catalog JSON") from error
    required = {"schema_version", "provenance", "masters", "same_companion_multiplier", "byebye_companion_id", "byebye_multiplier_percent", "bonus_weights"}
    if not isinstance(document, dict) or set(document) != required:
        raise CompanionStrengthenCatalogError("Companion-strengthen catalog has an invalid schema")
    if document["schema_version"] != 1 or document["provenance"] != "user-supplied":
        raise CompanionStrengthenCatalogError("Companion-strengthen catalog requires schema version 1 and user-supplied provenance")
    if type(document["same_companion_multiplier"]) is not int or document["same_companion_multiplier"] <= 0:
        raise CompanionStrengthenCatalogError("same_companion_multiplier must be a positive integer")
    byebye = document["byebye_companion_id"]
    if byebye is not None and (type(byebye) is not int or byebye <= 0):
        raise CompanionStrengthenCatalogError("byebye_companion_id must be null or a positive integer")
    if type(document["byebye_multiplier_percent"]) is not int or document["byebye_multiplier_percent"] <= 0:
        raise CompanionStrengthenCatalogError("byebye_multiplier_percent must be a positive integer")
    raw_masters = document["masters"]
    if not isinstance(raw_masters, list) or not raw_masters:
        raise CompanionStrengthenCatalogError("masters must be a nonempty array")
    masters = tuple(_master(value) for value in raw_masters)
    ids = [master.companion_id for master in masters]
    if ids != sorted(ids) or len(ids) != len(set(ids)):
        raise CompanionStrengthenCatalogError("masters must be ordered and unique by companion_id")
    raw_weights = document["bonus_weights"]
    if not isinstance(raw_weights, list) or not raw_weights:
        raise CompanionStrengthenCatalogError("bonus_weights must be a nonempty array")
    weights: list[tuple[int, int]] = []
    for value in raw_weights:
        if not isinstance(value, dict) or set(value) != {"percent", "weight"} or type(value["percent"]) is not int or type(value["weight"]) is not int or value["percent"] < 0 or value["weight"] <= 0:
            raise CompanionStrengthenCatalogError("each bonus weight requires nonnegative percent and positive weight")
        weights.append((value["percent"], value["weight"]))
    if [percent for percent, _ in weights] != sorted(percent for percent, _ in weights) or len({percent for percent, _ in weights}) != len(weights):
        raise CompanionStrengthenCatalogError("bonus weights must be ordered and unique by percent")
    return CompanionStrengthenCatalog({master.companion_id: master for master in masters}, document["same_companion_multiplier"], byebye, document["byebye_multiplier_percent"], tuple(weights))


def _master(value: object) -> CompanionProgressionMaster:
    required = {"companion_id", "base_exp", "max_level", "exp_max", "exp_coeff", "same_bonus_bias"}
    if not isinstance(value, dict) or set(value) != required:
        raise CompanionStrengthenCatalogError("each Companion progression master must have the required fields")
    integer_fields = ("companion_id", "base_exp", "max_level", "exp_max", "same_bonus_bias")
    if any(type(value[name]) is not int for name in integer_fields) or type(value["exp_coeff"]) not in {int, float}:
        raise CompanionStrengthenCatalogError("Companion progression fields have invalid types")
    if value["companion_id"] <= 0 or value["base_exp"] < 0 or not 1 <= value["max_level"] <= 99 or value["exp_max"] < 0 or value["exp_coeff"] <= 0 or value["same_bonus_bias"] <= 0:
        raise CompanionStrengthenCatalogError("Companion progression values are outside range")
    return CompanionProgressionMaster(value["companion_id"], value["base_exp"], value["max_level"], value["exp_max"], float(value["exp_coeff"]), value["same_bonus_bias"])
