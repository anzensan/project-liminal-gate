"""Recovered event-archive manifest identities from the final client.

Each row names one archived event: the selector flag the client builds and reads
(``String.Concat("sp_ch_", chapter)``), the BattleData chapter carrying its
sections, and the character IDs the client's own catalog associates with it.

What is recovered: the flag, the chapter, and the character association. What is
**not**: the original release schedule and the retired service's reward tables.
The ``unlock_after_chapter`` values are therefore **local archive policy** --
a permanent, ordered release cadence chosen so the content is reachable in a
sensible order, not a claim about when each event actually ran.

Section economics are not here. They live in the user's own BattleData and are
read by :mod:`liminal_gate.battledata_importer`, which covers these chapters
exactly as it covers the main story.

Each row is ``(event_id, flag, chapter, unlock_after_chapter, (character_id, ...))``.
"""

from __future__ import annotations

# event_id, flag, chapter, unlock_after_chapter, character_ids
EVENT_MANIFEST_ROWS: tuple[tuple[str, str, int, int, tuple[int, ...]], ...] = (
    ("bahamut_descent", "sp_ch_2000", 2000, 2, (148,)),
    ("leviathan_descent", "sp_ch_2001", 2001, 10, (144,)),
    ("odin_descent", "sp_ch_2002", 2002, 20, (151,)),
    ("the_last_story_archive", "sp_ch_2003", 2003, 20, (596, 597)),
    ("jade_dragon_hunt", "sp_ch_2004", 2004, 4, (673,)),
    ("mobius_final_fantasy_archive", "sp_ch_2005", 2005, 13, (736,)),
    ("lucia_archive", "sp_ch_2006", 2006, 13, ()),
    ("yamamoto_archive", "sp_ch_2007", 2007, 10, ()),
    ("captive_golem_archive", "sp_ch_2008", 2008, 15, (805,)),
    ("dragon_king_one_archive", "sp_ch_2009", 2009, 30, ()),
    ("dragon_king_two_archive", "sp_ch_2010", 2010, 31, ()),
    ("dragon_king_three_archive", "sp_ch_2011", 2011, 32, ()),
    ("vengeful_vision_archive", "sp_ch_2014", 2014, 10, ()),
    ("final_fantasy_xv_archive", "sp_ch_2015", 2015, 20, (1080,)),
    ("sun_moon_kings_archive", "sp_ch_2016", 2016, 30, ()),
    ("mechtula_story_archive", "sp_ch_2017", 2017, 20, ()),
    ("encounter_with_sarah_archive", "sp_ch_2018", 2018, 20, (1288,)),
    ("spinetrich_kino_strikes_back", "sp_ch_8000", 8000, 5, ()),
    ("kraken_kino_strikes_back", "sp_ch_8001", 8001, 6, ()),
    ("slugosaur_kino_strikes_back", "sp_ch_8002", 8002, 7, ()),
    ("tiamat_kino_strikes_back", "sp_ch_8003", 8003, 8, ()),
    ("eight_bit_orbling_strikes_back", "sp_ch_8004", 8004, 9, ()),
    ("eight_bit_spinetrich_strikes_back", "sp_ch_8005", 8005, 10, ()),
    ("eight_bit_golem_strikes_back", "sp_ch_8006", 8006, 11, ()),
    ("eight_bit_hiso_alien_strikes_back", "sp_ch_8007", 8007, 12, ()),
    ("lich_kino_strikes_back", "sp_ch_8012", 8012, 13, ()),
    ("marilith_kino_strikes_back", "sp_ch_8013", 8013, 14, ()),
    ("mechanic_kino_strikes_back", "sp_ch_8014", 8014, 15, ()),
    ("odin_kino_strikes_back", "sp_ch_8015", 8015, 16, ()),
    ("bahamut_kino_strikes_back", "sp_ch_8016", 8016, 17, ()),
    ("leviathan_kino_strikes_back", "sp_ch_8017", 8017, 18, ()),
)

# Mode 0 of UISpecialSelect uses the nonempty server ``specialQuestList`` and
# only falls back to its embedded 50-entry array when that server list is null
# or empty. Some packaged chapters use one folded chapter card while later
# additions use one explicit card per section. The generator records that
# presentation identity separately from the start/clear stage identity.
#
# Which is which is read off the client's own quest-identity strings: a chapter
# it names bare (``"2017"``) is a folded card, one it names per section
# (``"2003-1"``) is not. Getting this wrong is not cosmetic -- every row here is
# a row of `specialQuestList`, and that list cannot exceed
# `SPECIAL_QUEST_LIST_MAX` without hanging the client, so unfolding a family the
# client folds spends rows this server then has to withhold from somewhere else.
#
# ``2015`` is the one chapter whose bare literal is deliberately **not**
# honoured. The client folds it because it shipped six sections; sections 4--6
# are the ``空き`` placeholders below, with zero battles and no banners, and a
# folded card offers a tier per section the flag answers for -- `CheckQuestFlag`
# retries an unset ``sp_ch_2015-4`` as ``sp_ch_2015``, which is set. Folding it
# would advertise three tiers this archive cannot draw and this server refuses
# to start. Per-section rows cost two extra rows and offer only what exists.
FOLDED_ARCHIVE_CHAPTERS = frozenset({
    2000, 2001, 2002, 2006, 2007, 2008, 2009, 2016, 2017,
})

# Chapter 2012 consists of three explicitly named attribute-test rows and
# Chapter 2013 has no SpecialBanner catalog entry; neither is a release-facing
# archive manifest. Chapter 2015 sections 4--6 are titled ``空き`` (empty), have
# zero battles, and have no section banners. Keep those placeholders out while
# retaining the three actual Final Fantasy XV battles.
ARCHIVE_SECTION_ALLOWLIST: dict[int, tuple[int, ...]] = {
    2015: (1, 2, 3),
}

# event_id, flag, chapter, unlock_after_chapter
#
# Tower of Temptation is served from Chapters 9000--9003, not the 9010--9013
# copy. BattleData carries the family twice and the two blocks are the same
# content: both hold the four `[誘いの塔]` bosses Arika, Guguba, Bahanna and
# Jeera across three sections at 15 stamina, at assumed levels 35, 65 and 80,
# chained by the same `parentQuest` links. Only 9000--9003 have retained
# `sp<chapter>-1`--`-3` banner bundles; 9010--9013 have none, so the earlier
# placement advertised four cards the retained archive cannot draw. Chapter 3
# is a permanent local archive gate, not a recovered Tower schedule or
# shared-progression model.
#
# Chapters 9100--9102 are the separate Donation range and carry Melting Pot;
# see MELTING_POT_MANIFEST_ROWS below.
TOWER_MANIFEST_ROWS: tuple[tuple[str, str, int, int], ...] = (
    ("tower_of_temptation_1", "sp_ch_9000", 9000, 3),
    ("tower_of_temptation_2", "sp_ch_9001", 9001, 3),
    ("tower_of_temptation_3", "sp_ch_9002", 9002, 3),
    ("tower_of_temptation_4", "sp_ch_9003", 9003, 3),
)

# event_id, chapter, unlock_after_chapter
#
# Six standing Special Quests the earlier manifest never named. Each is present
# in BattleData with a nonzero battle count and each has its own retained
# `sp<chapter>-<section>` banner bundles, so they are advertised from the
# archive the operator already owns rather than from anything derived.
#
# The event_ids follow the names the running client renders, read off its own
# Special Quest selector rather than translated from the BattleData titles:
# Gormandizer Hunt (`ナミダン` and `リュウシン`, shown as Tears and Particles),
# The Hunt For Joker, Blade Falcon, Bone Killer and Ethereal, and KINO World.
# Two of those correct the obvious reading of the Japanese -- `ブレイドイーグル`
# is Blade *Falcon* to the client, and `インビジブル` is Ethereal, not Invisible.
#
# Every one of them carries an empty `dropBuddies`, so no Companion manifest is
# being left unread, and like Counter Descent and Melting Pot they settle from
# the client's own reported drops -- the retired result service authored their
# rewards and no capture survives. Chapter 3 is the same permanent local
# availability gate Tower, the Eidolon quests and Melting Pot carry.
STANDING_SPECIAL_MANIFEST_ROWS: tuple[tuple[str, int, int], ...] = (
    ("gormandizer_hunt", 3001, 3),
    ("joker_hunt", 3100, 3),
    ("blade_falcon_hunt", 3200, 3),
    ("bone_killer_hunt", 3201, 3),
    ("ethereal_hunt", 3202, 3),
    ("kino_world", 3300, 3),
)

#: Chapter 3001 is the one member whose retained banners do not cover every
#: BattleData section: `sp3001-1` and `sp3001-2` exist, the third section's card
#: does not. Advertising 3001-3 would place a card the archive cannot draw --
#: the same blank-card failure the Coin Creeps derivation produced -- so the
#: section is withheld rather than backed by invented artwork. The other five
#: chapters are single-section and fully covered.
STANDING_SPECIAL_SECTION_ALLOWLIST: dict[int, tuple[int, ...]] = {
    3001: (1, 2),
}

#: `ChapterInterface.NumOfDonationQuestSections`, the section count the final
#: client returns from `GetSectionCount` for every chapter in that range. The
#: generator checks the BattleData import against it rather than trusting
#: either source alone.
MELTING_POT_SECTIONS = 15

# event_id, flag, chapter, unlock_after_chapter
#
# Melting Pot. The final client's `ChapterInterface..cctor` puts 9100--9199 in
# the Donation range, but the only chapters present in it are 9100--9102 and
# BattleData titles them `[るつぼの都] トカゲ / ケモノ / ヒト` -- Melting Pot:
# Lizardfolk, Beastfolk, and Human. Each carries fifteen five-battle sections
# whose stamina and assumed levels match the community record quest for quest.
#
# The client hard-codes `NumOfDonationQuestSections` = 15 and returns it from
# `UISpecialSelect.GetSectionCount` for any chapter in the range, so these are
# advertised as one folded card per chapter and the client expands the sections
# itself -- the same shape the folded archive chapters use. Chapter 3 is the
# same permanent local archive gate Tower and the Eidolon quests carry, not a
# recovered schedule.
#
# See `findings.md`, 2026-08-07: the two consumers once cited as making Donation
# unrecreatable (`DispDonationQuest`, `GetDonationQuestAmount`) are dead code in
# the final build.
MELTING_POT_MANIFEST_ROWS: tuple[tuple[str, str, int, int], ...] = (
    ("melting_pot_lizardfolk", "sp_ch_9100", 9100, 3),
    ("melting_pot_beastfolk", "sp_ch_9101", 9101, 3),
    ("melting_pot_human", "sp_ch_9102", 9102, 3),
)

# event_id, flag, chapter, unlock_after_chapter, (section, summon_id) drops
#
# Chapters 4100--4111 are the final client's converted single-player Eidolon
# quests. Only the twelve sections below have both a nonzero BattleData battle
# count and a matching final-client SpecialBanner. The other sixteen raw rows
# are disabled tier-I/tier-II progression placeholders, not independent cards.
#
# Older co-op enemy records contain Eidolon drop ratios, but the banner-backed
# solo programs use different enemy records. Until one of their result paths is
# captured, the generated catalog must not move those old rewards onto the solo
# sections. The runtime can still enforce a reviewed explicit catalog's
# ``summon_ids`` ceiling. Chapter 3 is local availability policy.
EIDOLON_MANIFEST_ROWS: tuple[
    tuple[str, str, int, int, tuple[tuple[int, int], ...]], ...
] = (
    ("eidolon_artemis", "sp_ch_4100", 4100, 3, ()),
    ("eidolon_chaos", "sp_ch_4101", 4101, 3, ()),
    ("eidolon_valkyrie", "sp_ch_4102", 4102, 3, ()),
    ("eidolon_lamia", "sp_ch_4103", 4103, 3, ()),
    ("eidolon_risin", "sp_ch_4104", 4104, 3, ()),
    ("eidolon_phoenix", "sp_ch_4105", 4105, 3, ()),
    ("eidolon_king", "sp_ch_4106", 4106, 3, ()),
    ("eidolon_bahamut", "sp_ch_4107", 4107, 3, ()),
    ("eidolon_odin", "sp_ch_4108", 4108, 3, ()),
    ("eidolon_leviathan", "sp_ch_4109", 4109, 3, ()),
    ("eidolon_apollo", "sp_ch_4110", 4110, 3, ()),
    ("eidolon_selene", "sp_ch_4111", 4111, 3, ()),
)

EIDOLON_PLAYABLE_SECTIONS: dict[int, int] = {
    4100: 3,
    4101: 3,
    4102: 3,
    4103: 1,
    4104: 3,
    4105: 3,
    4106: 1,
    4107: 3,
    4108: 3,
    4109: 3,
    4110: 1,
    4111: 1,
}

# BattleData records a start cost for each event section but no fixed clear
# increment, so the default remains zero rather than inventing a retired-service
# reward. Variable battle Coins are reported separately by the surviving client
# and reconciled against its submitted wallet during settlement.
EVENT_CLEAR_COINS = 0

#: Sections that admit only parties within a class band, as ``(chapter,
#: section) -> (class_min, class_max)``.
#:
#: Recovered, not chosen: these are `BattleData.Section.classMin`/`classMax`
#: read out of the reviewed client. Every section of every chapter it carries
#: was checked -- all forty-two story chapters, both Huntland ranges and every
#: event archive -- and Captive Golem's four are the only ones in the game that
#: declare a limit at all. The descending ladder is the quest: 6, then 5, then
#: 4, then 3, against the same class scale `ChrDatabase.rarity` uses, which the
#: local character catalog carries as `rarity`.
#:
#: The limit is enforced here because nothing else enforces it. The client owns
#: `StartQuestErrorCode.ClassLimit`, but the gate that returns it --
#: `AppServerUtil.IsEnableToStartQuestLocal` -- reads only stamina, Coins,
#: items and VS stamina; it makes no class-related call, so it cannot produce
#: that code. See the CHANGELOG entry for the report that found this.
SECTION_CLASS_LIMITS: dict[tuple[int, int], tuple[int, int]] = {
    (2008, 1): (1, 6),
    (2008, 2): (1, 5),
    (2008, 3): (1, 4),
    (2008, 4): (1, 3),
}
