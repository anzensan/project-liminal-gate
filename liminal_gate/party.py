"""Which six roster members an account is actually fielding.

One rule, in one place, because it has now been got wrong twice from two
different directions. `teamMembers` reads like a party and is not one, so every
reader that reaches for it directly is a fault waiting to be reported: the
species lock judged all fifteen squads a save carried and refused a party that
never held a Human, and the Luck runtime rolled and paid a battle's growth to
whichever characters happened to sit in the first squad.

This module holds nothing else. It exists so that `bootstrap_server` and
`luck_runtime` can share the answer without one importing the other, and so the
next reader of "the party" has somewhere obvious to find it.
"""

from __future__ import annotations

from typing import Any

#: Slots in one squad. `UserData.GetTeamMember` reads it from a static rather
#: than a literal, and every save seen carries a `teamMembers` whose length is a
#: multiple of six.
TEAM_MEMBERS_PER_SQUAD = 6


def active_party_members(userdata: dict[str, Any]) -> list[Any] | None:
    """The six members the account is actually fielding.

    **`teamMembers` is not a party.** It is every squad the account has kept,
    flattened into one array, and `teamNo` says which of them is on screen: a
    played save carries fifteen squads and ninety entries. The client indexes it
    as `UserData.GetTeamMember` (ARM64 `0x19D95D8`) does --
    ``(teamID - 1) * membersPerTeam + memberID - 1``, both indices one-based --
    and nothing but that slice is the party.

    Reading the whole array as one is what refused Machine Road to a squad of
    two Machines: the species lock walked all ninety entries, found the Humans
    and Lizards sitting in the other fourteen squads, and answered
    `SpeciesLimit` to a party that never held one. No squad the player could
    build would have passed, which is the shape of the bug -- a gate that reads
    more state than the rule it enforces covers cannot be satisfied at all.

    Reading only the *front* of the array is the same mistake turned around, and
    is what stopped Luck from sticking: taking the first six entries names Squad
    1 whatever the player is fielding, so a party fought with Squad 3 had its
    growth rolled against six characters it did not contain and paid to them.

    A save with one squad is returned unchanged, which is every save written
    before a second squad existed and every party in the tests. A `teamNo` that
    names no squad in the array is treated as the first, because a squad number
    outside its own array is a malformed pairing rather than a statement about
    the party, and the first squad is what a single-squad save means by it.
    """
    members = userdata.get("teamMembers")
    if not isinstance(members, list) or len(members) <= TEAM_MEMBERS_PER_SQUAD:
        return members if isinstance(members, list) else None
    squad = userdata.get("teamNo")
    start = (squad - 1) * TEAM_MEMBERS_PER_SQUAD if type(squad) is int and squad >= 1 else 0
    if start + TEAM_MEMBERS_PER_SQUAD > len(members):
        start = 0
    return members[start:start + TEAM_MEMBERS_PER_SQUAD]
