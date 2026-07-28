"""Generate and load source-free Companion equipment restrictions.

The catalog projects only character ancestry, active-job species, and the two
restriction fields read by ``Buddy.CanEquip``. It is derived from the
operator's own final APK and remains in the ignored local data directory.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile
from typing import Any


SCHEMA_VERSION = 1
SOURCE_PROFILE = "terra-battle-android-5.5.7-170"
DEFAULT_COMPANION_EQUIPMENT_CATALOG = "companion-equipment.json"


class CompanionEquipmentCatalogError(ValueError):
    """A derived Companion equipment catalog is incomplete or invalid."""


@dataclass(frozen=True)
class CharacterEquipmentMaster:
    character_id: int
    ancestor_character_id: int
    job_species: tuple[int, ...]


@dataclass(frozen=True)
class CompanionEquipmentMaster:
    companion_id: int
    exclusive_character_id: int
    exclusive_species_id: int


@dataclass(frozen=True)
class CompanionEquipmentCatalog:
    apk_sha256: str
    characters: dict[int, CharacterEquipmentMaster]
    companions: dict[int, CompanionEquipmentMaster]


def build_companion_equipment_catalog(
    character_tree: dict[str, Any],
    companion_tree: dict[str, Any],
    apk_sha256: str,
) -> dict[str, object]:
    """Project the exact master fields needed to authorize a new equip link."""
    infos = character_tree.get("infos")
    jobs = character_tree.get("data")
    companions = companion_tree.get("data")
    if not isinstance(infos, list) or not infos:
        raise CompanionEquipmentCatalogError(
            "ChrDatabase must contain a nonempty infos array"
        )
    if not isinstance(jobs, list) or not jobs:
        raise CompanionEquipmentCatalogError(
            "ChrDatabase must contain a nonempty data array"
        )
    if not isinstance(companions, list) or not companions:
        raise CompanionEquipmentCatalogError(
            "BuddyDatabase must contain a nonempty data array"
        )
    if not _valid_sha256(apk_sha256):
        raise CompanionEquipmentCatalogError("APK SHA-256 must be lowercase hexadecimal")

    job_species: dict[int, int] = {}
    for record in jobs:
        if (
            not isinstance(record, dict)
            or type(record.get("ID")) is not int
            or record["ID"] <= 0
            or type(record.get("Species")) is not int
            or record["Species"] <= 0
            or record["ID"] in job_species
        ):
            raise CompanionEquipmentCatalogError(
                "ChrDatabase jobs require unique positive IDs and species"
            )
        job_species[record["ID"]] = record["Species"]

    character_rows: list[dict[str, int | list[int]]] = []
    character_ids: set[int] = set()
    for record in infos:
        if (
            not isinstance(record, dict)
            or type(record.get("ID")) is not int
            or record["ID"] <= 0
            or record["ID"] in character_ids
            or type(record.get("ancestorChrID")) is not int
            or record["ancestorChrID"] < 0
            or not isinstance(record.get("Jobs"), list)
            or not record["Jobs"]
            or any(type(job_id) is not int or job_id <= 0 for job_id in record["Jobs"])
            or len(record["Jobs"]) != len(set(record["Jobs"]))
        ):
            raise CompanionEquipmentCatalogError(
                "ChrDatabase characters have invalid identity, ancestor, or job fields"
            )
        try:
            species = [job_species[job_id] for job_id in record["Jobs"]]
        except KeyError as error:
            raise CompanionEquipmentCatalogError(
                "ChrDatabase character references an unknown job"
            ) from error
        character_ids.add(record["ID"])
        character_rows.append(
            {
                "character_id": record["ID"],
                "ancestor_character_id": record["ancestorChrID"],
                "job_species": species,
            }
        )
    character_rows.sort(key=lambda record: int(record["character_id"]))
    if any(
        row["ancestor_character_id"] != 0
        and row["ancestor_character_id"] not in character_ids
        for row in character_rows
    ):
        raise CompanionEquipmentCatalogError(
            "ChrDatabase character ancestor does not resolve"
        )

    companion_rows: list[dict[str, int]] = []
    companion_ids: set[int] = set()
    known_species = set(job_species.values())
    for record in companions:
        fields = ("ID", "exclusiveChrID", "exclusiveSpeciesID")
        if (
            not isinstance(record, dict)
            or any(type(record.get(field)) is not int for field in fields)
            or record["ID"] <= 0
            or record["ID"] in companion_ids
            or record["exclusiveChrID"] < 0
            or record["exclusiveSpeciesID"] < 0
        ):
            raise CompanionEquipmentCatalogError(
                "BuddyDatabase restrictions require unique IDs and nonnegative values"
            )
        if (
            record["exclusiveChrID"] != 0
            and record["exclusiveChrID"] not in character_ids
        ):
            raise CompanionEquipmentCatalogError(
                "BuddyDatabase restriction references an unknown character"
            )
        if (
            record["exclusiveSpeciesID"] != 0
            and record["exclusiveSpeciesID"] not in known_species
        ):
            raise CompanionEquipmentCatalogError(
                "BuddyDatabase restriction references an unknown species"
            )
        companion_ids.add(record["ID"])
        companion_rows.append(
            {
                "companion_id": record["ID"],
                "exclusive_character_id": record["exclusiveChrID"],
                "exclusive_species_id": record["exclusiveSpeciesID"],
            }
        )
    companion_rows.sort(key=lambda record: record["companion_id"])

    return {
        "schema_version": SCHEMA_VERSION,
        "provenance": "user-derived",
        "source": {
            "profile": SOURCE_PROFILE,
            "apk_sha256": apk_sha256,
        },
        "characters": character_rows,
        "companions": companion_rows,
    }


def load_companion_equipment_catalog(path: Path) -> CompanionEquipmentCatalog:
    """Load a strictly shaped generated equipment catalog."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CompanionEquipmentCatalogError(
            "could not read Companion equipment catalog JSON"
        ) from error
    required = {
        "schema_version", "provenance", "source", "characters", "companions",
    }
    if not isinstance(document, dict) or set(document) != required:
        raise CompanionEquipmentCatalogError(
            "Companion equipment catalog has an invalid schema"
        )
    if (
        document["schema_version"] != SCHEMA_VERSION
        or document["provenance"] != "user-derived"
    ):
        raise CompanionEquipmentCatalogError(
            "Companion equipment catalog requires schema version 1 and user-derived provenance"
        )
    source = document["source"]
    if (
        not isinstance(source, dict)
        or set(source) != {"profile", "apk_sha256"}
        or source["profile"] != SOURCE_PROFILE
        or not _valid_sha256(source["apk_sha256"])
    ):
        raise CompanionEquipmentCatalogError(
            "Companion equipment catalog has invalid source provenance"
        )

    raw_characters = document["characters"]
    raw_companions = document["companions"]
    if not isinstance(raw_characters, list) or not raw_characters:
        raise CompanionEquipmentCatalogError("characters must be a nonempty array")
    if not isinstance(raw_companions, list) or not raw_companions:
        raise CompanionEquipmentCatalogError("companions must be a nonempty array")
    characters = tuple(_character(value) for value in raw_characters)
    companions = tuple(_companion(value) for value in raw_companions)
    character_ids = [record.character_id for record in characters]
    companion_ids = [record.companion_id for record in companions]
    if (
        character_ids != sorted(character_ids)
        or len(character_ids) != len(set(character_ids))
    ):
        raise CompanionEquipmentCatalogError(
            "characters must be ordered and unique by character_id"
        )
    if (
        companion_ids != sorted(companion_ids)
        or len(companion_ids) != len(set(companion_ids))
    ):
        raise CompanionEquipmentCatalogError(
            "companions must be ordered and unique by companion_id"
        )
    character_id_set = set(character_ids)
    known_species = {
        species
        for character in characters
        for species in character.job_species
    }
    if any(
        character.ancestor_character_id
        and character.ancestor_character_id not in character_id_set
        for character in characters
    ):
        raise CompanionEquipmentCatalogError("character ancestor does not resolve")
    if any(
        companion.exclusive_character_id
        and companion.exclusive_character_id not in character_id_set
        for companion in companions
    ):
        raise CompanionEquipmentCatalogError(
            "Companion restriction references an unknown character"
        )
    if any(
        companion.exclusive_species_id
        and companion.exclusive_species_id not in known_species
        for companion in companions
    ):
        raise CompanionEquipmentCatalogError(
            "Companion restriction references an unknown species"
        )
    return CompanionEquipmentCatalog(
        source["apk_sha256"],
        {record.character_id: record for record in characters},
        {record.companion_id: record for record in companions},
    )


def _character(value: object) -> CharacterEquipmentMaster:
    required = {"character_id", "ancestor_character_id", "job_species"}
    if not isinstance(value, dict) or set(value) != required:
        raise CompanionEquipmentCatalogError(
            "each character equipment master must have the required fields"
        )
    species = value["job_species"]
    if (
        type(value["character_id"]) is not int
        or value["character_id"] <= 0
        or type(value["ancestor_character_id"]) is not int
        or value["ancestor_character_id"] < 0
        or not isinstance(species, list)
        or not species
        or any(type(item) is not int or item <= 0 for item in species)
    ):
        raise CompanionEquipmentCatalogError(
            "character equipment master values are outside range"
        )
    return CharacterEquipmentMaster(
        value["character_id"],
        value["ancestor_character_id"],
        tuple(species),
    )


def _companion(value: object) -> CompanionEquipmentMaster:
    required = {
        "companion_id", "exclusive_character_id", "exclusive_species_id",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise CompanionEquipmentCatalogError(
            "each Companion equipment master must have the required fields"
        )
    if (
        any(type(value[field]) is not int for field in required)
        or value["companion_id"] <= 0
        or value["exclusive_character_id"] < 0
        or value["exclusive_species_id"] < 0
    ):
        raise CompanionEquipmentCatalogError(
            "Companion equipment master values are outside range"
        )
    return CompanionEquipmentMaster(
        value["companion_id"],
        value["exclusive_character_id"],
        value["exclusive_species_id"],
    )


def write_companion_equipment_catalog(
    path: Path, document: dict[str, object],
) -> None:
    """Write the generated catalog atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _valid_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
