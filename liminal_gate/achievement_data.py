"""Recovered achievement rows from the final client's master data.

The client ships 99 achievement records.  Nine carry an `unlockType` of 0
(ClearChapter) with a positive `unlockValue1`, so their predicate is a
story-progress comparison this server can evaluate on its own; eight of those
nine are reachable and keep their condition.  Every other record is decided by
the client against its own state, which is why `ACHIEVEMENT_ROWS` below carries
a zero `required_chapter` for them rather than a condition this server cannot
see.

The nineteen Co-op and VS records are the one family whose state the server
still supplies, through `UserData.multiplayData`; see
`MULTIPLAY_ACHIEVEMENT_CONDITIONS`.

Each row is ``(achievement_id, required_chapter, free_energy, coins, items)``.
The eight clear-chapter rows pay the same present list -- one Energy and one of
item 50 -- and that uniformity is the client's, not a simplification made here.
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


#: The nineteen Co-op and VS conditions, read out of `AchievementUtil.IsUnlocked`
#: in the reviewed ARM64 `libil2cpp.so`.  That method is a 27-way switch on
#: `unlockType`; cases 11 through 20 all take the same shape::
#:
#:     UserData.instance.multiplayData.GetXxx(info.unlockValue1) >= info.unlockValue2
#:
#: so `unlockValue1` is a *list index* and `unlockValue2` is the threshold.  The
#: shared `GetNumImpl` returns 0 when the index is past the list's end, and sums
#: every element when the index is -1.  `CoopPrize` is the exception: it reads
#: the scalar `prize` and compares it against `unlockValue1`, with no index at
#: all, which is why those two rows carry `None`.
#:
#: Two details worth keeping: the `VsFreeConsectiveWin` and
#: `VsFriendConsectiveWin` types read the `...Max` lists rather than the
#: identically named `...Num` lists the client also carries, and every threshold
#: is a `>=`.
#:
#: ``(achievement_id, key, field, index, threshold)``.  ``field`` is the JSON key
#: `MultiplayUserData.LoadFromJsonNormal` loads that list from, not the C# field
#: name, because two of them differ.
MULTIPLAY_ACHIEVEMENT_CONDITIONS: tuple[tuple[int, str, str, int | None, int], ...] = (
    (68, "Freedom", "coopFreePlayNum", -1, 30),
    (69, "Friendly", "coopFriendPlayNum", -1, 30),
    (70, "Ownership", "coopFreePlayNum", 0, 50),
    (71, "Supporter", "coopFreePlayNum", 1, 50),
    (72, "Speedy", "coopSimplePlayNum", -1, 30),
    (73, "Prize1", "prize", None, 20),
    (74, "VsMaster", "vsFreePlayNum", -1, 100),
    (75, "VsMaster2", "vsFreePlayNum", -1, 300),
    (76, "VsMaster3", "vsFreePlayNum", -1, 500),
    (77, "FriendBattler", "vsFriendPlayNum", -1, 20),
    (78, "VsKiller", "vsFreeWinNum", -1, 50),
    (79, "VsKiller2", "vsFreeWinNum", -1, 150),
    (80, "VsKiller3", "vsFreeWinNum", -1, 250),
    (81, "FriendKiller", "vsFriendWinNum", -1, 50),
    (82, "Striker", "vsFreeConsectiveWinMax", -1, 3),
    (83, "Striker2", "vsFreeConsectiveWinMax", -1, 5),
    (84, "Striker3", "vsFreeConsectiveWinMax", -1, 10),
    (85, "FriendStriker", "vsFriendConsectiveWinMax", -1, 20),
    (93, "Prize2", "prize", None, 50),
)

#: Every key `MultiplayUserData.LoadFromJsonNormal` reads, in the order it reads
#: them.  The object is sent complete rather than trimmed to the counters the
#: conditions need: `SafeJsonLoader` tolerates a missing key, but a partial
#: object would leave the next reader of this file guessing which omissions were
#: deliberate.  `rank` is absent on purpose -- the client derives it from `exp`
#: rather than loading it.
_MULTIPLAY_SCALARS: tuple[str, ...] = ("exp", "prize", "vsPlayChapter", "vsPlayMatchType", "vsStaminaRefillStartTime")
_MULTIPLAY_LISTS: tuple[str, ...] = (
    "titleList", "showTitles", "friendList",
    "coopFriendPlayNum", "coopFreePlayNum", "coopSimplePlayNum",
    "vsFreePlayNum", "vsFriendPlayNum", "vsFreeWinNum", "vsFriendWinNum",
    "vsFreeConsectiveWinNum", "vsFriendConsectiveWinNum",
    "vsFreeConsectiveWinMax", "vsFriendConsectiveWinMax",
)


def multiplay_achievement_projection() -> dict[str, object]:
    """Return the `multiplayData` object that settles all nineteen conditions.

    Co-op and VS ran against a player population, and no archive can restore
    one, so these counters are the only channel by which their achievements can
    ever be reached.  The values are *derived from the recovered conditions*
    rather than picked: each indexed slot carries the largest threshold declared
    for it, and a sum condition tops up the first slot only if the indexed
    thresholds have not already covered it.  Nothing here exceeds what the
    client asks for, and `test_achievement_policy` re-evaluates the client's own
    predicate against the result.

    This is a fabricated play history, and it is a deliberate one: the same
    reasoning that lists these records at all -- that hiding them reproduces a
    live service's judgement rather than an archive's -- decides that a screen
    the player can otherwise never finish should be finishable.  The cost is
    that `exp` stays 0 and the title lists stay empty, so the multiplay rank and
    title surfaces these counters also feed report nothing rather than a rank
    the account never held.
    """
    indexed: dict[str, dict[int, int]] = {}
    sums: dict[str, int] = {}
    scalars: dict[str, int] = {}
    for _, _, field, index, threshold in MULTIPLAY_ACHIEVEMENT_CONDITIONS:
        if index is None:
            scalars[field] = max(scalars.get(field, 0), threshold)
        elif index < 0:
            sums[field] = max(sums.get(field, 0), threshold)
        else:
            slots = indexed.setdefault(field, {})
            slots[index] = max(slots.get(index, 0), threshold)

    projection: dict[str, object] = {name: scalars.get(name, 0) for name in _MULTIPLAY_SCALARS}
    for name in _MULTIPLAY_LISTS:
        slots = indexed.get(name, {})
        values = [slots.get(position, 0) for position in range(max(slots, default=-1) + 1)]
        shortfall = sums.get(name, 0) - sum(values)
        if shortfall > 0:
            values = (values or [0])[:]
            values[0] += shortfall
        projection[name] = values
    return projection
