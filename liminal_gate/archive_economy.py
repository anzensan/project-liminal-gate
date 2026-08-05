"""Preservation-mode Energy income for a service that no longer sells it.

The retired service supplied Energy three ways this archive cannot reproduce:
in-app purchase, timed campaign gifts, and operator compensation mail.  Nothing
in the final client mints Energy on its own -- ``ChapterClearEnergyBonus`` and
``EnergyBonusByDailyQuest`` are display strings the server's own response is
expected to back with a real balance.  A local server that grants none therefore
leaves an account permanently poorer than it started, because Pacts, job
unlocks, Metal Zone openings and stamina refills all debit the same wallet with
no path back to it.

This module is the replacement income, and it is stated plainly as **local
preservation policy, not recovered service behaviour**.  The original per-stage
award, if any existed, was never captured; these rates are chosen to be small,
transparent and replay-safe, and they match the private reference server so the
two economies stay interchangeable while it is retired.

Two grants:

- Every unique story or event stage pays ``FIRST_CLEAR_FREE_ENERGY`` the first
  time it is cleared and ``REPEAT_CLEAR_FREE_ENERGY`` on every later clear.
  The first-clear half is guarded by a per-account key set rather than by
  request identity, so replaying an old clear under a fresh request id cannot
  farm it.  The optional areas pay nothing at all; see
  ``ENERGY_BEARING_KINDS``.
- Completing a chapter pays ``CHAPTER_CLEAR_FREE_ENERGY`` once, ever, tracked
  by chapter number.

Both are capped at ``MAX_FREE_ENERGY``, which *is* recovered: it is the
``maxFreeEnergy`` this server already advertises in its constants block.
"""

from __future__ import annotations

from typing import Any


#: ``ServerConstants.maxFreeEnergy``, as advertised to the client.
MAX_FREE_ENERGY = 9_999
#: Local policy: the award for a stage's first accepted clear.
# For comparison, not reproduction: the community record documents the
# retired service's chapter income as one Energy per chapter first-clear plus
# daily login bonuses (five on day one), neither of which this archive
# reimplements.  The larger local rates below are sized for an environment
# with no login bonuses, campaigns, gifts, or commerce, and stay labeled as
# such.
FIRST_CLEAR_FREE_ENERGY = 2
#: Local policy: the award for any later clear of a stage already cleared.
REPEAT_CLEAR_FREE_ENERGY = 1
#: Local policy: the one-time award for completing a chapter.
CHAPTER_CLEAR_FREE_ENERGY = 50
#: Local policy: the stage families whose clears pay at all.  Story and event
#: chapters are played through once, so what they can ever mint is bounded by
#: the content itself.  The optional areas -- Hunting, Metal Zone, the special
#: quest, Daily Quests, and the Chapter 1100 Roads -- are replayable without
#: bound, and a stage that both repeats forever and mints Energy is a farm
#: rather than income: it makes every Energy price in the client, from Pacts to
#: stamina refills, a matter of how long a Metal Zone run is repeated.  They
#: therefore pay nothing, on the first clear as on the hundredth, and the
#: wallet's only local income stays the story an account is actually advancing.
ENERGY_BEARING_KINDS = frozenset({"story", "event"})


def stage_energy_key(kind: str, chapter: int, section: int) -> str:
    """Return the per-account first-clear key for one stage."""
    return f"{kind}:{chapter}-{section}"


def award_stage_energy(
    account: dict[str, Any], kind: str, chapter: int, section: int,
) -> int:
    """Grant and record one stage clear's Energy, returning the amount minted.

    The award is applied to ``freeEnergy`` only.  The paid Energy families are
    never written by this server, so a local grant can never be confused with a
    purchase the account did not make.  A stage family outside
    ``ENERGY_BEARING_KINDS`` mints nothing and records no history, so a clear it
    repeats stays free of any wallet effect whatsoever.
    """
    if kind not in ENERGY_BEARING_KINDS:
        return 0
    history = account.setdefault("stage_energy_history", [])
    key = stage_energy_key(kind, chapter, section)
    first_clear = key not in history
    if first_clear:
        history.append(key)
    requested = FIRST_CLEAR_FREE_ENERGY if first_clear else REPEAT_CLEAR_FREE_ENERGY
    return _mint(account["userdata"], requested)


def award_chapter_energy(account: dict[str, Any], chapter: int) -> int:
    """Grant the one-time completion award for ``chapter``, if still unclaimed."""
    granted = account.setdefault("chapter_energy_granted", [])
    if chapter < 1 or chapter in granted:
        return 0
    granted.append(chapter)
    return _mint(account["userdata"], CHAPTER_CLEAR_FREE_ENERGY)


def _mint(userdata: dict[str, Any], requested: int) -> int:
    balance = int(userdata.get("freeEnergy", 0))
    minted = max(0, min(requested, MAX_FREE_ENERGY - balance))
    if minted:
        userdata["freeEnergy"] = balance + minted
    return minted
