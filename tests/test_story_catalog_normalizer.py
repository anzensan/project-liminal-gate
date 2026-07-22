from __future__ import annotations
import tempfile
from pathlib import Path
import unittest
from liminal_gate.story_catalog import load_story_catalog
from liminal_gate.story_catalog_normalizer import normalize

class StoryCatalogNormalizerTest(unittest.TestCase):
    def test_normalizes_fictional_sorted_csv(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "stages.csv"
            source.write_text("chapter,section,stamina,coins,clear_progress_code,clear_coins\n2,1,5,0,10,30\n", encoding="utf-8")
            document = normalize(source)
            output = Path(directory) / "stages.json"
            import json
            output.write_text(json.dumps(document), encoding="utf-8")
            self.assertEqual(1, len(load_story_catalog(output).stages))

    def test_rejects_extra_columns(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "stages.csv"
            source.write_text("chapter,section,stamina,coins,clear_progress_code,clear_coins,name\n2,1,5,0,10,30,x\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "columns"):
                normalize(source)

    def test_rejects_duplicate_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "stages.csv"
            source.write_text("chapter,section,stamina,coins,clear_progress_code,clear_coins\n2,1,5,0,10,30\n2,1,5,0,10,30\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unique"):
                normalize(source)
