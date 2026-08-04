"""Derive a minimal local character catalog from a user-owned reviewed APK.

The catalog is an ignored local projection.  It deliberately contains no
localized names, profiles, images, skills, event schedule, or acquisition
rules.  Those are separate compatibility boundaries.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any
import zipfile

from liminal_gate.file_digests import sha256_file
from liminal_gate.reviewed_build import APK_DATA_MEMBER, SOURCE_PROFILE
from liminal_gate.atomic_json import write_json_document


SERIALIZED_FILE = "resources.assets"
CHR_DATABASE_PATH_ID = 12688
SCHEMA_VERSION = 1


class CharacterCatalogImportError(ValueError):
    """A local APK or its locally generated type trees cannot be decoded."""


def build_character_catalog(tree: dict[str, Any], apk_sha256: str) -> dict[str, object]:
    """Project only stable character identity and structural eligibility fields."""
    infos = tree.get("infos")
    if not isinstance(infos, list) or not infos:
        raise CharacterCatalogImportError("ChrDatabase must contain a nonempty infos array")
    characters: list[dict[str, int | bool | list[int]]] = []
    seen: set[int] = set()
    for record in infos:
        fields = ("ID", "chrType", "isLambda", "rebirthFromID", "rarity", "Jobs")
        if not isinstance(record, dict) or any(field not in record for field in fields):
            raise CharacterCatalogImportError("ChrDatabase character has missing required fields")
        numeric = ("ID", "chrType", "isLambda", "rebirthFromID", "rarity")
        if any(type(record[field]) is not int for field in numeric):
            raise CharacterCatalogImportError("ChrDatabase character has invalid numeric fields")
        character_id = record["ID"]
        if character_id <= 0 or character_id in seen:
            raise CharacterCatalogImportError("ChrDatabase character IDs must be positive and unique")
        jobs = record["Jobs"]
        if not isinstance(jobs, list) or not jobs or any(type(job) is not int or job <= 0 for job in jobs):
            raise CharacterCatalogImportError("ChrDatabase character has invalid job IDs")
        seen.add(character_id)
        characters.append({
            "character_id": character_id,
            "character_type": record["chrType"],
            "is_lambda": bool(record["isLambda"]),
            "rebirth_from_id": record["rebirthFromID"],
            "rarity": record["rarity"],
            "job_ids": list(jobs),
        })
    characters.sort(key=lambda record: int(record["character_id"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "provenance": "user-derived",
        "source": {"profile": SOURCE_PROFILE, "apk_sha256": apk_sha256},
        "characters": characters,
    }


#: The master-data objects this importer can read, by serialized path id. They
#: share one `data.unity3d` load, because building the type trees is the slow
#: part and doing it once per object would trebled it.
MASTER_PATH_IDS = {
    "ChrDatabase": CHR_DATABASE_PATH_ID, "ItemSet": 12695, "BuddyDatabase": 13474,
    # `BattleData` duplicates :mod:`liminal_gate.battledata_importer`'s own load.
    # It is listed here so a caller that needs stage rows *and* another master
    # object pays for the type-tree build once instead of twice.
    "BattleData": 12684, "EnemyData": 12693,
}


def load_master_trees(apk: Path, dummy_dll_dir: Path, names: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    """Load several reviewed master-data objects in one pass."""
    unknown = [name for name in names if name not in MASTER_PATH_IDS]
    if unknown:
        raise CharacterCatalogImportError(f"unknown master-data object(s): {', '.join(unknown)}")
    return _load_trees(apk, dummy_dll_dir, {name: MASTER_PATH_IDS[name] for name in names})


def load_character_master_tree(apk: Path, dummy_dll_dir: Path) -> dict[str, Any]:
    """Load the reviewed APK's ChrDatabase using locally generated type trees."""
    return load_master_trees(apk, dummy_dll_dir, ("ChrDatabase",))["ChrDatabase"]


def _load_trees(apk: Path, dummy_dll_dir: Path, path_ids: dict[str, int]) -> dict[str, Any]:
    """Read the named serialized objects out of one loaded data.unity3d."""
    try:
        import UnityPy
        from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator
    except ImportError as error:
        raise CharacterCatalogImportError(
            "character catalog import requires UnityPy==1.25.2 and TypeTreeGeneratorAPI==0.0.10; "
            "install the master-import optional dependency"
        ) from error
    try:
        apk = apk.resolve(strict=True)
        dlls = sorted(dummy_dll_dir.resolve(strict=True).glob("*.dll"))
    except OSError as error:
        raise CharacterCatalogImportError("APK or local dummy-DLL directory is unavailable") from error
    if not dlls:
        raise CharacterCatalogImportError("dummy-DLL directory contains no local .dll files")
    try:
        with zipfile.ZipFile(apk) as archive:
            payload = archive.read(APK_DATA_MEMBER)
    except (OSError, KeyError, zipfile.BadZipFile) as error:
        raise CharacterCatalogImportError("APK does not contain the reviewed data.unity3d member") from error
    try:
        # From memory, not from a staged file: a temporary file the reader
        # still holds cannot be removed on Windows, which fails the import at
        # cleanup after the work has succeeded.
        environment = UnityPy.load(payload)
        generator = TypeTreeGenerator("2017.4.37f1")
        for dll in dlls:
            generator.load_dll(dll.read_bytes())
        environment.typetree_generator = generator
        trees: dict[str, Any] = {}
        for label, path_id in path_ids.items():
            matches = [
                obj for obj in environment.objects
                if obj.assets_file.name == SERIALIZED_FILE and obj.path_id == path_id
            ]
            if len(matches) != 1:
                raise CharacterCatalogImportError(f"expected one {label} object, found {len(matches)}")
            trees[label] = matches[0].parse_as_dict(check_read=True)
    except CharacterCatalogImportError:
        raise
    except Exception as error:
        raise CharacterCatalogImportError(
            f"could not parse master data with local type trees: {type(error).__name__}: {error}"
        ) from error
    for label, tree in trees.items():
        if not isinstance(tree, dict):
            raise CharacterCatalogImportError(f"{label} did not decode to an object")
    return trees


def write_character_catalog(path: Path, document: dict[str, object]) -> None:
    write_json_document(path, document, indent=2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apk", required=True, type=Path)
    parser.add_argument("--dummy-dll-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        apk = args.apk.resolve(strict=True)
        document = build_character_catalog(load_character_master_tree(apk, args.dummy_dll_dir), sha256_file(apk))
        write_character_catalog(args.output, document)
    except (CharacterCatalogImportError, OSError) as error:
        raise SystemExit(f"character catalog import failed: {error}") from error
    print(f"wrote local character catalog: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
