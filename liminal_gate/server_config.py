"""Strict user-local configuration for the bootstrap-server launcher."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib


class ServerConfigError(ValueError):
    """A user-local bootstrap-server configuration is invalid."""


_PATH_FIELDS = (
    "profile", "state_file", "event_log", "resource_root", "resource_manifest",
    "story_catalog", "story_progression_catalog", "settlement_catalog", "story_outcome_catalog", "statusup_catalog",
    "clear_state_catalog",
    "job_catalog", "rebirth_catalog", "summon_skill_catalog", "companion_catalog",
    "companion_strengthen_catalog", "companion_evolution_catalog", "companion_draw_catalog",
    "pact_draw_catalog",
    "achievement_catalog",
    "message_catalog",
    "exchange_catalog",
)
_REQUIRED = {"schema_version", "provenance", "profile", "state_file"}
_OPTIONAL = set(_PATH_FIELDS[2:]) | {"host", "port", "core_story", "pacts"}


@dataclass(frozen=True)
class ServerConfig:
    profile: Path
    state_file: Path
    host: str
    port: int
    core_story: bool = False
    pacts: bool = False
    event_log: Path | None = None
    resource_root: Path | None = None
    resource_manifest: Path | None = None
    story_catalog: Path | None = None
    story_progression_catalog: Path | None = None
    settlement_catalog: Path | None = None
    story_outcome_catalog: Path | None = None
    clear_state_catalog: Path | None = None
    statusup_catalog: Path | None = None
    job_catalog: Path | None = None
    rebirth_catalog: Path | None = None
    summon_skill_catalog: Path | None = None
    companion_catalog: Path | None = None
    companion_strengthen_catalog: Path | None = None
    companion_evolution_catalog: Path | None = None
    companion_draw_catalog: Path | None = None
    pact_draw_catalog: Path | None = None
    achievement_catalog: Path | None = None
    message_catalog: Path | None = None
    exchange_catalog: Path | None = None


def load_server_config(path: Path) -> ServerConfig:
    """Load TOML and resolve relative paths from its containing directory."""
    try:
        document = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ServerConfigError("could not read bootstrap-server configuration TOML") from error
    if not isinstance(document, dict) or set(document) - (_REQUIRED | _OPTIONAL) or not _REQUIRED <= set(document):
        raise ServerConfigError("bootstrap-server configuration has an invalid schema")
    if document["schema_version"] != 1 or document["provenance"] != "user-supplied":
        raise ServerConfigError("bootstrap-server configuration requires schema version 1 and user-supplied provenance")
    paths = {field: _path(document.get(field), path.parent, field, field in _REQUIRED) for field in _PATH_FIELDS}
    host = document.get("host", "127.0.0.1")
    port = document.get("port", 8080)
    core_story = document.get("core_story", False)
    pacts = document.get("pacts", False)
    if not isinstance(host, str) or not host or "\x00" in host:
        raise ServerConfigError("host must be a nonempty string")
    if type(port) is not int or not 1 <= port <= 65535:
        raise ServerConfigError("port must be an integer from 1 through 65535")
    if type(core_story) is not bool:
        raise ServerConfigError("core_story must be a boolean")
    if type(pacts) is not bool:
        raise ServerConfigError("pacts must be a boolean")
    return ServerConfig(host=host, port=port, core_story=core_story, pacts=pacts, **paths)


def _path(value: object, root: Path, field: str, required: bool) -> Path | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ServerConfigError(f"{field} must be a nonempty path string")
    candidate = Path(value)
    return candidate if candidate.is_absolute() else root / candidate
