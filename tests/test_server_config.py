from __future__ import annotations

import json
from argparse import Namespace
from http.client import HTTPConnection
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from liminal_gate.bootstrap_server import BootstrapServer, BootstrapState, ProfileError, load_launch_config, load_profile, parse_args
from liminal_gate.server_config import ServerConfigError, load_server_config
from tests.support import serve


class ServerConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        (self.root / "profiles").mkdir()
        (self.root / "profiles" / "bootstrap.json").write_text(json.dumps({
            "schema_version": 1,
            "routes": {"time": "/local/time", "status": "/local/status", "signup": "/local/signup", "login": "/local/login", "userdata": "/local/userdata"},
            "response_signing": {"algorithm": "md5-uppercase-slice", "salt": "local-test", "digest_start": 0, "digest_end": 16},
            "account_binding": {"signup_response_field": "id", "login_query_field": "uuid"},
            "responses": {"signup": {"success": True, "id": "local"}, "login": {"success": True}, "status": {"success": True}},
            "userdata_seed": {"coins": 0},
        }), encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_relative_configuration_drives_real_http_server(self) -> None:
        configuration_path = self.root / "server.toml"
        configuration_path.write_text(
            'schema_version = 1\nprovenance = "user-supplied"\nprofile = "profiles/bootstrap.json"\nstate_file = "state/bootstrap.json"\nevent_log = "logs/events.jsonl"\n',
            encoding="utf-8",
        )
        config = load_server_config(configuration_path)
        self.assertEqual(self.root / "profiles" / "bootstrap.json", config.profile)
        self.assertEqual(self.root / "state" / "bootstrap.json", config.state_file)
        server = BootstrapServer((config.host, 0), load_profile(config.profile), BootstrapState(config.state_file), config.event_log)
        thread = serve(server)
        try:
            connection = HTTPConnection(*server.server_address)
            connection.request("GET", "/local/time?otk=test-token")
            response = connection.getresponse()
            payload = json.loads(response.read())
            connection.close()
        finally:
            server.shutdown()
            thread.join()
            server.server_close()
        self.assertEqual(200, response.status)
        self.assertTrue(payload["success"])

    def test_story_progression_catalog_path_is_resolved(self) -> None:
        configuration_path = self.root / "server.toml"
        configuration_path.write_text(
            'schema_version = 1\nprovenance = "user-supplied"\nprofile = "profiles/bootstrap.json"\nstate_file = "state/bootstrap.json"\nstory_progression_catalog = "catalogs/progression.json"\ncompanion_equipment_catalog = "catalogs/companion-equipment.json"\n',
            encoding="utf-8",
        )
        config = load_server_config(configuration_path)
        self.assertEqual(self.root / "catalogs" / "progression.json", config.story_progression_catalog)
        self.assertEqual(
            self.root / "catalogs" / "companion-equipment.json",
            config.companion_equipment_catalog,
        )

    def test_core_story_policy_flag_is_loaded_strictly(self) -> None:
        configuration_path = self.root / "server.toml"
        configuration_path.write_text(
            'schema_version = 1\nprovenance = "user-supplied"\nprofile = "profiles/bootstrap.json"\nstate_file = "state/bootstrap.json"\ncore_story = true\n',
            encoding="utf-8",
        )
        self.assertTrue(load_server_config(configuration_path).core_story)

    def test_pact_policy_flag_is_loaded_strictly(self) -> None:
        configuration_path = self.root / "server.toml"
        configuration_path.write_text(
            'schema_version = 1\nprovenance = "user-supplied"\nprofile = "profiles/bootstrap.json"\nstate_file = "state/bootstrap.json"\npacts = true\n',
            encoding="utf-8",
        )
        self.assertTrue(load_server_config(configuration_path).pacts)

    def test_config_only_launcher_arguments_load_the_documented_toml_mode(self) -> None:
        configuration_path = self.root / "server.toml"
        configuration_path.write_text(
            'schema_version = 1\nprovenance = "user-supplied"\nprofile = "profiles/bootstrap.json"\nstate_file = "state/bootstrap.json"\n',
            encoding="utf-8",
        )
        with patch("sys.argv", ["liminal-gate-bootstrap-server", "--config", str(configuration_path)]):
            config = load_launch_config(parse_args())
        self.assertEqual(self.root / "profiles" / "bootstrap.json", config.profile)
        self.assertEqual(self.root / "state" / "bootstrap.json", config.state_file)

    def test_config_cannot_be_mixed_with_an_explicit_boolean_flag(self) -> None:
        configuration_path = self.root / "server.toml"
        configuration_path.write_text(
            'schema_version = 1\nprovenance = "user-supplied"\nprofile = "profiles/bootstrap.json"\nstate_file = "state/bootstrap.json"\n',
            encoding="utf-8",
        )
        with patch(
            "sys.argv",
            ["liminal-gate-bootstrap-server", "--config", str(configuration_path), "--core-story"],
        ):
            with self.assertRaisesRegex(ProfileError, "cannot be combined"):
                load_launch_config(parse_args())

    def test_outcome_strict_survives_the_toml_round_trip(self) -> None:
        configuration_path = self.root / "server.toml"
        configuration_path.write_text(
            'schema_version = 1\nprovenance = "user-supplied"\n'
            'profile = "profiles/bootstrap.json"\nstate_file = "state/bootstrap.json"\n'
            'story_outcome_catalog = "outcomes.json"\noutcome_strict = true\n',
            encoding="utf-8",
        )
        config = load_server_config(configuration_path)
        self.assertTrue(config.outcome_strict)
        self.assertEqual(self.root / "outcomes.json", config.story_outcome_catalog)
        self.assertFalse(load_launch_config(Namespace(
            config=None, profile=self.root / "profiles" / "bootstrap.json",
            state_file=self.root / "state.json", host=None, port=None,
            **{field: None for field in (
                "event_log", "resource_root", "resource_manifest", "public_data_root",
                "story_catalog", "story_progression_catalog", "settlement_catalog",
                "story_outcome_catalog", "clear_state_catalog", "statusup_catalog",
                "job_catalog", "rebirth_catalog", "summon_skill_catalog", "companion_catalog",
                "companion_equipment_catalog",
                "companion_strengthen_catalog", "companion_evolution_catalog",
                "companion_draw_catalog", "pact_draw_catalog", "event_catalog",
                "character_catalog", "hunting_catalog", "achievement_catalog",
                "message_catalog", "exchange_catalog",
            )},
        )).outcome_strict)

    def test_every_bundled_policy_flag_requires_a_toml_boolean(self) -> None:
        configuration_path = self.root / "server.toml"
        prefix = (
            'schema_version = 1\nprovenance = "user-supplied"\n'
            'profile = "profiles/bootstrap.json"\nstate_file = "state/bootstrap.json"\n'
        )
        for field, value in (
            ("drop_eligibility", '"false"'),
            ("achievements", "1"),
            ("summon_skills", "[true]"),
            ("outcome_strict", '"yes"'),
        ):
            with self.subTest(field=field):
                configuration_path.write_text(
                    f"{prefix}{field} = {value}\n",
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(ServerConfigError, f"{field} must be a boolean"):
                    load_server_config(configuration_path)

    def test_unknown_keys_and_non_user_provenance_fail(self) -> None:
        configuration_path = self.root / "server.toml"
        configuration_path.write_text(
            'schema_version = 1\nprovenance = "user-supplied"\nprofile = "profile.json"\nstate_file = "state.json"\ntypo = "no"\n',
            encoding="utf-8",
        )
        with self.assertRaises(ServerConfigError):
            load_server_config(configuration_path)
        configuration_path.write_text(
            'schema_version = 1\nprovenance = "bundled"\nprofile = "profile.json"\nstate_file = "state.json"\n',
            encoding="utf-8",
        )
        with self.assertRaises(ServerConfigError):
            load_server_config(configuration_path)

    def test_launcher_rejects_ambiguous_config_and_flag_mix(self) -> None:
        args = Namespace(config=self.root / "server.toml", profile=self.root / "profile.json", state_file=None, host=None, port=None, event_log=None, resource_root=None, resource_manifest=None, story_catalog=None, story_progression_catalog=None, settlement_catalog=None, story_outcome_catalog=None, clear_state_catalog=None, statusup_catalog=None, job_catalog=None, rebirth_catalog=None, summon_skill_catalog=None, companion_catalog=None, companion_equipment_catalog=None, companion_strengthen_catalog=None, companion_evolution_catalog=None, companion_draw_catalog=None, pact_draw_catalog=None, achievement_catalog=None, message_catalog=None, exchange_catalog=None)
        with self.assertRaises(ProfileError):
            load_launch_config(args)
