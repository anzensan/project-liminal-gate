from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from liminal_gate.companion_strengthen_catalog import build_bundled_companion_strengthen_policy, CompanionStrengthenCatalogError, load_companion_strengthen_catalog


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


class BundledCompanionStrengthenPolicyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = build_bundled_companion_strengthen_policy()

    def test_declares_every_recovered_master(self) -> None:
        self.assertEqual(497, len(self.catalog.masters))
        self.assertEqual(list(range(1, 498)), sorted(self.catalog.masters))
        for companion_id, master in self.catalog.masters.items():
            with self.subTest(companion_id=companion_id):
                self.assertGreater(master.base_exp, 0)
                self.assertTrue(1 <= master.max_level <= 99)
                self.assertGreater(master.exp_coeff, 0)
                self.assertGreater(master.same_bonus_bias, 0)

    def test_same_bonus_bias_matches_the_recovered_split(self) -> None:
        biases = [master.same_bonus_bias for master in self.catalog.masters.values()]
        self.assertEqual(446, biases.count(1))
        # The 51 level-30 Omicron-II rows; with the 2x same-Companion rule a
        # matching material is worth 14x.
        self.assertEqual(51, biases.count(7))
        self.assertEqual({1, 7}, set(biases))

    def test_carries_the_recovered_multipliers(self) -> None:
        self.assertEqual(2, self.catalog.same_companion_multiplier)
        self.assertEqual(245, self.catalog.byebye_companion_id)
        self.assertEqual(150, self.catalog.byebye_multiplier_percent)

    def test_bonus_weights_are_local_policy_making_no_bonus_the_common_case(self) -> None:
        # No production odds survive, so these keep all three documented
        # outcomes reachable without asserting the retired service's rates.
        self.assertEqual(((0, 85), (25, 8), (50, 5), (100, 2)), self.catalog.bonus_weights)
        weights = dict(self.catalog.bonus_weights)
        self.assertGreater(weights[0], sum(w for p, w in self.catalog.bonus_weights if p))
