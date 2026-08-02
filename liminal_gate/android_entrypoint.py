"""Android in-process lifecycle for the packaged compatibility server.

The Android host calls :func:`start` before it lets Unity initialize.  Runtime
metadata lives in signed APK members, while the account state is app-private and
never replaced after the first successful seed.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import tempfile
from threading import Lock, Thread
from typing import Any
import zipfile

from liminal_gate.bootstrap_server import BootstrapServer, ProfileError, build_server
from liminal_gate.resource_catalog import ResourceCatalogError, load_resource_catalog_document
from liminal_gate.server_config import ServerConfig, _PATH_FIELDS


LOOPBACK_HOST = "127.0.0.1"
LOOPBACK_PORT = 8002
RUNTIME_SERVER_MEMBER = "assets/liminal_gate/runtime/server.json"
PACKAGED_MANIFEST_MEMBER = "assets/liminal_gate/packaged-resource-manifest.json"
RUNTIME_SEED_MEMBER = "assets/liminal_gate/seed-state.json"
RUNTIME_SERVER_FILE = "server.json"
RUNTIME_SEED_FILE = "seed-state.json"
STATE_FILE = "state.json"


@dataclass
class _Supervisor:
    server: BootstrapServer
    thread: Thread
    apk_path: Path
    files_dir: Path
    build_id: str
    failure: BaseException | None = None


_lock = Lock()
_supervisor: _Supervisor | None = None


def start(apk_path: str | Path, files_dir: str | Path, expected_build_id: str) -> BootstrapServer:
    """Start (or return) the one loopback server for this Android process.

    ``server.json`` is a JSON rendering of ``ServerConfig`` plus either a
    relative profile path or an inline Bootstrap profile object.  Referenced
    catalog paths are relative to ``files_dir``. Small generated catalogs and
    runtime files are digest-checked and materialized from signed APK members;
    resources stream from the APK itself. The optional state seed creates the
    durable state file only when it is absent.
    """
    if not _is_sha256(expected_build_id):
        raise ValueError("expected_build_id must be exactly 64 lowercase hexadecimal characters")
    apk = Path(apk_path).resolve(strict=True)
    root = Path(files_dir).resolve()
    if not apk.is_file():
        raise ValueError("apk_path must be a regular file")
    with _lock:
        global _supervisor
        if _supervisor is not None:
            if _supervisor.thread.is_alive():
                if (_supervisor.apk_path, _supervisor.files_dir, _supervisor.build_id) != (apk, root, expected_build_id):
                    raise RuntimeError("Android compatibility server is already running for another package")
                return _supervisor.server
            _close_supervisor_locked()
        root.mkdir(parents=True, exist_ok=True)
        manifest = _load_packaged_manifest(apk, expected_build_id)
        _materialize_runtime_files(apk, root, manifest)
        _seed_state_once(apk, root, manifest)
        config = _load_runtime_config(root)
        catalog = load_resource_catalog_document({"schema_version": 2, "resources": manifest["resources"]}, apk)
        try:
            server = build_server(
                replace(config, host=LOOPBACK_HOST, port=LOOPBACK_PORT, state_file=root / STATE_FILE),
                resource_catalog=catalog,
                build_id=expected_build_id,
            )
        except BaseException:
            catalog.close()
            raise
        supervisor = _Supervisor(server, Thread(), apk, root, expected_build_id)
        thread = Thread(target=_serve, args=(supervisor,), name="liminal-gate-server", daemon=True)
        supervisor.thread = thread
        _supervisor = supervisor
        thread.start()
        return server


def stop() -> None:
    """Stop the embedded server and release the save/APK immediately."""
    with _lock:
        _close_supervisor_locked()


def retry(apk_path: str | Path, files_dir: str | Path, expected_build_id: str) -> BootstrapServer:
    """Replace a stopped or failed instance without touching durable state."""
    stop()
    return start(apk_path, files_dir, expected_build_id)


def _serve(supervisor: _Supervisor) -> None:
    try:
        supervisor.server.serve_forever()
    except BaseException as error:  # surfaced to the next lifecycle call
        supervisor.failure = error


def _close_supervisor_locked() -> None:
    global _supervisor
    supervisor = _supervisor
    _supervisor = None
    if supervisor is None:
        return
    # ``BaseServer.shutdown`` waits for ``serve_forever`` to signal its exit.
    # Calling it after the serving thread has already failed waits forever,
    # which would strand Retry precisely when it is needed most.
    if supervisor.thread.is_alive():
        supervisor.server.shutdown()
        supervisor.thread.join()
    supervisor.server.server_close()


def _materialize_runtime_files(apk: Path, root: Path, manifest: dict[str, object]) -> None:
    with zipfile.ZipFile(apk) as archive:
        seen: set[Path] = set()
        for category, prefix in (("catalogs", "catalogs"), ("runtime", "")):
            entries = manifest[category]
            if not isinstance(entries, list):
                raise ProfileError(f"packaged APK {category} manifest is invalid")
            for entry in entries:
                name, data = _verified_small_member(archive, entry)
                target = root / prefix / Path(*PurePosixPath(name).parts)
                if target in seen:
                    raise ProfileError("packaged APK has duplicate extracted member names")
                seen.add(target)
                _write_atomic(target, data, replace_existing=True)
        if root / RUNTIME_SERVER_FILE not in seen:
            raise ProfileError(f"packaged APK is missing {RUNTIME_SERVER_MEMBER}")


def _seed_state_once(apk: Path, root: Path, manifest: dict[str, object]) -> None:
    """Publish an optional seed atomically without replacing player state."""
    state = root / STATE_FILE
    if state.exists():
        return
    seed = manifest.get("seed")
    if seed is None:
        return
    with zipfile.ZipFile(apk) as archive:
        _, data = _verified_small_member(archive, seed, require_name=False)
    _write_if_absent(state, data)


def _load_packaged_manifest(apk: Path, expected_build_id: str) -> dict[str, object]:
    try:
        with zipfile.ZipFile(apk) as archive:
            document = json.loads(_read_member(archive, PACKAGED_MANIFEST_MEMBER).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ResourceCatalogError("could not read packaged APK resource manifest") from error
    if (
        not isinstance(document, dict)
        or document.get("schema_version") != 2
        or document.get("build_id") != expected_build_id
        or not isinstance(document.get("resources"), list)
        or not isinstance(document.get("catalogs"), list)
        or not isinstance(document.get("runtime"), list)
        or document.get("seed") is not None and not isinstance(document.get("seed"), dict)
    ):
        raise ResourceCatalogError("packaged APK resource manifest is invalid or names another build")
    return document


def _verified_small_member(
    archive: zipfile.ZipFile, entry: object, *, require_name: bool = True,
) -> tuple[str, bytes]:
    if not isinstance(entry, dict):
        raise ProfileError("packaged APK extracted member is invalid")
    required = {"member", "sha256", "size"} | ({"name"} if require_name else set())
    if set(entry) != required:
        raise ProfileError("packaged APK extracted member has an invalid schema")
    name = entry.get("name", "seed-state.json")
    relative = _safe_relative(name, "member name")
    member = entry.get("member")
    digest = entry.get("sha256")
    size = entry.get("size")
    if not isinstance(member, str) or not _safe_relative(member, "member").parts or not _is_sha256(digest) or type(size) is not int or size < 0:
        raise ProfileError("packaged APK extracted member is invalid")
    try:
        info = archive.getinfo(member)
    except KeyError as error:
        raise ProfileError("packaged APK extracted member is unavailable") from error
    if info.is_dir() or info.compress_type != zipfile.ZIP_STORED or info.flag_bits & (0x1 | 0x8) or info.file_size != size:
        raise ProfileError("packaged APK extracted member metadata is invalid")
    with archive.open(info) as stream:
        data = stream.read()
    if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
        raise ProfileError("packaged APK extracted member digest does not match")
    return relative.as_posix(), data


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _load_runtime_config(root: Path) -> ServerConfig:
    try:
        document = json.loads((root / RUNTIME_SERVER_FILE).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ProfileError("could not read packaged Android server configuration") from error
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise ProfileError("packaged Android server configuration requires schema version 1")
    values = document.get("config", document)
    if not isinstance(values, dict):
        raise ProfileError("packaged Android server configuration must contain an object")
    values = dict(values)
    values.pop("schema_version", None)
    profile = values.get("profile")
    if isinstance(profile, dict):
        _write_atomic(root / "profile.json", (json.dumps(profile, separators=(",", ":")) + "\n").encode("utf-8"), replace_existing=True)
        values["profile"] = "profile.json"
    permitted = {field.name for field in fields(ServerConfig)}
    if set(values) - permitted:
        raise ProfileError("packaged Android server configuration has an invalid schema")
    for name in _PATH_FIELDS:
        if name in {"profile", "state_file"} or values.get(name) is None:
            continue
        values[name] = _runtime_path(root, values[name], name)
    values["profile"] = _runtime_path(root, values.get("profile"), "profile")
    # The host never trusts a package-supplied external address or state path.
    values["state_file"] = root / STATE_FILE
    values["host"] = LOOPBACK_HOST
    values["port"] = LOOPBACK_PORT
    try:
        return ServerConfig(**values)
    except TypeError as error:
        raise ProfileError("packaged Android server configuration is incomplete") from error


def _runtime_path(root: Path, value: object, field: str) -> Path:
    relative = _safe_relative(value, field)
    candidate = (root / Path(*relative.parts)).resolve()
    if not candidate.is_relative_to(root):
        raise ProfileError(f"packaged Android {field} escapes files_dir")
    return candidate


def _safe_relative(value: object, field: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ProfileError(f"packaged Android {field} must be a nonempty relative path")
    relative = PurePosixPath(value)
    if relative.is_absolute() or not relative.parts or "." in relative.parts or ".." in relative.parts:
        raise ProfileError(f"packaged Android {field} must be a safe relative path")
    return relative


def _read_member(archive: zipfile.ZipFile, member: str) -> bytes:
    try:
        with archive.open(member) as stream:
            return stream.read()
    except KeyError as error:
        raise ProfileError(f"packaged APK is missing {member}") from error


def _write_atomic(path: Path, data: bytes, *, replace_existing: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        if replace_existing:
            os.replace(temporary, path)
        else:
            os.link(temporary, path)
    except FileExistsError:
        pass
    finally:
        temporary.unlink(missing_ok=True)


def _write_if_absent(path: Path, data: bytes) -> None:
    _write_atomic(path, data, replace_existing=False)
