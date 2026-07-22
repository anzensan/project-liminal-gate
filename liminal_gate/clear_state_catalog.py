"""User-local character progression constraints for generic story clears."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import tomllib


class ClearStateCatalogError(ValueError):
    """A user-local clear-state catalog is invalid."""


@dataclass(frozen=True)
class JobProgression:
    maximum_experience: int
    level_thresholds: tuple[int, ...]


@dataclass(frozen=True)
class CharacterProgression:
    character_id: int
    duplicate_skill_boost: int
    jobs: tuple[JobProgression, JobProgression, JobProgression]


@dataclass(frozen=True)
class ClearStateCatalog:
    team_slots: int
    max_skill_boost: int
    max_skill_boost_per_battle: int
    characters: dict[int, CharacterProgression]


def load_clear_state_catalog(path: Path) -> ClearStateCatalog:
    """Load strict JSON or TOML operator-supplied character progression facts."""
    try:
        value = tomllib.loads(path.read_text(encoding="utf-8")) if path.suffix.lower() == ".toml" else json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, tomllib.TOMLDecodeError) as error:
        raise ClearStateCatalogError("could not read clear-state catalog JSON or TOML") from error
    required = {"schema_version", "provenance", "team_slots", "max_skill_boost", "max_skill_boost_per_battle", "characters"}
    if not isinstance(value, dict) or set(value) != required or value.get("schema_version") != 1 or value.get("provenance") != "user-supplied":
        raise ClearStateCatalogError("clear-state catalog has an invalid schema or provenance")
    for name in ("team_slots", "max_skill_boost", "max_skill_boost_per_battle"):
        if type(value[name]) is not int or value[name] <= 0:
            raise ClearStateCatalogError(f"{name} must be a positive integer")
    if value["team_slots"] != 6:
        raise ClearStateCatalogError("team_slots must be the confirmed six-slot clear shape")
    if not isinstance(value["characters"], list) or not value["characters"]:
        raise ClearStateCatalogError("characters must be a nonempty array")
    characters = tuple(_character(item) for item in value["characters"])
    identifiers = [character.character_id for character in characters]
    if identifiers != sorted(identifiers) or len(identifiers) != len(set(identifiers)):
        raise ClearStateCatalogError("characters must be ordered and unique")
    return ClearStateCatalog(value["team_slots"], value["max_skill_boost"], value["max_skill_boost_per_battle"], {character.character_id: character for character in characters})


def _character(value: object) -> CharacterProgression:
    if not isinstance(value, dict) or set(value) != {"character_id", "duplicate_skill_boost", "jobs"} or type(value["character_id"]) is not int or value["character_id"] <= 0 or type(value["duplicate_skill_boost"]) is not int or value["duplicate_skill_boost"] < 0:
        raise ClearStateCatalogError("each character requires a positive character_id, nonnegative duplicate_skill_boost, and jobs")
    jobs = value["jobs"]
    if not isinstance(jobs, list) or len(jobs) != 3:
        raise ClearStateCatalogError("each character requires exactly three job progressions")
    return CharacterProgression(value["character_id"], value["duplicate_skill_boost"], tuple(_job(item) for item in jobs))


def _job(value: object) -> JobProgression:
    if not isinstance(value, dict) or set(value) != {"maximum_experience", "level_thresholds"}:
        raise ClearStateCatalogError("each job requires maximum_experience and level_thresholds")
    maximum = value["maximum_experience"]
    thresholds = value["level_thresholds"]
    if type(maximum) is not int or maximum < 0 or not isinstance(thresholds, list) or not thresholds or any(type(item) is not int or item < 0 for item in thresholds):
        raise ClearStateCatalogError("job progression values are outside range")
    if thresholds[0] != 0 or thresholds != sorted(set(thresholds)) or thresholds[-1] > maximum:
        raise ClearStateCatalogError("job thresholds must be unique ascending values from zero within maximum_experience")
    return JobProgression(maximum, tuple(thresholds))
