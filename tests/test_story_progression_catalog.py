from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from liminal_gate.story_progression_catalog import StoryProgressionCatalogError, load_story_progression_catalog
from liminal_gate.story_progression_importer import build_story_progression
from tests.test_story_progression_importer import _metadata


class StoryProgressionCatalogTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "progression.json"

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_loads_exact_derived_core_sequence(self) -> None:
        self.path.write_text(json.dumps(build_story_progression(_metadata())), encoding="utf-8")
        catalog = load_story_progression_catalog(self.path)
        self.assertEqual((2, 1), (catalog.stages[0].chapter, catalog.stages[0].section))
        self.assertEqual((43, 1), (catalog.stages[-1].successor_chapter, catalog.stages[-1].successor_section))
        self.assertEqual(0x030000C1, catalog.expected_clear_progress(0x01000085, (2, 5)))
        self.assertEqual(0x010000C1, catalog.expected_reveal_progress(0x030000C1))
        self.assertEqual(0x010000C1, catalog.expected_clear_progress(0x010000C1, (2, 5)))

    def test_rejects_changed_successor(self) -> None:
        document = build_story_progression(_metadata())
        document["stages"][0]["successor_low_progress"] = 0
        self.path.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaisesRegex(StoryProgressionCatalogError, "inconsistent"):
            load_story_progression_catalog(self.path)
