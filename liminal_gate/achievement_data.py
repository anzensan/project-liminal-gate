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

#: Every achievement the client carries, recovered from its own `AchivementSet`
#: by :mod:`liminal_gate.achievement_importer` and transcribed here so the
#: bundled policy needs no APK at runtime.
#:
#: ``(achievement_id, required_chapter, free_energy, coins, items)``.
#:
#: **A zero `required_chapter` means free to claim**, and 89 of the 98 carry
#: one. Only the nine `ClearChapter` rows declare a condition this server can
#: check; the rest turn on `CharaLevel`, `CharaJob`, `SpeciesNum`, `SummonLevel`,
#: `GatheringExp`, `SpeedClear` and the retired Co-op and VS counters, none of
#: which the server observes. The client holds every threshold and evaluates
#: them against its own state, so it -- not this table -- decides what it shows
#: as achieved. Gating a claim on a condition this server cannot see would only
#: refuse a reward the player had already earned.
#:
#: The reward columns are the records' own `presents`, read as
#: `Energy`/`Coin`/`Item`. Twelve `Title` presents are dropped rather than
#: guessed at: a title lands on the client's `multiplayTitle` through a channel
#: this route does not carry, and awarding the wrong one is worse than awarding
#: none. The one empty-keyed placeholder record grants nothing and is omitted.
ACHIEVEMENT_ROWS: tuple[tuple[int, int, int, int, dict[int, int]], ...] = (
    (1, 5, 1, 0, {50: 1}),  # ClearChapter5
    (2, 10, 1, 0, {50: 1}),  # ClearChapter10
    (3, 15, 1, 0, {50: 1}),  # ClearChapter15
    (4, 20, 1, 0, {50: 1}),  # ClearChapter20
    (5, 25, 1, 0, {50: 1}),  # ClearChapter25
    (6, 30, 1, 0, {50: 1}),  # ClearChapter30
    (7, 35, 1, 0, {50: 1}),  # ClearChapter35
    (8, 40, 1, 0, {50: 1}),  # ClearChapter40
    (9, 0, 0, 0, {18: 1, 19: 1, 20: 1, 21: 1}),  # CharaLevel20
    (10, 0, 0, 0, {18: 1, 19: 1, 20: 1, 21: 1}),  # CharaLevel30
    (11, 0, 0, 0, {22: 1, 23: 1, 24: 1, 25: 1}),  # CharaLevel40
    (12, 0, 0, 0, {22: 1, 23: 1, 24: 1, 25: 1}),  # CharaLevel50
    (13, 0, 0, 0, {22: 1, 23: 1, 24: 1, 25: 1}),  # CharaLevel60
    (14, 0, 0, 0, {26: 1, 27: 1, 28: 1, 29: 1}),  # CharaLevel70
    (15, 0, 0, 0, {26: 1, 27: 1, 28: 1, 29: 1}),  # CharaLevel80
    (16, 0, 0, 0, {26: 1, 27: 1, 28: 1, 29: 1}),  # CharaLevel90
    (17, 0, 0, 0, {50: 1, 55: 1, 56: 1}),  # CharaJob2x3
    (18, 0, 0, 0, {50: 1, 55: 1, 56: 1}),  # CharaJob2x6
    (19, 0, 0, 0, {50: 1, 55: 1, 56: 1}),  # CharaJob2x12
    (20, 0, 0, 0, {50: 1, 55: 1, 56: 1}),  # CharaJob2x24
    (21, 0, 0, 0, {50: 1, 55: 1, 56: 1}),  # CharaJob2x36
    (22, 0, 0, 0, {50: 1, 55: 1, 56: 1}),  # CharaJob3x3
    (23, 0, 0, 0, {50: 1, 55: 1, 56: 1}),  # CharaJob3x6
    (24, 0, 0, 0, {50: 1, 55: 1, 56: 1}),  # CharaJob3x12
    (25, 0, 0, 0, {50: 1, 55: 1, 56: 1}),  # CharaJob3x24
    (26, 0, 0, 0, {50: 1, 55: 1, 56: 1}),  # CharaJob3x36
    (27, 0, 0, 0, {1: 10, 2: 10}),  # HumanCollector1
    (28, 0, 0, 0, {1: 10, 2: 10}),  # HumanCollector2
    (29, 0, 0, 0, {1: 10, 2: 10}),  # HumanCollector3
    (30, 0, 0, 0, {3: 10, 4: 10}),  # LizardCollector1
    (31, 0, 0, 0, {3: 10, 4: 10}),  # LizardCollector2
    (32, 0, 0, 0, {3: 10, 4: 10}),  # LizardCollector3
    (33, 0, 0, 0, {5: 10, 6: 10}),  # BeastCollector1
    (34, 0, 0, 0, {5: 10, 6: 10}),  # BeastCollector2
    (35, 0, 0, 0, {5: 10, 6: 10}),  # BeastCollector3
    (36, 0, 0, 0, {7: 10, 8: 10}),  # StoneCollector1
    (37, 0, 0, 0, {7: 10, 8: 10}),  # StoneCollector2
    (38, 0, 0, 0, {7: 10, 8: 10}),  # StoneCollector3
    (39, 0, 0, 0, {9: 10, 10: 10, 11: 10, 12: 10}),  # WildCollector1
    (40, 0, 0, 0, {13: 10, 14: 10, 15: 10, 16: 10}),  # WildCollector2
    (41, 0, 0, 0, {18: 1, 19: 1, 20: 1, 21: 1}),  # WildCollector3
    (42, 0, 0, 0, {89: 15, 90: 15}),  # DragonCollector1
    (43, 0, 0, 0, {59: 1, 60: 1}),  # SummonLevel1
    (44, 0, 0, 0, {59: 1, 60: 1}),  # SummonLevel2
    (45, 0, 0, 0, {59: 1, 60: 1}),  # SummonLevel3
    (46, 0, 1, 0, {}),  # SwordParty1
    (47, 0, 1, 0, {}),  # SwordParty2
    (48, 0, 1, 0, {}),  # SwordParty3
    (49, 0, 1, 0, {}),  # SpearParty1
    (50, 0, 1, 0, {}),  # SpearParty2
    (51, 0, 1, 0, {}),  # SpearParty3
    (52, 0, 1, 0, {}),  # ArrowParty1
    (53, 0, 1, 0, {}),  # ArrowParty2
    (54, 0, 1, 0, {}),  # ArrowPartyt3
    (55, 0, 1, 0, {}),  # WandParty1
    (56, 0, 1, 0, {}),  # WandParty2
    (57, 0, 1, 0, {}),  # WandParty3
    (58, 0, 1, 0, {}),  # SkillMaster1
    (59, 0, 1, 0, {}),  # SkillMaster2
    (60, 0, 1, 0, {}),  # SkillMaster3
    (61, 0, 1, 0, {}),  # SkillMaster4
    (62, 0, 0, 0, {53: 1, 55: 1}),  # ExpGatherer
    (63, 0, 0, 0, {53: 1, 56: 1}),  # CoinGatherer
    (64, 0, 0, 0, {53: 1, 54: 1}),  # ItemGatherer
    (65, 0, 2, 0, {}),  # GirlsTalk
    (66, 0, 2, 0, {}),  # SpeedStar
    (67, 0, 2, 0, {}),  # BeastMaster
    (68, 0, 1, 0, {}),  # Freedom
    (69, 0, 1, 0, {}),  # Friendly
    (70, 0, 1, 0, {}),  # Ownership
    (71, 0, 1, 0, {}),  # Supporter
    (72, 0, 1, 0, {}),  # Speedy
    (73, 0, 0, 0, {81: 2}),  # Prize1
    (74, 0, 1, 0, {}),  # VsMaster
    (75, 0, 1, 0, {}),  # VsMaster2
    (76, 0, 1, 0, {}),  # VsMaster3
    (77, 0, 1, 0, {}),  # FriendBattler
    (78, 0, 1, 0, {}),  # VsKiller
    (79, 0, 1, 0, {}),  # VsKiller2
    (80, 0, 1, 0, {}),  # VsKiller3
    (81, 0, 1, 0, {}),  # FriendKiller
    (82, 0, 1, 0, {}),  # Striker
    (83, 0, 1, 0, {}),  # Striker2
    (84, 0, 1, 0, {}),  # Striker3
    (85, 0, 1, 0, {}),  # FriendStriker
    (86, 0, 1, 0, {}),  # PostTwitter1
    (87, 0, 1, 0, {}),  # PostLine1
    (88, 0, 1, 0, {}),  # Temp1
    (89, 0, 1, 0, {}),  # Temp2
    (90, 0, 0, 0, {53: 1, 55: 1}),  # ExpGatherer2
    (91, 0, 0, 0, {53: 1, 56: 1}),  # CoinGatherer2
    (92, 0, 0, 0, {53: 1, 54: 1}),  # ItemGatherer2
    (93, 0, 0, 0, {81: 5}),  # Prize2
    (94, 0, 1, 0, {}),  # Survey1
    (95, 0, 1, 0, {}),  # SpecialQuest9010
    (96, 0, 1, 0, {}),  # SpecialQuest9011
    (97, 0, 1, 0, {}),  # SpecialQuest9012
    (98, 0, 1, 0, {}),  # SpecialQuest9013
)

# The eight clear-chapter rows above pay exactly this, and the constants remain
# because the recovered table confirms them rather than replaces them.
ACHIEVEMENT_FREE_ENERGY = 1
ACHIEVEMENT_ITEM_ID = 50
ACHIEVEMENT_ITEM_COUNT = 1
