"""Validate the public server's metadata-only user-data boundary."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any


MANIFEST_FILENAME = "liminal-gate-data.json"
MANIFEST_SCHEMA_VERSION = 1
DATASET_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


class ManifestError(ValueError):
    """A user-data manifest did not satisfy the public boundary."""


@dataclass(frozen=True)
class DataManifest:
    """Validated metadata only; referenced data files are never opened."""

    dataset_count: int


def load_data_manifest(data_directory: Path) -> DataManifest | None:
    """Load an optional manifest without reading any referenced dataset files."""
    manifest_path = data_directory / MANIFEST_FILENAME
    if not manifest_path.exists():
        return None
    try:
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ManifestError(f"could not read {MANIFEST_FILENAME}") from error
    if not isinstance(document, dict):
        raise ManifestError("manifest must be a JSON object")
    if document.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ManifestError(f"schema_version must be {MANIFEST_SCHEMA_VERSION}")
    if document.get("provenance") != "user-supplied":
        raise ManifestError("provenance must be user-supplied")
    datasets = document.get("datasets")
    if not isinstance(datasets, list):
        raise ManifestError("datasets must be an array")
    seen_ids: set[str] = set()
    for dataset in datasets:
        _validate_dataset(dataset, seen_ids)
    return DataManifest(dataset_count=len(datasets))


def _validate_dataset(dataset: Any, seen_ids: set[str]) -> None:
    if not isinstance(dataset, dict):
        raise ManifestError("each dataset must be an object")
    dataset_id = dataset.get("id")
    if not isinstance(dataset_id, str) or not DATASET_ID_PATTERN.fullmatch(dataset_id):
        raise ManifestError("dataset id must be lowercase ASCII metadata")
    if dataset_id in seen_ids:
        raise ManifestError("dataset ids must be unique")
    seen_ids.add(dataset_id)
    relative_path = dataset.get("path")
    if not isinstance(relative_path, str) or not _is_safe_relative_path(relative_path):
        raise ManifestError("dataset path must be a safe relative POSIX path")
    sha256 = dataset.get("sha256")
    if not isinstance(sha256, str) or not SHA256_PATTERN.fullmatch(sha256):
        raise ManifestError("dataset sha256 must be lowercase hexadecimal")


def _is_safe_relative_path(value: str) -> bool:
    path = PurePosixPath(value)
    return not path.is_absolute() and value not in {"", "."} and ".." not in path.parts
