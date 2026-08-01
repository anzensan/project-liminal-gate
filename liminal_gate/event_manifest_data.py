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
FOLDED_ARCHIVE_CHAPTERS = frozenset({
    2000, 2001, 2002, 2006, 2007, 2008, 2009,
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
# The final client defines Chapters 9010--9013 as Tower of Temptation and
# Chapters 9100--9102 as the separate Donation event. Matching BattleData has
# three stages in each Tower chapter. Chapter 3 is a permanent local archive
# gate, not a recovered Tower schedule or shared-progression model.
TOWER_MANIFEST_ROWS: tuple[tuple[str, str, int, int], ...] = (
    ("tower_of_temptation_1", "sp_ch_9010", 9010, 3),
    ("tower_of_temptation_2", "sp_ch_9011", 9011, 3),
    ("tower_of_temptation_3", "sp_ch_9012", 9012, 3),
    ("tower_of_temptation_4", "sp_ch_9013", 9013, 3),
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
