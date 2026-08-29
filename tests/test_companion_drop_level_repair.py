"""A granted Companion's level and its experience are one statement.

`BuddyData.DropLevel` was recovered after this server had already minted a great
many Companions at a literal 1, and the recovery fixed the wrong half on its
own. Two things were left behind, both reported by the same tester on issue 77
in the same sentence: "Previously pulled Companions were restored, but now
display at level 1 and, for some reason, also have their skills at 0% trigger
chance?"

Those are not two complaints. `BuddyData.GetParamAtLevel` (ARM64 `0xD026C4`)
gives every stat as `min + (max - min) * ((level - 1) / (MaxLevel - 1)) **
Coeff`, so level 1 is the interpolation's origin and each stat sits at its
floor -- and all 51 OII Companions carry `BOOSTmin` 0 against a `BOOSTmax` of
100. A level 1 OII Companion has a skill that fires 0% of the time. The tester
saw one symptom and described it twice.

The grant was also writing a level and an experience that disagreed. The client
tolerates it -- `Buddy`'s JSON constructor (`0xD012F8`) reads `lv` and `exp` as
independent keys -- but this server's own strengthen route derives the level
back out of the experience, so a Companion granted at level 30 holding 0
experience fell to about level 6 on its first fusion. The client does not mint
that way: `Buddy.SetLevel` (`0xD02414`) sets the level and then takes the
experience from `GetParamAtLevel(level).EXP`.
"""

from __future__ import annotations

import unittest

from liminal_gate.bootstrap_server import (
    _companion_exp_at,
    _companion_level_at_exp,
    _migrate_companion_drop_level,
)
from liminal_gate.companion_master_data import (
    COMPANIONS_DROPPED_AT_LEVEL_30,
    companion_drop_level,
)
from liminal_gate.companion_progression_data import companion_granted_exp
from liminal_gate.companion_strengthen_catalog import (
    build_bundled_companion_strengthen_policy,
)

#: Spinetrich Kino OII. Its base O form, 282, drops at level 1.
OMICRON_TWO = 317
#: The experience `GetParamAtLevel(30).EXP` gives every one of the 51: they
#: share one curve exactly, `EXPmax` 20,000,000 at `EXPcoeff` 2.1.
EXP_AT_THIRTY = 1550568


def companion(bid: int, level: int, exp: int, iid: int = 1) -> dict[str, object]:
    return {"bid": bid, "lv": level, "date": 0.0, "iid": iid, "exp": exp, "flag": 0, "chrID": 0}


def account(*owned: dict[str, object]) -> dict[str, object]:
    return {"userdata": {"buddyInfo": {"list": list(owned), "record": list(owned)}}}


class GrantedExperienceTest(unittest.TestCase):
    def test_the_fifty_one_share_one_curve_and_one_value_at_thirty(self) -> None:
        """A single constant is the whole of it, which is why the level 30
        arrival can be checked against a literal rather than recomputed."""
        self.assertEqual(
            {EXP_AT_THIRTY},
            {companion_granted_exp(bid, 30) for bid in COMPANIONS_DROPPED_AT_LEVEL_30},
        )

    def test_level_one_is_the_origin_and_holds_nothing(self) -> None:
        """The pairing that was always right, and the reason a literal 0 went
        unnoticed for as long as every grant was a level 1 grant."""
        self.assertEqual(0, companion_granted_exp(OMICRON_TWO, 1))
        self.assertEqual(0, companion_granted_exp(282, companion_drop_level(282)))

    def test_a_companion_with_no_progression_row_arrives_at_the_origin(self) -> None:
        self.assertEqual(0, companion_granted_exp(999999, 30))

    def test_the_granted_level_survives_a_fusion(self) -> None:
        """The defect this pairing exists to prevent.

        `_companion_level_at_exp` is how the strengthen route restates a level
        after adding experience, so a grant whose experience does not support
        its level is demoted the first time the player fuses anything into it.
        """
        master = build_bundled_companion_strengthen_policy().masters[OMICRON_TWO]
        granted = companion_granted_exp(OMICRON_TWO, 30)
        self.assertEqual(30, _companion_level_at_exp(master, granted))
        # And the old literal is what it was demoted to instead.
        self.assertEqual(1, _companion_level_at_exp(master, 0))

    def test_the_strengthen_route_reads_the_same_curve_as_a_grant(self) -> None:
        """One implementation, so the two directions cannot drift apart."""
        master = build_bundled_companion_strengthen_policy().masters[OMICRON_TWO]
        for level in (1, 2, 30, 55, master.max_level):
            self.assertEqual(
                companion_granted_exp(OMICRON_TWO, level),
                _companion_exp_at(master, level),
            )


class CompanionDropLevelMigrationTest(unittest.TestCase):
    def test_a_copy_minted_below_its_drop_level_is_raised(self) -> None:
        state = account(companion(OMICRON_TWO, 1, 0))
        _migrate_companion_drop_level(state)
        owned = state["userdata"]["buddyInfo"]["list"]
        self.assertEqual((30, EXP_AT_THIRTY), (owned[0]["lv"], owned[0]["exp"]))

    def test_the_book_is_reprojected_from_the_repaired_list(self) -> None:
        """`record` is the best copy held per Companion and is derived from the
        owned list, so a repair that raises a level can change which copy it
        names. Leaving it behind is the defect `_migrate_companion_record`
        already exists for."""
        state = account(companion(OMICRON_TWO, 1, 0), companion(OMICRON_TWO, 1, 0, iid=2))
        _migrate_companion_drop_level(state)
        record = state["userdata"]["buddyInfo"]["record"]
        self.assertEqual([(OMICRON_TWO, 30)], [(row["bid"], row["lv"]) for row in record])

    def test_a_strengthened_copy_keeps_what_it_earned(self) -> None:
        """At or above the drop level is left exactly as it is: the repair
        raises a floor, it does not restate a level."""
        earned = companion(OMICRON_TWO, 44, 5_000_000)
        state = account(dict(earned))
        _migrate_companion_drop_level(state)
        self.assertEqual(earned, state["userdata"]["buddyInfo"]["list"][0])

    def test_an_ordinary_level_one_companion_is_untouched(self) -> None:
        """446 of the 497 drop at 1, and a level 1 copy of one of those is
        correct rather than damaged."""
        ordinary = companion(282, 1, 0)
        state = account(dict(ordinary))
        _migrate_companion_drop_level(state)
        self.assertEqual(ordinary, state["userdata"]["buddyInfo"]["list"][0])

    def test_one_malformed_row_stops_the_whole_repair(self) -> None:
        """The box is repaired whole or not at all.

        `_companion_info` cannot reproject a list holding a row it cannot read,
        so repairing the readable rows beside it would leave the book derived
        from a list that no longer matches. A save in that state is for the
        validation layer to name, which is `_migrate_companion_record`'s rule
        one field over.
        """
        state = account({"bid": "317", "lv": 1}, companion(OMICRON_TWO, 1, 0, iid=2))
        _migrate_companion_drop_level(state)
        owned = state["userdata"]["buddyInfo"]["list"]
        self.assertEqual({"bid": "317", "lv": 1}, owned[0])
        self.assertEqual(1, owned[1]["lv"], "the readable row is left for the repaired save")

    def test_a_save_with_no_box_is_left_alone(self) -> None:
        """The repair must not create a Companion box an account never had."""
        for state in ({}, {"userdata": {}}, {"userdata": {"buddyInfo": {}}}):
            _migrate_companion_drop_level(state)
            self.assertNotIn("list", state.get("userdata", {}).get("buddyInfo", {}))


if __name__ == "__main__":
    unittest.main()
