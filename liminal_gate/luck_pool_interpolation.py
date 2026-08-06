"""Chest pools for the stages the record does not document, by donation.

The community record documents thirty story stages. Without this, every other
stage rolls six empty slots -- honest, and it leaves a feature the game clearly
had almost entirely inert: a player at Chapter 10 with real Luck never sees a
chest, because nobody wrote that page.

This fills the rest, and it is **on by default**. `--no-interpolated-luck-pools`
turns it off and restores the record-only behaviour.

**What is chosen, and what is not.** No reward here is invented. An undocumented
stage is answered with the pools the record documents for the two chapters it
brackets -- the nearest documented chapter at or below and at or above --
merged across their sections and deduplicated. Every Coin
amount, item, Companion and character a chest can produce under this rule
already appears in the record, for a chapter adjacent to the one being played.
What is chosen is *placement*: that Chapter 10, which the record does not cover,
should pay what Chapters 9 and 13 pay. Nothing else. In particular no Coin curve is fitted and no reward is scaled,
because the record's own Coin values do not sit on a clean curve -- Chapter 1
pays 50 where the trend through Chapters 4 to 36 would predict far more -- and
fitting one would replace a sourced value with a derived one.

**A documented stage is never touched.** Interpolation only answers where the
record is silent, so the thirty sourced stages keep their exact pools and remain
distinguishable from everything else. An explicit `--luck-pool-catalog` still
overrides both.

**This is not recovered data and nothing here pretends otherwise.** The retired
service owned the real table and no capture of it survives, so the odds a player
experiences under this rule are this project's arrangement of the record's
contents, not the retired service's. `PARITY_ROADMAP.md` continues to classify
the real rates and pools as unrecoverable. The server names the mode it is
running in at startup for the same reason.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from liminal_gate.luck_data import CHEST_TIERS
from liminal_gate.luck_pool_data import LUCK_CHEST_POOLS, pool_for


@lru_cache(maxsize=1)
def _documented_chapters() -> tuple[int, ...]:
    return tuple(sorted({chapter for chapter, _section in LUCK_CHEST_POOLS}))


@lru_cache(maxsize=None)
def _donor_pools(chapters: tuple[int, ...]) -> dict[str, tuple[str, ...]]:
    """Every reward the record documents in these chapters, by tier.

    Merged across each chapter's own sections as well, and deduplicated, so a
    reward the record repeats does not become a weight -- selection inside a
    tier is equal-weight and the record carries no weights.
    """
    merged: dict[str, list[str]] = {tier.name: [] for tier in CHEST_TIERS}
    for (documented, _section), tiers in sorted(LUCK_CHEST_POOLS.items()):
        if documented not in chapters:
            continue
        for name, pool in tiers.items():
            for reward in pool:
                if reward not in merged[name]:
                    merged[name].append(reward)
    return {name: tuple(rewards) for name, rewards in merged.items() if rewards}


def donor_chapters(chapter: int) -> tuple[int, ...]:
    """The documented chapters an undocumented one borrows from.

    The nearest documented chapter at or below, and the nearest at or above --
    the two the record brackets it with. Both, rather than the closer one
    alone, because single-chapter coverage is often a stub: Chapter 9's only
    documented stage carries one item in A and one in B, so a Chapter 10 player
    donated from 9 alone would get a chest barely worth rendering. Taking both
    sides is still only the record's own rewards, from the chapters adjacent to
    the one being played.
    """
    documented = _documented_chapters()
    below = [entry for entry in documented if entry <= chapter]
    above = [entry for entry in documented if entry >= chapter]
    return tuple(sorted({*below[-1:], *above[:1]}))


@dataclass(frozen=True)
class InterpolatedLuckPools:
    """Answers for undocumented stages; defers to the record everywhere else."""

    def pool_for(self, chapter: int, section: int, tier: str) -> tuple[str, ...]:
        documented = pool_for(chapter, section, tier)
        if documented or (chapter, section) in LUCK_CHEST_POOLS:
            # Either the record answers, or it answers this stage and left this
            # tier empty on purpose. Both are the record speaking; neither is a
            # gap to fill.
            return documented
        return _donor_pools(donor_chapters(chapter)).get(tier, ())


@dataclass(frozen=True)
class LayeredLuckPools:
    """An operator's catalog first, then interpolation, then the record."""

    catalog: object | None = None
    interpolated: InterpolatedLuckPools | None = None

    def pool_for(self, chapter: int, section: int, tier: str) -> tuple[str, ...]:
        if self.catalog is not None and (chapter, section) in getattr(self.catalog, "pools", {}):
            return self.catalog.pool_for(chapter, section, tier)
        if self.interpolated is not None:
            return self.interpolated.pool_for(chapter, section, tier)
        return pool_for(chapter, section, tier)


def build_luck_pools(
    catalog: object | None = None, interpolate: bool = True,
) -> LayeredLuckPools | None:
    """Compose the pool resolver a server should roll against.

    Returns ``None`` when neither layer is active, so the runtime keeps reading
    the record directly and no behaviour changes for a server that asked for
    neither.
    """
    if catalog is None and not interpolate:
        return None
    return LayeredLuckPools(catalog, InterpolatedLuckPools() if interpolate else None)
