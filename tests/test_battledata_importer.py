from __future__ import annotations

import unittest

from liminal_gate.battledata_importer import BattleDataImportError, build_stage_metadata


class BattleDataImporterTest(unittest.TestCase):
    def test_projects_only_stage_metadata(self) -> None:
        document = build_stage_metadata({"chapters": [{"chapterNo": 2, "sections": [
            {"rawStamina": 5, "coins": 20, "itemID": 110, "itemCount": 1,
             "battleCnt": 3, "title": "not exported"},
            {"rawStamina": 0, "coins": 0, "itemID": 0, "itemCount": 0,
             "battleCnt": 0, "dropBuddies": [99]},
        ]}]}, "a" * 64)
        self.assertEqual("user-derived", document["provenance"])
        self.assertEqual(2, len(document["stages"]))
        self.assertEqual(
            {"chapter": 2, "section": 1, "stamina": 5, "coins": 20,
             "entry_item_id": 110, "entry_item_count": 1,
             "battle_count": 3, "has_battle": True},
            document["stages"][0],
        )
        self.assertNotIn("title", document["stages"][0])
        self.assertNotIn("dropBuddies", document["stages"][1])

    def test_rejects_invalid_stage_metadata(self) -> None:
        with self.assertRaisesRegex(BattleDataImportError, "invalid numeric"):
            build_stage_metadata({"chapters": [{"chapterNo": 2, "sections": [
                {"rawStamina": -1, "coins": 0, "battleCnt": 1},
            ]}]}, "a" * 64)

    def test_rejects_an_incomplete_entry_item(self) -> None:
        with self.assertRaisesRegex(BattleDataImportError, "incomplete entry item"):
            build_stage_metadata({"chapters": [{"chapterNo": 2006, "sections": [
                {"rawStamina": 35, "coins": 0, "itemID": 110,
                 "itemCount": 0, "battleCnt": 5},
            ]}]}, "a" * 64)
