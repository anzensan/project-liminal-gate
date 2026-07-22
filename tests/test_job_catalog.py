from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from liminal_gate.job_catalog import JobCatalogError, load_job_catalog


class JobCatalogTest(unittest.TestCase):
    def test_requires_consecutive_ordered_unlocks(self) -> None:
        document = {"schema_version": 1, "provenance": "user-supplied", "item_slots": 2, "unlocks": [{"character_id": 3, "job_index": 1, "coins": 2, "materials": {"1": 1}}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "jobs.json"; path.write_text(json.dumps(document), encoding="utf-8")
            self.assertEqual(2, load_job_catalog(path).item_slots)
            document["unlocks"][0]["job_index"] = 2
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(JobCatalogError, "consecutive"):
                load_job_catalog(path)
