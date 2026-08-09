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

Two instances of one defect were enough: an unmodelled member is now read
rather than refused, because an allowlist of optional members only ever fixes
the member already reported, and the cost of being wrong is an account that can
never clear another stage. The required members are still required and every
modelled member is still typed; what moved is where an unfamiliar shape is
reported -- `save_validation` names it and keeps the save loadable, and a
refused write records the member names this server models.
"""

from __future__ import annotations

import unittest

from liminal_gate.bootstrap_parsers import _valid_generic_character_record
from liminal_gate.luck_data import LUCK_TENTHS_MAX
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

    def test_an_unmodelled_member_is_read_rather_than_ending_the_account(self) -> None:
        """The general form of this defect, after fixing two instances of it.

        An allowlist of optional members only ever fixes the member already
        reported. Twice a row carrying something this server did not model --
        a grant's `isNew`/`levelAdded`, then `plusCount` -- cost an account
        every clear it would ever attempt, and both times the member was
        decoration the settlement never reads. An extra key is no longer fatal
        to a route with no way to recover from one.
        """
        self.assertTrue(_valid_generic_character_record(row(nonsense=1)))
        self.assertTrue(_valid_generic_character_record(row(unknown=1, alsoUnknown=2)))

    def test_the_save_layer_reports_the_member_the_parser_now_admits(self) -> None:
        """Strictness moved rather than disappeared."""
        findings = _validate_roster("account", {"chrdata": [row(nonsense=1)]})
        self.assertEqual(["chrdata[0]"], [finding.field for finding in findings])
        self.assertIn("does not model", findings[0].message)

    def test_required_members_and_their_types_are_still_contract(self) -> None:
        """Admitting an extra member is not admitting a malformed one."""
        missing = row()
        del missing["flags"]
        self.assertFalse(_valid_generic_character_record(missing))
        self.assertFalse(_valid_generic_character_record(row(jobSlots=[0, 0])))
        self.assertFalse(_valid_generic_character_record(row(skillBoost=-1)))

    def test_the_grant_shape_stays_unreadable_so_its_migration_still_fires(self) -> None:
        """`_migrate_granted_character_rows` repairs only rows this refuses.

        Admitting unknown members must not quietly disable that repair: the
        grant shape is caught on its one-element `jobLevels` and empty
        `jobSlots`, not on the two response-only keys it also carries.
        """
        granted = {"id": 25, "isNew": True, "levelAdded": 3, "jobLevels": [90], "jobSlots": []}
        self.assertFalse(_valid_generic_character_record(granted))

    def test_luck_is_typed_but_no_longer_bounded_either(self) -> None:
        """The same disagreement as the plus count, one field over.

        The parser capped Luck at the client's own 1000 tenths while
        `save_validation` said nothing about the member at all, so a save this
        project called clean was again one its clear path would not read.
        """
        self.assertTrue(_valid_generic_character_record(row(luck=LUCK_TENTHS_MAX + 1)))
        self.assertFalse(_valid_generic_character_record(row(luck=-1)))
        self.assertFalse(_valid_generic_character_record(row(luck="800")))
        findings = _validate_roster("account", {"chrdata": [row(luck=LUCK_TENTHS_MAX + 1)]})
        self.assertEqual(["chrdata[0].luck"], [finding.field for finding in findings])


if __name__ == "__main__":
    unittest.main()
