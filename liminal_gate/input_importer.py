"""Create a local manifest for user-supplied client and resource inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import tempfile
from typing import Any
import zipfile

from liminal_gate.il2cpp_plan_generator import PlanGenerationError, generate_plan


IMPORT_MANIFEST_FILENAME = "liminal-gate-import.json"
IMPORT_SCHEMA_VERSION = 1
REVIEWED_ANDROID_5_5_7_PROFILE = "terra-battle-android-5.5.7-170"
_REVIEWED_APK_MEMBERS = (
    "assets/bin/Data/Managed/Metadata/global-metadata.dat",
    "lib/arm64-v8a/libil2cpp.so",
    "lib/armeabi-v7a/libil2cpp.so",
)
_REVIEWED_METADATA_LITERALS = (
    b"https://gdappserver.appspot.com/",
    b"http://storage.googleapis.com/gdresources/data_u2017/android/",
    b"http://www.terra-battle.com",
)
_REVIEWED_RESOURCE_CATEGORIES = (
    "BG", "BGM", "Banner", "BuddyImages", "BuddyThumbs", "Illust", "Pieces", "SE", "Scenario",
)


class ImportError(ValueError):
    """User-supplied input cannot be safely inventoried."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_import_manifest(
    apk: Path, resource_root: Path | None = None, *, reviewed_android_5_5_7: bool = False,
) -> dict[str, Any]:
    """Inventory local input metadata without extracting or copying content."""
    apk = apk.resolve(strict=True)
    archive = _inspect_apk(apk)
    resources = _inspect_resources(resource_root.resolve(strict=True)) if resource_root else None
    manifest: dict[str, Any] = {
        "schema_version": IMPORT_SCHEMA_VERSION,
        "provenance": "user-supplied",
        "apk": {
            "sha256": sha256_file(apk),
            "size": apk.stat().st_size,
            **archive,
        },
    }
    if resources is not None:
        manifest["resources"] = resources
    if reviewed_android_5_5_7:
        if resource_root is None:
            raise ImportError("reviewed Android 5.5.7 import requires --resource-root")
        _validate_reviewed_android_5_5_7(apk, resource_root.resolve(strict=True))
        manifest["reviewed_input"] = {
            "profile": REVIEWED_ANDROID_5_5_7_PROFILE,
            "validation": "structural",
        }
    return manifest


def write_import_manifest(output_directory: Path, manifest: dict[str, Any]) -> Path:
    """Durably write locally derived metadata without retaining source paths."""
    output_directory.mkdir(parents=True, exist_ok=True)
    output = output_directory / IMPORT_MANIFEST_FILENAME
    encoded = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    with tempfile.NamedTemporaryFile(dir=output_directory, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    return output


def _inspect_apk(apk: Path) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(apk) as archive:
            names: set[str] = set()
            records: list[dict[str, int | str]] = []
            for info in archive.infolist():
                _validate_member_name(info.filename)
                if info.filename in names:
                    raise ImportError(f"duplicate APK member: {info.filename}")
                names.add(info.filename)
                records.append({"name": info.filename, "size": info.file_size})
    except (OSError, zipfile.BadZipFile) as error:
        raise ImportError("APK must be a readable ZIP archive") from error
    digest = hashlib.sha256(
        json.dumps(records, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()
    return {"member_count": len(records), "member_manifest_sha256": digest}


def _inspect_resources(resource_root: Path) -> dict[str, Any]:
    if not resource_root.is_dir():
        raise ImportError("resource root must be a directory")
    records: list[dict[str, int | str]] = []
    for path in sorted(resource_root.rglob("*")):
        if path.is_symlink():
            raise ImportError(f"resource root contains symbolic link: {path.name}")
        if path.is_file():
            records.append({
                "path": path.relative_to(resource_root).as_posix(),
                "sha256": sha256_file(path),
                "size": path.stat().st_size,
            })
    digest = hashlib.sha256(
        json.dumps(records, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()
    return {"file_count": len(records), "manifest_sha256": digest}


def _validate_reviewed_android_5_5_7(apk: Path, resource_root: Path) -> None:
    """Check the non-content structure required by the reviewed local workflow."""
    try:
        with zipfile.ZipFile(apk) as archive:
            names = set(archive.namelist())
            missing = sorted(set(_REVIEWED_APK_MEMBERS) - names)
            if missing:
                raise ImportError(f"APK is missing reviewed Android members: {', '.join(missing)}")
    except (OSError, zipfile.BadZipFile) as error:
        raise ImportError("APK must be a readable ZIP archive") from error
    try:
        generate_plan(
            apk,
            _REVIEWED_APK_MEMBERS[0],
            ((literal, b"x") for literal in _REVIEWED_METADATA_LITERALS),
        )
    except PlanGenerationError as error:
        raise ImportError("APK does not match the reviewed routing-literal structure") from error
    missing_categories = [
        category for category in _REVIEWED_RESOURCE_CATEGORIES
        if not (resource_root / category).is_dir()
    ]
    if missing_categories:
        raise ImportError(
            "resource root is missing reviewed Android categories: " + ", ".join(missing_categories)
        )


def _validate_member_name(name: str) -> None:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or not name:
        raise ImportError(f"unsafe APK member: {name!r}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apk", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--resource-root", type=Path)
    parser.add_argument(
        "--reviewed-android-5-5-7", action="store_true",
        help="require the reviewed Android 5.5.7-170 APK and data_u2017/android resource layout",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        manifest = build_import_manifest(
            args.apk, args.resource_root, reviewed_android_5_5_7=args.reviewed_android_5_5_7,
        )
        output = write_import_manifest(args.output_dir, manifest)
    except (ImportError, OSError) as error:
        raise SystemExit(f"input import failed: {error}") from error
    print(f"wrote local input manifest: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
