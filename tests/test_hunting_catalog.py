from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from liminal_gate.hunting_catalog import HuntingCatalogError, load_hunting_catalog


def document(**overrides) -> dict:
    stage = {
        "family": "pudding", "chapter": 1001, "section": 1,
        "stamina": 3, "coins": 0, "entry_item_id": 0, "entry_item_count": 0,
        "unlock_progress_code": 0, "max_coins": 0, "max_exp": 0,
        "item_maxima": {"2": 5},
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


if __name__ == "__main__":
    unittest.main()
