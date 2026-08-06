"""An operator's own chest pools, for the stages the record does not document.

The bundled table covers thirty story stages and every other stage yields six
empty slots, because the contents were server-side and no capture survives.
This is the sanctioned way past that: opt-in, operator-supplied, and named in
the server's own startup output, so the bundled table stays exactly as sourced.
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from liminal_gate.luck_data import CHEST_TIERS
from liminal_gate.luck_pool_catalog import (
    LuckPoolCatalogError,
    load_luck_pool_catalog,
)
from liminal_gate.luck_pool_data import LUCK_CHEST_POOLS, pool_for
from liminal_gate.luck_pool_interpolation import build_luck_pools, donor_chapters
from liminal_gate.luck_runtime import roll_luck_result

#: A stage the community record does document, so an override is observable.
DOCUMENTED = (1, 1)
#: One it does not, which is most of the game.
UNDOCUMENTED = (10, 2)


def catalog_document(stages: list[dict]) -> dict:
    return {"schema_version": 1, "provenance": "user-supplied", "stages": stages}


class LuckPoolCatalogLoaderTest(unittest.TestCase):
    def load(self, document: object, suffix: str = ".json"):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / f"pools{suffix}"
            path.write_text(json.dumps(document), encoding="utf-8")
            return load_luck_pool_catalog(path)

    def test_a_minimal_catalog_loads(self) -> None:
        catalog = self.load(catalog_document([
            {"chapter": 10, "section": 2, "tiers": {"A": ["C100", "I5"]}},
        ]))
        self.assertEqual(1, catalog.stage_count())
        self.assertEqual(("C100", "I5"), catalog.pool_for(10, 2, "A"))

    def test_every_client_reward_form_is_accepted(self) -> None:
        catalog = self.load(catalog_document([
            {"chapter": 10, "section": 2, "tiers": {"A": ["C100", "I5", "O128", "M199"]}},
        ]))
        self.assertEqual(("C100", "I5", "O128", "M199"), catalog.pool_for(10, 2, "A"))

    def test_a_stage_it_does_not_name_keeps_the_recorded_pool(self) -> None:
        catalog = self.load(catalog_document([
            {"chapter": 10, "section": 2, "tiers": {"A": ["C100"]}},
        ]))
        self.assertEqual(pool_for(*DOCUMENTED, "A"), catalog.pool_for(*DOCUMENTED, "A"))
        self.assertTrue(catalog.pool_for(*DOCUMENTED, "A"))

    def test_a_stage_it_names_replaces_the_recorded_pool_outright(self) -> None:
        """Half-overriding would leave a pool sourced in part and invented in
        part, with nothing recording which half was which."""
        catalog = self.load(catalog_document([
            {"chapter": DOCUMENTED[0], "section": DOCUMENTED[1], "tiers": {"A": ["C999"]}},
        ]))
        self.assertEqual(("C999",), catalog.pool_for(*DOCUMENTED, "A"))
        # The record gives this stage a B pool; the override does not, and that
        # is the operator saying B pays nothing rather than falling back.
        self.assertTrue(pool_for(*DOCUMENTED, "B"))
        self.assertEqual((), catalog.pool_for(*DOCUMENTED, "B"))

    def test_it_refuses_a_wrong_schema_or_provenance(self) -> None:
        for document in (
            {"schema_version": 2, "provenance": "user-supplied", "stages": []},
            {"schema_version": 1, "provenance": "bundled", "stages": []},
            {"schema_version": 1, "stages": []},
        ):
            with self.subTest(document=document), self.assertRaises(LuckPoolCatalogError) as raised:
                self.load(document)
            self.assertIn("invalid schema or provenance", str(raised.exception))

    def test_it_refuses_an_empty_catalog(self) -> None:
        with self.assertRaises(LuckPoolCatalogError) as raised:
            self.load(catalog_document([]))
        self.assertIn("stages must be a nonempty array", str(raised.exception))

    def test_it_refuses_an_unknown_tier(self) -> None:
        with self.assertRaises(LuckPoolCatalogError) as raised:
            self.load(catalog_document([
                {"chapter": 10, "section": 2, "tiers": {"S": ["C100"]}},
            ]))
        self.assertIn("unknown chest tier 'S'", str(raised.exception))

    def test_it_refuses_a_reward_that_is_not_a_client_wire_form(self) -> None:
        for reward in ("X100", "100", "C", "", "Cx"):
            with self.subTest(reward=reward), self.assertRaises(LuckPoolCatalogError):
                self.load(catalog_document([
                    {"chapter": 10, "section": 2, "tiers": {"A": [reward]}},
                ]))

    def test_it_refuses_a_zero_amount_or_identifier(self) -> None:
        with self.assertRaises(LuckPoolCatalogError) as raised:
            self.load(catalog_document([
                {"chapter": 10, "section": 2, "tiers": {"A": ["I0"]}},
            ]))
        self.assertIn("must carry a positive", str(raised.exception))

    def test_it_refuses_a_repeated_reward(self) -> None:
        """Selection within a tier is equal-weight, so a repeat is a weight by
        another name -- the thing the record does not carry."""
        with self.assertRaises(LuckPoolCatalogError) as raised:
            self.load(catalog_document([
                {"chapter": 10, "section": 2, "tiers": {"A": ["C100", "C100"]}},
            ]))
        self.assertIn("repeats a reward", str(raised.exception))

    def test_it_refuses_a_duplicate_stage(self) -> None:
        with self.assertRaises(LuckPoolCatalogError) as raised:
            self.load(catalog_document([
                {"chapter": 10, "section": 2, "tiers": {"A": ["C100"]}},
                {"chapter": 10, "section": 2, "tiers": {"B": ["C200"]}},
            ]))
        self.assertIn("declared more than once", str(raised.exception))

    def test_it_refuses_a_missing_or_extra_stage_key(self) -> None:
        for stage in (
            {"chapter": 10, "tiers": {"A": ["C100"]}},
            {"chapter": 10, "section": 2, "tiers": {"A": ["C100"]}, "note": "x"},
        ):
            with self.subTest(stage=stage), self.assertRaises(LuckPoolCatalogError) as raised:
                self.load(catalog_document([stage]))
            self.assertIn("requires chapter, section, and tiers", str(raised.exception))

    def test_it_refuses_unreadable_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pools.json"
            path.write_text("{not json", encoding="utf-8")
            with self.assertRaises(LuckPoolCatalogError) as raised:
                load_luck_pool_catalog(path)
        self.assertIn("could not read", str(raised.exception))


class LuckPoolCatalogRollTest(unittest.TestCase):
    """The roll, with and without an operator catalog."""

    def catalog(self, stages: list[dict]):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pools.json"
            path.write_text(json.dumps(catalog_document(stages)), encoding="utf-8")
            return load_luck_pool_catalog(path)

    def test_an_undocumented_stage_still_rolls_nothing_without_a_catalog(self) -> None:
        self.assertEqual(
            [""] * len(CHEST_TIERS),
            roll_luck_result(*UNDOCUMENTED, 1000, "req", "body"),
        )
        self.assertNotIn(UNDOCUMENTED, LUCK_CHEST_POOLS)

    def test_a_catalog_gives_an_undocumented_stage_a_chest(self) -> None:
        catalog = self.catalog([{
            "chapter": UNDOCUMENTED[0], "section": UNDOCUMENTED[1],
            "tiers": {tier.name: ["C100"] for tier in CHEST_TIERS},
        }])
        slots = roll_luck_result(*UNDOCUMENTED, 1000, "req", "body", catalog=catalog)
        self.assertTrue(any(slots))

    def test_a_catalog_leaves_the_stages_it_does_not_name_alone(self) -> None:
        """The point of the whole design: the sourced table stays sourced."""
        catalog = self.catalog([{
            "chapter": UNDOCUMENTED[0], "section": UNDOCUMENTED[1],
            "tiers": {"A": ["C100"]},
        }])
        self.assertEqual(
            roll_luck_result(*DOCUMENTED, 500, "req", "body"),
            roll_luck_result(*DOCUMENTED, 500, "req", "body", catalog=catalog),
        )

    def test_the_roll_stays_replay_stable_with_a_catalog(self) -> None:
        catalog = self.catalog([{
            "chapter": UNDOCUMENTED[0], "section": UNDOCUMENTED[1],
            "tiers": {"A": ["C100", "I5", "O128"]},
        }])
        first = roll_luck_result(*UNDOCUMENTED, 1000, "req", "body", catalog=catalog)
        again = roll_luck_result(*UNDOCUMENTED, 1000, "req", "body", catalog=catalog)
        self.assertEqual(first, again)


if __name__ == "__main__":
    unittest.main()


class InterpolatedLuckPoolTest(unittest.TestCase):
    """Donated pools for the stages the record does not document.

    On by default, because the record covers thirty story stages and the rest of
    the game would otherwise never show a chest. What it chooses is placement,
    not contents: every reward it can produce is one the record documents for a
    chapter adjacent to the one being played.
    """

    def setUp(self) -> None:
        self.pools = build_luck_pools()

    def test_a_documented_stage_is_never_touched(self) -> None:
        """The thirty sourced stages stay exactly as sourced."""
        for (chapter, section), tiers in LUCK_CHEST_POOLS.items():
            for tier, pool in tiers.items():
                with self.subTest(stage=(chapter, section), tier=tier):
                    self.assertEqual(pool, self.pools.pool_for(chapter, section, tier))

    def test_a_tier_a_documented_stage_leaves_empty_stays_empty(self) -> None:
        """The record naming a stage and omitting a tier is the record
        speaking, not a gap to fill."""
        stage = next(k for k, tiers in LUCK_CHEST_POOLS.items() if "D" not in tiers)
        self.assertEqual((), self.pools.pool_for(*stage, "D"))

    def test_an_undocumented_stage_gains_a_pool(self) -> None:
        self.assertNotIn(UNDOCUMENTED, LUCK_CHEST_POOLS)
        self.assertEqual((), pool_for(*UNDOCUMENTED, "A"))
        self.assertTrue(self.pools.pool_for(*UNDOCUMENTED, "A"))

    def test_it_donates_from_the_two_documented_chapters_it_brackets(self) -> None:
        self.assertEqual((9, 13), donor_chapters(10))
        self.assertEqual((1, 4), donor_chapters(2))
        # Past the last documented chapter there is only one side to take.
        self.assertEqual((36,), donor_chapters(42))
        self.assertEqual((1,), donor_chapters(1))

    def test_every_donated_reward_appears_in_the_record(self) -> None:
        """The whole claim: placement is chosen, contents are not."""
        recorded = {
            reward
            for tiers in LUCK_CHEST_POOLS.values()
            for pool in tiers.values()
            for reward in pool
        }
        for chapter in range(1, 43):
            for tier in CHEST_TIERS:
                for reward in self.pools.pool_for(chapter, 1, tier.name):
                    with self.subTest(chapter=chapter, tier=tier.name, reward=reward):
                        self.assertIn(reward, recorded)

    def test_a_donated_pool_never_repeats_a_reward(self) -> None:
        """A repeat inside an equal-weight tier is a weight by another name."""
        for chapter in range(1, 43):
            for tier in CHEST_TIERS:
                pool = self.pools.pool_for(chapter, 1, tier.name)
                with self.subTest(chapter=chapter, tier=tier.name):
                    self.assertEqual(len(set(pool)), len(pool))

    def test_disabling_it_restores_the_record_only_behaviour(self) -> None:
        self.assertIsNone(build_luck_pools(interpolate=False))
        self.assertEqual([""] * len(CHEST_TIERS),
                         roll_luck_result(*UNDOCUMENTED, 1000, "r", "b"))

    def test_an_operator_catalog_still_wins_over_a_donated_pool(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pools.json"
            path.write_text(json.dumps(catalog_document([
                {"chapter": UNDOCUMENTED[0], "section": UNDOCUMENTED[1],
                 "tiers": {"A": ["C777"]}},
            ])), encoding="utf-8")
            layered = build_luck_pools(load_luck_pool_catalog(path))
        self.assertEqual(("C777",), layered.pool_for(*UNDOCUMENTED, "A"))
        # And a stage the operator did not name still gets its donation.
        self.assertTrue(layered.pool_for(11, 1, "A"))

    def test_the_roll_stays_replay_stable(self) -> None:
        first = roll_luck_result(*UNDOCUMENTED, 1000, "r", "b", catalog=self.pools)
        self.assertEqual(first, roll_luck_result(*UNDOCUMENTED, 1000, "r", "b", catalog=self.pools))
