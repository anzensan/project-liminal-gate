from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from liminal_gate.summon_skill_catalog import SummonSkillCatalogError, load_summon_skill_catalog


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
            path.write_text(json.dumps(document), encoding="utf-8")
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
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(SummonSkillCatalogError):
                load_summon_skill_catalog(path)
