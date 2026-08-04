from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from liminal_gate.pact_draw_catalog import PactDrawCatalogError, build_bundled_pact_policy, load_character_rarity, load_pact_draw_catalog
from tests.support import write_json


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
        self.assertEqual((1000, 50), (policy.max_luck, policy.fate_duplicate_luck))
        self.assertEqual(103, len(policy.draws_for_kind(0)))
        self.assertEqual(122, len(policy.draws_for_kind(1)))

    def test_without_a_catalog_every_entry_keeps_the_flat_default(self) -> None:
        """No master data in hand means no class claim, so nothing is weighted."""
        policy = build_bundled_pact_policy()
        self.assertEqual({1}, {draw.weight for draw in policy.draws_for_kind(1)})
        self.assertEqual({(1, 10)}, {(draw.duplicate_level_added, draw.duplicate_skill_boost) for draw in policy.draws_for_kind(1)})

    def test_rarity_bands_set_duplicate_gains_for_both_pools(self) -> None:
        rarity = {1: 8, 2: 7, 3: 6, 4: 5, 5: 4, 6: 3, 7: 2}
        policy = build_bundled_pact_policy(rarity)
        gains = {
            draw.character_id: (draw.duplicate_level_added, draw.duplicate_skill_boost)
            for draw in policy.draws_for_kind(0) + policy.draws_for_kind(1)
        }
        self.assertEqual((6, 120), gains[1])
        self.assertEqual((5, 100), gains[2])
        self.assertEqual((5, 100), gains[3])
        for lower in (4, 5, 6, 7):
            self.assertEqual((1, 50), gains[lower])

    def test_truth_weights_reproduce_the_documented_class_shares(self) -> None:
        from liminal_gate.pact_draw_catalog import _TRUTH_IDS

        # Two members per class keeps the even within-class split exact.
        by_class = {8: "z", 7: "ss", 6: "s", 5: "a", 4: "b"}
        rarity = {character_id: 8 for character_id in _TRUTH_IDS}
        for offset, value in enumerate((8, 8, 7, 7, 6, 6, 5, 5, 4, 4)):
            rarity[_TRUTH_IDS[offset]] = value
        for character_id in _TRUTH_IDS[10:]:
            rarity[character_id] = 4
        policy = build_bundled_pact_policy(rarity)
        total = sum(draw.weight for draw in policy.draws_for_kind(1))
        share: dict[str, int] = {}
        for draw in policy.draws_for_kind(1):
            share[by_class[rarity[draw.character_id]]] = share.get(by_class[rarity[draw.character_id]], 0) + draw.weight
        self.assertAlmostEqual(0.04, share["z"] / total, places=4)
        self.assertAlmostEqual(0.10, share["ss"] / total, places=4)
        self.assertAlmostEqual(0.15, share["s"] / total, places=4)
        self.assertAlmostEqual(0.71, (share["a"] + share["b"]) / total, places=4)

    def test_fellowship_selection_stays_uniform(self) -> None:
        """No sourced Fellowship rate table exists, so none is invented."""
        policy = build_bundled_pact_policy({1: 8, 2: 4})
        self.assertEqual({1}, {draw.weight for draw in policy.draws_for_kind(0)})

    def test_character_rarity_rejects_a_foreign_catalog(self) -> None:
        for document in (
            {"schema_version": 2, "provenance": "user-derived", "characters": [{"character_id": 1, "rarity": 8}]},
            {"schema_version": 1, "provenance": "bundled", "characters": [{"character_id": 1, "rarity": 8}]},
            {"schema_version": 1, "provenance": "user-derived", "characters": [{"character_id": 1, "rarity": 9}]},
            {"schema_version": 1, "provenance": "user-derived", "characters": []},
        ):
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "characters.json"
                write_json(path, document)
                with self.assertRaises(PactDrawCatalogError):
                    load_character_rarity(path)
