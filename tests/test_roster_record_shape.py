"""What a roster row may carry, and why refusing an extra member is costly.

`_valid_generic_character_record` gates the clear parser, so a row it will not
read does not fail one request: it refuses *every* clear the account attempts
afterwards, and reaches the player as a Network Error with no way out.
`_migrate_granted_character_rows` exists because a grant shape did exactly that
once. `plusCount` did it again -- accepted by `save_validation`, merged by
`_preserved_progress`, reported by the recode result, and refused here -- so a
row this project's own save layer called valid was one its clear path would not
take. Recode is where a count first appears for most accounts, which is why the
reports arrive at the chapter that unlocks it.
"""

from __future__ import annotations

import unittest

from liminal_gate.bootstrap_parsers import _valid_generic_character_record
from liminal_gate.plus_type_data import PLUS_COUNT_DECLARED_MAX, PLUS_COUNT_MAX
from liminal_gate.save_validation import _validate_roster


def row(**extra: object) -> dict[str, object]:
    return {
        "id": 25, "buddy": 0, "date": 0.0, "jobSlots": [0, 0, 0],
        "jobLevels": [90, 0, 0], "jobID": 0, "flags": 0, "skillBoost": 950,
    } | extra


class RosterRecordShapeTest(unittest.TestCase):
    def test_the_plain_and_luck_shapes_still_read(self) -> None:
        self.assertTrue(_valid_generic_character_record(row()))
        self.assertTrue(_valid_generic_character_record(row(luck=800)))

    def test_a_recoded_row_carrying_a_plus_count_reads(self) -> None:
        """The regression. Refusing this refused every later clear."""
        self.assertTrue(_valid_generic_character_record(row(plusCount=1)))
        self.assertTrue(_valid_generic_character_record(row(luck=800, plusCount=12)))

    def test_the_two_validators_agree_about_a_plus_count(self) -> None:
        """The contradiction that made this reachable.

        A row `save_validation` accepts must be one the clear path can read.
        These are the only two places that decide what a roster row is, and
        they disagreed: one bounded `plusCount` to the client's own ceiling
        while the other refused the member outright.
        """
        findings = _validate_roster("account", {"chrdata": [row(plusCount=7)]})
        self.assertEqual(
            [], [finding for finding in findings if "plusCount" in finding.field],
            "save_validation accepts a plus count the clear parser must also read",
        )
        self.assertTrue(_valid_generic_character_record(row(plusCount=7)))

    def test_a_count_the_client_reads_as_tampering_is_read_anyway(self) -> None:
        """Typed, deliberately not bounded, and the reasoning is the whole point.

        Past `ActualMaxCount` the client reads a count as tampering and awards
        no bonus at all, so such a row *is* wrong -- but it is wrong in a way
        the client already punishes, and refusing it here costs far more than
        it saves. A refused parse is a refused clear, which leaves the battle
        active and refuses every later stage too, for a value the player can
        neither see nor repair. That is the failure this module exists to
        document, and bounding the member here would have reintroduced it.

        The client's two constants make the case concrete: it compares against
        `ActualMaxCount` (300) but also declares `MaxCount` (1000), so a tool
        honouring the declared one produces a count in between -- and that
        account would have been unable to clear anything, anywhere, forever.
        """
        self.assertTrue(_valid_generic_character_record(row(plusCount=PLUS_COUNT_MAX)))
        self.assertTrue(_valid_generic_character_record(row(plusCount=PLUS_COUNT_MAX + 1)))
        self.assertTrue(_valid_generic_character_record(row(plusCount=PLUS_COUNT_DECLARED_MAX)))
        # Type and sign are still contract, because neither is recoverable.
        self.assertFalse(_valid_generic_character_record(row(plusCount=-1)))
        self.assertFalse(_valid_generic_character_record(row(plusCount="1")))

    def test_the_save_layer_is_where_an_impossible_count_is_reported(self) -> None:
        """Refusing and reporting are different severities, and this is the
        one that keeps the account playable while still naming the problem."""
        findings = _validate_roster("account", {"chrdata": [row(plusCount=PLUS_COUNT_MAX + 1)]})
        self.assertEqual(
            ["chrdata[0].plusCount"], [finding.field for finding in findings],
        )

    def test_the_shape_is_otherwise_exactly_as_strict(self) -> None:
        """Optional members are an allowlist, not an opening."""
        self.assertFalse(_valid_generic_character_record(row(nonsense=1)))
        self.assertFalse(_valid_generic_character_record(row(isNew=True, levelAdded=1)))
        missing = row()
        del missing["flags"]
        self.assertFalse(_valid_generic_character_record(missing))


if __name__ == "__main__":
    unittest.main()
