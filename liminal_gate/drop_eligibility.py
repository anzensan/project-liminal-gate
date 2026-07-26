"""The login ``chrBuddyData`` drop-eligibility allowlist.

Without this field the client discards every drop it rolls.

Login's response reader walks ``chrBuddyData.chrList`` and sets
``ChrInfo.canDrop = true`` for each character ID, and ``chrBuddyData.buddyList``
setting ``BuddyData.canDrop = true`` for each Companion ID.  In battle,
``BattleManager.<_CheckForDrops>c__Iterator0.MoveNext`` refuses a rolled drop
whose ``canDrop`` flag is false -- it logs "chr {0} is not available in server"
and creates no drop record.  A server that omits the field therefore rolls
drops correctly and then has all of them thrown away by the client, which is
why a login without it reports empty ``monsters``/``buddies`` on every clear.

This flag does not decide *what* drops.  Per-stage eligibility still governs
that: the enemy record's ``DropBuddyID``/``DropBuddyRatio`` and the stage's own
``BattleData.Section.dropBuddies`` allowlist and per-battle cap.  ``canDrop``
only tells the client that the content is known to the server at all.

Local policy, stated plainly: the final 5.5.7 client shipped with all recovered
master content released, so every recovered character and Companion master ID
is marked eligible here.  That is a preservation choice, not a recovered
per-account entitlement list.

``rebirthList`` is deliberately omitted.  It sets each
``RebirthInfo.evolveEnableVer`` and gates Rebirth availability rather than
drops, and its ``availableVersion`` values are not carried in this repository's
bundled Rebirth data -- :mod:`liminal_gate.rebirth_recipe_data` records only
that every recipe is at or below the final client's own version.  Emitting
invented version numbers would assert a gate this project has not recovered.
"""

from __future__ import annotations

from typing import Any

from liminal_gate.companion_master_data import COMPANION_MASTER_ROWS
from liminal_gate.job_unlock_data import JOB_UNLOCK_ROWS
from liminal_gate.statusup_character_data import STATUSUP_CHARACTER_ROWS


def character_master_ids() -> list[int]:
    """Every recovered character master ID, ascending.

    Unioned from the two bundled per-character tables so the list does not
    depend on which optional catalog an operator supplied.
    """
    return sorted({row[0] for row in STATUSUP_CHARACTER_ROWS} | {row[0] for row in JOB_UNLOCK_ROWS})


def companion_master_ids() -> list[int]:
    """Every recovered Companion master ID, ascending."""
    return sorted({row[0] for row in COMPANION_MASTER_ROWS})


def login_chr_buddy_data() -> dict[str, Any]:
    """Return the ``chrBuddyData`` object for a login response."""
    return {"chrList": character_master_ids(), "buddyList": companion_master_ids()}
