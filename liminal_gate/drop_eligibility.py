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

``rebirthList`` is **required**, not optional.  The client's login reader
null-guards ``chrBuddyData`` itself and then reads its three child lists
*unconditionally*: at ARM64 ``0xFB9C7C`` an absent list falls straight into the
null-reference thrower at ``0xBEF9E8``.  Sending the object without every list
therefore throws inside login, and the client hangs on "Connecting..." forever.
An earlier build omitted this list on the reasoning that it gates Rebirth rather
than drops, which was true and irrelevant.

Its ``availableVersion`` values are the recovered ``ChrDatabase.rebirthInfo``
figures.  They gate each ``RebirthInfo.evolveEnableVer``, and every one is at or
below the final client's own 5.5.7, so none of them withholds a recipe.
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


#: Recovered ``ChrDatabase.rebirthInfo`` availability versions, ``(id, version)``.
REBIRTH_AVAILABLE_VERSIONS: tuple[tuple[int, float], ...] = (
    (1, 2.5), (2, 2.5), (3, 2.5), (4, 2.5), (5, 2.5), (6, 2.5), (7, 2.5), (8, 2.5), (9, 2.5), (10, 2.5999999046325684), (11, 2.5999999046325684), (12, 2.5999999046325684), (13, 2.5999999046325684), (14, 2.5999999046325684), (15, 2.799999952316284), (16, 2.799999952316284), (17, 2.799999952316284), (18, 2.799999952316284), (19, 3.200000047683716), (20, 3.299999952316284), (21, 3.299999952316284), (22, 3.5999999046325684), (23, 3.700000047683716), (24, 3.799999952316284), (25, 4.0), (26, 4.0), (27, 4.099999904632568), (28, 4.099999904632568), (29, 4.099999904632568), (30, 4.099999904632568), (31, 4.110000133514404), (32, 4.110000133514404), (33, 4.099999904632568), (34, 4.099999904632568), (35, 4.199999809265137), (36, 4.199999809265137), (37, 4.199999809265137), (38, 4.199999809265137), (39, 4.199999809265137), (40, 4.300000190734863), (41, 4.300000190734863), (42, 4.300000190734863), (43, 4.300000190734863), (44, 4.300000190734863), (45, 4.300000190734863), (46, 4.400000095367432), (47, 4.400000095367432), (48, 4.400000095367432), (49, 4.400000095367432), (50, 4.400000095367432), (51, 4.400000095367432), (52, 4.5), (53, 4.699999809265137), (54, 4.699999809265137), (55, 4.699999809265137), (56, 5.199999809265137), (57, 5.199999809265137), (58, 5.199999809265137), (59, 5.199999809265137), (60, 5.199999809265137), (61, 5.199999809265137), (62, 5.199999809265137), (63, 5.199999809265137), (64, 5.199999809265137), (65, 5.300000190734863),
)


def rebirth_availability() -> list[dict[str, Any]]:
    """Return the ``rebirthList`` entries, ascending by recipe ID."""
    return [{"ID": recipe_id, "version": version} for recipe_id, version in REBIRTH_AVAILABLE_VERSIONS]


def login_chr_buddy_data() -> dict[str, Any]:
    """Return the ``chrBuddyData`` object for a login response.

    All three lists are always present. The client reads them unconditionally
    once the parent object exists, so omitting one throws inside its login
    reader rather than degrading gracefully.
    """
    return {
        "chrList": character_master_ids(),
        "buddyList": companion_master_ids(),
        "rebirthList": rebirth_availability(),
    }
