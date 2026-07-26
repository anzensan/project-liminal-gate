"""The final client appends `&lastUpdate=1` to mutation POST bodies.

Its shared mutation POST helper adds the field, so strict ordered-field parsers
must tolerate one trailing occurrence. `continue` and `add_job` already did;
`change_uname`, `refill_stamina`, `use_statusup_item`, `rebirth`, and
`summon_skill_unlock` did not, and returned an unsupported-form error against
the real client's body.

These are regression cases for that tolerance. They assert three things per
route: the bare form still parses identically, the client's trailing-field form
now parses to the same value, and a body with any other extra field is still
rejected -- the tolerance must not widen into "ignore unknown fields".
"""
from __future__ import annotations

import unittest

from liminal_gate.bootstrap_server import (
    _parse_change_uname,
    _parse_continue,
    _parse_rebirth,
    _parse_refill_stamina,
    _parse_statusup_item,
    _parse_summon_skill_unlock,
)


# (parser, bare body, expected value)
FORMS = (
    (_parse_change_uname, b"name=Ianderse", "Ianderse"),
    (_parse_continue, b"cost=10", 10),
    (_parse_refill_stamina, b"cost=50", 50),
    (_parse_statusup_item, b"targetChrID=3&useItemID=41&useAmount=1", (3, 41, 1)),
    (_parse_rebirth, b"rebirthID=7&useJoker=False", (7, False)),
    (_parse_summon_skill_unlock, b"targetID=4", 4),
)


class TrailingLastUpdateTest(unittest.TestCase):
    def test_bare_form_still_parses(self) -> None:
        for parse, body, expected in FORMS:
            with self.subTest(parse.__name__):
                self.assertEqual(expected, parse(body))

    def test_client_trailing_last_update_is_tolerated(self) -> None:
        for parse, body, expected in FORMS:
            with self.subTest(parse.__name__):
                self.assertEqual(expected, parse(body + b"&lastUpdate=1"))

    def test_other_trailing_fields_are_still_rejected(self) -> None:
        for parse, body, _ in FORMS:
            with self.subTest(parse.__name__):
                self.assertIsNone(parse(body + b"&bogus=1"))
                self.assertIsNone(parse(body + b"&lastUpdate=1&bogus=1"))

    def test_only_one_trailing_occurrence_is_dropped(self) -> None:
        for parse, body, _ in FORMS:
            with self.subTest(parse.__name__):
                self.assertIsNone(parse(body + b"&lastUpdate=1&lastUpdate=1"))

    def test_leading_last_update_is_not_accepted(self) -> None:
        # The helper strips a trailing pair only, so positional fields survive.
        self.assertIsNone(_parse_refill_stamina(b"lastUpdate=1&cost=50"))
        self.assertIsNone(_parse_change_uname(b"lastUpdate=1&name=Ianderse"))

    def test_value_validation_still_applies_with_the_trailing_field(self) -> None:
        self.assertIsNone(_parse_summon_skill_unlock(b"targetID=99&lastUpdate=1"))
        self.assertIsNone(_parse_summon_skill_unlock(b"targetID=0&lastUpdate=1"))
        self.assertIsNone(_parse_statusup_item(b"targetChrID=0&useItemID=41&useAmount=1&lastUpdate=1"))
        self.assertIsNone(_parse_rebirth(b"rebirthID=7&useJoker=Maybe&lastUpdate=1"))
        self.assertIsNone(_parse_change_uname(b"name=&lastUpdate=1"))


if __name__ == "__main__":
    unittest.main()
