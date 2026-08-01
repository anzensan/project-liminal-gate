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
    ("jade_dragon_hunt", "sp_ch_2004", 2004, 4, (673,)),
    ("lucia_archive", "sp_ch_2006", 2006, 13, ()),
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
# quests. The eight acquisition pairs below are recovered by mapping each
# chapter program's enemy enum through EnemyData's ordinal table; those enemy
# rows carry a 50 percent DropSummonRatio. The client performs the random roll
# and reports the result, so this policy records only which single Summon a
# stage is allowed to report. Chapter 3 is local availability policy.
EIDOLON_MANIFEST_ROWS: tuple[
    tuple[str, str, int, int, tuple[tuple[int, int], ...]], ...
] = (
    ("eidolon_artemis", "sp_ch_4100", 4100, 3, ((1, 4),)),
    ("eidolon_chaos", "sp_ch_4101", 4101, 3, ((1, 9),)),
    ("eidolon_valkyrie", "sp_ch_4102", 4102, 3, ((1, 3),)),
    ("eidolon_lamia", "sp_ch_4103", 4103, 3, ()),
    ("eidolon_risin", "sp_ch_4104", 4104, 3, ((1, 8),)),
    ("eidolon_phoenix", "sp_ch_4105", 4105, 3, ((1, 10),)),
    ("eidolon_king", "sp_ch_4106", 4106, 3, ()),
    ("eidolon_bahamut", "sp_ch_4107", 4107, 3, ((1, 6),)),
    ("eidolon_odin", "sp_ch_4108", 4108, 3, ((1, 5),)),
    ("eidolon_leviathan", "sp_ch_4109", 4109, 3, ((1, 7),)),
    ("eidolon_apollo", "sp_ch_4110", 4110, 3, ()),
    ("eidolon_selene", "sp_ch_4111", 4111, 3, ()),
)

# BattleData records a start cost for each event section but no fixed clear
# increment, so the default remains zero rather than inventing a retired-service
# reward. Variable battle Coins are reported separately by the surviving client
# and reconciled against its submitted wallet during settlement.
EVENT_CLEAR_COINS = 0
