from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from liminal_gate.hunting_catalog import (
    HuntingCatalogError, build_bundled_hunting_policy, load_hunting_catalog,
)


def document(**overrides) -> dict:
    stage = {
        "family": "pudding", "chapter": 1001, "section": 1,
        "stamina": 3, "coins": 0, "entry_item_id": 0, "entry_item_count": 0,
        "unlock_chapter": 1, "unlock_section": 1, "max_coins": 0, "max_exp": 0,
        "max_items_total": 5, "item_maxima": {"2": 5},
    }
    stage.update(overrides.pop("stage", {}))
    base = {
        "schema_version": 1, "provenance": "user-supplied",
        "item_slots": 8, "max_stack": 99, "stages": [stage],
    }
    base.update(overrides)
    return base


class HuntingCatalogTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary_directory.name) / "hunting.json"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def load(self, doc: dict):
        self.path.write_text(json.dumps(doc), encoding="utf-8")
        return load_hunting_catalog(self.path)

    def test_loads_a_well_formed_operator_catalog(self) -> None:
        catalog = self.load(document())
        stage = catalog.by_identity()[(1001, 1)]
        self.assertEqual(("pudding", 3, {2: 5}), (stage.family, stage.stamina, stage.item_maxima))
        self.assertEqual({}, stage.entry_items())

    def test_an_entry_item_is_declared_as_a_pair(self) -> None:
        catalog = self.load(document(stage={"entry_item_id": 5, "entry_item_count": 1}))
        self.assertEqual({5: 1}, catalog.by_identity()[(1001, 1)].entry_items())
        for half in ({"entry_item_id": 5}, {"entry_item_count": 1}):
            with self.subTest(half=half), self.assertRaises(HuntingCatalogError):
                self.load(document(stage=half))

    def test_rejects_provenance_schema_and_shape_errors(self) -> None:
        for label, doc in (
            ("bundled provenance", document(provenance="bundled")),
            ("future schema", document(schema_version=2)),
            ("no stages", document(stages=[])),
            ("unknown field", document(stage={"extra": 1})),
            ("negative stamina", document(stage={"stamina": -1})),
            ("zero section", document(stage={"section": 0})),
            ("zero unlock chapter", document(stage={"unlock_chapter": 0})),
        ):
            with self.subTest(label), self.assertRaises(HuntingCatalogError):
                self.load(doc)

    def test_rejects_bounds_outside_the_declared_inventory(self) -> None:
        for label, doc in (
            ("item beyond slots", document(stage={"item_maxima": {"99": 1}})),
            ("count beyond stack", document(stage={"item_maxima": {"2": 100}})),
            ("entry item beyond slots", document(stage={"entry_item_id": 99, "entry_item_count": 1})),
            ("non-decimal item key", document(stage={"item_maxima": {"gold": 1}})),
        ):
            with self.subTest(label), self.assertRaises(HuntingCatalogError):
                self.load(doc)

    def test_rejects_duplicate_stage_identities(self) -> None:
        doc = document()
        doc["stages"] = [doc["stages"][0], dict(doc["stages"][0])]
        with self.assertRaises(HuntingCatalogError):
            self.load(doc)



class BundledHuntingPolicyTest(unittest.TestCase):
    """The bundled policy must match the recovered client structure exactly."""

    def setUp(self) -> None:
        self.catalog = build_bundled_hunting_policy()
        self.stages = self.catalog.by_identity()

    def test_declares_every_recovered_non_metal_stage(self) -> None:
        self.assertEqual(
            [(chapter, section) for chapter in (1001, 1002, 1003, 1004) for section in (1, 2, 3)],
            sorted(self.stages),
        )
        self.assertEqual((181, 999), (self.catalog.item_slots, self.catalog.max_stack))

    def test_carries_the_recovered_entry_costs(self) -> None:
        for identity, stamina in (
            ((1001, 1), 5), ((1001, 2), 8), ((1001, 3), 10),
            ((1002, 1), 5), ((1002, 2), 8), ((1002, 3), 10),
            ((1003, 1), 10), ((1003, 2), 15), ((1003, 3), 20),
            ((1004, 1), 5), ((1004, 2), 8), ((1004, 3), 10),
        ):
            with self.subTest(identity):
                self.assertEqual(stamina, self.stages[identity].stamina)
                # No bundled stage charges Coins or an entry item; the ticket
                # contract belongs to Metal, which is deliberately absent.
                self.assertEqual((0, {}), (self.stages[identity].coins, self.stages[identity].entry_items()))

    def test_carries_the_recovered_result_ceilings(self) -> None:
        pudding = self.stages[(1001, 1)]
        self.assertEqual((0, 0, 79), (pudding.max_coins, pudding.max_exp, pudding.max_items_total))
        self.assertEqual((21, 20, 19), (pudding.item_maxima[13], pudding.item_maxima[26], pudding.item_maxima[122]))
        # Tin's first zone alone caps items 22-25 at one boss slot.
        self.assertEqual((63, 1), (self.stages[(1002, 1)].max_items_total, self.stages[(1002, 1)].item_maxima[22]))
        self.assertEqual((93, 31), (self.stages[(1002, 2)].max_items_total, self.stages[(1002, 2)].item_maxima[22]))
        self.assertEqual(
            [1500, 5000, 11000],
            [self.stages[(1003, section)].max_coins for section in (1, 2, 3)],
        )
        for section in (1, 2, 3):
            creeps = self.stages[(1003, section)]
            self.assertEqual(({}, 0), (creeps.item_maxima, creeps.max_items_total))
            self.assertEqual(60, self.stages[(1004, section)].max_items_total)
        self.assertEqual(2, self.stages[(1004, 3)].item_maxima[2])

    def test_metal_zone_is_absent_because_its_results_cannot_be_bounded(self) -> None:
        self.assertEqual(set(), {1000, 3000} & {chapter for chapter, _ in self.stages})

    def test_tiers_unlock_only_after_their_policy_chapter(self) -> None:
        for section, first_allowed in ((1, 4), (2, 10), (3, 19)):
            stage = self.stages[(1001, section)]
            with self.subTest(section=section):
                self.assertFalse(stage.unlocked_at(0x01000000 | ((first_allowed - 1) << 6) | 1))
                self.assertTrue(stage.unlocked_at(0x01000000 | (first_allowed << 6) | 1))
                # The show-progress high bits must not make an earlier chapter
                # compare as later.
                self.assertFalse(stage.unlocked_at(0x03000000 | ((first_allowed - 1) << 6) | 1))

if __name__ == "__main__":
    unittest.main()
