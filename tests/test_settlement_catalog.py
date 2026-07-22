from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from liminal_gate.bootstrap_server import _settlement_matches
from liminal_gate.settlement_catalog import SettlementCatalogError, load_settlement_catalog


class SettlementCatalogTest(unittest.TestCase):
    def test_validates_exact_user_declared_projection_delta(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settlement.json"
            path.write_text(json.dumps({"schema_version": 1, "provenance": "user-supplied", "character_ids": [1, 2], "item_slots": 2, "summon_slots": 2, "max_stack": 99, "stages": [{"chapter": 2, "section": 1, "character_rewards": [2], "item_rewards": {"1": 3}, "summon_rewards": {"2": 1}, "clear_coins": 10}]}), encoding="utf-8")
            catalog = load_settlement_catalog(path)
            self.assertEqual(10, catalog.rules[(2, 1)].clear_coins)
            userdata = {"chrdata": [{"id": 1}], "itemList": [4, 0], "summonList": [0, 0]}
            clear = {"chrdata": [{"id": 1}, {"id": 2}], "itemList": [7, 0], "summonList": [0, 1]}
            self.assertTrue(_settlement_matches(userdata, clear, (2, 1), catalog))
            clear["itemList"] = [8, 0]
            self.assertFalse(_settlement_matches(userdata, clear, (2, 1), catalog))

    def test_rejects_noncanonical_or_duplicate_character_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settlement.json"
            path.write_text(json.dumps({"schema_version": 1, "provenance": "user-supplied", "character_ids": [2, 2], "item_slots": 1, "summon_slots": 1, "max_stack": 1, "stages": [{"chapter": 2, "section": 1, "character_rewards": [], "item_rewards": {}, "summon_rewards": {}}]}), encoding="utf-8")
            with self.assertRaisesRegex(SettlementCatalogError, "character_ids"):
                load_settlement_catalog(path)

    def test_rejects_negative_clear_coins(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settlement.json"
            path.write_text(json.dumps({"schema_version": 1, "provenance": "user-supplied", "character_ids": [1], "item_slots": 1, "summon_slots": 1, "max_stack": 1, "stages": [{"chapter": 2, "section": 1, "character_rewards": [], "item_rewards": {}, "summon_rewards": {}, "clear_coins": -1}]}), encoding="utf-8")
            with self.assertRaisesRegex(SettlementCatalogError, "clear_coins"):
                load_settlement_catalog(path)
