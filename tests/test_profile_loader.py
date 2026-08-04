"""Profile-schema regressions for the shared transition validators."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from liminal_gate.bootstrap_server import ProfileError, load_profile
from tests.support import DEFAULT_PROFILE_PATH, write_json


class ProfileLoaderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.document = json.loads(DEFAULT_PROFILE_PATH.read_text(encoding="utf-8"))

    def _load(self, document: dict | None = None):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"
            write_json(path, self.document if document is None else document)
            return load_profile(path)

    def test_the_bundled_profile_survives_shared_validation(self) -> None:
        profile = self._load()
        self.assertIn("clear_quest", profile.routes)
        self.assertTrue(profile.tutorial_summons)
        self.assertTrue(profile.structural_writes)

    def test_body_transition_fields_and_values_remain_distinct_errors(self) -> None:
        extra_field = copy.deepcopy(self.document)
        extra_field["story_starts"][0]["unexpected"] = True
        with self.assertRaisesRegex(ProfileError, "story start must define"):
            self._load(extra_field)

        wrong_value = copy.deepcopy(self.document)
        wrong_value["tutorial_summons"][0]["outcomes"][0]["weight"] = 0
        with self.assertRaisesRegex(ProfileError, "tutorial summon values"):
            self._load(wrong_value)

    def test_first_tutorial_summon_declares_equal_bahl_and_grace_weights(self) -> None:
        first = self.document["tutorial_summons"][0]
        self.assertEqual(
            [(1, 1), (3, 1)],
            [
                (outcome["starter_character_id"], outcome["weight"])
                for outcome in first["outcomes"]
            ],
        )

        mismatched = copy.deepcopy(self.document)
        mismatched["tutorial_summons"][0]["outcomes"][0]["response"][
            "teamMembers"
        ] = [3]
        with self.assertRaisesRegex(ProfileError, "tutorial summon values"):
            self._load(mismatched)

    def test_story_and_userdata_structural_shapes_share_strict_json_kinds(self) -> None:
        wrong_clear = copy.deepcopy(self.document)
        wrong_clear["story_clears"][0]["json_fields"]["battle_result"] = "scalar"
        with self.assertRaisesRegex(ProfileError, "story clear values"):
            self._load(wrong_clear)

        wrong_write = copy.deepcopy(self.document)
        wrong_write["structural_writes"][0]["json_fields"]["chrdata"] = "scalar"
        with self.assertRaisesRegex(ProfileError, "structural write values"):
            self._load(wrong_write)


if __name__ == "__main__":
    unittest.main()
