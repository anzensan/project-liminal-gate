"""The bundled achievement policy: all 98 of the client's own records.

The client ships 99 achievement records and evaluates every one of them against
its own state. Only nine are `unlockType == 0` (ClearChapter), the one condition
a server can check for itself; the rest turn on client-local counters -- levels,
jobs, species, gathered EXP, and the retired Co-op and VS tallies -- that this
server never observes.

This policy used to carry eight rows and refuse the rest, which made the other
ninety unclaimable and, with no `achive-*` flag sent, invisible as well. Both
halves are fixed: every record is listed and every record is claimable, with the
eight story conditions kept because they cost nothing to honour.

These cases pin the recovered shape so a future edit cannot quietly narrow the
policy back, or widen a reward past what the master data actually declares.
"""
from __future__ import annotations

import unittest

from liminal_gate.achievement_catalog import (
    BUNDLED_ITEM_SLOTS,
    build_bundled_achievement_policy,
)
from liminal_gate.achievement_data import (
    ACHIEVEMENT_FREE_ENERGY,
    ACHIEVEMENT_ITEM_COUNT,
    ACHIEVEMENT_ITEM_ID,
    ACHIEVEMENT_ROWS,
    MULTIPLAY_ACHIEVEMENT_CONDITIONS,
    multiplay_achievement_projection,
)
from liminal_gate.event_flag_data import ACHIEVEMENT_EVENT_FLAGS, achievement_event_flags


class BundledAchievementPolicyTest(unittest.TestCase):
    def test_every_record_the_client_carries_is_claimable(self) -> None:
        """98 of the 99: the empty-keyed placeholder grants nothing."""
        catalog = build_bundled_achievement_policy()
        self.assertEqual(98, len(catalog.achievements))

    def test_the_clear_chapter_ladder_survives_unchanged(self) -> None:
        """The eight story rows keep the one condition a server can check."""
        catalog = build_bundled_achievement_policy()
        gated = sorted(
            achievement.required_chapter
            for achievement in catalog.achievements.values()
            if achievement.required_chapter
        )
        self.assertEqual([5, 10, 15, 20, 25, 30, 35, 40], gated)
        # The eight this project carried by hand are still exactly themselves.
        for identifier, chapter in enumerate([5, 10, 15, 20, 25, 30, 35, 40], start=1):
            with self.subTest(identifier):
                achievement = catalog.achievements[identifier]
                self.assertEqual(chapter, achievement.required_chapter)
                self.assertEqual(ACHIEVEMENT_FREE_ENERGY, achievement.free_energy)
                self.assertEqual({ACHIEVEMENT_ITEM_ID: ACHIEVEMENT_ITEM_COUNT}, achievement.items)

    def test_everything_else_is_free_to_claim(self) -> None:
        """A zero chapter is what makes a claim free.

        The gate refuses when the account's chapter is at or below
        `required_chapter`, so zero passes for any real account. That is the
        whole mechanism -- there is no separate "free" flag to get wrong.
        """
        catalog = build_bundled_achievement_policy()
        free = [a for a in catalog.achievements.values() if not a.required_chapter]
        self.assertEqual(90, len(free))

    def test_no_reward_exceeds_what_the_master_declares(self) -> None:
        catalog = build_bundled_achievement_policy()
        for achievement in catalog.achievements.values():
            with self.subTest(achievement.achievement_id):
                # Two Energy is the largest present in the recovered table, and
                # no record pays Coins at all.
                self.assertLessEqual(achievement.free_energy, 2)
                self.assertEqual(0, achievement.coins)
                self.assertTrue(all(1 <= item <= catalog.item_slots for item in achievement.items))
                self.assertTrue(all(count > 0 for count in achievement.items.values()))

    def test_limits_match_the_other_bundled_policies(self) -> None:
        catalog = build_bundled_achievement_policy()
        self.assertEqual(BUNDLED_ITEM_SLOTS, catalog.item_slots)
        # The ceiling is the save's own Energy bound now that a claim can pay
        # two: capping at one grant would have silently clamped the second.
        self.assertGreaterEqual(catalog.max_free_energy, 2)

    def test_rows_are_ordered_and_unique(self) -> None:
        ids = [row[0] for row in ACHIEVEMENT_ROWS]
        self.assertEqual(sorted(set(ids)), ids)

    def test_both_visibility_flags_are_sent(self) -> None:
        """Listing them is the other half; a claimable achievement nothing
        shows is exactly as unreachable as an unclaimable one."""
        self.assertEqual(("achive-1", "achive-hide"), ACHIEVEMENT_EVENT_FLAGS)
        flags = achievement_event_flags()
        self.assertEqual({"achive-1", "achive-hide"}, set(flags))
        self.assertTrue(all(entry["value"] is True for entry in flags.values()))


def _client_reads(projection: dict[str, object], field: str, index: int | None) -> int:
    """Evaluate `MultiplayUserData` exactly as the reviewed client does.

    `CoopPrize` reads the scalar `prize`; every other Co-op and VS case goes
    through `GetNumImpl`, which sums the whole list for index -1 and returns 0
    for an index at or past the list's end rather than throwing.
    """
    value = projection[field]
    if index is None:
        assert isinstance(value, int)
        return value
    assert isinstance(value, list)
    if index < 0:
        return sum(value)
    return value[index] if index < len(value) else 0


class MultiplayProjectionTest(unittest.TestCase):
    """The nineteen Co-op and VS records, settled through `multiplayData`.

    Co-op and VS needed a player population, so these are the one family whose
    conditions no amount of play can reach on an archived service. The client
    evaluates them against counters the server supplies, which makes the
    counters the only channel -- and makes it worth re-running the client's own
    predicate here rather than trusting the derivation to stay right.
    """

    def test_every_recovered_condition_is_satisfied(self) -> None:
        projection = multiplay_achievement_projection()
        self.assertEqual(19, len(MULTIPLAY_ACHIEVEMENT_CONDITIONS))
        for identifier, key, field, index, threshold in MULTIPLAY_ACHIEVEMENT_CONDITIONS:
            with self.subTest(f"{identifier} {key}"):
                self.assertGreaterEqual(_client_reads(projection, field, index), threshold)

    def test_no_counter_exceeds_what_the_conditions_ask_for(self) -> None:
        """A fabricated history is bounded by the thresholds that force it.

        `coopFreePlayNum` is the one list two kinds of condition touch at once:
        slots 0 and 1 each need 50, which already covers the separate sum
        condition of 30, so nothing is topped up on its account.
        """
        for field in {row[2] for row in MULTIPLAY_ACHIEVEMENT_CONDITIONS if row[3] is not None}:
            rows = [row for row in MULTIPLAY_ACHIEVEMENT_CONDITIONS if row[2] == field]
            slots = {row[3]: row[4] for row in rows if row[3] >= 0}
            wanted = max((row[4] for row in rows if row[3] < 0), default=0)
            with self.subTest(field):
                self.assertEqual(max(wanted, sum(slots.values())), sum(multiplay_achievement_projection()[field]))
        self.assertEqual(50, multiplay_achievement_projection()["prize"])
        self.assertEqual([50, 50], multiplay_achievement_projection()["coopFreePlayNum"])

    def test_the_object_carries_every_key_the_loader_reads(self) -> None:
        """`LoadFromJsonNormal`'s own key list, in the order it reads them.

        `rank` is absent because the client derives it from `exp` instead of
        loading it, and the two running consecutive-win lists stay empty
        because the conditions read the `...Max` lists beside them.
        """
        projection = multiplay_achievement_projection()
        self.assertEqual(
            {
                "exp", "titleList", "showTitles", "friendList", "prize",
                "coopFriendPlayNum", "coopFreePlayNum", "coopSimplePlayNum",
                "vsFreePlayNum", "vsFriendPlayNum", "vsFreeWinNum", "vsFriendWinNum",
                "vsFreeConsectiveWinNum", "vsFriendConsectiveWinNum",
                "vsFreeConsectiveWinMax", "vsFriendConsectiveWinMax",
                "vsPlayChapter", "vsPlayMatchType", "vsStaminaRefillStartTime",
            },
            set(projection),
        )
        self.assertNotIn("rank", projection)
        self.assertEqual([], projection["vsFreeConsectiveWinNum"])
        self.assertEqual([], projection["vsFriendConsectiveWinNum"])
        # An account that never played holds no titles and no multiplay rank.
        self.assertEqual(0, projection["exp"])
        self.assertEqual([], projection["titleList"])
        self.assertEqual([], projection["friendList"])

    def test_a_userdata_read_installs_it_on_a_save_written_without_it(self) -> None:
        """The field is null on the client until a response carries the key.

        A save from before this existed must not keep an achievements screen
        that raises rather than lists, so the read rebuilds the projection the
        same way it rebuilds the wallet.
        """
        import tempfile
        from pathlib import Path

        from liminal_gate.bootstrap_server import BootstrapState

        with tempfile.TemporaryDirectory() as directory:
            state = BootstrapState(Path(directory) / "state.json")
            try:
                state.create_account("token", "account", {
                    "coins": 30_000, "energy": 0, "freeEnergy": 72,
                    "energyAppStore": 0, "energyGooglePlay": 0, "energyAndApp": 0,
                    "itemList": [0] * 181, "chrdata": [], "summonList": [0] * 16,
                    "buddyInfo": {"list": [], "record": []},
                })
                self.assertNotIn("multiplayData", state.accounts["account"]["userdata"])
                served = state.userdata_for("token")
                self.assertIsNotNone(served)
                assert served is not None
                self.assertEqual(multiplay_achievement_projection(), served["multiplayData"])
                # And it is durable, so a restart does not serve a null field once.
                self.assertEqual(
                    multiplay_achievement_projection(),
                    state.accounts["account"]["userdata"]["multiplayData"],
                )
            finally:
                state.close()


if __name__ == "__main__":
    unittest.main()
