"""Build a local hash-validated /resources/ manifest from a user-owned tree."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
from pathlib import Path
import re
import tempfile

from liminal_gate.resource_catalog import RESOURCE_MANIFEST_SCHEMA_VERSION, ResourceCatalogError, _sha256_file


_CACHE_PREFIX = re.compile(r"^[0-9a-f]{32}(?P<name>.+)$")


def _logical_relative_path(relative: str) -> str:
    """Translate the known cache-prefixed Android filename form to its URL name."""
    path = Path(relative)
    match = _CACHE_PREFIX.fullmatch(path.name)
    if match is None:
        return relative
    return path.with_name(match.group("name")).as_posix()


def build_resource_manifest(resource_root: Path) -> dict[str, object]:
    """Map every regular user-local file beneath root to its client resource URL."""
    try:
        root = resource_root.resolve(strict=True)
    except OSError as error:
        raise ResourceCatalogError("resource root is unavailable") from error
    if not root.is_dir():
        raise ResourceCatalogError("resource root must be a directory")
    resources: list[dict[str, str]] = []
    mapped_paths: set[str] = set()
    for candidate in sorted(root.rglob("*")):
        if candidate.is_symlink():
            raise ResourceCatalogError("resource root must not contain symbolic links")
        if not candidate.is_file():
            continue
        relative = candidate.relative_to(root).as_posix()
        if not relative or ".." in Path(relative).parts:
            raise ResourceCatalogError("resource root contains an unsafe file path")
        logical_relative = _logical_relative_path(relative)
        path = "/resources/" + logical_relative
        if path in mapped_paths:
            raise ResourceCatalogError(f"resource root maps more than one file to {path}")
        mapped_paths.add(path)
        content_type = mimetypes.guess_type(relative)[0] or "application/octet-stream"
        resources.append({
            "path": path,
            "file": relative,
            "sha256": _sha256_file(candidate),
            "content_type": content_type,
        })
    if not resources:
        raise ResourceCatalogError("resource root contains no regular files")
    return {"schema_version": RESOURCE_MANIFEST_SCHEMA_VERSION, "resources": resources}


def write_resource_manifest(path: Path, manifest: dict[str, object]) -> None:
    """Atomically write a derived local manifest without copying resource data."""
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
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
    parser.add_argument("--resource-root", required=True, type=Path)
    parser.add_argument("--output-manifest", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        manifest = build_resource_manifest(args.resource_root)
        write_resource_manifest(args.output_manifest, manifest)
    except (OSError, ResourceCatalogError) as error:
        raise SystemExit(f"resource catalog build failed: {error}") from error
    print(f"wrote local resource manifest: {args.output_manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
