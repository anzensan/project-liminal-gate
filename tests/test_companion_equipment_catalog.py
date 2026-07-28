from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from liminal_gate.companion_equipment_catalog import (
    CompanionEquipmentCatalogError,
    build_companion_equipment_catalog,
    load_companion_equipment_catalog,
    write_companion_equipment_catalog,
)


class CompanionEquipmentCatalogTest(unittest.TestCase):
    def trees(self) -> tuple[dict[str, object], dict[str, object]]:
        characters = {
            "infos": [
                {"ID": 25, "ancestorChrID": 3, "Jobs": [70]},
                {"ID": 3, "ancestorChrID": 0, "Jobs": [30, 31]},
            ],
            "data": [
                {"ID": 31, "Species": 2},
                {"ID": 70, "Species": 7},
                {"ID": 30, "Species": 1},
            ],
        }
        companions = {
            "data": [
                {
                    "ID": 2,
                    "exclusiveChrID": 3,
                    "exclusiveSpeciesID": 0,
                    "RequiredLevel": 25,
                },
                {
                    "ID": 1,
                    "exclusiveChrID": 0,
                    "exclusiveSpeciesID": 7,
                    "RequiredLevel": 15,
                },
            ],
        }
        return characters, companions

    def test_builds_and_loads_only_equip_authority(self) -> None:
        characters, companions = self.trees()
        document = build_companion_equipment_catalog(
            characters, companions, "a" * 64,
        )
        self.assertEqual("user-derived", document["provenance"])
        self.assertEqual(
            [
                {
                    "character_id": 3,
                    "ancestor_character_id": 0,
                    "job_species": [1, 2],
                },
                {
                    "character_id": 25,
                    "ancestor_character_id": 3,
                    "job_species": [7],
                },
            ],
            document["characters"],
        )
        self.assertEqual(
            [
                {
                    "companion_id": 1,
                    "exclusive_character_id": 0,
                    "exclusive_species_id": 7,
                },
                {
                    "companion_id": 2,
                    "exclusive_character_id": 3,
                    "exclusive_species_id": 0,
                },
            ],
            document["companions"],
        )
        self.assertNotIn("RequiredLevel", json.dumps(document))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "equipment.json"
            write_companion_equipment_catalog(path, document)
            catalog = load_companion_equipment_catalog(path)
        self.assertEqual("a" * 64, catalog.apk_sha256)
        self.assertEqual((1, 2), catalog.characters[3].job_species)
        self.assertEqual(3, catalog.companions[2].exclusive_character_id)

    def test_rejects_unresolved_character_job_and_restriction(self) -> None:
        characters, companions = self.trees()
        broken_jobs = {
            **characters,
            "infos": [{"ID": 3, "ancestorChrID": 0, "Jobs": [999]}],
        }
        with self.assertRaisesRegex(
            CompanionEquipmentCatalogError, "unknown job",
        ):
            build_companion_equipment_catalog(
                broken_jobs, companions, "a" * 64,
            )
        broken_companions = {
            "data": [
                {
                    "ID": 1,
                    "exclusiveChrID": 999,
                    "exclusiveSpeciesID": 0,
                },
            ],
        }
        with self.assertRaisesRegex(
            CompanionEquipmentCatalogError, "unknown character",
        ):
            build_companion_equipment_catalog(
                characters, broken_companions, "a" * 64,
            )

    def test_loader_rejects_reordered_or_forged_provenance(self) -> None:
        characters, companions = self.trees()
        document = build_companion_equipment_catalog(
            characters, companions, "a" * 64,
        )
        document["characters"] = list(reversed(document["characters"]))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "equipment.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(
                CompanionEquipmentCatalogError, "ordered and unique",
            ):
                load_companion_equipment_catalog(path)
            document["characters"] = list(reversed(document["characters"]))
            document["provenance"] = "user-supplied"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(
                CompanionEquipmentCatalogError, "user-derived",
            ):
                load_companion_equipment_catalog(path)


if __name__ == "__main__":
    unittest.main()
