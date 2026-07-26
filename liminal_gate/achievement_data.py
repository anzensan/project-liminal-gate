"""Recovered clear-chapter achievement rows from the final client's master data.

The client ships 99 achievement records.  Only these eight are settleable by a
server: they are the ones whose `unlockType` is 0 (ClearChapter) with a positive
`unlockValue1`, so the predicate is a story-progress comparison the server can
evaluate on its own.  The other 91 are gated on client-local counters -- battles
fought, Companions raised, and similar -- which this project has not
reconstructed into authoritative server predicates and does not guess at.

Every one of the eight pays the same present list: one Energy and one of item
50.  That uniformity is the client's, not a simplification made here.

Each row is ``(achievement_id, required_chapter)``.  The reward is constant and
lives in :mod:`liminal_gate.achievement_catalog`.
"""

from __future__ import annotations

# achievement_id, required_chapter
ACHIEVEMENT_ROWS: tuple[tuple[int, int], ...] = (
    (1, 5),
    (2, 10),
    (3, 15),
    (4, 20),
    (5, 25),
    (6, 30),
    (7, 35),
    (8, 40),
)

# Every settleable achievement pays exactly this, per the recovered `presents`.
ACHIEVEMENT_FREE_ENERGY = 1
ACHIEVEMENT_ITEM_ID = 50
ACHIEVEMENT_ITEM_COUNT = 1
