"""An operator's own Luck Treasure Chest pools, for the stages the record misses.

The bundled pools in :mod:`liminal_gate.luck_pool_data` cover thirty-one core
story stages and the forty-two Strikes Back quests, because that is what the
community record covers. Every other stage
yields six empty slots. Almost certainly the retired service put chests on those
stages too; the table that decided their contents was server-side and no capture
of it survives, so the bundle states the absence rather than guessing at it.

This is the deliberate way to go further. An operator who wants chests on the
rest of the game supplies them here and passes ``--luck-pool-catalog``, and the
result is visibly theirs: the bundled table stays exactly as sourced, the
loaded file is named in the server's startup output, and `PARITY_ROADMAP.md`
keeps classifying the real rates and pools as unrecoverable, because they are.

**Why this is a file and not a default.** Everywhere else this project sets
local policy it sets a *bound* or a *gate* -- a reward ceiling, an unlock
chapter. Those fail safely: a ceiling that is too generous only ever declines to
refuse an honest claim. A chest pool is generative, so there is no direction in
which being wrong is harmless, and nothing can catch it being wrong: the server
authors the chest and the client renders whatever it is told, holding no table
of its own to disagree with. An invented pool is therefore permanently
unfalsifiable, and a save that collects from one cannot afterwards be told apart
from a save that did not. Keeping it opt-in is what preserves the difference
between what this project recovered and what an operator chose.

A stage this catalog names replaces the bundled pool for that stage outright,
tier for tier, rather than merging into it. Half-overriding a stage would leave
a pool no one authored, sourced in part and invented in part, with nothing
recording which half was which.

Rewards use the client's own wire encoding, the same four forms the bundle
uses: ``C`` and an amount for Coins, ``I`` and an item ID, ``O`` and a Companion
ID, ``M`` and a character ID.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import tomllib

from liminal_gate.luck_data import CHEST_TIERS
from liminal_gate.luck_pool_data import pool_for


#: Where the dedicated server looks for one without being told.
DEFAULT_LUCK_POOL_CATALOG = "luck-pools.json"


class LuckPoolCatalogError(ValueError):
    """A user-local Luck chest pool catalog is invalid."""


#: The tier names a stage may declare, in the order the client reads the slots.
TIER_NAMES: tuple[str, ...] = tuple(tier.name for tier in CHEST_TIERS)

#: The four reward forms, and the rule each one's payload follows.
REWARD_PREFIXES: tuple[str, ...] = ("C", "I", "O", "M")


@dataclass(frozen=True)
class LuckPoolCatalog:
    """Operator-declared chest pools, keyed by stage and then by tier."""

    pools: dict[tuple[int, int], dict[str, tuple[str, ...]]]

    def pool_for(self, chapter: int, section: int, tier: str) -> tuple[str, ...]:
        """This catalog's pool for one stage and tier, or the bundled one.

        A stage the catalog does not name keeps whatever the record documented
        for it, which is usually nothing. A stage it does name is answered
        entirely from here, including for a tier it left empty -- that is the
        operator declaring the tier pays nothing, not falling back.
        """
        stage = self.pools.get((chapter, section))
        if stage is None:
            return pool_for(chapter, section, tier)
        return stage.get(tier, ())

    def stage_count(self) -> int:
        return len(self.pools)


def load_luck_pool_catalog(path: Path) -> LuckPoolCatalog:
    """Load strict JSON or TOML operator-supplied chest pools."""
    try:
        value = (
            tomllib.loads(path.read_text(encoding="utf-8"))
            if path.suffix.lower() == ".toml"
            else json.loads(path.read_text(encoding="utf-8"))
        )
    except (OSError, json.JSONDecodeError, tomllib.TOMLDecodeError) as error:
        raise LuckPoolCatalogError("could not read Luck pool catalog JSON or TOML") from error
    required = {"schema_version", "provenance", "stages"}
    if (
        not isinstance(value, dict)
        or set(value) != required
        or value.get("schema_version") != 1
        or value.get("provenance") != "user-supplied"
    ):
        raise LuckPoolCatalogError("Luck pool catalog has an invalid schema or provenance")
    if not isinstance(value["stages"], list) or not value["stages"]:
        raise LuckPoolCatalogError("stages must be a nonempty array")
    pools: dict[tuple[int, int], dict[str, tuple[str, ...]]] = {}
    for item in value["stages"]:
        identity, tiers = _stage(item)
        if identity in pools:
            raise LuckPoolCatalogError(
                f"stage {identity[0]}-{identity[1]} is declared more than once"
            )
        pools[identity] = tiers
    return LuckPoolCatalog(pools)


def _stage(value: object) -> tuple[tuple[int, int], dict[str, tuple[str, ...]]]:
    if not isinstance(value, dict) or set(value) != {"chapter", "section", "tiers"}:
        raise LuckPoolCatalogError("each stage requires chapter, section, and tiers")
    for name in ("chapter", "section"):
        if type(value[name]) is not int or value[name] <= 0:
            raise LuckPoolCatalogError(f"{name} must be a positive integer")
    tiers = value["tiers"]
    if not isinstance(tiers, dict) or not tiers:
        raise LuckPoolCatalogError("tiers must be a nonempty object")
    unknown = set(tiers) - set(TIER_NAMES)
    if unknown:
        raise LuckPoolCatalogError(
            f"unknown chest tier {sorted(unknown)[0]!r}; the client reads {list(TIER_NAMES)}"
        )
    return (value["chapter"], value["section"]), {
        name: _pool(tiers[name], name) for name in TIER_NAMES if name in tiers
    }


def _pool(value: object, tier: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise LuckPoolCatalogError(f"tier {tier!r} must be an array of rewards")
    for reward in value:
        _reward(reward, tier)
    if len(set(value)) != len(value):
        raise LuckPoolCatalogError(f"tier {tier!r} repeats a reward")
    return tuple(value)


def _reward(value: object, tier: str) -> None:
    """Check one reward against the client's own wire encoding.

    Selection within a tier is equal-weight, so a repeat would be a weight by
    another name -- which is exactly the thing the record does not carry and
    this project does not invent. `_pool` refuses one for that reason.
    """
    if not isinstance(value, str) or len(value) < 2 or value[0] not in REWARD_PREFIXES:
        raise LuckPoolCatalogError(
            f"tier {tier!r} has a reward that is not one of {list(REWARD_PREFIXES)} "
            "followed by a value"
        )
    if not value[1:].isdigit():
        raise LuckPoolCatalogError(f"reward {value!r} must carry a nonnegative integer")
    if int(value[1:]) <= 0:
        raise LuckPoolCatalogError(
            f"reward {value!r} must carry a positive amount or identifier"
        )
