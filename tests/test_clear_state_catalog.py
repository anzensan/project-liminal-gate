from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from liminal_gate.bootstrap_server import _clear_state_matches
from liminal_gate.clear_state_catalog import ClearStateCatalogError, load_clear_state_catalog


class ClearStateCatalogTest(unittest.TestCase):
    def _catalog(self, root: Path) -> object:
        path = root / "clear-state.json"
        path.write_text(json.dumps({"schema_version": 1, "provenance": "user-supplied", "team_slots": 6, "max_skill_boost": 9, "max_skill_boost_per_battle": 2, "characters": [{"character_id": 1, "duplicate_skill_boost": 3, "jobs": [{"maximum_experience": 10, "level_thresholds": [0, 5, 10]}, {"maximum_experience": 0, "level_thresholds": [0]}, {"maximum_experience": 0, "level_thresholds": [0]}]}]}), encoding="utf-8")
        return load_clear_state_catalog(path)

    def test_validates_only_derived_existing_character_projection(self) -> None:
        row = {"id": 1, "buddy": 0, "date": 0.0, "jobSlots": [0, 0, 0], "jobLevels": [1, 0, 0], "jobID": 0, "flags": 0, "skillBoost": 0}
        candidate = {**row, "jobLevels": [(6 << 12) | 2, 0, 0], "skillBoost": 1}
        clear = {"chrdata": [candidate], "battle_result": {"exp": 6, "boostup": [1, 0, 0, 0, 0, 0]}}
        with tempfile.TemporaryDirectory() as directory:
            catalog = self._catalog(Path(directory))
            self.assertTrue(_clear_state_matches({"chrdata": [row], "teamMembers": [1, 0, 0, 0, 0, 0]}, clear, catalog))
            clear["chrdata"][0]["skillBoost"] = 2
            self.assertFalse(_clear_state_matches({"chrdata": [row], "teamMembers": [1, 0, 0, 0, 0, 0]}, clear, catalog))

    def test_rejects_forged_new_character_initialization(self) -> None:
        row = {"id": 1, "buddy": 0, "date": 0.0, "jobSlots": [0, 0, 0], "jobLevels": [1, 0, 0], "jobID": 0, "flags": 0, "skillBoost": 0}
        forged = {"id": 1, "buddy": 1, "date": 0.0, "jobSlots": [0, 0, 0], "jobLevels": [1, 0, 0], "jobID": 0, "flags": 0, "skillBoost": 0}
        clear = {"chrdata": [forged], "battle_result": {"exp": 0, "boostup": [0, 0, 0, 0, 0, 0]}}
        with tempfile.TemporaryDirectory() as directory:
            catalog = self._catalog(Path(directory))
            self.assertFalse(_clear_state_matches({"chrdata": [], "teamMembers": [0, 0, 0, 0, 0, 0]}, clear, catalog))

    def test_derives_configured_duplicate_skill_boost(self) -> None:
        row = {"id": 1, "buddy": 0, "date": 0.0, "jobSlots": [0, 0, 0], "jobLevels": [1, 0, 0], "jobID": 0, "flags": 0, "skillBoost": 1}
        candidate = {**row, "skillBoost": 4}
        clear = {"chrdata": [candidate], "battle_result": {"exp": 0, "boostup": [0, 0, 0, 0, 0, 0], "monsters": [1]}}
        with tempfile.TemporaryDirectory() as directory:
            catalog = self._catalog(Path(directory))
            self.assertTrue(_clear_state_matches({"chrdata": [row], "teamMembers": [1, 0, 0, 0, 0, 0]}, clear, catalog))
            clear["chrdata"][0]["skillBoost"] = 5
            self.assertFalse(_clear_state_matches({"chrdata": [row], "teamMembers": [1, 0, 0, 0, 0, 0]}, clear, catalog))

    def test_rejects_ambiguous_progression_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "clear-state.json"
            path.write_text(json.dumps({"schema_version": 1, "provenance": "user-supplied", "team_slots": 5, "max_skill_boost": 9, "max_skill_boost_per_battle": 2, "characters": []}), encoding="utf-8")
            with self.assertRaisesRegex(ClearStateCatalogError, "team_slots"):
                load_clear_state_catalog(path)
