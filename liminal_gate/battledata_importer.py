"""Derive local stage metadata from a user-owned reviewed Android APK.

The output is an ignored, local projection.  It contains no bundled game data
and deliberately omits localized text, reward lists, images, and battle assets.
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
BATTLE_DATA_PATH_ID = 12684
SCHEMA_VERSION = 1
SOURCE_PROFILE = "terra-battle-android-5.5.7-170"


class BattleDataImportError(ValueError):
    """A local APK or its locally derived type trees cannot be decoded safely."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_stage_metadata(tree: dict[str, Any], apk_sha256: str) -> dict[str, object]:
    """Project typed BattleData into a compact, local-only stage catalog."""
    chapters = tree.get("chapters")
    if not isinstance(chapters, list) or not chapters:
        raise BattleDataImportError("BattleData must contain a nonempty chapters array")
    stages: list[dict[str, int | bool]] = []
    seen: set[tuple[int, int]] = set()
    for chapter in chapters:
        if not isinstance(chapter, dict) or type(chapter.get("chapterNo")) is not int:
            raise BattleDataImportError("BattleData chapter has an invalid chapterNo")
        chapter_id = chapter["chapterNo"]
        sections = chapter.get("sections")
        if chapter_id <= 0 or not isinstance(sections, list):
            raise BattleDataImportError("BattleData chapter has invalid sections")
        for section_number, section in enumerate(sections, start=1):
            if not isinstance(section, dict):
                raise BattleDataImportError("BattleData section must be an object")
            fields = ("rawStamina", "coins", "battleCnt")
            if any(type(section.get(field)) is not int or section[field] < 0 for field in fields):
                raise BattleDataImportError("BattleData section has invalid numeric metadata")
            identity = (chapter_id, section_number)
            if identity in seen:
                raise BattleDataImportError("BattleData contains a duplicate stage identity")
            seen.add(identity)
            stages.append({
                "chapter": chapter_id,
                "section": section_number,
                "stamina": section["rawStamina"],
                "coins": section["coins"],
                "battle_count": section["battleCnt"],
                "has_battle": section["battleCnt"] > 0,
            })
    return {
        "schema_version": SCHEMA_VERSION,
        "provenance": "user-derived",
        "source": {"profile": SOURCE_PROFILE, "apk_sha256": apk_sha256},
        "stages": stages,
    }


def load_battledata_tree(apk: Path, dummy_dll_dir: Path) -> dict[str, Any]:
    """Load the reviewed APK's BattleData through locally derived type trees."""
    try:
        import UnityPy
        from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator
    except ImportError as error:
        raise BattleDataImportError(
            "BattleData import requires UnityPy==1.25.2 and TypeTreeGeneratorAPI==0.0.10; "
            "install the master-import optional dependency"
        ) from error
    try:
        apk = apk.resolve(strict=True)
        dlls = sorted(dummy_dll_dir.resolve(strict=True).glob("*.dll"))
    except OSError as error:
        raise BattleDataImportError("APK or local dummy-DLL directory is unavailable") from error
    if not dlls:
        raise BattleDataImportError("dummy-DLL directory contains no local .dll files")
    try:
        with zipfile.ZipFile(apk) as archive:
            payload = archive.read(APK_DATA_MEMBER)
    except (OSError, KeyError, zipfile.BadZipFile) as error:
        raise BattleDataImportError("APK does not contain the reviewed data.unity3d member") from error
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
                if obj.assets_file.name == SERIALIZED_FILE and obj.path_id == BATTLE_DATA_PATH_ID
            ]
            if len(matches) != 1:
                raise BattleDataImportError(f"expected one BattleData object, found {len(matches)}")
            tree = matches[0].parse_as_dict(check_read=True)
    except BattleDataImportError:
        raise
    except Exception as error:
        raise BattleDataImportError("could not parse BattleData with local type trees") from error
    if not isinstance(tree, dict):
        raise BattleDataImportError("BattleData did not decode to an object")
    return tree


def write_stage_metadata(path: Path, document: dict[str, object]) -> None:
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
        document = build_stage_metadata(load_battledata_tree(apk, args.dummy_dll_dir), sha256_file(apk))
        write_stage_metadata(args.output, document)
    except (BattleDataImportError, OSError) as error:
        raise SystemExit(f"BattleData import failed: {error}") from error
    print(f"wrote local BattleData stage metadata: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
