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

**Recovered.** Which Companion each Puzzle Quest may drop. 6011-1 and 6011-2
are the only two Daily Quests whose ``BattleData`` section declares a
``dropBuddies`` manifest at all; see ``_YAMAMOTO_COMPANIONS``.

**Local policy from a secondary source.** The settlement bounds. The retired
service owned Daily Quest rewards and the client only rendered them, so no
single APK table gives them and none can be recovered whole. The ceilings below
bound a client-reported clear the way the Hunting families do; they are
deliberately generous, because their job is to refuse an absurd claim rather
than to reproduce a drop rate. Item identities come from the community record
and were resolved to IDs through the operator's own master data, which is what
makes them checkable: ``Energy`` resolves to 80, the same number the client's
own ``DailyQuestManager.EnergyItemId`` carries, and the two tickets resolve to
the 50 and 81 this project already uses elsewhere.

A bound here is only ever too generous safely, never too tight. A refused clear
is not a refused reward: it leaves the account's battle active, which blocks
every other stage until that same quest is replayed and accepted, so a ceiling
that a real clear can cross reads to the player as a corrupted installation.
Every ceiling widened in this file was widened for that reason.

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

#: The weapon items plus the four attribute items above them, which is the
#: whole of Yamamoto II's first reward tier.
_YAMAMOTO_II_FIRST_TIER = tuple(range(9, 17))

#: The four Tears a Tear Hoarder guarantees.
_TEAR_ITEMS = (18, 19, 20, 21)

#: The attribute rings Tearjerker Time's minor enemies drop.
_RING_ITEMS = (13, 14, 15, 16, 17, 46, 122, 123, 164, 165)

#: Orichalcum, Dark Matter, Animaton and Oxsecium.
_ORE_ITEMS = (26, 27, 28, 29)

_METAL_TICKET, _FELLOWSHIP_TICKET, _COMPANION_TICKET = 50, 81, 112
_ENERGY_ITEM = 80

#: EXP Boost, Coin Boost, Time Extension and Disarmer: the recovered power-up
#: IDs this project already accepts on Crystal Road.
_POWER_UP_ITEMS = (53, 54, 55, 56)

#: A clear may report at most this many of any chest item. The chests are
#: bounded per run rather than per enemy, so a small ceiling is the honest one.
_CHEST_CEILING = 2

#: **Local policy.** The most EXP one Daily Quest clear may report.
#:
#: Zero was the wrong bound and refused honest clears: a Daily Quest is an
#: ordinary battle and pays ordinary battle EXP, and Metal Runner Rampage pays
#: nothing else -- its three waves of recovered Metal Runner and Golden Runner
#: spawns reach 306,000 on their own. No per-stage EXP table is recovered for
#: the other thirteen, so one generous ceiling covers them all. This is the
#: figure Metal Zone 7 already permits across five battles, and no Daily Quest
#: runs more than three at an assumed level of 80 or below, so nothing honest
#: can reach it. Erring high is deliberate: a ceiling that is too tight refuses
#: a real clear, and a refused clear leaves the account's battle active.
_DAILY_QUEST_EXP_CEILING = 7_720_000


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
    # Fellowship Ticket from Gormandette.  Both are bounded: the four Ore
    # identities are the ones the recovered enemy records name.
    (6005, 1, "rarity_rumble", 0, _chest(
        {_FELLOWSHIP_TICKET: 2} | {item: _CHEST_CEILING for item in _ORE_ITEMS}
    ), 20),
    (6006, 1, "sweet_temptation", 0, _chest({_ENERGY_ITEM: 1}), 20),
    (6007, 1, "tropical_haze", 0, _chest({
        _METAL_TICKET: 10, _FELLOWSHIP_TICKET: 10, _COMPANION_TICKET: 10,
    }), 40),
    # Two Tear Hoarders each guarantee one Tear, and the six minor enemies each
    # roll one attribute ring, so both families are bounded rather than only
    # the chest.
    (6008, 1, "tearjerker_time", 0, _chest(
        {item: _CHEST_CEILING for item in _TEAR_ITEMS + _RING_ITEMS}
    ), 20),
    (6009, 1, "hidden_stars", 0, _chest({item: 40 for item in _STAR_ITEMS}), 80),
    (6010, 1, "lucky_orbling", 0, _chest(), 20),
    # Both Puzzle Quests pay three reward tiers, not one. A qualifying linked
    # group promotes an enemy's item to a certain drop, so the honest ceiling
    # is the wave capacity behind each tier rather than a flat per-item guess:
    # a tier's whole capacity is allowed on any one of its items, and the run's
    # total bounds the clear. Bounding only the weapon tier is what refused the
    # Tears and Particles a real clear reports.
    (6011, 1, "yamamotos_puzzle_quest", 0, _chest(
        {item: 61 for item in _WEAPON_ITEMS}
        | {item: 45 for item in _TEAR_ITEMS}
        | {item: 29 for item in _PARTICLE_ITEMS}
    ), 93),
    # The second Puzzle Quest widens the first tier to the attribute items and
    # replaces the third with the four Ores.
    (6011, 2, "yamamotos_puzzle_quest_ii", 0, _chest(
        {item: 53 for item in _YAMAMOTO_II_FIRST_TIER}
        | {item: 28 for item in _PARTICLE_ITEMS}
        | {item: 25 for item in _ORE_ITEMS}
    ), 81),
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

#: **Recovered.** The Companion each Yamamoto Puzzle Quest may drop.
#:
#: These two are the only Daily Quests whose own ``BattleData`` section carries
#: a non-empty ``dropBuddies``: 6011-1 holds the single packed code 68353 and
#: 6011-2 holds 35841, in the same ``code >> 8`` Companion / ``code & 0xFF``
#: count packing every other manifest in this project uses. That decodes to
#: Companion 267 at count 1 and Companion 140 at count 1, and both IDs are
#: present in the recovered Companion master data. The community record agrees
#: independently, naming them Glassy Minion Λ and Golden Minion Λ and putting
#: each behind a 60% Ancient Key roll. The other twelve Daily Quests declare an
#: empty manifest and so keep refusing a reported Companion outright.
#:
#: Declaring nothing here is what refused an honest Puzzle Quest clear: the
#: client rolls the drop its own data allows, reports it, and the settlement
#: called it an unbounded claim. The odds stay the client's to roll; this
#: server only bounds the outcome.
_YAMAMOTO_COMPANIONS = {(6011, 1): 267, (6011, 2): 140}

#: A dropped copy arrives at level 1, like every other bundled Companion drop.
_COMPANION_DROP_LEVEL = 1

#: A further Joker Λ recruit adds 10% Skill Boost and 10 Luck, both in the
#: client's tenths wire unit.
#:
#: The Luck figure was reduced to 10 -- 1.0 Luck -- on the reading that the
#: community record's Luck page ("by 1 for each duplicate character recruited")
#: describes this drop, and that 10.0 a clear would cross the whole Luck grind
#: in ten repeats of one Daily Quest. A tester's report is what settled it back:
#: the client announces the recruit as +10 Luck and the player then saw +1.0.
#:
#: The client's announcement is decisive here in a way it is not elsewhere,
#: because Luck is the one progression member the client cannot correct on its
#: own. `Character.ToHashTable` (ARM64 `0xD0A318`) serializes eight members --
#: `id`, `jobID`, `flags`, `jobLevels`, `jobSlots`, `skillBoost`, `buddy`,
#: `date` -- and `luck` is not among them, while `Character.LoadFromJson`
#: (`0xD07C5C`) reads it. The client therefore renders whatever figure it
#: announces and then takes the server's back on the next userdata read: a
#: server that pays a tenth of the announcement is not being conservative, it
#: is contradicting the game's own message with no way for the player to tell
#: which number is real. The record's "by 1" is left as the weaker reading of
#: an ambiguous unit -- the same page states Luck in whole displayed points.
#:
#: The Skill Boost figure is unchanged: no source contradicts it. Note that the
#: client raises Skill Boost itself and reports the raised value, which is why
#: `_apply_hunting_character_grants` runs before a clear merges the client's
#: roster rather than after it.
_JOKER_DUPLICATE_SKILL_BOOST = 100
_JOKER_DUPLICATE_LUCK = 100


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
            max_coins=max_coins, max_exp=_DAILY_QUEST_EXP_CEILING,
            max_items_total=max_items_total, item_maxima=dict(item_maxima),
            # Only the two Puzzle Quests declare a Companion, one apiece, and
            # their manifests name a single candidate each -- so the per-id
            # bound and the total say the same thing here, and both are stated
            # rather than left to be inferred from a one-entry manifest.
            companion_maxima=(
                {_YAMAMOTO_COMPANIONS[(chapter, section)]: 1}
                if (chapter, section) in _YAMAMOTO_COMPANIONS else {}
            ),
            max_companions_total=1 if (chapter, section) in _YAMAMOTO_COMPANIONS else None,
            companion_drop_levels=(
                {_YAMAMOTO_COMPANIONS[(chapter, section)]: _COMPANION_DROP_LEVEL}
                if (chapter, section) in _YAMAMOTO_COMPANIONS else {}
            ),
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
