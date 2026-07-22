"""User-local Companion master values for bounded ownership mutations."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


class CompanionCatalogError(ValueError):
    """A user-local Companion catalog is invalid."""


@dataclass(frozen=True)
class CompanionMaster:
    companion_id: int
    base_coins: int


@dataclass(frozen=True)
class CompanionCatalog:
    coin_cap: int
    masters: dict[int, CompanionMaster]


def load_companion_catalog(path: Path) -> CompanionCatalog:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CompanionCatalogError("could not read Companion catalog JSON") from error
    required = {"schema_version", "provenance", "coin_cap", "masters"}
    if not isinstance(document, dict) or set(document) != required:
        raise CompanionCatalogError("Companion catalog has an invalid schema")
    if document["schema_version"] != 1 or document["provenance"] != "user-supplied":
        raise CompanionCatalogError("Companion catalog requires schema version 1 and user-supplied provenance")
    if type(document["coin_cap"]) is not int or document["coin_cap"] < 0:
        raise CompanionCatalogError("coin_cap must be a nonnegative integer")
    raw_masters = document["masters"]
    if not isinstance(raw_masters, list) or not raw_masters:
        raise CompanionCatalogError("masters must be a nonempty array")
    masters = tuple(_master(value) for value in raw_masters)
    ids = [master.companion_id for master in masters]
    if ids != sorted(ids) or len(ids) != len(set(ids)):
        raise CompanionCatalogError("masters must be ordered and unique by companion_id")
    return CompanionCatalog(document["coin_cap"], {master.companion_id: master for master in masters})


def _master(value: object) -> CompanionMaster:
    required = {"companion_id", "base_coins"}
    if not isinstance(value, dict) or set(value) != required:
        raise CompanionCatalogError("each Companion master must have the required fields")
    if any(type(value[name]) is not int for name in required):
        raise CompanionCatalogError("Companion master fields must be integers")
    if value["companion_id"] <= 0 or value["base_coins"] < 0:
        raise CompanionCatalogError("Companion master values are outside range")
    return CompanionMaster(value["companion_id"], value["base_coins"])
