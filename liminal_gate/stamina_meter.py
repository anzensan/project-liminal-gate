"""The client's stamina meter, recovered from the final 5.5.7 ARM64 binary.

Stamina and Energy are two different currencies and the server must not
confuse them.  Energy (``energy``/``freeEnergy``/``energyAppStore``/...) is the
premium wallet spent on Pacts, job unlocks and stamina refills.  Stamina is a
time-refilling meter that quest entry consumes, and it is *not* stored as a
balance at all -- the client derives it from one Unix-seconds fill origin,
``UserData.refillStartTime`` (ARM64 field offset ``0x40``).

``GameManager.CalcStamina`` (ARM64 ``0xD9CFC0-0xD9D150``) is the whole model:

    elapsed   = max(0, now - refillStartTime)
    filled    = elapsed / ServerConstants.refillInterval        # integer div
    nextInSec = refillInterval - elapsed % refillInterval       # UI countdown
    stamina   = min(filled, GetMaxStamina()) + UserData.bonusStamina

A zero origin therefore reads as a full meter, because ``now - 0`` is a very
large elapsed time that the ``min`` clamps to the maximum.  That is why a
server which always answers ``refillStartTime: 0.0`` shows a bar that never
moves however many quests are entered -- the value is not a placeholder the
client ignores, it is an assertion that the meter refilled at the epoch.

``UserData.GetMaxStamina`` (ARM64 ``0x19D8BDC-0x19D8D60``) is a two-branch
single-precision curve on the account's current chapter, scaled by a percentage
bias:

    ch <= 30:  trunc((ch - 1)  / 29.0f * 80.0f + 20.0f)
    ch >  30:  trunc((ch - 30) / 30.0f * 80.0f + 100.0f)
    result  =  MaxStaminaBias * that / 100

The two ``80.0f``/``100.0f`` operands are code constants read from ``0x204F418``
and ``0x204F1FC``.  The arithmetic is genuinely ``float``, not ``double`` and
not integer, so it is reproduced here at single precision rather than
simplified -- a rounded rewrite would disagree with the client's own bar.

A version gate in front of the curve clamps the chapter to
``ServerConstants.maxChapter`` only when the running client is older than
``2.6``; the final client is ``5.5.7``, so that branch is never taken and no
clamp applies.

``ServerConstants.MaxStaminaBias`` is not sent by this server, and it does not
have to be: ``SetServerConstants`` writes a literal ``100`` when the key is
absent (ARM64 ``0x19D57AC``).  The constant below is that default, so the two
agree without adding a key whose production value was never recovered.

Confidence: Confirmed.  Every constant and branch above was read from the
shipped ARM64 ``libil2cpp.so``; none of it is inferred from secondary sources.
"""

from __future__ import annotations

import struct


#: ``ServerConstants.refillInterval``, in seconds, as this server advertises it.
REFILL_INTERVAL_SECONDS = 120
#: The client's own fallback for ``ServerConstants.MaxStaminaBias``.
MAX_STAMINA_BIAS_PERCENT = 100
#: The meter is full whenever the fill origin is at or before the epoch.
FULL_METER_ORIGIN = 0.0


def _f32(value: float) -> float:
    """Round to single precision, the width the client's curve actually uses."""
    return struct.unpack("<f", struct.pack("<f", value))[0]


def max_stamina_for_chapter(chapter: int) -> int:
    """Return ``UserData.GetMaxStamina`` for one chapter."""
    # `csel w8, w8, w19, eq` substitutes 1 for a zero chapter before the curve.
    chapter = 1 if chapter == 0 else chapter
    if chapter - 30 > 0:
        raw = _f32(_f32(_f32(chapter - 30) / _f32(30.0)) * _f32(80.0)) + _f32(100.0)
    else:
        raw = _f32(_f32(_f32(chapter - 1) / _f32(29.0)) * _f32(80.0)) + _f32(20.0)
    # `fcvtzs` truncates toward zero, and the trailing magic-number division is
    # a signed C division by 100, which truncates toward zero as well.
    truncated = int(_f32(raw))
    product = MAX_STAMINA_BIAS_PERCENT * truncated
    return -(-product // 100) if product < 0 else product // 100


def current_stamina(refill_start_time: float, chapter: int, now: float) -> int:
    """Return the meter the client would display, excluding ``bonusStamina``."""
    maximum = max_stamina_for_chapter(chapter)
    if refill_start_time <= FULL_METER_ORIGIN:
        return maximum
    elapsed = max(now - refill_start_time, 0.0)
    return min(int(elapsed // REFILL_INTERVAL_SECONDS), maximum)


def seconds_to_next_point(refill_start_time: float, now: float) -> int:
    """Return the client's own countdown to the next refilled point."""
    if refill_start_time <= FULL_METER_ORIGIN:
        return REFILL_INTERVAL_SECONDS
    elapsed = max(now - refill_start_time, 0.0)
    return REFILL_INTERVAL_SECONDS - int(elapsed % REFILL_INTERVAL_SECONDS)


def spend_stamina(
    refill_start_time: float, cost: int, chapter: int, now: float,
) -> float | None:
    """Return the fill origin after a spend, or ``None`` if the meter is short.

    Partial refill progress is preserved rather than discarded: pushing the
    origin forward by whole intervals alone would silently hand back the
    seconds already accumulated toward the next point on every entry.
    """
    if cost < 0:
        return None
    maximum = max_stamina_for_chapter(chapter)
    if refill_start_time <= FULL_METER_ORIGIN:
        current, partial = maximum, 0.0
    else:
        elapsed = max(now - refill_start_time, 0.0)
        current = min(int(elapsed // REFILL_INTERVAL_SECONDS), maximum)
        partial = 0.0 if current >= maximum else elapsed % REFILL_INTERVAL_SECONDS
    if cost > current:
        return None
    if current - cost >= maximum:
        # Still capped after the spend, so the meter is full and the origin
        # returns to the client's own full-meter representation.
        return FULL_METER_ORIGIN
    return float(now - ((current - cost) * REFILL_INTERVAL_SECONDS + partial))


def chapter_for_progress(progress_code: int) -> int:
    """Return the chapter the account has unlocked, for the maximum curve.

    ``GetMaxStamina``'s default argument reads ``UserData._chapterNo``, which
    tracks the account's own progress rather than the stage being entered, so
    the low progress bits are the matching server-side source.

    Confidence: Strongly inferred -- the encoding is confirmed and used
    elsewhere in this server, the identification with ``_chapterNo`` is not.
    """
    return max((progress_code & 0xFFFF) >> 6, 1)
