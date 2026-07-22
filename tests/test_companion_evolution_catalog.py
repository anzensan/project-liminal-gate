from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from liminal_gate.companion_evolution_catalog import CompanionEvolutionCatalogError, load_companion_evolution_catalog


class CompanionEvolutionCatalogTest(unittest.TestCase):
    def test_loads_user_local_evolution_recipe(self) -> None:
        document = {"schema_version": 1, "provenance": "user-supplied", "item_slots": 1, "recipes": [{"source_companion_id": 1, "destination_companion_id": 2, "max_level": 2, "coins": 3, "items": {"1": 1}, "duplicate_source_count": 0}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evolve.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            catalog = load_companion_evolution_catalog(path)
        self.assertEqual(2, catalog.recipes[1].destination_companion_id)

    def test_rejects_duplicate_recipe_sources(self) -> None:
        document = {"schema_version": 1, "provenance": "user-supplied", "item_slots": 1, "recipes": [{"source_companion_id": 1, "destination_companion_id": 2, "max_level": 1, "coins": 0, "items": {}, "duplicate_source_count": 0}, {"source_companion_id": 1, "destination_companion_id": 3, "max_level": 1, "coins": 0, "items": {}, "duplicate_source_count": 0}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evolve.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(CompanionEvolutionCatalogError):
                load_companion_evolution_catalog(path)
