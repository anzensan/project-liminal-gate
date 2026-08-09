"""The longest Special Quest list the final client can render, and what goes.

A 31-row `specialQuestList` never reaches the title flow: the client hangs on
the Mistwalker splash and then raises its transport dialog, while every request
this server answers returns 200. Nothing in `events.jsonl` points at it, which
is why two reports of a Network Error "on the Chapter 20 clear" could not be
diagnosed from a log -- Chapter 20 is simply where an ordinary account crosses
the line, five families opening at once and the list going 20 -> 31 in a step.

Measured against the reviewed client, same account, only `progressCode` moved:
20 rows reach the home screen, 31 hang, 30 reach it again. Dropping any one
family fixed it (2002 and 2018 were both tried), which rules out a bad row;
capping the list while leaving every `sp_ch_` flag in place fixed it too, which
rules out the flag block.
"""

from __future__ import annotations

import unittest

from liminal_gate.bootstrap_server import (
    SPECIAL_QUEST_LIST_MAX,
    _bounded_special_quest_list,
    _is_archive_row,
)


def rows(archive: int, standing: int) -> list[str]:
    """`archive` archived-event rows followed by `standing` permanent ones."""
    return (
        [f"20{index:02d}-1" for index in range(archive)]
        + [f"9{index:03d}" for index in range(standing)]
    )


class SpecialQuestListCapTest(unittest.TestCase):
    def test_a_list_within_the_limit_is_served_unchanged(self) -> None:
        served = rows(20, 10)
        self.assertEqual(30, len(served))
        self.assertEqual(served, _bounded_special_quest_list(served, set(), None))

    def test_the_row_that_would_hang_the_client_is_withheld(self) -> None:
        """The regression. One row over is an account that cannot reach play."""
        served = rows(21, 10)
        bounded = _bounded_special_quest_list(served, set(), None)
        self.assertEqual(SPECIAL_QUEST_LIST_MAX, len(bounded))

    def test_permanent_quests_are_never_the_ones_withheld(self) -> None:
        """Melting Pot and the standing rows outlive any archive row.

        They are always-available content a player builds a routine around;
        an archive event that opened this chapter is not yet.
        """
        served = rows(28, 10)
        bounded = _bounded_special_quest_list(served, set(), None)
        self.assertTrue(all(row in bounded for row in served if not _is_archive_row(row)))
        self.assertEqual(SPECIAL_QUEST_LIST_MAX, len(bounded))

    def test_archive_rows_are_withheld_newest_first(self) -> None:
        served = rows(21, 10)
        bounded = _bounded_special_quest_list(served, set(), None)
        self.assertNotIn("2020-1", bounded)
        self.assertIn("2000-1", bounded)

    def test_display_order_is_not_reshuffled_by_the_cap(self) -> None:
        """Membership is decided here; the menu's order is not."""
        served = rows(25, 10)
        bounded = _bounded_special_quest_list(served, set(), None)
        self.assertEqual([row for row in served if row in set(bounded)], bounded)

    def test_the_archive_range_is_what_separates_the_two(self) -> None:
        """Which catalog emitted a row does not: the event catalog carries both."""
        self.assertTrue(_is_archive_row("2002"))
        self.assertTrue(_is_archive_row("2017-5"))
        self.assertFalse(_is_archive_row("9100"))
        self.assertFalse(_is_archive_row("3001-2"))
        self.assertFalse(_is_archive_row("not-a-chapter"))

    def test_a_cap_is_never_silent(self) -> None:
        """A withheld row is recorded, never dropped without a trace."""
        recorded: list[dict[str, object]] = []

        class Recorder:
            def record(self, method, target, status, details=None):
                recorded.append(details or {})

        served = rows(21, 10)
        _bounded_special_quest_list(served, set(), Recorder())
        self.assertEqual(1, len(recorded))
        capped = recorded[0]["special_quest_list_capped"]
        self.assertEqual(SPECIAL_QUEST_LIST_MAX, capped["served"])
        self.assertEqual(SPECIAL_QUEST_LIST_MAX, capped["limit"])
        self.assertEqual(len(served) - SPECIAL_QUEST_LIST_MAX, len(capped["withheld"]))

    def test_nothing_is_withheld_before_the_chapter_20_boundary(self) -> None:
        """20 rows is what an account holds with Chapter 20 still uncleared."""
        served = rows(12, 8)
        self.assertEqual(served, _bounded_special_quest_list(served, set(), None))


if __name__ == "__main__":
    unittest.main()
