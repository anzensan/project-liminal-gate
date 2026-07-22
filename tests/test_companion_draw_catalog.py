from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from liminal_gate.companion_draw_catalog import CompanionDrawCatalogError, load_companion_draw_catalog


class CompanionDrawCatalogTest(unittest.TestCase):
    def test_loads_ordered_user_local_pool(self) -> None:
        document = {"schema_version": 1, "provenance": "user-supplied", "item_slots": 1, "ticket_item_id": 1, "energy_cost": 3, "max_owned": 10, "draws": [{"companion_id": 1, "weight": 1}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "draw.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            catalog = load_companion_draw_catalog(path)
        self.assertEqual((1, 3), (catalog.ticket_item_id, catalog.energy_cost))

    def test_loads_equivalent_toml_pool(self) -> None:
        document = """schema_version = 1
provenance = "user-supplied"
item_slots = 1
ticket_item_id = 1
energy_cost = 3
max_owned = 10

[[draws]]
companion_id = 1
weight = 1
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "draw.toml"
            path.write_text(document, encoding="utf-8")
            catalog = load_companion_draw_catalog(path)
        self.assertEqual(1, catalog.draws[0].companion_id)

    def test_rejects_unordered_pool(self) -> None:
        document = {"schema_version": 1, "provenance": "user-supplied", "item_slots": 1, "ticket_item_id": 1, "energy_cost": 1, "max_owned": 1, "draws": [{"companion_id": 2, "weight": 1}, {"companion_id": 1, "weight": 1}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "draw.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(CompanionDrawCatalogError):
                load_companion_draw_catalog(path)
