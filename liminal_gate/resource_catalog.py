"""Serve only resource files explicitly mapped by a user-local manifest."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import BinaryIO
import zipfile


RESOURCE_MANIFEST_SCHEMA_VERSION = 1
APK_RESOURCE_MANIFEST_SCHEMA_VERSION = 2

#: The URL base the patched Android client asks on. Its resource literal is
#: rewritten at build time, so it reaches this server under a prefix of the
#: project's own choosing.
RESOURCE_URL_PREFIX = "/resources/"

#: The URL base the iOS client asks on. Its resource literal lives in a
#: FairPlay-encrypted binary and cannot be rewritten, so it arrives spelled
#: exactly as the retired CDN served it and the server has to answer that.
#:
#: The two bases must stay distinct, because the platforms do not share bytes:
#: the 32-hex filename prefix hashes the logical asset name rather than the
#: content, so `BG/52329f63...stage_back_9000.bin` names a 101,967-byte bundle
#: in the Android tree and a different 247,692-byte bundle in the iOS one.
#: Serving both from one prefix would hand a client the other platform's
#: bundle under a Content-Length taken from its own manifest.
IOS_RESOURCE_URL_PREFIX = "/gdresources/data_u2017/iOS_2/"

#: Every URL base a v1 filesystem manifest may map onto, longest first so a
#: prefix that contains another still identifies the longer one.
_MANIFEST_URL_PREFIXES = (IOS_RESOURCE_URL_PREFIX, RESOURCE_URL_PREFIX)


class ResourceCatalogError(ValueError):
    """A local resource manifest is unsafe, malformed, or stale."""


@dataclass(frozen=True)
class ResourceEntry:
    path: str
    content_type: str
    size: int
    file: Path | None = None
    member: str | None = None
    #: The manifest digest, retained for filesystem entries so serving can
    #: check the file again rather than trusting a load-time result. APK
    #: members do not carry one: they are read through a `ZipFile` handle the
    #: catalog holds open, so the bytes served are the bytes validated even if
    #: the package on disk is replaced underneath a running server.
    sha256: str | None = None


class ResourceCatalog:
    """Immutable manifest mapping backed by files or stored APK members.

    The catalog retains the APK handle for schema-v2 entries.  Call ``close``
    when its server stops so Android can immediately replace its package during
    a development reinstall.
    """

    def __init__(self, entries: dict[str, ResourceEntry], archive: zipfile.ZipFile | None = None) -> None:
        self.entries = entries
        self._archive = archive
        self.casefolded_entries: dict[str, ResourceEntry | None] = {}
        for entry in entries.values():
            key = entry.path.casefold()
            if key not in self.casefolded_entries:
                self.casefolded_entries[key] = entry
            elif self.casefolded_entries[key] != entry:
                self.casefolded_entries[key] = None

    def resolve(self, path: str) -> ResourceEntry | None:
        return self.entries.get(path) or self.casefolded_entries.get(path.casefold())

    def open(self, entry: ResourceEntry) -> BinaryIO:
        """Open one resource, re-checking a filesystem entry as it does.

        Validating at load and then reopening the path per request trusted a
        result that stops being true the moment the file changes: a replacement
        was served under the manifest's identity, and a replacement of a
        *different length* also made the `Content-Length` already computed from
        the manifest disagree with the bytes streamed, which reaches the client
        as a truncated or over-long body rather than as an error.

        So the file is measured and digested again here, before the caller has
        framed a response around the manifest's numbers. The cost is one read
        of a file that is about to be read anyway.
        """
        if entry.file is not None:
            stream = entry.file.open("rb")
            try:
                size = entry.file.stat().st_size
                if size != entry.size:
                    raise ResourceCatalogError(
                        f"resource {entry.path} changed size on disk since it was "
                        f"validated ({entry.size} to {size}); reload the manifest"
                    )
                if entry.sha256 is not None and _sha256_rewinding(stream) != entry.sha256:
                    raise ResourceCatalogError(
                        f"resource {entry.path} changed on disk since it was validated; "
                        f"reload the manifest"
                    )
            except BaseException:
                stream.close()
                raise
            return stream
        if self._archive is None or entry.member is None:
            raise ResourceCatalogError("resource catalog is closed")
        return self._archive.open(entry.member, "r")

    def close(self) -> None:
        """Release a retained APK archive; safe to call more than once."""
        if self._archive is not None:
            self._archive.close()
            self._archive = None


def load_resource_catalog(manifest: Path, resource_root: Path) -> ResourceCatalog:
    """Load an explicit v1 filesystem or v2 APK-member manifest.

    For v1, ``resource_root`` is the user-owned resource directory.  For v2 it
    is the final APK itself; every referenced member must be ZIP_STORED, so the
    server can stream it directly rather than extracting another resource copy.
    """
    try:
        document = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ResourceCatalogError("could not read local resource manifest") from error
    return load_resource_catalog_document(document, resource_root)


def load_resource_catalog_document(document: object, resource_root: Path) -> ResourceCatalog:
    """Load a parsed manifest supplied by a signed package member."""
    if not isinstance(document, dict):
        raise ResourceCatalogError("resource manifest must be a JSON object")
    schema_version = document.get("schema_version")
    if schema_version not in {RESOURCE_MANIFEST_SCHEMA_VERSION, APK_RESOURCE_MANIFEST_SCHEMA_VERSION}:
        raise ResourceCatalogError("resource manifest schema_version must be 1 or 2")
    resources = document.get("resources")
    if not isinstance(resources, list) or not resources:
        raise ResourceCatalogError("resource manifest must contain a nonempty resources list")
    try:
        root = resource_root.resolve(strict=True)
    except OSError as error:
        raise ResourceCatalogError("resource source is unavailable") from error
    if schema_version == RESOURCE_MANIFEST_SCHEMA_VERSION:
        if not root.is_dir():
            raise ResourceCatalogError("resource root must be a directory")
        return _load_filesystem_catalog(resources, root)
    if not root.is_file():
        raise ResourceCatalogError("APK resource source must be a regular file")
    return _load_apk_catalog(resources, root)


def combine_resource_catalogs(*catalogs: ResourceCatalog) -> ResourceCatalog:
    """Serve several manifests from one server, refusing any overlap.

    One server answers both clients at once, each on its own URL base, so the
    catalogs it holds are expected to be disjoint. An overlap would mean two
    manifests claiming the same URL, and there is no basis for preferring
    either, so it fails here rather than resolving to whichever loaded last.

    At most one catalog may hold an archive handle: the packaged APK manifest
    is the only one that does, and that deployment serves a single platform.
    """
    entries: dict[str, ResourceEntry] = {}
    archive: zipfile.ZipFile | None = None
    for catalog in catalogs:
        if catalog._archive is not None:
            if archive is not None:
                raise ResourceCatalogError("only one resource catalog may hold an archive")
            archive = catalog._archive
        for path, entry in catalog.entries.items():
            if path in entries:
                raise ResourceCatalogError(f"resource catalogs both map {path}")
            entries[path] = entry
    return ResourceCatalog(entries, archive)


def _load_filesystem_catalog(resources: list[object], root: Path) -> ResourceCatalog:
    entries: dict[str, ResourceEntry] = {}
    for resource in resources:
        entry = _load_file_entry(resource, root)
        if entry.path in entries:
            raise ResourceCatalogError("resource manifest has duplicate URL paths")
        entries[entry.path] = entry
    return ResourceCatalog(entries)


def _load_file_entry(resource: object, root: Path) -> ResourceEntry:
    if not isinstance(resource, dict):
        raise ResourceCatalogError("every resource manifest entry must be an object")
    path = resource.get("path")
    relative = resource.get("file")
    expected_hash = resource.get("sha256")
    content_type = resource.get("content_type", "application/octet-stream")
    if not isinstance(path, str) or not any(
        path.startswith(prefix) and path != prefix for prefix in _MANIFEST_URL_PREFIXES
    ):
        raise ResourceCatalogError(
            "resource path must start with " + " or ".join(_MANIFEST_URL_PREFIXES)
        )
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
    return ResourceEntry(
        path, content_type, candidate.stat().st_size,
        file=candidate, sha256=expected_hash,
    )


def _load_apk_catalog(resources: list[object], apk: Path) -> ResourceCatalog:
    try:
        archive = zipfile.ZipFile(apk)
    except (OSError, zipfile.BadZipFile) as error:
        raise ResourceCatalogError("could not read APK resource archive") from error
    try:
        entries: dict[str, ResourceEntry] = {}
        for resource in resources:
            entry = _load_apk_entry(resource, archive)
            if entry.path in entries:
                raise ResourceCatalogError("resource manifest has duplicate URL paths")
            entries[entry.path] = entry
        return ResourceCatalog(entries, archive)
    except BaseException:
        archive.close()
        raise


def _load_apk_entry(resource: object, archive: zipfile.ZipFile) -> ResourceEntry:
    if not isinstance(resource, dict):
        raise ResourceCatalogError("every resource manifest entry must be an object")
    path = resource.get("path")
    member = resource.get("member")
    expected_hash = resource.get("sha256")
    expected_size = resource.get("size")
    content_type = resource.get("content_type", "application/octet-stream")
    if not isinstance(path, str) or not path.startswith("/resources/") or path == "/resources/":
        raise ResourceCatalogError("resource path must start with /resources/")
    if not isinstance(member, str) or not _safe_zip_member(member):
        raise ResourceCatalogError("APK resource member must be a safe relative path")
    if not isinstance(expected_hash, str) or len(expected_hash) != 64 or any(char not in "0123456789abcdef" for char in expected_hash):
        raise ResourceCatalogError("resource sha256 must be lowercase hexadecimal")
    if type(expected_size) is not int or expected_size < 0:
        raise ResourceCatalogError("APK resource size must be a nonnegative integer")
    if not isinstance(content_type, str) or not content_type or "\r" in content_type or "\n" in content_type:
        raise ResourceCatalogError("resource content_type is invalid")
    try:
        info = archive.getinfo(member)
    except KeyError as error:
        raise ResourceCatalogError("APK resource member is unavailable") from error
    if (
        info.is_dir()
        or info.compress_type != zipfile.ZIP_STORED
        or info.flag_bits & (0x1 | 0x8)
        or info.file_size != info.compress_size
    ):
        raise ResourceCatalogError("APK resource member must use ZIP_STORED")
    if info.file_size != expected_size:
        raise ResourceCatalogError("APK resource size does not match local manifest")
    # The full digest is verified by the source-hash-guarded package build and
    # APK signature.  Re-reading a ~900 MiB resource payload here would delay
    # the app's readiness gate and defeat the direct-streaming design.
    return ResourceEntry(path, content_type, info.file_size, member=member)


def _safe_relative_path(value: str) -> bool:
    path = PurePosixPath(value)
    return not path.is_absolute() and bool(path.parts) and ".." not in path.parts and "." not in path.parts


def _safe_zip_member(value: str) -> bool:
    return _safe_relative_path(value) and "\\" not in value


def _sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        return _sha256_stream(stream)


def _sha256_rewinding(stream: BinaryIO) -> str:
    """Digest an open stream and hand it back ready to read from the start.

    Separate from `_sha256_stream`, which closes what it reads: this one is for
    the stream that is about to be served, so the file is read once rather than
    opened a second time and risking a different file between the two.
    """
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)
    stream.seek(0)
    return digest.hexdigest()


def _sha256_stream(stream: BinaryIO) -> str:
    digest = hashlib.sha256()
    try:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    finally:
        stream.close()
    return digest.hexdigest()
