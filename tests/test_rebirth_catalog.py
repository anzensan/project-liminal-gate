from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from liminal_gate.rebirth_catalog import build_bundled_rebirth_policy, RebirthCatalogError, load_rebirth_catalog


class RebirthCatalogTest(unittest.TestCase):
    def test_validates_user_local_recipe_rows(self) -> None:
        document = {"schema_version": 1, "provenance": "user-supplied", "item_slots": 3, "joker_character_id": 9, "recipes": [{"recipe_id": 1, "source_character_id": 2, "destination_character_id": 3, "coins": 10, "items": {"1": 2}, "materials": [{"character_id": 7, "level": 50}, {"character_id": 8, "level": 60}]}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rebirth.json"; path.write_text(json.dumps(document), encoding="utf-8")
            catalog = load_rebirth_catalog(path)
            self.assertEqual((2, 3, {1: 2}), (catalog.recipes[1].source_character_id, catalog.recipes[1].destination_character_id, catalog.recipes[1].items))
            # A recipe may require no Companions: the client's own master rows
            # carry three such recipes with empty requirement slots.
            document["recipes"][0]["materials"] = []
            path.write_text(json.dumps(document), encoding="utf-8")
            self.assertEqual((), load_rebirth_catalog(path).recipes[1].materials)
            document["recipes"][0]["materials"] = [{"character_id": n, "level": 50} for n in (7, 8, 9)]
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(RebirthCatalogError, "at most two"):
                load_rebirth_catalog(path)


class BundledRebirthPolicyTest(unittest.TestCase):
    """The bundled policy must match the recovered ChrDatabase recipe rows."""

    def setUp(self) -> None:
        self.catalog = build_bundled_rebirth_policy()

    def test_declares_every_recovered_recipe(self) -> None:
        self.assertEqual(65, len(self.catalog.recipes))
        self.assertEqual(list(range(1, 66)), sorted(self.catalog.recipes))
        self.assertEqual((181, 1018), (self.catalog.item_slots, self.catalog.joker_character_id))

    def test_requirements_stay_inside_the_client_shapes(self) -> None:
        for recipe_id, recipe in self.catalog.recipes.items():
            with self.subTest(recipe_id=recipe_id):
                self.assertGreaterEqual(recipe.coins, 0)
                self.assertLessEqual(len(recipe.materials), 2)
                for item_id, count in recipe.items.items():
                    self.assertTrue(1 <= item_id <= self.catalog.item_slots)
                    self.assertGreater(count, 0)
                for character_id, level in recipe.materials:
                    # An empty master slot must be dropped, never kept as
                    # character 0 at level 0.
                    self.assertGreater(character_id, 0)
                    self.assertGreater(level, 0)

    def test_carries_the_recovered_costs_including_the_free_recipes(self) -> None:
        first = self.catalog.recipes[1]
        self.assertEqual((2, 623, 30000), (first.source_character_id, first.destination_character_id, first.coins))
        self.assertEqual({10: 15, 93: 5, 96: 1}, first.items)
        self.assertEqual(((237, 50), (145, 50)), first.materials)
        # Three recipes cost nothing at all and require no Companions.
        self.assertEqual([33, 34, 50], sorted(i for i, r in self.catalog.recipes.items() if not r.materials))
        for recipe_id in (33, 34, 50):
            self.assertEqual((0, {}), (self.catalog.recipes[recipe_id].coins, self.catalog.recipes[recipe_id].items))
