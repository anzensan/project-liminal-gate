from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from liminal_gate.story_outcome_catalog import StoryOutcomeCatalogError, load_story_outcome_catalog
from tests.support import write_json


class StoryOutcomeCatalogTest(unittest.TestCase):
    def test_loads_toml_outcome_bounds(self) -> None:
        document = '''schema_version = 1
provenance = "user-supplied"
character_ids = [9001, 9002]
item_slots = 1
max_stack = 99
max_companions = 3

[[companion_masters]]
companion_id = 8001
drop_level = 2

[[stages]]
chapter = 2
section = 2
item_maxima = { "1" = 1 }
character_maxima = { "9002" = 1 }
companion_maxima = { "8001" = 1 }
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "outcomes.toml"; path.write_text(document, encoding="utf-8")
            catalog = load_story_outcome_catalog(path)
        self.assertEqual((2, 1), (catalog.companion_masters[8001].drop_level, catalog.rules[(2, 2)].item_maxima[1]))

    def test_rejects_undeclared_stage_outcome_id(self) -> None:
        document = {"schema_version": 1, "provenance": "user-supplied", "character_ids": [1], "item_slots": 1, "max_stack": 1, "max_companions": 1, "companion_masters": [], "stages": [{"chapter": 2, "section": 1, "item_maxima": {}, "character_maxima": {"2": 1}, "companion_maxima": {}}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "outcomes.json"; write_json(path, document)
            with self.assertRaisesRegex(StoryOutcomeCatalogError, "undeclared"):
                load_story_outcome_catalog(path)

    def test_rejects_mismatched_generated_source_provenance(self) -> None:
        document = {
            "schema_version": 1,
            "provenance": "user-supplied",
            "character_ids": [1],
            "item_slots": 1,
            "max_stack": 1,
            "max_companions": 1,
            "companion_masters": [],
            "stages": [{
                "chapter": 2,
                "section": 1,
                "item_maxima": {},
                "character_maxima": {},
                "companion_maxima": {},
            }],
            "source": {
                "profile": "terra-battle-android-5.5.7-170",
                "apk_sha256": "a" * 64,
                "native_encounters_sha256": "b" * 64,
                "character_catalog_sha256": "c" * 64,
                "native_encounters": {
                    "profile": "terra-battle-android-5.5.7-170",
                    "abi": "arm64",
                    "apk_sha256": "d" * 64,
                    "dump_cs_sha256": "e" * 64,
                    "libil2cpp_sha256": "f" * 64,
                    "objdump": "GNU objdump 2.44",
                    "vtable_calibration": "verified",
                },
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "outcomes.json"
            write_json(path, document)
            with self.assertRaisesRegex(StoryOutcomeCatalogError, "native source"):
                load_story_outcome_catalog(path)
