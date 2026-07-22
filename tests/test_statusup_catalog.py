from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from liminal_gate.statusup_catalog import StatusupCatalogError, load_statusup_catalog


class StatusupCatalogTest(unittest.TestCase):
    def test_accepts_a_strict_user_local_catalog(self) -> None:
        value = {
            "schema_version": 1, "provenance": "user-supplied", "item_slots": 3,
            "level_cap": 90, "skill_boost_cap": 1000,
            "items": [{"item_id": 1, "level": 1, "skill_boost": 0, "luck": 0, "species": None}],
            "characters": [{"character_id": 3, "species": 1, "luck_cap": 1000}],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            catalog = load_statusup_catalog(path)
        self.assertEqual((3, 90, 1000), (catalog.item_slots, catalog.level_cap, catalog.skill_boost_cap))
        self.assertEqual(1, catalog.items[1].level)

    def test_rejects_noncanonical_item_order(self) -> None:
        value = {
            "schema_version": 1, "provenance": "user-supplied", "item_slots": 3,
            "level_cap": 90, "skill_boost_cap": 1000,
            "items": [
                {"item_id": 2, "level": 1, "skill_boost": 0, "luck": 0, "species": None},
                {"item_id": 1, "level": 1, "skill_boost": 0, "luck": 0, "species": None},
            ],
            "characters": [{"character_id": 3, "species": 1, "luck_cap": 1000}],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(StatusupCatalogError, "ordered"):
                load_statusup_catalog(path)
