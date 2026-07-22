from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from liminal_gate.companion_catalog import CompanionCatalogError, load_companion_catalog


class CompanionCatalogTest(unittest.TestCase):
    def test_loads_ordered_user_local_masters(self) -> None:
        document = {"schema_version": 1, "provenance": "user-supplied", "coin_cap": 999, "masters": [{"companion_id": 1, "base_coins": 2}, {"companion_id": 2, "base_coins": 3}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "companions.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            catalog = load_companion_catalog(path)
        self.assertEqual((999, 3), (catalog.coin_cap, catalog.masters[2].base_coins))

    def test_rejects_unordered_or_duplicate_masters(self) -> None:
        document = {"schema_version": 1, "provenance": "user-supplied", "coin_cap": 0, "masters": [{"companion_id": 2, "base_coins": 0}, {"companion_id": 1, "base_coins": 0}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "companions.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(CompanionCatalogError):
                load_companion_catalog(path)
