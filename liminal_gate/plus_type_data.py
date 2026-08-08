"""Recovered plus-stat curves from the final client's `ChrDatabase.plusTypes`.

A character carries a *plus count*, and the client turns that count into flat
ATK/DEF/SATK/SDEF bonuses through the curve its `ChrInfo.plusType` names.
`Entity.Status.EvaluatePlusEff` applies the result, so this is a battle stat
channel rather than a display.

Why this table is here rather than in the character-catalog import: the array is
a *private* field on `ChrDatabase`, so Unity never serialized it and it is not
in the APK's asset data at all.  `ChrDatabase.GetPlusTypeParams` builds it in
code on first use -- fourteen entries, `mov w1, #0xe` -- and the values below
were read out of that method.  The fourteen rows match the fourteen distinct
`plusType` values across the client's 346 recruitable characters exactly.

`PlusTypeParams..ctor` establishes the rest of each row: it zeroes both the min
block (`0x10`) and the max block (`0x20`), then writes 1.0 across all five
coefficients (`fmov v0.4s, #1.0` at `0x30`, `mov w8, #0x3f800000` at `0x40`).
The builder overrides only the four maxima, so every minimum is 0 and every
coefficient is 1.0, and `CalcValueAtCount` reduces to a straight line:

    bonus = maximum * count / PLUS_COUNT_MAX

**Nothing here grants a plus count.**  The two channels that did -- a Pact
result's `plusup` and a Rebirth's `addedPlusCount` -- were server-owned rules
that the retired service kept to itself, and no recovered source gives their
size.  This module describes what a count is worth; it does not invent one.
"""

from __future__ import annotations

#: `PlusTypeParams.ActualMaxCount`.  The client clamps against this, and a
#: count above it is not merely capped: `CalcValueAtCount` takes the branch
#: that logs "Detected plusCount cheating.." and returns a bonus of zero.  A
#: server that hands out more therefore takes the whole bonus away.
PLUS_COUNT_MAX = 300
#: `PlusTypeParams.MaxCount`.  Recorded for completeness; the client compares
#: against `ActualMaxCount` above and never against this one.
PLUS_COUNT_DECLARED_MAX = 1000

#: Plus type to `(ATKmax, DEFmax, SATKmax, SDEFmax)`: the bonus each stat
#: reaches at `PLUS_COUNT_MAX`.  Type 0 is the no-effect curve that 91 of the
#: 346 characters carry.
PLUS_TYPE_MAXIMA: tuple[tuple[int, int, int, int], ...] = (
    (0, 0, 0, 0),        # 0  -- no plus effect
    (100, 50, 20, 20),   # 1  -- attack
    (100, 30, 30, 30),   # 2  -- attack, spread
    (50, 100, 20, 20),   # 3  -- defence
    (30, 100, 30, 30),   # 4  -- defence, spread
    (20, 20, 100, 50),   # 5  -- special attack
    (30, 30, 100, 30),   # 6  -- special attack, spread
    (20, 20, 50, 100),   # 7  -- special defence
    (30, 30, 30, 100),   # 8  -- special defence, spread
    (90, 0, 100, 0),     # 9  -- offensive hybrid
    (50, 20, 100, 20),   # 10 -- special attack, attack lean
    (0, 100, 0, 90),     # 11 -- defensive hybrid
    (20, 100, 20, 50),   # 12 -- defence, special-defence lean
    (0, 90, 0, 100),     # 13 -- special defence, defence lean
)


def plus_stat_bonus(plus_type: int, count: int) -> tuple[int, int, int, int]:
    """Return the ATK/DEF/SATK/SDEF a plus count is worth on a curve.

    Mirrors `PlusTypeParams.CalcValueAtCount` for the recovered rows, where
    every minimum is zero and every coefficient is one.  A count past
    `PLUS_COUNT_MAX` returns zeroes, which is what the client does with it.
    """
    if not 0 <= plus_type < len(PLUS_TYPE_MAXIMA):
        raise ValueError(f"unknown plus type {plus_type}")
    if count < 0 or count > PLUS_COUNT_MAX:
        return (0, 0, 0, 0)
    return tuple(maximum * count // PLUS_COUNT_MAX for maximum in PLUS_TYPE_MAXIMA[plus_type])
