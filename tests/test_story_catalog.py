from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from liminal_gate.story_catalog import StoryCatalogError, load_story_catalog


class StoryCatalogTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary_directory.name) / "story-catalog.json"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write(self, stages: list[dict[str, int]], *, provenance: str = "user-supplied") -> None:
        self.path.write_text(json.dumps({"schema_version": 1, "provenance": provenance, "stages": stages}), encoding="utf-8")

    def test_accepts_ordered_user_supplied_stages(self) -> None:
        self.write([
            {"chapter": 2, "section": 1, "stamina": 5, "coins": 0, "clear_progress_code": 1, "clear_coins": 10},
            {"chapter": 2, "section": 2, "stamina": 5, "coins": 0, "clear_progress_code": 2, "clear_coins": 20},
        ])
        catalog = load_story_catalog(self.path)
        self.assertEqual((2, 2), (catalog.stages[-1].chapter, catalog.stages[-1].section))
        self.assertEqual(20, catalog.by_identity()[(2, 2)].clear_coins)

    def test_rejects_nonlocal_provenance_duplicate_and_noninteger_values(self) -> None:
        stage = {"chapter": 2, "section": 1, "stamina": 5, "coins": 0, "clear_progress_code": 1, "clear_coins": 10}
        self.write([stage], provenance="bundled")
        with self.assertRaisesRegex(StoryCatalogError, "provenance"):
            load_story_catalog(self.path)
        self.write([stage, stage])
        with self.assertRaisesRegex(StoryCatalogError, "ordered"):
            load_story_catalog(self.path)
        invalid = dict(stage, clear_coins=True)
        self.write([invalid])
        with self.assertRaisesRegex(StoryCatalogError, "integer"):
            load_story_catalog(self.path)
