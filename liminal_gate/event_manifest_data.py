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
)

# BattleData records a start cost for each event section but no clear reward, so
# an event clear credits no Coins. This is the same reading applied to Dragon and
# Machine Road, which settle at zero for the same reason: it reports what the
# recovered data says rather than inventing a reward the service once sent.
EVENT_CLEAR_COINS = 0
