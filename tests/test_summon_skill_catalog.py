from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from liminal_gate.summon_skill_catalog import SummonSkillCatalogError, load_summon_skill_catalog
from tests.support import write_json


class SummonSkillCatalogTest(unittest.TestCase):
    def test_loads_all_summons_with_consecutive_levels(self) -> None:
        document = {
            "schema_version": 1,
            "provenance": "user-supplied",
            "item_slots": 2,
            "levels": [
                {"summon_id": summon_id, "skill_level": level, "coins": level, "materials": {"1": level}}
                for summon_id in range(1, 17)
                for level in range(2)
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "summons.json"
            write_json(path, document)
            catalog = load_summon_skill_catalog(path)
        self.assertEqual(2, catalog.level_counts[1])
        self.assertEqual(1, catalog.levels[(1, 1)].coins)

    def test_rejects_missing_summon_or_nonconsecutive_level(self) -> None:
        document = {
            "schema_version": 1,
            "provenance": "user-supplied",
            "item_slots": 1,
            "levels": [
                {"summon_id": summon_id, "skill_level": 0, "coins": 0, "materials": {}}
                for summon_id in range(1, 16)
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "summons.json"
            write_json(path, document)
            with self.assertRaises(SummonSkillCatalogError):
                load_summon_skill_catalog(path)
