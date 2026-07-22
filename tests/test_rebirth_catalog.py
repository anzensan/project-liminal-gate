from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from liminal_gate.rebirth_catalog import RebirthCatalogError, load_rebirth_catalog


class RebirthCatalogTest(unittest.TestCase):
    def test_validates_user_local_recipe_rows(self) -> None:
        document = {"schema_version": 1, "provenance": "user-supplied", "item_slots": 3, "joker_character_id": 9, "recipes": [{"recipe_id": 1, "source_character_id": 2, "destination_character_id": 3, "coins": 10, "items": {"1": 2}, "materials": [{"character_id": 7, "level": 50}, {"character_id": 8, "level": 60}]}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rebirth.json"; path.write_text(json.dumps(document), encoding="utf-8")
            catalog = load_rebirth_catalog(path)
            self.assertEqual((2, 3, {1: 2}), (catalog.recipes[1].source_character_id, catalog.recipes[1].destination_character_id, catalog.recipes[1].items))
            document["recipes"][0]["materials"] = []
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(RebirthCatalogError, "exactly two"):
                load_rebirth_catalog(path)
