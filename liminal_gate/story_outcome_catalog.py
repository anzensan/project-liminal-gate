"""User-local bounds for client-reported generic story outcomes."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
import tomllib


class StoryOutcomeCatalogError(ValueError):
    """A user-local story-outcome catalog is invalid."""


@dataclass(frozen=True)
class CompanionDropMaster:
    companion_id: int
    drop_level: int


@dataclass(frozen=True)
class StoryOutcomeRule:
    chapter: int
    section: int
    item_maxima: dict[int, int]
    character_maxima: dict[int, int]
    companion_maxima: dict[int, int]
    #: Whether a recovered source could speak to this stage's item and character
    #: outcome at all.  False means "unknown", not "nothing"; see `_evidence`.
    item_evidence: bool = True
    character_evidence: bool = True


@dataclass(frozen=True)
class StoryOutcomeCatalog:
    character_ids: frozenset[int]
    item_slots: int
    max_stack: int
    max_companions: int
    companion_masters: dict[int, CompanionDropMaster]
    rules: dict[tuple[int, int], StoryOutcomeRule]


def load_story_outcome_catalog(path: Path) -> StoryOutcomeCatalog:
    try:
        value = tomllib.loads(path.read_text(encoding="utf-8")) if path.suffix.lower() == ".toml" else json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, tomllib.TOMLDecodeError) as error:
        raise StoryOutcomeCatalogError("could not read story-outcome catalog JSON or TOML") from error
    required = {"schema_version", "provenance", "character_ids", "item_slots", "max_stack", "max_companions", "companion_masters", "stages"}
    if not isinstance(value, dict) or not required <= set(value) or set(value) - required != ({"source"} if "source" in value else set()) or value.get("schema_version") != 1 or value.get("provenance") != "user-supplied":
        raise StoryOutcomeCatalogError("story-outcome catalog has an invalid schema or provenance")
    if "source" in value:
        _source(value["source"])
    character_ids = _ids(value["character_ids"], "character_ids")
    numeric = ("item_slots", "max_stack", "max_companions")
    if any(type(value[name]) is not int or value[name] <= 0 for name in numeric):
        raise StoryOutcomeCatalogError("story-outcome catalog capacities must be positive integers")
    if not isinstance(value["companion_masters"], list):
        raise StoryOutcomeCatalogError("companion_masters must be an array")
    if not isinstance(value["stages"], list) or not value["stages"]:
        raise StoryOutcomeCatalogError("stages must be a nonempty array")
    masters = tuple(_master(item) for item in value["companion_masters"])
    master_ids = [master.companion_id for master in masters]
    if master_ids != sorted(master_ids) or len(master_ids) != len(set(master_ids)):
        raise StoryOutcomeCatalogError("companion_masters must be ordered and unique")
    rules = tuple(_rule(item) for item in value["stages"])
    identities = [(rule.chapter, rule.section) for rule in rules]
    if identities != sorted(identities) or len(identities) != len(set(identities)):
        raise StoryOutcomeCatalogError("stages must be ordered and unique")
    masters_by_id = {master.companion_id: master for master in masters}
    if any(any(companion_id not in masters_by_id for companion_id in rule.companion_maxima) or any(character_id not in character_ids for character_id in rule.character_maxima) or any(item_id > value["item_slots"] for item_id in rule.item_maxima) for rule in rules):
        raise StoryOutcomeCatalogError("stage maxima reference an undeclared ID")
    return StoryOutcomeCatalog(frozenset(character_ids), *(value[name] for name in numeric), masters_by_id, {identity: rule for identity, rule in zip(identities, rules)})


def _valid_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _scenario_provenance(scenario: object, value: dict[str, object]) -> None:
    """Check the MoonSharp scenario map's recorded provenance.

    Held to the same standard as the native map beside it: it must name the same
    APK, and it must account for every chapter listing it read rather than
    asserting coverage in the abstract.
    """
    required = {"profile", "apk_sha256", "format", "decoder", "chapter_sha256"}
    if (
        not isinstance(scenario, dict)
        or set(scenario) != required
        or scenario.get("profile") != value["profile"]
        or scenario.get("apk_sha256") != value["apk_sha256"]
        or scenario.get("format") != "moonsharp-binary-dump"
        or not isinstance(scenario.get("decoder"), str)
        or not scenario["decoder"]
        or not isinstance(scenario.get("chapter_sha256"), dict)
        or not scenario["chapter_sha256"]
        or not all(
            isinstance(chapter, str) and chapter.isdecimal() and _valid_sha256(digest)
            for chapter, digest in scenario["chapter_sha256"].items()
        )
    ):
        raise StoryOutcomeCatalogError("story-outcome catalog has invalid scenario source provenance")


def _source(value: object) -> None:
    required = {
        "profile",
        "apk_sha256",
        "native_encounters_sha256",
        "character_catalog_sha256",
        "native_encounters",
    }
    # A scenario encounter map is optional and comes in as a pair: the file's own
    # hash and the provenance of the chapter listings it was decoded from.  The
    # two are accepted or refused together, so a catalog cannot name one without
    # accounting for the other.
    scenario = {"scenario_encounters_sha256", "scenario_encounters"}
    optional = {frozenset(), frozenset({"baseline_sha256"})}
    optional |= {names | scenario for names in frozenset(optional)}
    if (
        not isinstance(value, dict)
        or not required <= set(value)
        or frozenset(set(value) - required) not in optional
        or value.get("profile") != "terra-battle-android-5.5.7-170"
        or not all(
            _valid_sha256(value.get(field))
            for field in (
                "apk_sha256",
                "native_encounters_sha256",
                "character_catalog_sha256",
            )
        )
        or (
            "baseline_sha256" in value
            and not _valid_sha256(value["baseline_sha256"])
        )
        or (
            "scenario_encounters_sha256" in value
            and not _valid_sha256(value["scenario_encounters_sha256"])
        )
    ):
        raise StoryOutcomeCatalogError("story-outcome catalog has invalid source provenance")
    if "scenario_encounters" in value:
        _scenario_provenance(value["scenario_encounters"], value)
    native = value["native_encounters"]
    native_required = {
        "profile",
        "abi",
        "apk_sha256",
        "dump_cs_sha256",
        "libil2cpp_sha256",
        "objdump",
        "vtable_calibration",
    }
    if (
        not isinstance(native, dict)
        or set(native) != native_required
        or native.get("profile") != value["profile"]
        or native.get("abi") != "arm64"
        or native.get("apk_sha256") != value["apk_sha256"]
        or not all(
            _valid_sha256(native.get(field))
            for field in ("dump_cs_sha256", "libil2cpp_sha256")
        )
        or not isinstance(native.get("objdump"), str)
        or not native["objdump"]
        or native.get("vtable_calibration") not in {"verified", "unverified"}
    ):
        raise StoryOutcomeCatalogError("story-outcome catalog has invalid native source provenance")


def _ids(value: object, name: str) -> list[int]:
    if not isinstance(value, list) or not value or value != sorted(value) or len(value) != len(set(value)) or any(type(item) is not int or item <= 0 for item in value):
        raise StoryOutcomeCatalogError(f"{name} must be ordered unique positive integers")
    return value


def _master(value: object) -> CompanionDropMaster:
    if not isinstance(value, dict) or set(value) != {"companion_id", "drop_level"} or any(type(value[name]) is not int or value[name] <= 0 for name in ("companion_id", "drop_level")):
        raise StoryOutcomeCatalogError("each companion master requires positive ID and drop level")
    return CompanionDropMaster(value["companion_id"], value["drop_level"])


def _rule(value: object) -> StoryOutcomeRule:
    required = {"chapter", "section", "item_maxima", "character_maxima", "companion_maxima"}
    if not isinstance(value, dict) or set(value) - {"evidence"} != required or type(value["chapter"]) is not int or type(value["section"]) is not int or value["chapter"] < 2 or value["section"] < 1:
        raise StoryOutcomeCatalogError("each stage has an invalid identity")
    return StoryOutcomeRule(
        value["chapter"], value["section"],
        _maxima(value["item_maxima"]), _maxima(value["character_maxima"]), _maxima(value["companion_maxima"]),
        *_evidence(value.get("evidence")),
    )


def _evidence(value: object) -> tuple[bool, bool]:
    """Read a stage's optional evidence declaration as ``(items, characters)``.

    A ceiling of zero and a ceiling nobody could recover are both an empty
    ``maxima`` object, and enforcement must not treat them alike: the first is a
    statement that the stage drops nothing, the second is an admission that we
    do not know.  Since an empty ceiling forbids, conflating them refuses
    ordinary play on every stage whose encounters could not be joined.

    Absent means both are evidenced, which keeps an operator-authored catalog
    written before this field behaving exactly as it did.  A catalog the
    generator produces always states the field explicitly.
    """
    if value is None:
        return True, True
    if not isinstance(value, list) or any(entry not in {"items", "characters"} for entry in value) or len(set(value)) != len(value):
        raise StoryOutcomeCatalogError("stage evidence must be a unique list of 'items' and/or 'characters'")
    return "items" in value, "characters" in value


def _maxima(value: object) -> dict[int, int]:
    if not isinstance(value, dict):
        raise StoryOutcomeCatalogError("outcome maxima must be objects")
    result: dict[int, int] = {}
    for raw_id, maximum in value.items():
        if not isinstance(raw_id, str) or not raw_id.isdecimal() or raw_id != str(int(raw_id)) or int(raw_id) <= 0 or type(maximum) is not int or maximum < 1:
            raise StoryOutcomeCatalogError("outcome maxima require positive decimal IDs and counts")
        result[int(raw_id)] = maximum
    return result


def allowed(counter: Counter[int], maxima: dict[int, int]) -> bool:
    return all(value <= maxima.get(key, 0) for key, value in counter.items())
