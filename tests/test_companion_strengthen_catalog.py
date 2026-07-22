from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from liminal_gate.companion_strengthen_catalog import CompanionStrengthenCatalogError, load_companion_strengthen_catalog


class CompanionStrengthenCatalogTest(unittest.TestCase):
    def test_loads_user_local_progression_and_bonus_policy(self) -> None:
        document = {"schema_version": 1, "provenance": "user-supplied", "same_companion_multiplier": 2, "byebye_companion_id": None, "byebye_multiplier_percent": 150, "bonus_weights": [{"percent": 0, "weight": 1}], "masters": [{"companion_id": 1, "base_exp": 1, "max_level": 2, "exp_max": 100, "exp_coeff": 1, "same_bonus_bias": 1}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "strengthen.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            catalog = load_companion_strengthen_catalog(path)
        self.assertEqual((2, ((0, 1),)), (catalog.same_companion_multiplier, catalog.bonus_weights))

    def test_rejects_unordered_bonus_policy(self) -> None:
        document = {"schema_version": 1, "provenance": "user-supplied", "same_companion_multiplier": 1, "byebye_companion_id": None, "byebye_multiplier_percent": 1, "bonus_weights": [{"percent": 10, "weight": 1}, {"percent": 0, "weight": 1}], "masters": [{"companion_id": 1, "base_exp": 0, "max_level": 1, "exp_max": 0, "exp_coeff": 1, "same_bonus_bias": 1}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "strengthen.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(CompanionStrengthenCatalogError):
                load_companion_strengthen_catalog(path)
