from __future__ import annotations

import unittest

from liminal_gate.bootstrap_server import _preserved_progress
from liminal_gate.plus_type_data import (
    PLUS_COUNT_DECLARED_MAX,
    PLUS_COUNT_MAX,
    PLUS_TYPE_MAXIMA,
    plus_stat_bonus,
)


class PlusTypeTableTest(unittest.TestCase):
    """The recovered `ChrDatabase.plusTypes` table, and what a count is worth."""

    def test_carries_every_curve_the_client_builds(self) -> None:
        # `GetPlusTypeParams` allocates fourteen entries (`mov w1, #0xe`), which
        # is also the number of distinct `plusType` values across the client's
        # 346 recruitable characters.
        self.assertEqual(14, len(PLUS_TYPE_MAXIMA))
        for maxima in PLUS_TYPE_MAXIMA:
            self.assertEqual(4, len(maxima))
            self.assertTrue(all(0 <= value <= 100 for value in maxima))

    def test_type_zero_is_the_no_effect_curve(self) -> None:
        self.assertEqual((0, 0, 0, 0), PLUS_TYPE_MAXIMA[0])
        self.assertEqual((0, 0, 0, 0), plus_stat_bonus(0, PLUS_COUNT_MAX))

    def test_a_full_count_pays_the_recovered_maximum(self) -> None:
        for plus_type, maxima in enumerate(PLUS_TYPE_MAXIMA):
            with self.subTest(plus_type=plus_type):
                self.assertEqual(maxima, plus_stat_bonus(plus_type, PLUS_COUNT_MAX))

    def test_the_curve_is_the_straight_line_the_client_computes(self) -> None:
        """Every minimum is 0 and every coefficient 1.0, so it interpolates."""
        self.assertEqual((0, 0, 0, 0), plus_stat_bonus(1, 0))
        self.assertEqual((50, 25, 10, 10), plus_stat_bonus(1, PLUS_COUNT_MAX // 2))
        self.assertEqual((100, 50, 20, 20), plus_stat_bonus(1, PLUS_COUNT_MAX))

    def test_a_count_past_the_ceiling_is_worth_nothing(self) -> None:
        """`CalcValueAtCount` logs "Detected plusCount cheating.." and returns 0.

        Handing out more than the ceiling does not cap the bonus, it removes
        it, so the ceiling is a hard contract rather than a clamp.
        """
        self.assertEqual((0, 0, 0, 0), plus_stat_bonus(1, PLUS_COUNT_MAX + 1))
        self.assertEqual((0, 0, 0, 0), plus_stat_bonus(1, PLUS_COUNT_DECLARED_MAX))

    def test_an_unknown_curve_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            plus_stat_bonus(len(PLUS_TYPE_MAXIMA), 1)



class PlusCountPreservationTest(unittest.TestCase):
    """A count survives a clear the client reports without one.

    `Character.LoadFromJson` reads `plusCount` and `Character.ToHashTable` never
    writes it back, so every clear arrives without it. Taking the client's row
    wholesale would drop the count on the first battle after it was granted.
    """

    HELD = {"id": 3, "jobLevels": [1.0], "skillBoost": 4, "luck": 20, "plusCount": 120}
    REPORTED = {"id": 3, "jobLevels": [1.0], "skillBoost": 4}

    def test_a_count_the_client_omits_is_kept(self) -> None:
        merged = _preserved_progress(self.HELD, self.REPORTED)
        self.assertEqual(120, merged["plusCount"])
        # Luck is kept for the same reason and must not have regressed.
        self.assertEqual(20, merged["luck"])

    def test_a_count_only_ever_grows(self) -> None:
        merged = _preserved_progress(self.HELD, {**self.REPORTED, "plusCount": 5})
        self.assertEqual(120, merged["plusCount"])

    def test_a_roster_without_a_count_gains_none(self) -> None:
        merged = _preserved_progress({"id": 3, "jobLevels": [1.0]}, self.REPORTED)
        self.assertNotIn("plusCount", merged)

if __name__ == "__main__":
    unittest.main()
