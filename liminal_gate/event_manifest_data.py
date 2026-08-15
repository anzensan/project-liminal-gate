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
    # One card, so one gate: see `FOLDED_CARD_CHAPTERS`. The 30/31/32 ladder
    # these carried was written when each chapter was believed to be a card of
    # its own, and it staged a single card's three tiers across three chapters.
    ("dragon_king_one_archive", "sp_ch_2009", 2009, 30, ()),
    ("dragon_king_two_archive", "sp_ch_2010", 2010, 30, ()),
    ("dragon_king_three_archive", "sp_ch_2011", 2011, 30, ()),
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
# ``2015`` folds like the rest, and the section flags below are what make that
# safe. It was unfolded here for as long as the chapter flag was the only flag
# it could carry: the client folds it because it shipped six sections, sections
# 4--6 are the ``空き`` placeholders with zero battles and no banners, and
# `CheckQuestFlag` retries an unset ``sp_ch_2015-4`` as ``sp_ch_2015`` -- so a
# folded card carrying the chapter flag would advertise three tiers this
# archive cannot draw. Withholding the chapter flag closes that door, which is
# the shape Battle Champs already uses (see `SECTION_FLAGGED_FOLDED_CHAPTERS`),
# and the retained ``sp2015.bin`` folded banner says the fold is what the
# service drew: the card is `Final Fantasy XV`, and Gladiolus, Ignis and
# Prompto are the three tiers inside it. Three unfolded rows advertised
# Gladiolus alone under a banner drawn for the whole card.
FOLDED_ARCHIVE_CHAPTERS = frozenset({
    2000, 2001, 2002, 2006, 2007, 2008, 2009, 2015, 2016, 2017,
})

#: Folded cards whose stages carry their own ``sp_ch_<chapter>-<section>`` flag
#: and never the chapter flag.
#:
#: Folding and flagging are separate decisions, and this is the pair that lets a
#: card fold without offering the sections the archive withholds. `GetSectionCount`
#: expands a folded card to a tier per section the client believes the chapter
#: has, and for a tier the archive does not serve `IsQuestOpen` defers to the
#: flag alone -- which the chapter flag would answer true. Flagged per section,
#: those tiers have neither a section nor a flag and the client drops them.
#: See `EventCatalog.flags`, which documents the same mechanism for the
#: Counter Descent range.
SECTION_FLAGGED_FOLDED_CHAPTERS = frozenset({2015})

# Chapter 2012 consists of three explicitly named attribute-test rows and
# Chapter 2013 has no SpecialBanner catalog entry; neither is a release-facing
# archive manifest. Chapter 2015 sections 4--6 are titled ``空き`` (empty), have
# zero battles, and have no section banners. Keep those placeholders out while
# retaining the three actual Final Fantasy XV battles.
#
# Chapters 8000--8007 are the same withholding for the same reason, and unlike
# 2015 their fifth section is not an empty placeholder: it carries a real battle
# at 15 stamina, which is why reading the tier count off BattleData alone
# produced it. The retained archive cannot draw it. Every family in the
# 8000--8018 range ships exactly one Special banner per card it lists -- three
# for 8012--8017, two for 8008--8011, one for 8018 -- and these eight ship
# `sp<chapter>-1` through `-4` and no fifth. The client has no name for it
# either and falls back to the literal placeholder `text`, which is what a
# tester's selector showed under a black rectangle. What the fifth section was
# for is unrecovered, so it is withheld rather than dressed in the fourth card's
# artwork.
ARCHIVE_SECTION_ALLOWLIST: dict[int, tuple[int, ...]] = {
    2015: (1, 2, 3),
    **{chapter: (1, 2, 3, 4) for chapter in range(8000, 8008)},
}

#: The archived families the final client listed under Arena -> Descent Quests
#: rather than Arena -> Special Quests.
#:
#: `UISpecialSelect.Mode` declares ten selectors, and `DescentQuest` (3) is a
#: different menu from `DescentHunting` (8), which is Huntland -> Strikes Back.
#: Mode 3 reads `ServerConstants.descentQuestList`, a key this server did not
#: send at all until the shutdown menu record named the five families it held:
#: the three Third Descents, the Dragon King, and the Royal Rings. Everything
#: here was previously advertised as an ordinary Special Quest card, which is
#: not where the retired service put it.
#:
#: Nothing about the start or the clear changes with the move.
#: `ChapterInterface` declares no Descent range at all -- the ranges it does
#: declare (Counter Descent 8000--8999, Raid 9000--9009, Tower 9010--9099,
#: Donation 9100--9199) are what pick a start path, and no 2000-series chapter
#: is in any of them. The menu follows the list a row is advertised on and
#: nothing else, so these rows keep the folded/unfolded identity, the flags and
#: the settlement they already had.
#:
#: The move also returns seven rows to `specialQuestList`, which matters because
#: that list is capped: at full progress it served 32 rows against a client that
#: hangs above 30, so two were already being withheld before anything was added.
DESCENT_QUEST_CHAPTERS = frozenset({2000, 2001, 2002, 2009, 2010, 2011, 2016})

#: Member chapter -> the chapter whose folded card lists it.
#:
#: A folded card is normally one chapter's own sections, but two families span
#: several chapters, and the final client carries their membership as literals
#: rather than deriving it. The reviewed 5.5.7 metadata holds the two member
#: lists contiguously and in card order:
#:
#:     '2009-1', '2010-1', '2011-1',
#:     '8010-1', '8010-2', '8008-1', '8008-2', '8009-1', '8009-2', '8011-1', '8011-2'
#:
#: which is exactly the order the shutdown menu record lists under
#: `Dragon King Descended` (The Primordial / Inexorable / Resplendent Dragon
#: King) and under `Battle Champs` (Void Venom I--II, Tempest I--II, Dire Fang
#: I--II, Brushfyr I--II). `UISpecialSelect.GetSectionTitlesIfSpecialFoldedQuest`
#: and `GetBannerTitleForFoldedQuest` are the two accessors that read them.
#:
#: Serving a member chapter as a card of its own is what this table prevents,
#: and the retained banners are the second witness for both halves of it. Only
#: `sp2009.bin` exists for the Dragon King -- there is no `sp2010.bin` or
#: `sp2011.bin` -- so 2010-1 and 2011-1 were advertising cards the archive
#: cannot draw. All four of `sp8008.bin`--`sp8011.bin` do exist, and all four
#: read `BATTLE CHAMPS`: four cards, one family, each expanding to the same
#: eight tiers. That is the duplicate a tester reported seeing.
#:
#: The card chapter is the member that keeps its own bare banner as the card's,
#: and nothing about a member's start or clear changes: each tier carries its
#: own chapter and section exactly as before.
FOLDED_CARD_CHAPTERS: dict[int, int] = {
    2010: 2009,
    2011: 2009,
    8009: 8008,
    8010: 8008,
    8011: 8008,
}


def folded_card_chapter(chapter: int) -> int:
    """The chapter whose card lists this chapter's sections."""
    return FOLDED_CARD_CHAPTERS.get(chapter, chapter)

# event_id, chapter, unlock_after_chapter, section stamina
#
# Battle Champs and 8-Bit Rush: the two families inside the Counter Descent
# chapter range that the final client listed under Arena -> Special Quests
# instead of Huntland -> Strikes Back. Both were excluded from this archive
# until the shutdown menu record placed them, and the reason recorded for
# excluding them -- that their progression and reward contracts were distinct
# and unrecovered -- is now answered rather than inherited: the distinction is
# `dropBuddies`, and it is in the tester's own BattleData. See
# `SECTION_COMPANION_MANIFESTS` below.
#
# Both were named `Little Noah` and `Hime Rush` here for as long as they were
# excluded, which is what BattleData calls them: `リトルノア：ケツァルコアトル`
# and `ヒメラッシュ`. Those are the Japanese internal names. The banner artwork
# the English client actually drew reads TEMPEST, DIRE FANG, VOID VENOM and
# BRUSHFYR over `sp8008-1`--`sp8011-2`, and `8-Bit Rush` over `sp8018-1`, which
# is what the final menus called them, so the identities below follow the client
# rather than the table behind it.
#
# Section economics are recovered: 8008--8011 carry two sections of three
# battles at 5 and 15 stamina, 8018 one section of six battles at 15. Every one
# of them declares an empty `parentQuest`, so nothing here is chained. The
# unlock chapters continue the same permanent local cadence the fourteen
# Strikes Back families carry through Chapter 18; they are archive policy, not
# a recovered schedule.
#
# The four Battle Champs chapters share one gate because they share one card --
# see `FOLDED_CARD_CHAPTERS`. The 19/20/21/22 ladder they carried was written
# when each was believed to be a card of its own; against a single card it
# would open `Battle Champs` at Chapter 19 holding two of its eight tiers and
# fill the rest in over three more chapters, with the two the client lists
# first missing until last.
COLLAB_SPECIAL_MANIFEST_ROWS: tuple[tuple[str, int, int, tuple[int, ...]], ...] = (
    ("battle_champs_stormy_serpent", 8008, 19, (5, 15)),
    ("battle_champs_fearsome_fiends", 8009, 19, (5, 15)),
    ("battle_champs_creature_from_the_void", 8010, 19, (5, 15)),
    ("battle_champs_dragon_awakens", 8011, 19, (5, 15)),
    ("eight_bit_rush", 8018, 23, (15,)),
)

#: Sections whose Companion drops are declared by the client's own
#: `BattleData.Section.dropBuddies`, as ``(chapter, section) -> ((companion_id,
#: cap), ...)``.
#:
#: Recovered, not chosen. The packed `code` is the same shape the story
#: outcomes and the Chapter-1100 manifests use -- `code >> 8` is the Companion
#: and the low byte its per-clear cap -- and these five sections are the only
#: members of the 8000--8018 range that carry a manifest at all. Every Strikes
#: Back section declares an empty one, which is exactly the difference that kept
#: these families out of the archive.
#:
#: An empty tuple is a declaration, not an absence: tier I of each Battle Champs
#: family declares no Companion, so a clear that claims one is refused. That is
#: the same reading `_outcome_buddy_info` already applies to a story rule whose
#: recovered maxima are empty. A stage absent from this table is unconstrained,
#: because no manifest was read for it -- the two are not the same and are not
#: collapsed.
#:
#: The Companions themselves resolve through the operator's own names catalog:
#: 367 Samatha, 368 Yukken, 369 Maverick, 370 Spike, and 422--424 the three
#: 8-Bit Rush drops.
SECTION_COMPANION_MANIFESTS: dict[tuple[int, int], tuple[tuple[int, int], ...]] = {
    (8008, 1): (),
    (8008, 2): ((367, 1), (369, 1)),
    (8009, 1): (),
    (8009, 2): ((368, 1), (369, 1)),
    (8010, 1): (),
    (8010, 2): ((368, 1), (370, 1)),
    (8011, 1): (),
    (8011, 2): ((367, 1), (370, 1)),
    (8018, 1): ((422, 1), (423, 1), (424, 1)),
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

#: The four Tower chapters are folded cards, one per boss.
#:
#: The shutdown menu record lists four cards -- Alika, Gugba, Bajanna and Zeera
#: -- each holding its three tiers, and the retained banners are shaped the same
#: way: every one of 9000--9003 ships a bare `sp<chapter>.bin` alongside its
#: `-1`--`-3` tiers, and the bare one is the tower architecture without the
#: boss portrait the tier banners carry. Twelve flat rows drew a tier's artwork
#: where a card belonged and spent twelve rows doing it.
#:
#: Folding is unconditionally safe here, which is *not* true of every family:
#: these chapters sit in the client's Raid range, so a folded card expands to
#: `ChapterInterface.NumOfRaidQuestSections` tiers, and that constant is 3
#: (`orr w10, wzr, #0x3` into static offset 0x70 in the `..cctor` at
#: `0xD07620`; the 15 written to 0x74 beside it is the Donation count this
#: project already had). Every Tower chapter carries exactly three BattleData
#: sections and three retained tier banners, so the fold offers three tiers,
#: three sections back them and three banners draw them -- there is no phantom
#: tier for a chapter flag to open, which is why these keep the chapter flag
#: rather than needing `SECTION_FLAGGED_FOLDED_CHAPTERS`.
#:
#: The Raid range decides the start path, and folding does not change it: a
#: tier is still started as `<chapter>-<section>`, and `raid_quest_params`
#: still answers for each one.
FOLDED_TOWER_CHAPTERS = frozenset({9000, 9001, 9002, 9003})


def is_folded_chapter(chapter: int) -> bool:
    """Whether the client draws this chapter as one card over its sections."""
    return chapter in FOLDED_ARCHIVE_CHAPTERS or chapter in FOLDED_TOWER_CHAPTERS

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
