"""The two permanent World Map Special routes, Chapter 1100.

`UIMap.InitPoints0` places two extra points on the ordinary world map once the
normal story has cleared Chapter 34.  No event flag, no schedule, no server
advertisement: the client draws them itself, so the local server's whole job is
to accept their entries and settle them without inventing rewards.

Both routes are five one-battle stages costing 25 stamina and no Coins.  The
client's own Chapter1100 behaviour class carries a `ShinenSettings` and a
`MutouSettings`, and drives `Battle_Shinen_1`..`_4` and `Battle_Mutou_1`..`_4`,
which is why the two routes are modeled separately here rather than as one
ten-stage chain.

Play order is the section ordinal, ascending, within each route -- Confirmed
by live traffic: a fresh account's very first `start_quest` for a route names
its lowest section id.  The embedded catalogue's own generator names
(`Battle_Shinen_1`.._4, `Battle_Mutou_1`.._4; see `native_encounter_importer`)
number each section by difficulty tier, not by play order, and that numbering
runs "4, 3, 2, 1" against the route's own section order -- the section titled
"battle 1" is the only one of its five with an assumed level of 80 rather than
90, in both routes independently, and it is the *fourth* section played, not
the first.  An earlier reading of this project took the title number as the
play sequence instead; that produced a frontier that rejected a route's own
opening battle outright (409 `world_map_special_locked` on the very first
entry), which is what live traffic caught.  The title/tier number is still the
community record's own vocabulary -- see the Companion paragraph below -- so
it is worth keeping straight from the play-order rank used here.

Confirmed from the final client's embedded `BattleData`: the ten identities,
25 stamina, zero entry Coins, `allowLucky=0`, the assumed levels, and the
packed Companion candidate manifests.  `allowLucky=0` is recorded here as a
fact and carries no conclusion about the Luck chest: every story chapter sets
it while still producing chests, so it does not mean what it looks like.  See
`hunting_catalog`'s Road note.  Local preservation policy: nothing.
The entry gate is the native map gate above, not a threshold this project chose.

The Companion payout is a bounded acceptance, not a reproduction.  The
community record (Mutoh Λ (Quest) and Shin'en Λ (Quest), terrabattle.fandom.com)
documents each battle's Companion reward as a single exclusive roll -- one
Companion per clear, drawn from that battle's own candidate set -- and its
per-tier candidate lists match this recovered `dropBuddies` manifest exactly:
three candidates on the record's "battle 4" (the record's Metal, Glassy and
Golden Minion Λ split; played *first*, not fourth -- see the play-order note
above), two on "battle 2" and "battle 3", one on "battle 1" (played fourth),
none on "battle 5" (the route's final, fifth-played section).  That agreement
between an independent source and the recovered manifest is why the
settlement now accepts **at most one** reported Companion per clear, and only
one the stage's own manifest names, minted at level 1.  The record's roll
weights (5/10, 3/10, 2/10 on "battle 4"; the 20% "battle 1" chance) and its
story-progress/UTC-hour difficulty schedule are recorded in the reference
ledger, not implemented: no settlement capture exists, so the odds are the
client's to roll and this server's only to bound.  The record also documents a
100%-if-unowned Mutoh Λ / Shin'en Λ *character* recruit on "battle 4" (the
route's opening section); character identities for the pair are not resolved
against recovered master data, so a clear claiming a character remains
refused.
"""

from __future__ import annotations

from dataclasses import dataclass


WORLD_MAP_SPECIAL_CHAPTER = 1100
# `UIMap.InitPoints0` adds both points after normal Chapter 34, so the earliest
# core progress that may enter is Chapter 35 Section 1.
UNLOCK_AFTER_CHAPTER = 34
WORLD_MAP_SPECIAL_STAMINA = 25
# A bound on the battle's own experience, not a recovered reward. Its purpose is
# to stop an arbitrary client-authored claim, so it is reasoned as an upper
# limit: Metal Zone 7 permits 7,720,000 across *five* battles at assumed level
# 70, and a Chapter-1100 section is a *single* battle at level 80 or 90, which
# cannot plausibly exceed that. Erring high is deliberate -- a bound that is too
# tight refuses honest clears, which is the failure this replaces.
WORLD_MAP_SPECIAL_EXP_CEILING = 7_720_000


@dataclass(frozen=True)
class WorldMapSpecialStage:
    """One recovered Chapter-1100 battle."""

    route: str
    battle: int
    section: int
    level: int
    stamina: int
    coins: int
    # (Companion id, packed level/count byte) exactly as `dropBuddies` stores
    # it.  See the module docstring for the acceptance rule built on it.
    companion_candidates: tuple[tuple[int, int], ...]

    @property
    def chapter(self) -> int:
        return WORLD_MAP_SPECIAL_CHAPTER

    @property
    def companion_drop_levels(self) -> dict[int, int]:
        """Accepted candidates mint at level 1, like every other bundled drop."""
        return {companion_id: 1 for companion_id, _ in self.companion_candidates}


@dataclass(frozen=True)
class WorldMapSpecialCatalog:
    stages: tuple[WorldMapSpecialStage, ...]

    def by_identity(self) -> dict[tuple[int, int], WorldMapSpecialStage]:
        return {(stage.chapter, stage.section): stage for stage in self.stages}

    def routes(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(stage.route for stage in self.stages))

    def final_battle(self, route: str) -> int:
        return max(stage.battle for stage in self.stages if stage.route == route)

    def unlocked_at(self, progress_chapter: int) -> bool:
        """Report whether core story progress has passed the native map gate."""
        return progress_chapter > UNLOCK_AFTER_CHAPTER


# route -> play-order rank (ascending section ordinal, Confirmed by live
# traffic) -> (section id, assumed level, candidates).  This rank is *not* the
# client's own difficulty/tier numbering recovered by
# `native_encounter_importer` (`Battle_Shinen_1`.._4 etc.), which runs
# "4, 3, 2, 1" against this order; see the docstring.
_ROUTES: dict[str, dict[int, tuple[int, int, tuple[tuple[int, int], ...]]]] = {
    "shinen": {
        1: (1, 90, ((129, 1), (267, 1), (140, 1))),
        2: (2, 90, ((223, 1), (66, 1))),
        3: (3, 90, ((213, 1), (96, 1))),
        4: (4, 80, ((137, 1),)),
        5: (5, 90, ()),
    },
    "mutoh": {
        1: (6, 90, ((129, 1), (267, 1), (140, 1))),
        2: (7, 90, ((120, 1), (125, 1))),
        3: (8, 90, ((171, 1), (175, 1))),
        4: (9, 80, ((111, 1),)),
        5: (10, 90, ()),
    },
}


def build_bundled_world_map_special_policy() -> WorldMapSpecialCatalog:
    """Return the recovered Chapter-1100 catalogue, ordered by route and battle."""
    stages = tuple(
        WorldMapSpecialStage(
            route=route, battle=battle, section=section, level=level,
            stamina=WORLD_MAP_SPECIAL_STAMINA, coins=0,
            companion_candidates=candidates,
        )
        for route, battles in _ROUTES.items()
        for battle, (section, level, candidates) in sorted(battles.items())
    )
    return WorldMapSpecialCatalog(stages)


def initial_route_progress(catalog: WorldMapSpecialCatalog) -> dict[str, int]:
    """Return the frontier every route starts at: its first battle."""
    return {route: 1 for route in catalog.routes()}


def world_map_special_companions_within_bounds(
    stage: WorldMapSpecialStage, buddies: list[int],
) -> bool:
    """Whether a reported Chapter-1100 Companion claim stays inside the policy.

    The community record describes one exclusive Companion roll per clear, so
    the bound is at most one reported Companion, and only one this stage's own
    recovered `dropBuddies` manifest names.  Battle 5 carries no candidates and
    therefore accepts none.
    """
    allowed = {companion_id for companion_id, _ in stage.companion_candidates}
    return len(buddies) <= 1 and all(companion_id in allowed for companion_id in buddies)
