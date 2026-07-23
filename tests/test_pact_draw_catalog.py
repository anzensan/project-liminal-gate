from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from liminal_gate.pact_draw_catalog import PactDrawCatalogError, build_bundled_pact_policy, load_pact_draw_catalog


class PactDrawCatalogTest(unittest.TestCase):
    def test_loads_toml_policy(self) -> None:
        document = '''schema_version = 1
provenance = "user-supplied"
coin_cost = 10
new_level = 1
max_level = 9
max_skill_boost = 100

[[draws]]
character_id = 9001
weight = 1
duplicate_level_added = 2
duplicate_skill_boost = 5
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pact.toml"; path.write_text(document, encoding="utf-8")
            catalog = load_pact_draw_catalog(path)
        self.assertEqual((10, 9001), (catalog.coin_cost, catalog.draws[0].character_id))

    def test_rejects_unsorted_characters(self) -> None:
        document = '{"schema_version":1,"provenance":"user-supplied","coin_cost":1,"new_level":1,"max_level":2,"max_skill_boost":1,"draws":[{"character_id":2,"weight":1,"duplicate_level_added":1,"duplicate_skill_boost":1},{"character_id":1,"weight":1,"duplicate_level_added":1,"duplicate_skill_boost":1}]}'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pact.json"; path.write_text(document, encoding="utf-8")
            with self.assertRaises(PactDrawCatalogError):
                load_pact_draw_catalog(path)

    def test_bundled_policy_exposes_fellowship_and_truth(self) -> None:
        policy = build_bundled_pact_policy()
        self.assertEqual(("coins", 3000), policy.cost_for_kind(0))
        self.assertEqual(("energy", 5), policy.cost_for_kind(1))
        self.assertEqual(103, len(policy.draws_for_kind(0)))
        self.assertEqual(122, len(policy.draws_for_kind(1)))
