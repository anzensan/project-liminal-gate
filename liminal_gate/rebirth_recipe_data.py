"""Recovered Rebirth recipes from the final client's ChrDatabase.

Each row is ``(recipe_id, source_character_id, destination_character_id,
coins, ((item_id, count), ...), ((material_character_id, level), ...))``.
Item costs are decoded ``ItemCode`` values (``code >> 8`` is the item,
``code & 0xFF`` the count).

A recipe may require no materials at all: three of these consume neither Coins,
items, nor Companions, and the client's own master rows carry empty
``chrID``/``level`` slots for them.  Those empty slots are dropped here rather
than represented as character 0.

Every recipe's ``availableVersion`` is at or below the final client's own
version, so all of them are reachable; no availability gate is implied.

This is recovered structure and observed cost, the same category as the pooled
character IDs and Pact costs in :mod:`liminal_gate.pact_draw_catalog`.
"""

from __future__ import annotations

#: What a recode carries into the character it produces, in the client's tenths.
#:
#: **Community record, not recovered structure.**  The retired service owned
#: this arithmetic and the client holds no table for it, so this is the same
#: evidence class as the Pact class shares -- a documented rule this bundle
#: applies rather than a value read out of the APK.  Mistwalker's own play
#: guide covers the requirements and the warnings
#: (`terra-battle.com/en/playguide/post-5.html` and `post-4.html`) but not the
#: proportions; the community wiki's Recode DNA page carries those, and states
#: four things this implements:
#:
#: - the source's own Skill Boost and Luck carry over in full;
#: - a fifth of each material monster's Skill Boost carries over, so a monster
#:   at 100% contributes 20% and the pair contribute at most 40%;
#: - **a fifth of each material monster's Luck carries over too**, on the same
#:   rule and in the same words -- the page states it in its own `Luck` section,
#:   sentence for sentence alongside the Skill Boost one;
#: - a recode into a character the account **already owns** does not reset that
#:   character's level -- it gains the Skill Boost and Luck instead, and 5 Luck
#:   on top.
#:
#: The carried total is bounded by the client's own ceilings either way.
#:
#: The material Luck share was missing from this transcription until a tester
#: recoded with a Megacell at its 70.0 cap, expected 14.0 Luck to come across,
#: and got none. Two of the page's four rules were read and two were not, which
#: is the failure mode a rule copied by hand has: nothing disagreed, because
#: nothing else held the rule.
MATERIAL_SKILL_BOOST_SHARE_PERCENT = 20
#: The share of each material monster's Luck that carries over, as a percent.
#: A fifth, the same as the Skill Boost share above and for the same reason:
#: the record gives one proportion and applies it to both. Kept as its own name
#: rather than folded into that one so neither can be changed by accident while
#: reasoning about the other.
MATERIAL_LUCK_SHARE_PERCENT = 20
#: The Luck an already-owned destination gains, in tenths: 5.0 Luck, the same
#: unit and the same size as the Fate duplicate gain in `pact_draw_catalog`.
OWNED_DESTINATION_LUCK_BONUS = 50

# recipe_id, source, destination, coins, ((item, count), ...), ((chr, level), ...)
REBIRTH_RECIPE_ROWS: tuple[tuple[int, int, int, int, tuple[tuple[int, int], ...], tuple[tuple[int, int], ...]], ...] = (
    (1, 2, 623, 30000, ((10, 15), (93, 5), (96, 1)), ((237, 50), (145, 50))),
    (2, 8, 624, 30000, ((10, 15), (93, 5), (96, 1)), ((237, 50), (285, 50))),
    (3, 13, 625, 30000, ((11, 15), (93, 5), (97, 1)), ((165, 50), (337, 50))),
    (4, 25, 626, 30000, ((17, 15), (94, 5), (99, 1)), ((163, 50), (264, 50))),
    (5, 34, 627, 30000, ((10, 15), (93, 5), (96, 1)), ((164, 50), (146, 50))),
    (6, 56, 628, 30000, ((13, 15), (94, 5), (98, 1)), ((166, 50), (150, 50))),
    (7, 57, 629, 30000, ((14, 15), (94, 5), (98, 1)), ((166, 50), (149, 50))),
    (8, 58, 630, 30000, ((15, 15), (94, 5), (98, 1)), ((239, 50), (286, 50))),
    (9, 59, 631, 30000, ((16, 15), (94, 5), (98, 1)), ((238, 50), (292, 50))),
    (10, 148, 632, 30000, ((13, 15), (94, 5), (98, 1)), ((99, 50), (524, 50))),
    (11, 144, 634, 30000, ((14, 15), (94, 5), (98, 1)), ((126, 50), (671, 50))),
    (12, 151, 633, 30000, ((10, 15), (93, 5), (96, 1)), ((86, 50), (463, 50))),
    (13, 163, 621, 20000, ((9, 15), (94, 5), (95, 1)), ((238, 50), (299, 50))),
    (14, 164, 622, 20000, ((9, 15), (93, 5), (95, 1)), ((239, 50), (307, 50))),
    (15, 23, 693, 30000, ((46, 15), (94, 5), (99, 1)), ((165, 50), (124, 50))),
    (16, 35, 692, 30000, ((9, 15), (93, 5), (95, 1)), ((164, 50), (216, 50))),
    (17, 52, 694, 30000, ((16, 15), (94, 5), (98, 1)), ((678, 50), (292, 50))),
    (18, 540, 691, 30000, ((9, 15), (93, 5), (95, 1)), ((163, 50), (313, 50))),
    (19, 718, 719, 30000, ((107, 5), (108, 5), (109, 5)), ((763, 50), (764, 50))),
    (20, 399, 801, 30000, ((10, 15), (93, 5), (96, 1)), ((85, 50), (107, 50))),
    (21, 27, 802, 30000, ((9, 15), (93, 5), (95, 1)), ((679, 50), (100, 50))),
    (22, 5, 804, 30000, ((46, 15), (94, 5), (99, 1)), ((648, 50), (115, 50))),
    (23, 42, 825, 30000, ((9, 15), (93, 5), (95, 1)), ((679, 50), (94, 50))),
    (24, 50, 827, 30000, ((11, 15), (93, 5), (97, 1)), ((703, 50), (314, 50))),
    (25, 11, 846, 30000, ((9, 15), (93, 5), (95, 1)), ((678, 50), (143, 50))),
    (26, 60, 848, 10000, ((46, 5), (94, 1), (115, 1)), ((212, 50), (98, 50))),
    (27, 12, 861, 20000, ((46, 15), (99, 1), (132, 5)), ((853, 50), (124, 50))),
    (28, 402, 862, 30000, ((9, 15), (95, 1), (133, 5)), ((855, 50), (299, 50))),
    (29, 403, 863, 30000, ((10, 15), (96, 1), (133, 5)), ((857, 50), (145, 50))),
    (30, 39, 864, 20000, ((9, 15), (95, 1), (132, 5)), ((859, 50), (313, 50))),
    (31, 16, 865, 20000, ((10, 15), (96, 1), (132, 5)), ((853, 50), (285, 50))),
    (32, 46, 866, 20000, ((13, 15), (98, 1), (132, 5)), ((857, 50), (150, 50))),
    (33, 871, 867, 0, (), ()),
    (34, 871, 868, 0, (), ()),
    (35, 894, 903, 30000, ((12, 15), (134, 5), (137, 50)), ((899, 50), (889, 50))),
    (36, 24, 890, 30000, ((17, 15), (94, 5), (99, 1)), ((901, 50), (264, 50))),
    (37, 29, 891, 20000, ((9, 15), (95, 1), (132, 5)), ((899, 50), (94, 50))),
    (38, 40, 892, 20000, ((10, 15), (96, 1), (132, 5)), ((895, 50), (176, 50))),
    (39, 17, 893, 20000, ((11, 15), (97, 1), (132, 5)), ((897, 50), (314, 50))),
    (40, 915, 916, 30000, ((123, 15), (136, 5), (137, 50)), ((938, 50), (888, 50))),
    (41, 47, 921, 30000, ((9, 15), (93, 5), (95, 1)), ((679, 50), (143, 50))),
    (42, 1, 920, 20000, ((9, 15), (95, 1), (132, 5)), ((648, 50), (221, 50))),
    (43, 6, 922, 20000, ((14, 15), (98, 1), (132, 5)), ((711, 50), (149, 50))),
    (44, 32, 923, 20000, ((10, 15), (96, 1), (132, 5)), ((703, 50), (146, 50))),
    (45, 918, 919, 30000, ((94, 5), (99, 1), (143, 5)), ((947, 50), (220, 50))),
    (46, 3, 998, 20000, ((11, 15), (97, 1), (132, 5)), ((703, 50), (199, 50))),
    (47, 588, 999, 30000, ((12, 15), (94, 5), (98, 1)), ((678, 50), (128, 50))),
    (48, 971, 972, 30000, ((12, 15), (135, 5), (137, 50)), ((965, 50), (887, 50))),
    (49, 974, 975, 30000, ((10, 15), (93, 5), (96, 1)), ((967, 50), (110, 50))),
    (50, 1004, 973, 0, (), ()),
    (51, 736, 1002, 30000, ((94, 5), (99, 1), (147, 5)), ((1003, 50), (107, 50))),
    (52, 620, 1007, 10000, ((16, 5), (94, 1), (98, 1)), ((337, 50), (346, 50))),
    (53, 81, 1082, 20000, ((9, 15), (95, 1), (132, 5)), ((969, 50), (1090, 50))),
    (54, 188, 1083, 20000, ((11, 5), (93, 1), (96, 1)), ((86, 50), (216, 50))),
    (55, 1084, 1085, 30000, ((46, 15), (134, 5), (137, 50)), ((1014, 50), (889, 50))),
    (56, 28, 1203, 20000, ((9, 15), (95, 1), (132, 5)), ((1224, 50), (220, 50))),
    (57, 7, 1204, 30000, ((10, 15), (93, 5), (96, 1)), ((1225, 50), (285, 50))),
    (58, 1097, 1217, 30000, ((94, 5), (98, 1), (165, 15)), ((711, 50), (149, 50))),
    (59, 831, 1218, 30000, ((94, 5), (98, 1), (122, 15)), ((648, 50), (145, 50))),
    (60, 828, 1219, 30000, ((93, 5), (95, 1), (123, 15)), ((938, 50), (292, 50))),
    (61, 834, 1220, 30000, ((94, 5), (98, 1), (122, 15)), ((1224, 50), (307, 50))),
    (62, 1201, 1221, 30000, ((11, 15), (96, 1), (132, 5)), ((1227, 50), (314, 50))),
    (63, 49, 1222, 30000, ((46, 15), (94, 5), (99, 1)), ((1226, 50), (286, 50))),
    (64, 41, 1223, 20000, ((11, 15), (96, 1), (132, 5)), ((855, 50), (337, 50))),
    (65, 37, 1251, 30000, ((11, 15), (95, 1), (132, 5)), ((1227, 50), (199, 50))),
)
