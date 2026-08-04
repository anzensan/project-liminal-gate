"""The stamina meter and the preservation Energy income.

Entering a quest debits stamina, a time-refilling meter the client derives from
one fill origin, and clearing one pays free Energy.  Before both existed the
server answered `refillStartTime: 0.0` to every start, which the client reads
as "this meter refilled at the epoch" -- a bar that never moved however many
quests were entered, and in particular a Metal Zone that could be re-entered
without limit once its ticket ran out and the entry fell back to stamina.
"""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import time
import unittest

from liminal_gate.archive_economy import (
    CHAPTER_CLEAR_FREE_ENERGY,
    FIRST_CLEAR_FREE_ENERGY,
    MAX_FREE_ENERGY,
    REPEAT_CLEAR_FREE_ENERGY,
    award_chapter_energy,
    award_stage_energy,
)
from liminal_gate.bootstrap_server import BootstrapState, entry_stamina_origin
from liminal_gate.stamina_meter import (
    FULL_METER_ORIGIN,
    REFILL_INTERVAL_SECONDS,
    chapter_for_progress,
    current_stamina,
    max_stamina_for_chapter,
    seconds_to_next_point,
    spend_stamina,
)


class MaxStaminaCurveTest(unittest.TestCase):
    """`UserData.GetMaxStamina`, ARM64 `0x19D8BDC`."""

    def test_recovered_endpoints_of_both_branches(self) -> None:
        # ch <= 30: (ch - 1) / 29 * 80 + 20, so 1 -> 20 and 30 -> 100.
        self.assertEqual(20, max_stamina_for_chapter(1))
        self.assertEqual(100, max_stamina_for_chapter(30))
        # ch > 30: (ch - 30) / 30 * 80 + 100, so 31 -> 102 and 60 -> 180.
        self.assertEqual(102, max_stamina_for_chapter(31))
        self.assertEqual(180, max_stamina_for_chapter(60))

    def test_the_branch_boundary_falls_on_the_low_side(self) -> None:
        # `subs w9, w8, #0x1e` then `b.le` puts chapter 30 itself on the first
        # curve; both happen to agree there, which is why only 31 proves it.
        self.assertEqual(100, max_stamina_for_chapter(30))
        self.assertNotEqual(max_stamina_for_chapter(30), max_stamina_for_chapter(31))

    def test_zero_chapter_is_substituted_with_one(self) -> None:
        self.assertEqual(max_stamina_for_chapter(1), max_stamina_for_chapter(0))

    def test_the_curve_never_decreases(self) -> None:
        values = [max_stamina_for_chapter(chapter) for chapter in range(1, 43)]
        self.assertEqual(values, sorted(values))

    def test_the_final_story_chapter_is_covered(self) -> None:
        self.assertEqual(132, max_stamina_for_chapter(42))


class MeterTest(unittest.TestCase):
    def test_a_zero_origin_reads_as_a_full_meter(self) -> None:
        # This is the whole reason the old constant answer hid the bug.
        self.assertEqual(
            max_stamina_for_chapter(5), current_stamina(0.0, 5, 1_000_000.0)
        )

    def test_points_accrue_one_per_interval(self) -> None:
        now = 1_000_000.0
        origin = now - 3 * REFILL_INTERVAL_SECONDS
        self.assertEqual(3, current_stamina(origin, 5, now))
        self.assertEqual(2, current_stamina(origin + 1, 5, now))

    def test_accrual_is_clamped_to_the_chapter_maximum(self) -> None:
        now = 1_000_000.0
        origin = now - 10_000 * REFILL_INTERVAL_SECONDS
        self.assertEqual(max_stamina_for_chapter(2), current_stamina(origin, 2, now))

    def test_countdown_matches_the_clients_own_remainder(self) -> None:
        now = 1_000_000.0
        self.assertEqual(
            REFILL_INTERVAL_SECONDS - 30,
            seconds_to_next_point(now - (REFILL_INTERVAL_SECONDS + 30), now),
        )


class SpendTest(unittest.TestCase):
    def test_a_spend_from_full_leaves_the_remainder_on_the_meter(self) -> None:
        now = 1_000_000.0
        maximum = max_stamina_for_chapter(10)
        origin = spend_stamina(0.0, 5, 10, now)
        self.assertIsNotNone(origin)
        self.assertEqual(maximum - 5, current_stamina(origin, 10, now))

    def test_a_spend_the_meter_cannot_cover_is_refused(self) -> None:
        now = 1_000_000.0
        origin = now - 2 * REFILL_INTERVAL_SECONDS
        self.assertIsNone(spend_stamina(origin, 3, 5, now))
        self.assertIsNotNone(spend_stamina(origin, 2, 5, now))

    def test_repeated_entries_exhaust_the_meter(self) -> None:
        """The Metal Zone regression: entry must not be unbounded."""
        now, origin, entries = 1_000_000.0, 0.0, 0
        # Chapter 1's maximum is 20 and a Metal King entry costs 20 stamina, so
        # exactly one run is affordable before the meter has to refill.
        while (moved := spend_stamina(origin, 20, 1, now)) is not None:
            origin, entries = moved, entries + 1
            self.assertLess(entries, 50, "entry never ran out of stamina")
        self.assertEqual(1, entries)

    def test_partial_refill_progress_survives_a_spend(self) -> None:
        now = 1_000_000.0
        # Two whole points plus 45 seconds toward the third.
        origin = now - (2 * REFILL_INTERVAL_SECONDS + 45)
        moved = spend_stamina(origin, 1, 5, now)
        self.assertIsNotNone(moved)
        self.assertEqual(1, current_stamina(moved, 5, now))
        self.assertEqual(REFILL_INTERVAL_SECONDS - 45, seconds_to_next_point(moved, now))

    def test_a_free_entry_from_full_keeps_the_full_meter_representation(self) -> None:
        self.assertEqual(0.0, spend_stamina(0.0, 0, 5, 1_000_000.0))

    def test_a_negative_cost_is_refused_rather_than_refunded(self) -> None:
        self.assertIsNone(spend_stamina(0.0, -1, 5, 1_000_000.0))


class DisabledStaminaPolicyTest(unittest.TestCase):
    """The shipped default, where the meter gates nothing.

    The timer gate paced a live service that no longer exists, so this server
    charges it only when an operator passes `--enable-stamina`.  Off has to mean
    the whole gate, not just the arithmetic: an entry that would have been
    refused is accepted, a save carrying a live fill origin reads back as a full
    bar, and the refill route stops selling an Energy for a meter nothing spends.
    """

    def exhausted(self) -> tuple[dict, float]:
        """A save whose meter a chapter-5 entry could not afford."""
        now = 1_000_000.0
        return {"refillStartTime": now, "progressCode": 0x01000000 | (5 << 6)}, now

    def test_an_entry_the_meter_cannot_cover_is_accepted_anyway(self) -> None:
        userdata, now = self.exhausted()
        self.assertEqual(
            FULL_METER_ORIGIN,
            entry_stamina_origin(userdata, 40, now, enabled=False),
        )

    def test_the_enabled_policy_still_refuses_that_entry(self) -> None:
        """The same call with the flag on, so a reversed test cannot pass both."""
        userdata, now = self.exhausted()
        self.assertIsNone(entry_stamina_origin(userdata, 40, now, enabled=True))

    def test_the_enabled_policy_debits_the_meter_it_reads(self) -> None:
        userdata = {"refillStartTime": 0.0, "progressCode": 0x01000000 | (10 << 6)}
        origin = entry_stamina_origin(userdata, 5, 1_000_000.0, enabled=True)
        self.assertEqual(
            max_stamina_for_chapter(10) - 5, current_stamina(origin, 10, 1_000_000.0),
        )

    def test_a_read_returns_a_save_written_with_the_meter_on_to_full(self) -> None:
        """A tester who turns the policy off must not inherit a half bar."""
        with tempfile.TemporaryDirectory() as directory:
            state = BootstrapState(Path(directory) / "state.json")
            try:
                state.create_account("token", "account", {
                    "coins": 0, "worldMapNo": 0, "progressCode": 0x01000000 | (5 << 6),
                    "chrdata": [], "itemList": [], "summonList": [],
                })
                with state.lock:
                    state.accounts["account"]["userdata"]["refillStartTime"] = 1_000_000.0
                    state._persist_locked()
                self.assertEqual(
                    FULL_METER_ORIGIN,
                    state.userdata_for("token", stamina=False)["refillStartTime"],
                )
                # Durable, not just projected: the next read is not the only
                # thing that has to agree, the next entry does too.
                self.assertEqual(
                    FULL_METER_ORIGIN,
                    json.loads((Path(directory) / "state.json").read_text(encoding="utf-8"))
                    ["accounts"]["account"]["userdata"]["refillStartTime"],
                )
            finally:
                state.close()

    def test_the_refill_route_sells_nothing_for_a_meter_nothing_spends(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = BootstrapState(Path(directory) / "state.json")
            try:
                state.create_account("token", "account", {
                    "coins": 0, "energy": 5, "freeEnergy": 5, "worldMapNo": 0,
                    "progressCode": 0x01000000 | (5 << 6),
                    "chrdata": [], "itemList": [], "summonList": [],
                })
                with state.lock:
                    # An origin at "now" is the empty meter a refill is for.
                    state.accounts["account"]["userdata"]["refillStartTime"] = time.time()
                    state._persist_locked()
                result, payload = state.refill_stamina(
                    "token", "refill", b"cost=1", stamina=False,
                )
                # `RefillStaminaErrorCode.NoNeedToRefill`, the client's own
                # refusal for a bar that is already full.
                self.assertEqual(("success", {"success": False, "errorCode": 1}), (result, payload))
                userdata = state.accounts["account"]["userdata"]
                self.assertEqual((5, 5), (userdata["energy"], userdata["freeEnergy"]))
            finally:
                state.close()


class ProgressChapterTest(unittest.TestCase):
    def test_the_chapter_comes_from_the_low_progress_bits(self) -> None:
        self.assertEqual(7, chapter_for_progress(0x01000000 | (7 << 6) | 1))

    def test_an_empty_progress_code_still_yields_a_playable_chapter(self) -> None:
        self.assertEqual(1, chapter_for_progress(0))


class ArchiveEnergyTest(unittest.TestCase):
    def account(self, free_energy: int = 0) -> dict:
        return {"userdata": {"freeEnergy": free_energy}}

    def test_first_clear_pays_more_than_a_repeat(self) -> None:
        account = self.account()
        self.assertEqual(FIRST_CLEAR_FREE_ENERGY, award_stage_energy(account, "story", 2, 1))
        self.assertEqual(REPEAT_CLEAR_FREE_ENERGY, award_stage_energy(account, "story", 2, 1))
        self.assertEqual(
            FIRST_CLEAR_FREE_ENERGY + REPEAT_CLEAR_FREE_ENERGY,
            account["userdata"]["freeEnergy"],
        )

    def test_each_stage_and_kind_earns_its_own_first_clear(self) -> None:
        account = self.account()
        award_stage_energy(account, "story", 2, 1)
        self.assertEqual(FIRST_CLEAR_FREE_ENERGY, award_stage_energy(account, "story", 2, 2))
        self.assertEqual(FIRST_CLEAR_FREE_ENERGY, award_stage_energy(account, "hunting", 2, 1))

    def test_the_award_is_capped_at_the_advertised_maximum(self) -> None:
        account = self.account(MAX_FREE_ENERGY - 1)
        self.assertEqual(1, award_stage_energy(account, "story", 2, 1))
        self.assertEqual(MAX_FREE_ENERGY, account["userdata"]["freeEnergy"])
        self.assertEqual(0, award_stage_energy(account, "story", 2, 2))
        self.assertEqual(MAX_FREE_ENERGY, account["userdata"]["freeEnergy"])

    def test_a_chapter_pays_its_completion_award_only_once(self) -> None:
        account = self.account()
        self.assertEqual(CHAPTER_CLEAR_FREE_ENERGY, award_chapter_energy(account, 2))
        self.assertEqual(0, award_chapter_energy(account, 2))
        self.assertEqual(CHAPTER_CLEAR_FREE_ENERGY, award_chapter_energy(account, 3))

    def test_only_free_energy_is_ever_minted(self) -> None:
        # A local grant must never be mistakable for a purchase.
        account = {"userdata": {"freeEnergy": 0, "energy": 5, "energyAppStore": 5}}
        award_stage_energy(account, "story", 2, 1)
        award_chapter_energy(account, 2)
        self.assertEqual((5, 5), (account["userdata"]["energy"], account["userdata"]["energyAppStore"]))


if __name__ == "__main__":
    unittest.main()
