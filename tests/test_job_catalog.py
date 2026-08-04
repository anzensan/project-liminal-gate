from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from liminal_gate.job_catalog import build_bundled_job_policy, JobCatalogError, load_job_catalog
from tests.support import write_json


class JobCatalogTest(unittest.TestCase):
    def test_requires_consecutive_ordered_unlocks(self) -> None:
        document = {"schema_version": 1, "provenance": "user-supplied", "item_slots": 2, "unlocks": [{"character_id": 3, "job_index": 1, "coins": 2, "materials": {"1": 1}}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "jobs.json"; write_json(path, document)
            self.assertEqual(2, load_job_catalog(path).item_slots)
            document["unlocks"][0]["job_index"] = 2
            write_json(path, document)
            with self.assertRaisesRegex(JobCatalogError, "consecutive"):
                load_job_catalog(path)


class BundledJobPolicyTest(unittest.TestCase):
    """The bundled policy must match the recovered ChrDatabase job rows."""

    def setUp(self) -> None:
        self.catalog = build_bundled_job_policy()

    def test_declares_only_unlockable_jobs(self) -> None:
        self.assertEqual(284, len(self.catalog.unlocks))
        self.assertEqual(181, self.catalog.item_slots)
        # Index 0 is a character's starting job and is never purchasable.
        self.assertEqual({1, 2}, {job_index for _, job_index in self.catalog.unlocks})

    def test_each_character_has_consecutive_indexes_from_one(self) -> None:
        by_character: dict[int, list[int]] = {}
        for character_id, job_index in self.catalog.unlocks:
            by_character.setdefault(character_id, []).append(job_index)
        for character_id, indexes in by_character.items():
            with self.subTest(character_id=character_id):
                self.assertEqual(list(range(1, len(indexes) + 1)), sorted(indexes))

    def test_costs_stay_inside_the_client_inventory(self) -> None:
        for identity, unlock in self.catalog.unlocks.items():
            with self.subTest(identity):
                self.assertGreaterEqual(unlock.coins, 0)
                for item_id, count in unlock.materials.items():
                    self.assertTrue(1 <= item_id <= self.catalog.item_slots)
                    self.assertGreater(count, 0)

    def test_carries_the_recovered_tutorial_and_later_costs(self) -> None:
        # Character 3's first job is the tutorial's free unlock; its second is
        # an ordinary Coin-and-materials purchase.
        self.assertEqual((0, {47: 1}), (self.catalog.unlocks[(3, 1)].coins, self.catalog.unlocks[(3, 1)].materials))
        self.assertEqual(16000, self.catalog.unlocks[(3, 2)].coins)
        self.assertEqual(10000, self.catalog.unlocks[(25, 1)].coins)
