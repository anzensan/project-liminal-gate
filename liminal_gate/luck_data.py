"""Luck: the stat, its caps, team averaging, and Luck Treasure Chest odds.

Luck is a per-character stat the client stores in tenths and displays divided by
ten -- `Character.get_luckRate` (ARM64 `0xD08B74`) loads the float at
`0x2056F48`, which is `0.1`, and multiplies by the stored value. Its only
purpose is Luck Treasure Chests: the retired service rolled six chest slots at
battle start, sent them as `luckResult` on `start_quest`, and the client
rendered them at the results screen. The client holds no chest table and no
spawn rule of its own, so nothing here can be recovered from the APK.

Three evidence grades are labeled below.

**Confirmed, primary.** Mistwalker's own Ver 4.2.0 announcement (2016-08-26,
archived) states the per-class caps, that a chest's "spawn rate and contents
depend on your team's average Luck value", that some quests spawn no chest at
all, and that Luck never increases from a quest costing less than eight
stamina.

**Community record.** The final wiki's Luck page supplies the six chest tiers
and four probability anchors, the 0.1--0.3 gain range, and the Companion
effects -- which independently corroborate the three Companion Luck constants
this server already derives from the operator's own APK, naming Unicorn (+10
personal), Panda (+30 personal), Senala O (+10 team), six Companions at +5
team, and Royal Ringstone doubling a gain.

**Local policy.** Exactly one thing: the *shape* of the curve between anchors.
Every endpoint below is sourced; only the interpolation joining them is chosen,
and it is chosen to add no free parameters -- each tier rises in proportion to
team Luck until it reaches the value the record states, and stays there. A
curve with invented coefficients was deliberately not used.

Note that `allowLucky` in the client's own `BattleData` is *not* the chest gate,
though it reads like one; see `docs/findings.md`, 2026-08-02.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The client's absolute ceiling, in the tenths it stores. Both a character's
#: own Luck and the team average stop here.
LUCK_TENTHS_MAX = 1000

#: **Confirmed, primary.** Per-class caps, in tenths. Any character whose name
#: carries a Lambda reaches 100.0 regardless of class.
LUCK_CAP_A_AND_BELOW = 700
LUCK_CAP_S_AND_SS = 800
LUCK_CAP_Z_AND_LAMBDA = 1000

#: **Confirmed, primary.** A quest costing less than this never raises Luck.
#: The one rule a preservation server is most tempted to drop, because it makes
#: every zero-stamina archive stage ineligible; it is the developer's own.
LUCK_GAIN_MIN_STAMINA = 8

#: **Community record.** A successful battle-end gain is 0.1 to 0.3, in tenths.
LUCK_GAIN_TENTHS = (1, 2, 3)

#: **Community record.** Pincering a Lucky Orbling correctly grants +0.3 to
#: every party member with a 50% chance, or certainly if it is outflanked; a
#: Lucky Runner grants +0.1. These are Luck *sources*, and are the reason
#: `allowLucky` marks the five chapters it does.
LUCKY_ORBLING_GAIN_TENTHS = 3
LUCKY_ORBLING_PINCER_CHANCE = 0.5
LUCKY_RUNNER_GAIN_TENTHS = 1

#: The five chapters whose recovered `BattleData` sets `allowLucky` to 1: 2006
#: Lucia, 3003 Money Money Time, 3004 Crystal Road, 6010 Lucky Orbling, and
#: 7010 Cryptid Forest. See the `allowLucky` finding in `docs/findings.md` for
#: why the flag reads as "Lucky-type enemies may spawn here" rather than as the
#: chest gate an earlier reading took it for.
#:
#: 7010 is `ChapterInterface.EidolonForestChapter` in the client and was
#: recorded here under that internal name. The player-facing name is Cryptid
#: Forest -- 幻獣の森, the same 幻獣 the game translates as Eidolon elsewhere --
#: and it matters because the record files this stage's Lucky enemy under the
#: English name, which is how the species below was found to be wrong.
#:
#: Two of them -- Money Money Time at five stamina and Crystal Road at seven --
#: sit *below* `LUCK_GAIN_MIN_STAMINA`, and Lucky Orbling is a free Daily
#: Quest. That is the whole reason a Lucky enemy has to be modelled as its own
#: source: fold it into the battle-end gain and the three stages the record
#: most clearly documents as Luck sources are the three it cannot reach.
ALLOW_LUCKY_CHAPTERS = frozenset({2006, 3003, 3004, 6010, 7010})

#: **Community record.** The flagged chapters whose Lucky enemy is a Lucky
#: Runner rather than a Lucky Orbling, and which therefore grant +0.1 rather
#: than +0.3.
#:
#: Cryptid Forest is the one flagged chapter the record documents enemy by
#: enemy, and what it documents is a Runner: one always spawns in a random
#: battle, a second spawns with a 30% chance, and pincering one *in any
#: direction* grants 0.1 Luck to every party member. Nothing about it is an
#: Orbling, so the reasoning that picked the Orbling's numbers for every
#: flagged chapter does not reach this one.
LUCKY_RUNNER_CHAPTERS = frozenset({7010})

#: **Community record.** One Lucky Runner is guaranteed per run and a second
#: appears with this chance. The record also gives a 50% variant for a party
#: carrying Dracorin Λ's *Cryptid Ruler* skill; this server does not model
#: which skills a party brings, so the unconditional rate is the one used and
#: the conditional one is deliberately left out rather than guessed at.
LUCKY_RUNNER_GUARANTEED_PER_BATTLE = 1
LUCKY_RUNNER_EXTRA_SPAWN_CHANCE = 0.3

#: **Local policy, and the second invented number in the Luck runtime.** How
#: many Lucky-type enemies one battle on an *Orbling* chapter offers a pincer
#: at. The record fixes the gain and the chance but never states a population
#: for those four, and the spawn itself is decided by client-side battle data
#: this server does not read. One per battle is the least the flag can mean
#: while still meaning anything, and it keeps the invented claim to a count
#: rather than a distribution.
#:
#: This number is invented only where the record is silent. It does not govern
#: `LUCKY_RUNNER_CHAPTERS`, whose population the record states outright.
LUCKY_ENEMIES_PER_BATTLE = 1


@dataclass(frozen=True)
class ChestTier:
    """One of the six chest slots, and the rule that decides it appears.

    `guaranteed_at` is the team Luck, in tenths, at or above which the record
    states the chest always drops. `ceiling` is the probability it reaches
    there: 1.0 for a chest that becomes guaranteed, and for C and D the value
    the record gives at 100.0 Luck. `threshold_only` marks the two chests named
    for a Luck value, which the record describes only as dropping at or above
    it and which therefore never drop below.
    """

    name: str
    guaranteed_at: int
    ceiling: float
    threshold_only: bool = False

    def probability(self, team_luck_tenths: int) -> float:
        """The chance this chest appears for a team at the given Luck."""
        luck = max(0, min(LUCK_TENTHS_MAX, team_luck_tenths))
        if self.threshold_only:
            return self.ceiling if luck >= self.guaranteed_at else 0.0
        if luck >= self.guaranteed_at:
            return self.ceiling
        # Local policy, and the only chosen number in this module: rise in
        # proportion to Luck up to the stated anchor. Higher Luck raises the
        # chance, which is what the record says, and no coefficient is invented.
        return self.ceiling * luck / self.guaranteed_at


#: **Community record**, anchor by anchor. A is guaranteed from 40.0 Luck and B
#: from 85.0; at 100.0 Luck a team always receives A, B, Luck 80 and Luck 100,
#: while C lands at 50% and D at 25%. A through D have no minimum Luck, so they
#: are proportional rather than gated; the two named chests are gated.
CHEST_TIERS: tuple[ChestTier, ...] = (
    ChestTier("A", guaranteed_at=400, ceiling=1.0),
    ChestTier("B", guaranteed_at=850, ceiling=1.0),
    ChestTier("C", guaranteed_at=LUCK_TENTHS_MAX, ceiling=0.5),
    ChestTier("D", guaranteed_at=LUCK_TENTHS_MAX, ceiling=0.25),
    ChestTier("Luck 80", guaranteed_at=800, ceiling=1.0, threshold_only=True),
    ChestTier("Luck 100", guaranteed_at=LUCK_TENTHS_MAX, ceiling=1.0, threshold_only=True),
)

#: The six wire slots the client renders, in the order it reads them.
CHEST_SLOT_COUNT = len(CHEST_TIERS)


def team_luck(
    member_luck_tenths: tuple[int, ...],
    personal_bonus_tenths: tuple[int, ...] = (),
    team_bonus_tenths: int = 0,
) -> int:
    """Return the team's average Luck in tenths, Companion effects included.

    Each member's own Luck takes its personally equipped Companion's bonus
    first, capped at the client's ceiling -- the record notes a personal bonus
    may carry a character past its own class cap, but never past 100.0. The
    average of those is then raised by the team-wide bonuses and capped again.
    An empty party has no average and is zero rather than an error.
    """
    party = tuple(member_luck_tenths)
    if not party:
        return 0
    bonuses = tuple(personal_bonus_tenths) + (0,) * max(0, len(party) - len(personal_bonus_tenths))
    total = sum(
        min(LUCK_TENTHS_MAX, max(0, luck) + max(0, bonus))
        for luck, bonus in zip(party, bonuses)
    )
    return min(LUCK_TENTHS_MAX, total // len(party) + max(0, team_bonus_tenths))


def chest_probabilities(team_luck_tenths: int) -> dict[str, float]:
    """Return each chest slot's appearance chance at this team Luck."""
    return {tier.name: tier.probability(team_luck_tenths) for tier in CHEST_TIERS}


def gains_luck(stamina: int) -> bool:
    """Whether a quest of this stamina cost may raise Luck at all."""
    return stamina >= LUCK_GAIN_MIN_STAMINA
