"""Orbling Cavern and Cryptid Forest: the two standing World 1 areas.

`UIMap` draws a permanent map point for each, and both were unreachable for the
same reason: this server sent no flag under the prefix each point tests, so
neither point was ever constructed and nothing anywhere said why.

**Confirmed, from the client's own `ChapterInterface::.cctor`** (ARM64
`0xD0741C`): `OrblingCavernChapter` is 7000 and `OrblingCavernEndChapter` 7009;
`EidolonForestChapter` is 7010 and `EidolonForestEndChapter` 7019. Chapter 7010
is Cryptid Forest -- `EidolonForest` is the internal name, and mistaking one for
the other is what once paid it a Lucky Orbling's Luck. Only 7000 and 7010 carry
sections, so the two areas are four stages between them.

**How the client reaches them, Confirmed.** `UIMap::InitPoints0` (`0xE6BB0C`)
builds each point behind `EventManager.IsEnabledAny`, which is a *prefix* scan
over the `eventFlags` object this server sends at login and status: any key
starting with the prefix and holding true passes.

    IsEnabledAny("sp_ch_700") -> AddSpecial(type=OrblingCavern, openChapter=6)
    IsEnabledAny("sp_ch_701") -> AddSpecial(type=EidolonForest, openChapter=5)

Tapping a point runs `UIMapPoint::OnClickBtn` (`0xE75014`), which opens
`UISpecialSelect` mode 1 or 2. Those two modes are the reason nothing here is
advertised: `SetMode` (`0xF84588`) reads a *hardcoded* list for each of them --
`UISpecialSelect::.cctor` (`0xF8768C`) sets `orblingCavernQuestList` to
`["7000-1", "7000-2"]` and `eidolonForestQuestList` to `["7010-1", "7010-2"]` --
and never consults a served list the way mode 0 consults `specialQuestList`.
The server cannot add, remove, or reorder these cards. It can only open the
door, which is why all four use the `hidden` selector the Daily Quests and the
secondary worlds already use.

The per-section flags below therefore do two jobs at once. Each satisfies its
own card's `UISpecialSelect.CheckQuestFlag`, and each also starts with the
prefix its map point scans for, so no separate chapter-level flag is needed.
A chapter-level flag would be safe here -- the client's embedded 50-entry
fallback list names no 7000 or 7010 row, so neither can leak into the Arena
selector the way a broad `sp_ch_3000` would -- but exact section flags are this
project's standing preference and are what the Daily Quests already send.

**Confirmed, from the operator's own embedded `BattleData`.** Every identity and
cost below. Both areas cost one stamina and zero Coins per section. Orbling
Cavern's two sections are titled `バルちゃん・Ο` and `グレース・Ο` and each
declares exactly one Companion in `dropBuddies`; Cryptid Forest's two are
`キリン・ビリ` and `キリン・ファンネ`, each three battles, and both declare an
empty manifest and carry `allowLucky` 1.

Orbling Cavern's sections declare `battleCnt` 0, which this project has read
elsewhere as a stage with no battle program. That reading does not apply.
Twenty-six chapters declare all-zero `battleCnt`, and they include the two
Yamamoto Puzzle Quests and Lucky Orbling, all three of which are confirmed
playable on hardware. What actually distinguishes a placeholder is whether the
client carries a `ChapterNNNN` class: 6006 has none, and both `Chapter7000` and
`Chapter7010` do, each with its own sections, battles and enemy constructors.

**Local policy, labeled as such.** Three things.

The story thresholds are the halves of the client's own gate this server owns.
The client compares cleared progress against `openChapter`, which carries a
chapter and no section, so the section half of each threshold below is this
server's choice and the chapter half is recovered.

Experience is paid under a ceiling, on the reasoning the two Roads and the
secondary worlds already use here: EXP is the battle's own product rather than a
reward the retired service chose, and refusing it means a player wins a battle
and is told no. Both areas take the Metal Zone tier above their own assumed
level, which is the method `_ROAD_EXP_CEILING` states: Orbling Cavern assumes
level 10 and Cryptid Forest 12 and 15, all three between Metal Zone 1 (level 1)
and Metal Zone 2 (level 20), so all three take zone 2's.

The Cryptid Forest item ceiling bounds a claim rather than reproducing a rate.
The rate itself is recovered and is not used: `Chapter7010`'s constructor sets
`JobItemDropRatio` to 75, and the Kirin constructors hand that ratio to the
engine with their own item lists. This server does not roll the drop -- the
client does, in its own battle -- so the ceiling exists only to refuse an
absurd report, exactly as Machine Road's does.

No Luck chest is authored for either. The Hunting settlement path authors none
for any stage, and the community record's own no-chest list names Orbling
Cavern outright. Cryptid Forest's Lucky Runner arrives through `luckUpTable`
instead, which `ALLOW_LUCKY_CHAPTERS` already routes for chapter 7010; that
source is not governed by `LUCK_GAIN_MIN_STAMINA`, so a one-stamina entry still
pays it.
"""

from __future__ import annotations

from liminal_gate.event_flag_data import event_flags_for
from liminal_gate.hunting_catalog import HuntingStage

#: **Confirmed.** `ChapterInterface::.cctor`, ARM64 `0xD0741C`.
ORBLING_CAVERN_CHAPTER = 7000
CRYPTID_FOREST_CHAPTER = 7010

#: **Local policy**, on the recovered half described above. `UIMap::InitPoints0`
#: passes `openChapter` 6 for Orbling Cavern and 5 for Cryptid Forest.
ORBLING_CAVERN_UNLOCK = (6, 1)
CRYPTID_FOREST_UNLOCK = (5, 1)

#: **Local policy.** The Metal Zone tier above each area's own assumed level.
#: Both land on zone 2; see the module docstring for the method.
_EXP_CEILING = 920_000

#: **Confirmed.** Section to the single Companion its own `dropBuddies` manifest
#: names, decoded through the `code >> 8` / `code & 0xFF` packing every other
#: manifest in this project uses. 7000-1 holds 75265 and 7000-2 holds 75777,
#: which decode to Companion 294 at count 1 and Companion 296 at count 1. Both
#: are present in the recovered Companion master data, where they carry a value
#: of 1 against the 7,500 to 50,000 their neighbours carry.
_CAVERN_COMPANIONS = {1: 294, 2: 296}

#: A dropped copy arrives at level 1, as every other bundled Companion drop does.
_COMPANION_DROP_LEVEL = 1

#: **Confirmed.** Section to the job materials its Kirin hands the engine.
#: `Chapter7010.Init_KR_KIRIN` (`0x1433628`) builds `[150, 151]` and
#: `Init_KR_KIRIN2` (`0x1434160`) builds `[152, 153]`, and each passes its list
#: with the shared `JobItemDropRatio` of 75.
#:
#: The operator's own `ChrDatabase` agrees from the other direction, and that
#: agreement is what identifies the area: `JOB_UNLOCK_ROWS` prices character
#: 188's first job at items 150 and 151 and its second at 152 and 153, and
#: character 188 is Dracorin -- the same Dracorin whose Λ form carries the
#: *Cryptid Ruler* skill the community record names here. Section 1 farms the
#: first job's materials and section 2 the second's.
_FOREST_JOB_ITEMS = {1: (150, 151), 2: (152, 153)}

#: **Local policy.** Three battles a section, one Kirin apiece at a 75% roll,
#: so a run cannot honestly produce many. Deliberately far above that: an
#: over-generous bound is inert when the client rolls nothing and costs a
#: player nothing when it rolls, while a tight one refuses a won battle. This
#: is the reasoning `_MACHINE_ROAD_STAR_CEILING` already states.
_FOREST_ITEM_CEILING = 20


def build_bundled_orbling_cavern_stages() -> tuple[HuntingStage, ...]:
    """Return Orbling Cavern's two sections as bounded, unadvertised stages.

    Each accepts at most the one Companion its own manifest names. The operator
    reports the drop is guaranteed while that Companion is unowned and does not
    occur once it is held, so a clear reporting none is ordinary rather than a
    fault, and nothing here limits how often a section may be entered.
    """
    return tuple(
        HuntingStage(
            family="orbling_cavern", chapter=ORBLING_CAVERN_CHAPTER, section=section,
            stamina=1, coins=0, entry_item_id=0, entry_item_count=0,
            unlock_chapter=ORBLING_CAVERN_UNLOCK[0], unlock_section=ORBLING_CAVERN_UNLOCK[1],
            max_coins=0, max_exp=_EXP_CEILING,
            # No section declares a Coin reward and no item manifest survives,
            # so there is nothing to bound either against.
            max_items_total=0, item_maxima={},
            companion_maxima={companion: 1},
            # The manifest names one candidate, so the per-id bound and the
            # total say the same thing. Both are stated rather than left to be
            # inferred from a one-entry manifest.
            max_companions_total=1,
            companion_drop_levels={companion: _COMPANION_DROP_LEVEL},
            selector="hidden",
        )
        for section, companion in sorted(_CAVERN_COMPANIONS.items())
    )


def build_bundled_cryptid_forest_stages() -> tuple[HuntingStage, ...]:
    """Return Cryptid Forest's two sections as bounded, unadvertised stages.

    Both declare an empty `dropBuddies`, so neither settles a Companion at all,
    on the game's own authority. The Lucky Runner these two carry is not a
    settlement channel: it reaches the client through `luckUpTable` at entry,
    which `roll_luck_up_table` already authors for chapter 7010.
    """
    return tuple(
        HuntingStage(
            family="cryptid_forest", chapter=CRYPTID_FOREST_CHAPTER, section=section,
            stamina=1, coins=0, entry_item_id=0, entry_item_count=0,
            unlock_chapter=CRYPTID_FOREST_UNLOCK[0], unlock_section=CRYPTID_FOREST_UNLOCK[1],
            max_coins=0, max_exp=_EXP_CEILING,
            max_items_total=_FOREST_ITEM_CEILING * len(items),
            item_maxima={item_id: _FOREST_ITEM_CEILING for item_id in items},
            companion_maxima={},
            selector="hidden",
        )
        for section, items in sorted(_FOREST_JOB_ITEMS.items())
    )


def cavern_forest_event_flags(
    progress_chapter: int, progress_section: int,
) -> dict[str, dict[str, object]]:
    """Return whichever of the four stage flags this account has reached.

    Sent per section rather than per chapter, so each flag answers its own
    card's `CheckQuestFlag` directly instead of relying on the chapter-level
    substring fallback. Each also carries the prefix its area's map point
    scans, so the same four flags open both doors and all four cards.

    Both areas are permanent once open, which is archive policy: their
    historical availability windows were live-service state and were never
    captured.
    """
    flags: dict[str, dict[str, object]] = {}
    reached = (progress_chapter, progress_section)
    families = (
        (ORBLING_CAVERN_UNLOCK, ORBLING_CAVERN_CHAPTER, sorted(_CAVERN_COMPANIONS)),
        (CRYPTID_FOREST_UNLOCK, CRYPTID_FOREST_CHAPTER, sorted(_FOREST_JOB_ITEMS)),
    )
    for unlock, chapter, sections in families:
        if reached < unlock:
            continue
        for section in sections:
            name = event_flags_for(chapter, section)[1]
            flags[name] = {"name": name, "value": True}
    return flags
