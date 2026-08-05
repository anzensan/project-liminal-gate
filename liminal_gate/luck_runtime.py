"""Author a battle's six chest slots and its Luck growth, replay-stably.

The retired service decided both at battle start and sent them on
`start_quest`; the client rendered the chests at the results screen and folded
their contents into the balances it reports back at clear. Nothing about either
decision is recoverable from the APK, so this module is where the sourced
anchors in `luck_data` and the documented pools in `luck_pool_data` become an
actual roll.

**Replay is handled by construction, not by storage.** Both rolls are seeded
from the request identity, so a client retrying the same start -- under the same
request ID or a fresh one -- receives byte-identical chests rather than a
re-roll. That matters more here than elsewhere: a re-roll on retry would be a
reward duplicator.

One number in this module is invented, and it is isolated here rather than
spread through the logic: the chance a character gains Luck at a given stamina
cost. No source states it. What the sources do fix are its boundaries -- the
gate below eight stamina is Mistwalker's own, and the 0.1--0.3 magnitude is the
community record's -- so only the slope between them is chosen.
"""

from __future__ import annotations

import hashlib
import random

from liminal_gate.luck_data import (
    CHEST_TIERS,
    LUCK_GAIN_TENTHS,
    LUCK_TENTHS_MAX,
    LUCKY_ENEMIES_PER_BATTLE,
    LUCKY_ORBLING_GAIN_TENTHS,
    LUCKY_ORBLING_PINCER_CHANCE,
    gains_luck,
    team_luck,
)
from liminal_gate.luck_pool_data import pool_for

#: The six wire slots, empty-string for a slot that did not appear. The client
#: reads a fixed-length array and treats an empty entry as no chest.
EMPTY_SLOT = ""

#: **Local policy, and the only invented number in the Luck runtime.** The
#: chance one character's Luck rises after a qualifying battle, as a fraction of
#: the stage's stamina cost. The record says the chance grows with stamina and
#: never states it; this makes a 40-stamina stage a 40% chance per member. The
#: private reference server used this same base and then multiplied it by 1.5
#: while also dropping the eight-stamina gate, which is why its curve was not
#: reused.
LUCK_GAIN_CHANCE_PER_STAMINA = 0.01


def _seeded(*parts: object) -> random.Random:
    """A generator fixed by the request identity, so retries never re-roll."""
    material = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return random.Random(hashlib.sha256(material).hexdigest())


def party_team_luck(userdata: dict) -> int:
    """Read the account's current team Luck in tenths from its own save.

    Companion Luck effects are not applied here. The client publishes the three
    constants that describe them and computes its own display value; this server
    does not model which Companion is equipped to which party member, so the
    average is taken over the characters' stored Luck alone. The effect is that
    a Companion-boosted team is treated as slightly unluckier than the client
    shows it, which errs toward fewer chests rather than more.
    """
    roster = userdata.get("chrdata")
    party = userdata.get("teamMembers")
    if not isinstance(roster, list) or not isinstance(party, list):
        return 0
    luck_by_id = {
        row.get("id"): int(row.get("luck", 0))
        for row in roster
        if isinstance(row, dict) and type(row.get("luck", 0)) is int
    }
    members = tuple(
        luck_by_id.get(member, 0) for member in party[:6] if member
    )
    return team_luck(members)


def roll_luck_result(
    chapter: int, section: int, team_luck_tenths: int, *seed: object,
) -> list[str]:
    """Return the six chest slots for one battle, in the client's order.

    A stage with no documented pool for a tier yields an empty slot rather than
    an invented reward, so most of the game returns six empty slots. That is a
    limit of the record, not a claim that those stages had no chests.
    """
    generator = _seeded("luckResult", chapter, section, team_luck_tenths, *seed)
    slots: list[str] = []
    for tier in CHEST_TIERS:
        pool = pool_for(chapter, section, tier.name)
        chance = tier.probability(team_luck_tenths)
        # Draw for every tier whether or not it can pay out, so that adding a
        # pool later cannot shift the rolls of the tiers beside it.
        appeared = generator.random() < chance
        choice = generator.randrange(len(pool)) if pool else -1
        slots.append(pool[choice] if appeared and pool else EMPTY_SLOT)
    return slots


def roll_lucky_enemy_gain(*seed: object) -> int:
    """Return the Luck in tenths a flagged chapter's Lucky enemies grant.

    This is the `allowLucky` source, and it is deliberately *not* the
    battle-end gain: the record describes a Lucky Orbling as granting its Luck
    to every party member when pincered, with no reference to what the stage
    cost to enter. Keeping it separate is what lets a free Daily Quest and a
    five-stamina Hunting stage grant Luck while `LUCK_GAIN_MIN_STAMINA`, the
    developer's own rule, stays intact for the battle-end gain.

    Drawn from its own stream so that adding this source cannot shift a single
    existing `luckUpTable` roll on the stages that already had one.
    """
    generator = _seeded("luckyEnemy", *seed)
    gained = 0
    for _ in range(LUCKY_ENEMIES_PER_BATTLE):
        if generator.random() < LUCKY_ORBLING_PINCER_CHANCE:
            gained += LUCKY_ORBLING_GAIN_TENTHS
    return gained


def roll_luck_up_table(
    userdata: dict, stamina: int, *seed: object, allow_lucky: bool = False,
) -> list[int]:
    """Return each party slot's Luck gain in tenths, zero where it did not rise.

    Two sources feed one table, because `luckUpTable` is the only channel the
    client renders a Luck gain through. A quest costing less than eight stamina
    never raises Luck *at battle end*, which is the developer's own rule and
    excludes every Daily Quest, all of which are free. ``allow_lucky`` adds the
    separate Lucky-type enemy source, which that rule does not govern.

    A character at its ceiling stays there, and an empty slot stays zero.
    """
    party = userdata.get("teamMembers")
    if not isinstance(party, list):
        return [0] * 6
    members = list(party[:6]) + [0] * max(0, 6 - len(party[:6]))
    lucky = roll_lucky_enemy_gain(*seed) if allow_lucky else 0
    if not gains_luck(stamina) and not lucky:
        return [0] * 6
    roster = userdata.get("chrdata")
    current = {
        row.get("id"): int(row.get("luck", 0))
        for row in roster
        if isinstance(roster, list) and isinstance(row, dict) and type(row.get("luck", 0)) is int
    }
    generator = _seeded("luckUpTable", stamina, *seed)
    # A stage below the gate still walks the draws below, so that a flagged
    # cheap stage and an unflagged one of the same cost stay on one code path;
    # a zero chance simply never rolls.
    chance = min(1.0, stamina * LUCK_GAIN_CHANCE_PER_STAMINA) if gains_luck(stamina) else 0.0
    table: list[int] = []
    for member in members:
        # Draw per slot regardless, so an empty or capped slot cannot shift the
        # draws of the slots after it.
        rolled = generator.random() < chance
        gain = generator.choice(LUCK_GAIN_TENTHS)
        if not member:
            table.append(0)
            continue
        headroom = max(0, LUCK_TENTHS_MAX - current.get(member, 0))
        table.append(min((gain if rolled else 0) + lucky, headroom))
    return table


def apply_luck_up_table(userdata: dict, table: list[int]) -> None:
    """Commit a rolled Luck gain to the roster, capped at the client's ceiling."""
    roster = userdata.get("chrdata")
    party = userdata.get("teamMembers")
    if not isinstance(roster, list) or not isinstance(party, list):
        return
    gains = {
        member: gain
        for member, gain in zip(party[:6], table)
        if member and gain
    }
    for row in roster:
        if isinstance(row, dict) and row.get("id") in gains:
            row["luck"] = min(
                LUCK_TENTHS_MAX, int(row.get("luck", 0)) + gains[row["id"]],
            )


def chest_coins(slots: list[str]) -> int:
    """Total Coins the authored chests award, which the client folds into its
    reported balance at clear and the settlement must therefore expect."""
    return sum(int(slot[1:]) for slot in slots if slot.startswith("C") and slot[1:].isdigit())


def chest_items(slots: list[str]) -> dict[int, int]:
    """Item IDs and counts the authored chests award, for the same reason."""
    items: dict[int, int] = {}
    for slot in slots:
        if slot.startswith("I") and slot[1:].isdigit():
            items[int(slot[1:])] = items.get(int(slot[1:]), 0) + 1
    return items


def chest_companions(slots: list[str]) -> tuple[int, ...]:
    """Companion IDs the authored chests award."""
    return tuple(
        int(slot[1:]) for slot in slots if slot.startswith("O") and slot[1:].isdigit()
    )
