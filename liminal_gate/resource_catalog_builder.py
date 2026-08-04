"""Build a local hash-validated /resources/ manifest from a user-owned tree."""

from __future__ import annotations

import argparse
import json
import mimetypes
from pathlib import Path, PurePosixPath
import re
from typing import Callable

from liminal_gate.resource_catalog import RESOURCE_MANIFEST_SCHEMA_VERSION, ResourceCatalogError, _sha256_file
from liminal_gate.atomic_json import write_json_document


_CACHE_PREFIX = re.compile(r"^[0-9a-f]{32}(?P<name>.+)$")


def _logical_relative_path(relative: str) -> str:
    """Translate the known cache-prefixed Android filename form to its URL name."""
    path = Path(relative)
    match = _CACHE_PREFIX.fullmatch(path.name)
    if match is None:
        return relative
    return path.with_name(match.group("name")).as_posix()


def resource_url_aliases(relative: str) -> tuple[str, ...]:
    """Every client resource URL one on-disk file answers to, literal name first.

    Android caches many bundles under a 32-hex-prefixed filename while the
    client requests the logical name, so a prefixed file has to be reachable
    under both.  Both manifest builders derive their URL sets here -- the v1
    filesystem tree the separate server reads and the v2 packaged manifest the
    on-device APK carries.  They diverged once, and the self-contained build
    served only the on-disk spelling: every prefixed resource 404ed there while
    the same content loaded from a separate server.
    """
    aliases = dict.fromkeys((relative, _logical_relative_path(relative)))
    return tuple("/resources/" + alias for alias in aliases)


def build_resource_manifest(
    resource_root: Path, digests: Callable[[Path], str] | None = None,
) -> dict[str, object]:
    """Map every regular user-local file beneath root to its client resource URL.

    `digests` accepts a shared hashing function so a caller that already
    inventoried this tree does not read every byte of it a second time.
    """
    hash_file = digests if digests is not None else _sha256_file
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
        content_type = mimetypes.guess_type(relative)[0] or "application/octet-stream"
        digest = hash_file(candidate)
        for path in resource_url_aliases(relative):
            if path in mapped_paths:
                raise ResourceCatalogError(f"resource root maps more than one file to {path}")
            mapped_paths.add(path)
            resources.append({
                "path": path,
                "file": relative,
                "sha256": digest,
                "content_type": content_type,
            })
    if not resources:
        raise ResourceCatalogError("resource root contains no regular files")
    return {"schema_version": RESOURCE_MANIFEST_SCHEMA_VERSION, "resources": resources}


def resource_category_counts(manifest: dict[str, object]) -> dict[str, int]:
    """Count the distinct source files a built manifest carries per category.

    One file answers to more than one client URL, so the count is over the
    ``file`` each entry names rather than over the entries themselves.
    """
    counts: dict[str, int] = {}
    resources = manifest.get("resources")
    if not isinstance(resources, list):
        return counts
    seen: set[str] = set()
    for entry in resources:
        if not isinstance(entry, dict):
            continue
        relative = entry.get("file")
        if not isinstance(relative, str) or relative in seen:
            continue
        seen.add(relative)
        parts = PurePosixPath(relative).parts
        if parts:
            counts[parts[0]] = counts.get(parts[0], 0) + 1
    return counts


def previous_resource_category_counts(manifest_path: Path) -> dict[str, int]:
    """Read the last build's per-category counts, or nothing if unavailable.

    A first build has no previous manifest and an unreadable one is not worth
    refusing a build over: both simply decline to make a comparison.
    """
    try:
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(document, dict):
        return {}
    return resource_category_counts(document)


def shrunken_resource_categories(
    previous: dict[str, int], current: dict[str, int],
) -> tuple[tuple[str, int, int], ...]:
    """Categories carrying fewer files than the last build recorded.

    The tree is the tester's own extraction, so there is no absolute count to
    check against; the previous successful build is the only reference for what
    "complete" means on this machine. A category that shrank is how a partial
    re-extraction shows up, and it is otherwise silent until the client stalls
    on something the package no longer carries.
    """
    return tuple(
        (category, previous[category], current.get(category, 0))
        for category in sorted(previous)
        if current.get(category, 0) < previous[category]
    )


def report_resource_inventory(
    manifest: dict[str, object], manifest_path: Path,
) -> tuple[tuple[str, int, int], ...]:
    """Print the per-category inventory and warn about any category that shrank."""
    counts = resource_category_counts(manifest)
    shrunk = shrunken_resource_categories(
        previous_resource_category_counts(manifest_path), counts,
    )
    total = sum(counts.values())
    inventory = ", ".join(f"{category} {counts[category]}" for category in sorted(counts))
    print(f"Resource inventory ({total} file(s)): {inventory}")
    for category, before, now in shrunk:
        print(
            f"  WARNING: {category} carries {now} file(s); the last build here had "
            f"{before}. Re-extract this category before installing, or the client "
            f"will stall on whatever is missing."
        )
    return shrunk


def write_resource_manifest(path: Path, manifest: dict[str, object]) -> None:
    """Atomically write a derived local manifest without copying resource data."""
    write_json_document(path, manifest, indent=2)


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
