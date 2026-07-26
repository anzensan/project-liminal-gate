"""Recovered Battle Summon skill-unlock costs from the final client.

`SummonData` names the `ChrJobParams` job row backing each Summon's skill tier;
this table is that join, carrying each tier's Coin cost and material list.

Every one of the sixteen Summons has a level 0 that costs nothing and requires
no materials -- the skill the Summon ships with. Summons 1 and 2 have only that
level; the other fourteen each have two paid tiers above it, so there are 44
rows in total. All main-story Summon skill unlocks cost zero Coins and are paid
for in materials alone, which is the client's own arrangement.

Each row is ``(summon_id, skill_level, coins, ((item_id, count), ...))``.
Material item IDs are decoded `ItemCode` values (``code >> 8`` is the item,
``code & 0xFF`` the count).
"""

from __future__ import annotations

# summon_id, skill_level, coins, ((item_id, count), ...)
SUMMON_SKILL_ROWS: tuple[tuple[int, int, int, tuple[tuple[int, int], ...]], ...] = (
    (1, 0, 0, ()),
    (2, 0, 0, ()),
    (3, 0, 0, ()),
    (3, 1, 0, ((59, 3), (61, 3), (9, 5))),
    (3, 2, 0, ((59, 3), (61, 3), (71, 3))),
    (4, 0, 0, ()),
    (4, 1, 0, ((59, 3), (63, 3), (11, 5))),
    (4, 2, 0, ((59, 3), (63, 3), (73, 3))),
    (5, 0, 0, ()),
    (5, 1, 0, ((59, 3), (62, 3), (10, 5))),
    (5, 2, 0, ((59, 3), (62, 3), (72, 3))),
    (6, 0, 0, ()),
    (6, 1, 0, ((60, 3), (65, 3), (13, 5))),
    (6, 2, 0, ((60, 3), (65, 3), (74, 3))),
    (7, 0, 0, ()),
    (7, 1, 0, ((60, 3), (66, 3), (14, 5))),
    (7, 2, 0, ((60, 3), (66, 3), (75, 3))),
    (8, 0, 0, ()),
    (8, 1, 0, ((60, 3), (68, 3), (15, 5))),
    (8, 2, 0, ((60, 3), (68, 3), (76, 3))),
    (9, 0, 0, ()),
    (9, 1, 0, ((60, 3), (67, 3), (16, 5))),
    (9, 2, 0, ((60, 3), (67, 3), (77, 3))),
    (10, 0, 0, ()),
    (10, 1, 0, ((60, 3), (69, 3), (17, 5))),
    (10, 2, 0, ((60, 3), (69, 3), (79, 3))),
    (11, 0, 0, ()),
    (11, 1, 0, ((60, 3), (70, 3), (46, 5))),
    (11, 2, 0, ((60, 3), (70, 3), (78, 3))),
    (12, 0, 0, ()),
    (12, 1, 0, ((59, 3), (61, 3), (9, 5))),
    (12, 2, 0, ((59, 3), (61, 3), (22, 5))),
    (13, 0, 0, ()),
    (13, 1, 0, ((60, 3), (69, 3), (12, 5))),
    (13, 2, 0, ((60, 3), (69, 3), (24, 5))),
    (14, 0, 0, ()),
    (14, 1, 0, ((60, 3), (64, 3), (12, 5))),
    (14, 2, 0, ((60, 3), (64, 3), (140, 3))),
    (15, 0, 0, ()),
    (15, 1, 0, ((59, 3), (173, 3), (164, 5))),
    (15, 2, 0, ((59, 3), (173, 3), (174, 3))),
    (16, 0, 0, ()),
    (16, 1, 0, ((60, 3), (178, 3), (165, 5))),
    (16, 2, 0, ((60, 3), (178, 3), (179, 3))),)
