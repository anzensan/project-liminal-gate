"""Derive a minimal local character catalog from a user-owned reviewed APK.

The catalog is an ignored local projection.  It deliberately contains no
localized names, profiles, images, skills, event schedule, or acquisition
rules.  Those are separate compatibility boundaries.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any
import zipfile


APK_DATA_MEMBER = "assets/bin/Data/data.unity3d"
SERIALIZED_FILE = "resources.assets"
CHR_DATABASE_PATH_ID = 12688
SCHEMA_VERSION = 1
SOURCE_PROFILE = "terra-battle-android-5.5.7-170"


class CharacterCatalogImportError(ValueError):
    """A local APK or its locally generated type trees cannot be decoded."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def load_character_master_tree(apk: Path, dummy_dll_dir: Path) -> dict[str, Any]:
    """Load the reviewed APK's ChrDatabase using locally generated type trees."""
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
        with tempfile.TemporaryDirectory() as directory:
            data_file = Path(directory) / "data.unity3d"
            data_file.write_bytes(payload)
            environment = UnityPy.load(str(data_file))
            generator = TypeTreeGenerator("2017.4.37f1")
            for dll in dlls:
                generator.load_dll(dll.read_bytes())
            environment.typetree_generator = generator
            matches = [
                obj for obj in environment.objects
                if obj.assets_file.name == SERIALIZED_FILE and obj.path_id == CHR_DATABASE_PATH_ID
            ]
            if len(matches) != 1:
                raise CharacterCatalogImportError(f"expected one ChrDatabase object, found {len(matches)}")
            tree = matches[0].parse_as_dict(check_read=True)
    except CharacterCatalogImportError:
        raise
    except Exception as error:
        raise CharacterCatalogImportError("could not parse ChrDatabase with local type trees") from error
    if not isinstance(tree, dict):
        raise CharacterCatalogImportError("ChrDatabase did not decode to an object")
    return tree


def write_character_catalog(path: Path, document: dict[str, object]) -> None:
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
