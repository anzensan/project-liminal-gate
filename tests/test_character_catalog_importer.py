import unittest

from liminal_gate.character_catalog_importer import CharacterCatalogImportError, build_character_catalog


class CharacterCatalogImporterTest(unittest.TestCase):
    def test_projects_only_structural_character_fields_in_id_order(self) -> None:
        tree = {"infos": [
            {"ID": 22, "chrType": 1, "isLambda": 0, "rebirthFromID": 0, "rarity": 5, "Jobs": [220, 221]},
            {"ID": 3, "chrType": 1, "isLambda": 1, "rebirthFromID": 2, "rarity": 4, "Jobs": [30]},
        ]}
        document = build_character_catalog(tree, "a" * 64)
        self.assertEqual("user-derived", document["provenance"])
        self.assertEqual({"profile": "terra-battle-android-5.5.7-170", "apk_sha256": "a" * 64}, document["source"])
        self.assertEqual([
            {"character_id": 3, "character_type": 1, "is_lambda": True, "rebirth_from_id": 2, "rarity": 4, "job_ids": [30]},
            {"character_id": 22, "character_type": 1, "is_lambda": False, "rebirth_from_id": 0, "rarity": 5, "job_ids": [220, 221]},
        ], document["characters"])

    def test_rejects_duplicate_character_ids(self) -> None:
        tree = {"infos": [
            {"ID": 3, "chrType": 1, "isLambda": 0, "rebirthFromID": 0, "rarity": 4, "Jobs": [30]},
            {"ID": 3, "chrType": 1, "isLambda": 0, "rebirthFromID": 0, "rarity": 4, "Jobs": [31]},
        ]}
        with self.assertRaisesRegex(CharacterCatalogImportError, "unique"):
            build_character_catalog(tree, "a" * 64)

    def test_rejects_missing_or_invalid_job_ids(self) -> None:
        with self.assertRaisesRegex(CharacterCatalogImportError, "invalid job IDs"):
            build_character_catalog({"infos": [{"ID": 3, "chrType": 1, "isLambda": 0, "rebirthFromID": 0, "rarity": 4, "Jobs": []}]}, "a" * 64)


if __name__ == "__main__":
    unittest.main()
