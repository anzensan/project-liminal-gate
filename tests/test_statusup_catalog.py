from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from liminal_gate.statusup_catalog import build_bundled_statusup_policy, StatusupCatalogError, load_statusup_catalog


class StatusupCatalogTest(unittest.TestCase):
    def test_accepts_a_strict_user_local_catalog(self) -> None:
        value = {
            "schema_version": 1, "provenance": "user-supplied", "item_slots": 3,
            "level_cap": 90, "skill_boost_cap": 1000,
            "items": [{"item_id": 1, "level": 1, "skill_boost": 0, "luck": 0, "species": None}],
            "characters": [{"character_id": 3, "species": 1, "luck_cap": 1000}],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            catalog = load_statusup_catalog(path)
        self.assertEqual((3, 90, 1000), (catalog.item_slots, catalog.level_cap, catalog.skill_boost_cap))
        self.assertEqual(1, catalog.items[1].level)

    def test_rejects_noncanonical_item_order(self) -> None:
        value = {
            "schema_version": 1, "provenance": "user-supplied", "item_slots": 3,
            "level_cap": 90, "skill_boost_cap": 1000,
            "items": [
                {"item_id": 2, "level": 1, "skill_boost": 0, "luck": 0, "species": None},
                {"item_id": 1, "level": 1, "skill_boost": 0, "luck": 0, "species": None},
            ],
            "characters": [{"character_id": 3, "species": 1, "luck_cap": 1000}],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(StatusupCatalogError, "ordered"):
                load_statusup_catalog(path)


class BundledStatusupPolicyTest(unittest.TestCase):
    """The bundled policy must match the recovered item and Luck-cap rules."""

    def setUp(self) -> None:
        self.catalog = build_bundled_statusup_policy()

    def test_declares_the_recovered_item_table(self) -> None:
        self.assertEqual([161, 162, 163, 168, 175, 176, 177], sorted(self.catalog.items))
        self.assertEqual((181, 90, 1000), (self.catalog.item_slots, self.catalog.level_cap, self.catalog.skill_boost_cap))
        # Displayed points; the server stores them in tenths.
        self.assertEqual((1, 0, 0, None), _effect(self.catalog.items[161]))
        self.assertEqual((0, 3, 0, None), _effect(self.catalog.items[176]))
        # Only the Machine-only item carries a species gate.
        self.assertEqual((0, 1, 0, 8), _effect(self.catalog.items[168]))
        self.assertEqual({None}, {item.species for item in self.catalog.items.values() if item.item_id != 168})

    def test_every_item_has_exactly_one_kind_of_effect(self) -> None:
        for item_id, item in self.catalog.items.items():
            with self.subTest(item_id=item_id):
                self.assertEqual(1, sum(1 for value in (item.level, item.skill_boost, item.luck) if value))

    def test_luck_caps_follow_the_recovered_rarity_rule(self) -> None:
        self.assertEqual(346, len(self.catalog.characters))
        # Luck is tenths of one percent: 70, 80, or 100 percent.
        self.assertEqual({700, 800, 1000}, {c.luck_cap for c in self.catalog.characters.values()})
        for character_id, character in self.catalog.characters.items():
            with self.subTest(character_id=character_id):
                self.assertGreater(character.species, 0)


def _effect(item) -> tuple[int, int, int, int | None]:
    return item.level, item.skill_boost, item.luck, item.species
