"""Serve only resource files explicitly mapped by a user-local manifest."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath


RESOURCE_MANIFEST_SCHEMA_VERSION = 1


class ResourceCatalogError(ValueError):
    """A local resource manifest is unsafe, malformed, or stale."""


@dataclass(frozen=True)
class ResourceEntry:
    path: str
    file: Path
    content_type: str


class ResourceCatalog:
    """Immutable, hash-validated mapping from URL paths to local files."""

    def __init__(self, entries: dict[str, ResourceEntry]) -> None:
        self.entries = entries

    def resolve(self, path: str) -> ResourceEntry | None:
        return self.entries.get(path)


def load_resource_catalog(manifest: Path, resource_root: Path) -> ResourceCatalog:
    """Load an explicit local manifest without discovering or exporting files."""
    try:
        document = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ResourceCatalogError("could not read local resource manifest") from error
    if not isinstance(document, dict) or document.get("schema_version") != RESOURCE_MANIFEST_SCHEMA_VERSION:
        raise ResourceCatalogError(f"resource manifest schema_version must be {RESOURCE_MANIFEST_SCHEMA_VERSION}")
    resources = document.get("resources")
    if not isinstance(resources, list) or not resources:
        raise ResourceCatalogError("resource manifest must contain a nonempty resources list")
    try:
        root = resource_root.resolve(strict=True)
    except OSError as error:
        raise ResourceCatalogError("resource root is unavailable") from error
    if not root.is_dir():
        raise ResourceCatalogError("resource root must be a directory")
    entries: dict[str, ResourceEntry] = {}
    for resource in resources:
        entry = _load_entry(resource, root)
        if entry.path in entries:
            raise ResourceCatalogError("resource manifest has duplicate URL paths")
        entries[entry.path] = entry
    return ResourceCatalog(entries)


def _load_entry(resource: object, root: Path) -> ResourceEntry:
    if not isinstance(resource, dict):
        raise ResourceCatalogError("every resource manifest entry must be an object")
    path = resource.get("path")
    relative = resource.get("file")
    expected_hash = resource.get("sha256")
    content_type = resource.get("content_type", "application/octet-stream")
    if not isinstance(path, str) or not path.startswith("/resources/") or path == "/resources/":
        raise ResourceCatalogError("resource path must start with /resources/")
    if not isinstance(relative, str) or not _safe_relative_path(relative):
        raise ResourceCatalogError("resource file must be a safe relative path")
    if not isinstance(expected_hash, str) or len(expected_hash) != 64 or any(char not in "0123456789abcdef" for char in expected_hash):
        raise ResourceCatalogError("resource sha256 must be lowercase hexadecimal")
    if not isinstance(content_type, str) or not content_type or "\r" in content_type or "\n" in content_type:
        raise ResourceCatalogError("resource content_type is invalid")
    candidate = (root / Path(*PurePosixPath(relative).parts)).resolve()
    if not candidate.is_relative_to(root) or not candidate.is_file():
        raise ResourceCatalogError("resource file is unavailable")
    if _sha256_file(candidate) != expected_hash:
        raise ResourceCatalogError("resource file hash does not match local manifest")
    return ResourceEntry(path, candidate, content_type)


def _safe_relative_path(value: str) -> bool:
    path = PurePosixPath(value)
    return not path.is_absolute() and bool(path.parts) and ".." not in path.parts and "." not in path.parts


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
