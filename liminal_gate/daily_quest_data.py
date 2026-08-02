"""Daily Quest stage identities and bounded local settlement.

Three different evidence grades live in this file and are labeled row by row.

**Recovered.** The stage set itself. ``DailyQuestData.questOrder`` in the
operator's own APK names fourteen stages, Chapters 6000--6012 plus section 2 of
6011; see :mod:`liminal_gate.daily_quest_importer`. A real BattleData tree
carries exactly those fourteen rows and no others, and the resource tree carries
exactly those fourteen ``Banner/sp<chapter>-<section>`` bundles. Three
independent assets agree on the same set.

**Confirmed identity.** Which stage is which quest. Each of the fourteen banner
textures in the APK was matched pixel-wise against the community record's own
banner images; every one matched a distinct quest, eleven of them essentially
identically, with the nearest rival roughly fifty times further away in every
case. Three of the assignments were independently predicted before the match
and confirmed by it: 6006 is the Energy quest because the client's own
``DailyQuestManager.EnergyGetChapter`` says so, 6011 carries the two Yamamoto
variants because it is the only chapter with two sections, and the rotation's
frequency classes force 6010 once 6006 is fixed.

**Local policy from a secondary source.** The settlement bounds. The retired
service owned Daily Quest rewards and the client only rendered them, so no APK
table exists and none can be recovered. The ceilings below bound a
client-reported clear the way the Hunting families do; they are deliberately
generous, because their job is to refuse an absurd claim rather than to
reproduce a drop rate. Item identities come from the community record and were
resolved to IDs through the operator's own master data, which is what makes them
checkable: ``Energy`` resolves to 80, the same number the client's own
``DailyQuestManager.EnergyItemId`` carries, and the two tickets resolve to the
50 and 81 this project already uses elsewhere.

The Hunt For Joker grants **character 1018, Joker Λ**, which is neither an item
nor a Companion and so travels through a dedicated server-side grant rather than
the reported-drop channel. Its identity is resolved from the operator's own
master data. The community record puts the drop at 100% and a further recruit at
+10% Skill Boost and +10 Luck; those two increments are the same grade of
secondary-source policy as the ceilings.

Every Daily Quest pays out **once per UTC day**, the boundary the record gives
for the rotation switching over. The client greys a played quest out from the
``lastDailyQuestPlayTime`` fields the login response carries, and the same limit
is enforced server-side as well, so a client that asks anyway is refused with
the client's own soft refusal rather than an error.

**Which two quests are today's is the server's answer, not the client's.**
``DailyQuestManager`` holds ``todaysQuest``/``todaysQuest1``/``todaysQuest2`` and
fills them from the login response's ``dailyQuest``/``dailyQuest1``/
``dailyQuest2``; ``IsDailyQuestPlayable1``/``2`` gate entry on those strings.
Sending the category flag without them leaves the menu drawn and every entry
greyed out, which is the shape of the defect this rotation exists to fix.
"""

from __future__ import annotations

from datetime import date

from liminal_gate.hunting_catalog import HuntingStage

#: Every Daily Quest also has Luck Treasure Chests, and the community record
#: gives them all the same Luck-80 tier except Tropical Haze, which gives
#: tickets instead. Version 4.4.0 changed these contents, so this is the final
#: schedule rather than the original one.
_LUCK_CHEST_ITEMS = (93, 94, 132, 137, 95, 96, 97, 98, 99)

#: The sixteen species-type items Puppet Pandemonium drops.
_SPECIES_ITEMS = (1, 2, 3, 4, 5, 6, 7, 8, 82, 83, 89, 90, 91, 92, 105, 106)

#: Dark, Evanescent, Shooting and Binary Star.
_STAR_ITEMS = (118, 119, 120, 121)

#: Lore, Spirit, Warped and Wish Particle.
_PARTICLE_ITEMS = (22, 23, 24, 25)

#: Terra Swordsteel, Spearbronze, Bowstring and Staffwood: the weapon-type
#: items a Yamamoto match awards.
_WEAPON_ITEMS = (9, 10, 11, 12)

_METAL_TICKET, _FELLOWSHIP_TICKET, _COMPANION_TICKET = 50, 81, 112
_ENERGY_ITEM = 80

#: EXP Boost, Coin Boost, Time Extension and Disarmer: the recovered power-up
#: IDs this project already accepts on Crystal Road.
_POWER_UP_ITEMS = (53, 54, 55, 56)

#: A clear may report at most this many of any chest item. The chests are
#: bounded per run rather than per enemy, so a small ceiling is the honest one.
_CHEST_CEILING = 2


def _chest(extra: dict[int, int] | None = None) -> dict[int, int]:
    maxima = {item_id: _CHEST_CEILING for item_id in _LUCK_CHEST_ITEMS}
    if extra:
        for item_id, ceiling in extra.items():
            maxima[item_id] = max(maxima.get(item_id, 0), ceiling)
    return maxima


# chapter, section, family, max_coins, item_maxima, max_items_total
_DAILY_QUEST_ROWS: tuple[tuple[int, int, str, int, dict[int, int], int], ...] = (
    (6000, 1, "metal_runner_rampage", 0, _chest(), 20),
    (6001, 1, "puppet_pandemonium", 0, _chest({item: 30 for item in _SPECIES_ITEMS}), 60),
    # The community record gives Crystal Roundelay one guaranteed power-up per
    # run (EXP Boost, Coin Boost, Time Extension, or Disarmer): the same four
    # recovered power-up IDs Crystal Road accepts.
    (6002, 1, "crystal_roundelay", 0, _chest({item: 2 for item in _POWER_UP_ITEMS}), 20),
    # 300 Coins per enemy defeated is the only per-enemy Coin rule recorded for
    # any Daily Quest. The enemy count is not recovered, so the ceiling bounds a
    # generous run rather than asserting a population.
    (6003, 1, "hedgehog_hullabaloo", 15_000, _chest(), 20),
    (6004, 1, "particle_hoarder_horde", 0, _chest({item: 4 for item in _PARTICLE_ITEMS}), 24),
    # Rarity Rumble's documented drops are one guaranteed Ore plus a ten-percent
    # Fellowship Ticket from Gormandette.  The Ore identities are not resolved
    # against recovered master data, so only the ticket is bounded here.
    (6005, 1, "rarity_rumble", 0, _chest({_FELLOWSHIP_TICKET: 2}), 20),
    (6006, 1, "sweet_temptation", 0, _chest({_ENERGY_ITEM: 1}), 20),
    (6007, 1, "tropical_haze", 0, _chest({
        _METAL_TICKET: 10, _FELLOWSHIP_TICKET: 10, _COMPANION_TICKET: 10,
    }), 40),
    (6008, 1, "tearjerker_time", 0, _chest(), 20),
    (6009, 1, "hidden_stars", 0, _chest({item: 40 for item in _STAR_ITEMS}), 80),
    (6010, 1, "lucky_orbling", 0, _chest(), 20),
    (6011, 1, "yamamotos_puzzle_quest", 0, _chest({item: 12 for item in _WEAPON_ITEMS}), 36),
    # The second Puzzle Quest adds particle and ore tiers above the weapon tier.
    # The ore identities are not resolved, so only the recovered weapon and
    # particle items are bounded here.
    (6011, 2, "yamamotos_puzzle_quest_ii", 0, _chest(
        {item: 12 for item in _WEAPON_ITEMS} | {item: 6 for item in _PARTICLE_ITEMS}
    ), 48),
    (6012, 1, "the_hunt_for_joker", 0, _chest(), 20),
)

#: The client's own gate for the whole Huntland category.
DAILY_QUEST_EVENT_FLAG = "enableDailyQuest"

#: **Recovered.** ``DailyQuestData.questOrder`` verbatim, in asset order. This is
#: the same asset :mod:`liminal_gate.daily_quest_importer` reads out of the
#: operator's own APK, and running that importer against a matching APK is the
#: check that this bundled copy is still the right one: it must reproduce these
#: forty-one entries exactly. It is bundled for the same reason the stage set
#: above is -- the rotation is a client asset, identical for every operator on
#: the same build -- and refusing to bundle it would only mean the category
#: cannot work without an optional UnityPy install.
DAILY_QUEST_ROTATION: tuple[str, ...] = (
    "6010-1", "6011-1", "6009-1", "6006-1", "6001-1", "6007-1",
    "6008-1", "6002-1", "6012-1", "6004-1", "6000-1", "6005-1",
    "6003-1", "6011-2", "6006-1", "6010-1", "6011-1", "6002-1",
    "6009-1", "6005-1", "6012-1", "6008-1", "6010-1", "6004-1",
    "6003-1", "6000-1", "6011-2", "6007-1", "6006-1", "6005-1",
    "6009-1", "6000-1", "6001-1", "6010-1", "6006-1", "6003-1",
    "6004-1", "6007-1", "6011-2", "6002-1", "6012-1",
)

#: **Local policy from a secondary source**, on the same footing as the reward
#: ceilings. The rotation asset says which stages exist and in what order; it
#: does not say which day the ring started on. Anchoring index nine to
#: 2018-10-10 UTC reproduces the community record's published final schedule
#: over its whole run, which is the strongest check available now that the
#: service that owned the answer is gone. Two quests are served a day, so the
#: ring advances by two.
DAILY_QUEST_EPOCH_DAY = (date(2018, 10, 10) - date(1970, 1, 1)).days
DAILY_QUEST_EPOCH_INDEX = 9
DAILY_QUEST_SLOTS_PER_DAY = 2


def daily_quest_rotation(utc_day: int) -> tuple[str, str]:
    """Return the two ``chapter-section`` quests a UTC day offers.

    ``utc_day`` is a whole day count since the Unix epoch, the same unit the
    server stamps a played quest with, so no timezone participates.
    """
    offset = (
        DAILY_QUEST_EPOCH_INDEX
        + DAILY_QUEST_SLOTS_PER_DAY * (utc_day - DAILY_QUEST_EPOCH_DAY)
    ) % len(DAILY_QUEST_ROTATION)
    return (
        DAILY_QUEST_ROTATION[offset],
        DAILY_QUEST_ROTATION[(offset + 1) % len(DAILY_QUEST_ROTATION)],
    )

#: Joker Λ, the wild-card Recode DNA material The Hunt For Joker awards.
#: Resolved from the operator's own master data rather than bundled by name.
JOKER_LAMBDA_CHARACTER_ID = 1018

#: A further Joker Λ recruit adds 10% Skill Boost and 1 Luck, both in the
#: client's tenths wire unit.
#:
#: The Luck figure was 100, i.e. 10.0 Luck, which is ten times what a duplicate
#: pays. Both sources agree on the rule and neither is stage-specific: the
#: community record's Luck page says an already-owned Lambda dropping from a
#: quest gains Luck "by 1 for each duplicate character recruited", and
#: Mistwalker's own Ver 4.2.0 announcement lists receiving an already-owned
#: character from a quest drop as a Luck source without exception. Ten Luck a
#: clear would carry a character from nothing to the 100.0 ceiling in ten
#: repeats of one Daily Quest, which is the length of the whole Luck grind.
#: The Skill Boost figure is unchanged: no source contradicts it.
_JOKER_DUPLICATE_SKILL_BOOST = 100
_JOKER_DUPLICATE_LUCK = 10


def build_bundled_daily_quest_stages() -> tuple[HuntingStage, ...]:
    """Return the fourteen Daily Quests as bounded, unadvertised stages.

    They use the ``hidden`` selector deliberately. The client draws the Daily
    Quest menu from the two quests login names, not from a selector list, so
    advertising them in a Hunting or Special list would duplicate them into the
    wrong menu. ``hidden`` is exactly the case this project already has for a
    stage the server honours when asked but never lists.

    All fourteen are built, because the rotation reaches all fourteen; which two
    a given day offers is :func:`daily_quest_rotation`'s answer.

    Entry is free. Every recorded Daily Quest costs no stamina, which the
    operator's own BattleData agrees with -- all fourteen rows carry zero.
    """
    return tuple(
        HuntingStage(
            family=family, chapter=chapter, section=section,
            stamina=0, coins=0, entry_item_id=0, entry_item_count=0,
            # Daily Quests carry no recovered story gate. They are available
            # whenever the client's own category flag is on, so this is the
            # lowest possible gate rather than an invented threshold.
            unlock_chapter=1, unlock_section=1,
            max_coins=max_coins, max_exp=0,
            max_items_total=max_items_total, item_maxima=dict(item_maxima),
            selector="hidden",
            once_per_utc_day=True,
            character_grants=(JOKER_LAMBDA_CHARACTER_ID,) if family == "the_hunt_for_joker" else (),
            duplicate_grant_skill_boost=_JOKER_DUPLICATE_SKILL_BOOST if family == "the_hunt_for_joker" else 0,
            duplicate_grant_luck=_JOKER_DUPLICATE_LUCK if family == "the_hunt_for_joker" else 0,
        )
        for chapter, section, family, max_coins, item_maxima, max_items_total in _DAILY_QUEST_ROWS
    )


def daily_quest_event_flags() -> dict[str, dict[str, object]]:
    """Return the category flag plus the per-stage flags the client checks.

    ``CheckQuestFlag`` builds ``sp_ch_<chapter>-<section>`` for a stage, and
    ``DailyQuestManager.get_enableDailyQuest`` reads the category flag. Both are
    sent, because a stage whose flag is missing is silently unreachable and
    nothing anywhere says why.
    """
    flags: dict[str, dict[str, object]] = {
        DAILY_QUEST_EVENT_FLAG: {"name": DAILY_QUEST_EVENT_FLAG, "value": True},
    }
    for chapter, section, *_ in _DAILY_QUEST_ROWS:
        name = f"sp_ch_{chapter}-{section}"
        flags[name] = {"name": name, "value": True}
    return flags
