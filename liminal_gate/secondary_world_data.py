"""BreaSoul and the Five Emperors: the client's two secondary world maps.

`UIMap` can swap the world map for one of two others. `IsWorld1ChangeEnable`
opens BreaSoul and `IsWorld2ChangeEnable` opens the Five Emperors, each behind a
client version predicate that is already true for the supported 5.5.7 APK, a
story threshold, and a map flag the server sends. Neither family appears in a
Hunting or Special selector, so both use the `hidden` selector the Daily Quests
already use: the client draws the map point itself and asks this server only to
honour the entry.

**Confirmed, from the operator's own embedded `BattleData`.** Every identity,
stamina cost and Coin cost below, and the Companion candidate manifests. BreaSoul
is twenty sections across Chapters 100--104, each 15 stamina and zero Coins, and
every one of them declares an *empty* `dropBuddies`. The Five Emperors are ten
sections, one per chapter across 110--119, zero Coins throughout, 15 stamina for
the five normal descents and 20 for the five marked hard, each declaring one or
two candidate Companions.

**Local policy, labeled as such.** Three things.

The story thresholds -- section 26-1 for BreaSoul and 20-1 for the Five Emperors
-- are the halves of the client's map predicates this server owns. They are not
recovered from a table; the client's own version predicate is the part that is.

Experience is paid, under a ceiling, on the same reasoning the two Roads already
use here: EXP is the battle's own product rather than a reward the retired
service chose, and refusing it means a player wins a battle and is told no. The
ceiling exists to refuse an absurd claim, not to reproduce a rate.

The Companion payout is a bounded acceptance, not a reproduction. A Five
Emperors clear may report at most one Companion its own manifest names, minted
at level 1 -- the rule Chapter 1100 already uses, for the identical situation of
a manifest that proves candidates without proving a roll. BreaSoul's manifests
are empty, so it settles no Companion at all, on the game's own authority.

Coins and items are refused for both. No section declares a Coin reward and no
item manifest survives, so there is nothing to bound them against.
"""

from __future__ import annotations

from liminal_gate.hunting_catalog import HuntingStage

#: The client's own map flags. `sp_matsuno` opens the BreaSoul map; the Five
#: Emperors need both of theirs, because the final map's expanded coordinate
#: branch checks the second once the world-2 selector is on.
BREASOUL_EVENT_FLAG = "sp_matsuno"
FIVE_EMPERORS_EVENT_FLAGS = ("sp_five_emperors", "sp_five_emperors2")

#: **Local policy.** The story sections at which each map becomes reachable.
BREASOUL_UNLOCK = (26, 1)
FIVE_EMPERORS_UNLOCK = (20, 1)

#: **Local policy.** An EXP ceiling per entry, taken from the Metal Zone tier
#: whose stamina these stages match, exactly as the two Roads take theirs.
_BREASOUL_EXP_CEILING = 1_560_000
_FIVE_EMPERORS_EXP_CEILING = 1_560_000
_FIVE_EMPERORS_HARD_EXP_CEILING = 2_270_000

#: **Confirmed.** Chapter to its section count. 100 carries four sections and
#: 104 carries one; the three between carry five each, twenty in total.
_BREASOUL_SECTIONS: tuple[tuple[int, int], ...] = (
    (100, 4), (101, 5), (102, 5), (103, 5), (104, 1),
)

#: **Confirmed.** Chapter, stamina, and the Companion candidates its own
#: `dropBuddies` manifest names. The five hard descents cost 20.
_FIVE_EMPERORS_ROWS: tuple[tuple[int, int, tuple[int, ...]], ...] = (
    (110, 15, (464,)),
    (111, 15, (462,)),
    (112, 15, (460,)),
    (113, 15, (466,)),
    (114, 15, (471, 48)),
    (115, 20, (470, 478)),
    (116, 20, (473, 480)),
    (117, 20, (472, 481)),
    (118, 20, (469, 479)),
    (119, 20, (468, 49)),
)

#: A dropped Companion arrives at level 1, as Chapter 1100's do.
_COMPANION_DROP_LEVEL = 1


def build_bundled_breasoul_stages() -> tuple[HuntingStage, ...]:
    """Return BreaSoul's twenty sections as bounded, unadvertised stages."""
    return tuple(
        HuntingStage(
            family="breasoul", chapter=chapter, section=section,
            stamina=15, coins=0, entry_item_id=0, entry_item_count=0,
            unlock_chapter=BREASOUL_UNLOCK[0], unlock_section=BREASOUL_UNLOCK[1],
            max_coins=0, max_exp=_BREASOUL_EXP_CEILING,
            max_items_total=0, item_maxima={},
            # Empty `dropBuddies` in every one of the twenty: the game says
            # this family drops no Companion, so none is accepted.
            companion_maxima={},
            selector="hidden",
        )
        for chapter, sections in _BREASOUL_SECTIONS
        for section in range(1, sections + 1)
    )


def build_bundled_five_emperors_stages() -> tuple[HuntingStage, ...]:
    """Return the ten Five Emperors descents as bounded, unadvertised stages."""
    return tuple(
        HuntingStage(
            family="five_emperors", chapter=chapter, section=1,
            stamina=stamina, coins=0, entry_item_id=0, entry_item_count=0,
            unlock_chapter=FIVE_EMPERORS_UNLOCK[0],
            unlock_section=FIVE_EMPERORS_UNLOCK[1],
            max_coins=0,
            max_exp=_FIVE_EMPERORS_HARD_EXP_CEILING if stamina == 20 else _FIVE_EMPERORS_EXP_CEILING,
            max_items_total=0, item_maxima={},
            # One per candidate, but the total is what bounds a clear: the
            # record's rule for this shape of manifest is a single exclusive
            # roll, so a clear naming two of them is refused.
            companion_maxima={companion: 1 for companion in candidates},
            # The manifest proves which Companions a descent can give, not how
            # many. One exclusive roll is the record's rule for this shape, so
            # a clear naming both candidates of a two-candidate descent is
            # refused rather than paying twice.
            max_companions_total=1,
            companion_drop_levels={companion: _COMPANION_DROP_LEVEL for companion in candidates},
            selector="hidden",
        )
        for chapter, stamina, candidates in _FIVE_EMPERORS_ROWS
    )


def secondary_world_event_flags(progress_chapter: int, progress_section: int) -> dict[str, dict[str, object]]:
    """Return whichever secondary-world map flags this account has reached.

    Both maps are permanent once open, which is archive policy: their
    historical availability windows were live-service state and were never
    captured.
    """
    flags: dict[str, dict[str, object]] = {}
    reached = (progress_chapter, progress_section)
    if reached >= BREASOUL_UNLOCK:
        flags[BREASOUL_EVENT_FLAG] = {"name": BREASOUL_EVENT_FLAG, "value": True}
    if reached >= FIVE_EMPERORS_UNLOCK:
        for name in FIVE_EMPERORS_EVENT_FLAGS:
            flags[name] = {"name": name, "value": True}
    return flags
