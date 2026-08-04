from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from liminal_gate.companion_evolution_catalog import build_bundled_companion_evolution_policy, CompanionEvolutionCatalogError, load_companion_evolution_catalog
from tests.support import write_json


class CompanionEvolutionCatalogTest(unittest.TestCase):
    def test_loads_user_local_evolution_recipe(self) -> None:
        document = {"schema_version": 1, "provenance": "user-supplied", "item_slots": 1, "recipes": [{"source_companion_id": 1, "destination_companion_id": 2, "max_level": 2, "coins": 3, "items": {"1": 1}, "duplicate_source_count": 0}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evolve.json"
            write_json(path, document)
            catalog = load_companion_evolution_catalog(path)
        self.assertEqual(2, catalog.recipes[1].destination_companion_id)

    def test_rejects_duplicate_recipe_sources(self) -> None:
        document = {"schema_version": 1, "provenance": "user-supplied", "item_slots": 1, "recipes": [{"source_companion_id": 1, "destination_companion_id": 2, "max_level": 1, "coins": 0, "items": {}, "duplicate_source_count": 0}, {"source_companion_id": 1, "destination_companion_id": 3, "max_level": 1, "coins": 0, "items": {}, "duplicate_source_count": 0}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evolve.json"
            write_json(path, document)
            with self.assertRaises(CompanionEvolutionCatalogError):
                load_companion_evolution_catalog(path)


class BundledCompanionEvolutionPolicyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = build_bundled_companion_evolution_policy()

    def test_declares_every_evolving_master(self) -> None:
        self.assertEqual(153, len(self.catalog.recipes))
        self.assertEqual(181, self.catalog.item_slots)
        for source, recipe in self.catalog.recipes.items():
            with self.subTest(source=source):
                self.assertGreater(recipe.destination_companion_id, 0)
                self.assertGreater(recipe.coins, 0)
                for item_id, count in recipe.items.items():
                    self.assertTrue(1 <= item_id <= self.catalog.item_slots)
                    self.assertGreater(count, 0)

    def test_only_the_metal_minions_consume_duplicates_instead_of_items(self) -> None:
        duplicates = {source: recipe.duplicate_source_count
                      for source, recipe in self.catalog.recipes.items() if recipe.duplicate_source_count}
        self.assertEqual({128: 10, 129: 3}, duplicates)
        # Those two carry no item codes at all, which is why the counts cannot
        # be inferred from the item slots.
        for source in (128, 129):
            self.assertEqual({}, self.catalog.recipes[source].items)
        for source, recipe in self.catalog.recipes.items():
            if source not in (128, 129):
                with self.subTest(source=source):
                    self.assertTrue(recipe.items, "an ordinary recipe must cost items")

    def test_carries_the_recovered_costs(self) -> None:
        first = self.catalog.recipes[1]
        self.assertEqual((2, 30, 10000), (first.destination_companion_id, first.max_level, first.coins))
        self.assertEqual({17: 15, 20: 5, 24: 5}, first.items)
        self.assertEqual(1106, self.catalog.recipes[128].coins)
