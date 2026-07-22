"""User-local ordered job-unlock costs for the public compatibility server."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


class JobCatalogError(ValueError):
    """A user-local job catalog is invalid."""


@dataclass(frozen=True)
class JobUnlock:
    character_id: int
    job_index: int
    coins: int
    materials: dict[int, int]


@dataclass(frozen=True)
class JobCatalog:
    item_slots: int
    unlocks: dict[tuple[int, int], JobUnlock]


def load_job_catalog(path: Path) -> JobCatalog:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise JobCatalogError("could not read job catalog JSON") from error
    required = {"schema_version", "provenance", "item_slots", "unlocks"}
    if not isinstance(document, dict) or set(document) != required:
        raise JobCatalogError("job catalog has an invalid schema")
    if document["schema_version"] != 1 or document["provenance"] != "user-supplied":
        raise JobCatalogError("job catalog requires schema version 1 and user-supplied provenance")
    if type(document["item_slots"]) is not int or document["item_slots"] <= 0:
        raise JobCatalogError("item_slots must be a positive integer")
    raw_unlocks = document["unlocks"]
    if not isinstance(raw_unlocks, list) or not raw_unlocks:
        raise JobCatalogError("unlocks must be a nonempty array")
    unlocks = tuple(_unlock(value) for value in raw_unlocks)
    identities = [(unlock.character_id, unlock.job_index) for unlock in unlocks]
    if identities != sorted(identities) or len(identities) != len(set(identities)):
        raise JobCatalogError("unlocks must be ordered and unique by character_id/job_index")
    for character_id in {unlock.character_id for unlock in unlocks}:
        indexes = [unlock.job_index for unlock in unlocks if unlock.character_id == character_id]
        if indexes != list(range(1, len(indexes) + 1)):
            raise JobCatalogError("each character's job indexes must start at 1 and be consecutive")
    return JobCatalog(document["item_slots"], {(unlock.character_id, unlock.job_index): unlock for unlock in unlocks})


def _unlock(value: object) -> JobUnlock:
    required = {"character_id", "job_index", "coins", "materials"}
    if not isinstance(value, dict) or set(value) != required:
        raise JobCatalogError("each unlock must have the required fields")
    if any(type(value[name]) is not int for name in ("character_id", "job_index", "coins")):
        raise JobCatalogError("unlock numeric fields must be integers")
    if value["character_id"] <= 0 or value["job_index"] <= 0 or value["coins"] < 0:
        raise JobCatalogError("unlock values are outside range")
    materials = value["materials"]
    if not isinstance(materials, dict):
        raise JobCatalogError("materials must be an object")
    parsed: dict[int, int] = {}
    for raw_id, count in materials.items():
        if not isinstance(raw_id, str) or not raw_id.isdecimal() or raw_id != str(int(raw_id)) or int(raw_id) <= 0 or type(count) is not int or count < 0:
            raise JobCatalogError("materials require positive decimal IDs and nonnegative counts")
        parsed[int(raw_id)] = count
    return JobUnlock(value["character_id"], value["job_index"], value["coins"], parsed)
