from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, call, patch

from liminal_gate.server_setup import (
    DEFAULT_CHARACTER_CATALOG,
    DEFAULT_COMPANION_EQUIPMENT_CATALOG,
    DEFAULT_EVENT_CATALOG,
    DEFAULT_OUTCOME_CATALOG,
    DERIVED_CATALOGS,
    REQUIRED_RESOURCE_CATEGORIES,
    STANDARD_POLICY_FLAGS,
    ServerSetupError,
    catalogs_match_apk,
    derive_local_catalogs,
    ensure_drop_compendium,
    main,
    prepare_server,
    resolve_companion_equipment_catalog,
    resolve_event_catalog,
    resolve_resource_root,
    resolve_story_outcome_catalog,
    run_server,
    server_arguments,
)
from liminal_gate.tester_setup import TesterSetupError


class ServerOnlySetupTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.resources = self.root / "gdresources" / "data_u2017" / "android"
        for category in REQUIRED_RESOURCE_CATEGORIES:
            (self.resources / category).mkdir(parents=True, exist_ok=True)
            # Every category has to carry a file: an empty one is a partial
            # extraction, and the resolver refuses it rather than packaging it.
            (self.resources / category / "sample.bin").write_bytes(b"local resource")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_detects_final_android_resource_root(self) -> None:
        self.assertEqual(
            self.resources.resolve(),
            resolve_resource_root(self.root),
        )

    def test_rejects_wrong_resource_nesting(self) -> None:
        with self.assertRaisesRegex(ServerSetupError, "data_u2017/android"):
            resolve_resource_root(self.resources / "BG")

    def test_prepares_hash_manifest_and_durable_data_directory(self) -> None:
        resource_root, data_directory, resource_count = prepare_server(
            self.root, self.root / "state"
        )
        self.assertEqual(self.resources.resolve(), resource_root)
        self.assertEqual((self.root / "state").resolve(), data_directory)
        # One mapped entry per seeded category file; none of these names carry
        # a cache prefix, so no entry gains a second URL alias.
        self.assertEqual(len(REQUIRED_RESOURCE_CATEGORIES), resource_count)
        self.assertTrue((data_directory / "resources.json").is_file())

    def test_server_command_enables_standard_policies_without_android_tools(self) -> None:
        arguments = server_arguments(
            self.resources.resolve(),
            (self.root / "state").resolve(),
            "0.0.0.0",
            8696,
            self.root / "profile.json",
        )
        for flag in STANDARD_POLICY_FLAGS:
            self.assertIn(flag, arguments)
        self.assertNotIn("--summon-skills", arguments)
        rendered = " ".join(arguments).lower()
        for android_term in ("apk", "adb", "zipalign", "apksigner", "keystore"):
            self.assertNotIn(android_term, rendered)
        self.assertIn("0.0.0.0", arguments)
        self.assertIn("8696", arguments)

    def test_story_outcome_catalog_is_picked_up_from_the_data_directory(self) -> None:
        data_directory = self.root / "state"
        data_directory.mkdir()
        self.assertIsNone(resolve_story_outcome_catalog(None, data_directory))
        catalog = data_directory / DEFAULT_OUTCOME_CATALOG
        catalog.write_text("{}", encoding="utf-8")
        self.assertEqual(catalog.resolve(), resolve_story_outcome_catalog(None, data_directory))

    def test_a_mistyped_story_outcome_catalog_is_an_error_not_a_silent_skip(self) -> None:
        # Skipping it quietly would present as the exact failure the catalog is
        # there to fix: a server that discards every Companion the client rolls.
        with self.assertRaisesRegex(ServerSetupError, "does not exist"):
            resolve_story_outcome_catalog(self.root / "absent.json", self.root)

    def test_a_story_outcome_catalog_is_passed_without_strictness(self) -> None:
        catalog = self.root / "story-outcomes.json"
        catalog.write_text("{}", encoding="utf-8")
        without = server_arguments(
            self.resources.resolve(), (self.root / "state").resolve(), "0.0.0.0", 8696,
            self.root / "profile.json",
        )
        self.assertNotIn("--story-outcome-catalog", without)
        arguments = server_arguments(
            self.resources.resolve(), (self.root / "state").resolve(), "0.0.0.0", 8696,
            self.root / "profile.json", story_outcome_catalog=catalog,
        )
        self.assertEqual(str(catalog), arguments[arguments.index("--story-outcome-catalog") + 1])
        # Bounding the reported items and monsters on top can only refuse a
        # clear, never enable one, so the guided launcher never asks for it.
        self.assertNotIn("--outcome-strict", arguments)

    def test_companion_equipment_catalog_is_discovered_and_passed(self) -> None:
        data_directory = self.root / "state"
        data_directory.mkdir()
        self.assertIsNone(
            resolve_companion_equipment_catalog(None, data_directory)
        )
        catalog = data_directory / DEFAULT_COMPANION_EQUIPMENT_CATALOG
        catalog.write_text("{}", encoding="utf-8")
        self.assertEqual(
            catalog.resolve(),
            resolve_companion_equipment_catalog(None, data_directory),
        )
        arguments = server_arguments(
            self.resources.resolve(),
            data_directory.resolve(),
            "0.0.0.0",
            8696,
            self.root / "profile.json",
            companion_equipment_catalog=catalog,
        )
        self.assertEqual(
            str(catalog),
            arguments[
                arguments.index("--companion-equipment-catalog") + 1
            ],
        )

    def test_mistyped_companion_equipment_catalog_is_an_error(self) -> None:
        with self.assertRaisesRegex(ServerSetupError, "does not exist"):
            resolve_companion_equipment_catalog(
                self.root / "absent.json", self.root,
            )

    def test_archive_event_catalog_is_discovered_with_its_character_authority(self) -> None:
        data_directory = self.root / "state"
        data_directory.mkdir()
        self.assertIsNone(resolve_event_catalog(None, data_directory))
        event_catalog = data_directory / DEFAULT_EVENT_CATALOG
        event_catalog.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ServerSetupError, "character catalog"):
            resolve_event_catalog(None, data_directory)
        (data_directory / "character-catalog.json").write_text(
            "{}", encoding="utf-8",
        )
        self.assertEqual(
            event_catalog.resolve(),
            resolve_event_catalog(None, data_directory),
        )
        arguments = server_arguments(
            self.resources.resolve(),
            data_directory.resolve(),
            "0.0.0.0",
            8696,
            self.root / "profile.json",
            event_catalog=event_catalog,
        )
        self.assertEqual(
            str(event_catalog),
            arguments[arguments.index("--event-catalog") + 1],
        )
        self.assertEqual(
            str((data_directory / "character-catalog.json").resolve()),
            arguments[arguments.index("--character-catalog") + 1],
        )

    def test_mistyped_archive_event_catalog_is_an_error(self) -> None:
        with self.assertRaisesRegex(ServerSetupError, "does not exist"):
            resolve_event_catalog(self.root / "absent.json", self.root)

    def test_prepare_only_never_launches_server(self) -> None:
        data_directory = self.root / "state"
        with patch.object(
            sys,
            "argv",
            [
                "server_setup",
                "--resource-root",
                str(self.resources),
                "--data-dir",
                str(data_directory),
                # Named rather than defaulted, so this stays a test of the
                # launcher: the default points into the developer's own
                # `local-input/`, where a real APK would send the run off to
                # derive catalogs from it for minutes.
                "--apk",
                str(self.root / "absent.apk"),
                "--prepare-only",
            ],
        ), patch("liminal_gate.server_setup.run_server") as run_server:
            self.assertEqual(0, main())
        run_server.assert_not_called()
        self.assertTrue((data_directory / "resources.json").is_file())

    def write_derived_catalogs(self, data_directory: Path, apk_sha256: str) -> None:
        """Publish the four catalogs a derivation from this APK would leave."""
        data_directory.mkdir(parents=True, exist_ok=True)
        for name in (
            DEFAULT_CHARACTER_CATALOG,
            DEFAULT_COMPANION_EQUIPMENT_CATALOG,
            DEFAULT_OUTCOME_CATALOG,
        ):
            (data_directory / name).write_text(
                json.dumps({"source": {"apk_sha256": apk_sha256}}), encoding="utf-8",
            )
        character_catalog = data_directory / DEFAULT_CHARACTER_CATALOG
        (data_directory / DEFAULT_EVENT_CATALOG).write_text(
            json.dumps({
                "character_catalog_sha256": hashlib.sha256(
                    character_catalog.read_bytes()
                ).hexdigest(),
            }),
            encoding="utf-8",
        )

    def test_catalogs_derived_from_this_apk_are_not_derived_again(self) -> None:
        """An always-on host restarts for reasons that are not its APK.

        Deriving costs minutes, so a restart that repeats it would make every
        `systemctl restart` an outage.
        """
        data_directory = self.root / "state"
        digest = "a" * 64
        self.assertFalse(catalogs_match_apk(data_directory, digest))
        self.write_derived_catalogs(data_directory, digest)
        self.assertTrue(catalogs_match_apk(data_directory, digest))
        # A different APK is a different game; those catalogs are not current.
        self.assertFalse(catalogs_match_apk(data_directory, "b" * 64))

    def test_an_event_catalog_from_another_character_catalog_is_stale(self) -> None:
        """The pair is joined by digest, and only one half names the APK."""
        data_directory = self.root / "state"
        digest = "a" * 64
        self.write_derived_catalogs(data_directory, digest)
        (data_directory / DEFAULT_EVENT_CATALOG).write_text(
            json.dumps({"character_catalog_sha256": "c" * 64}), encoding="utf-8",
        )
        self.assertFalse(catalogs_match_apk(data_directory, digest))

    def test_a_truncated_catalog_is_rederived_rather_than_fatal(self) -> None:
        data_directory = self.root / "state"
        digest = "a" * 64
        self.write_derived_catalogs(data_directory, digest)
        (data_directory / DEFAULT_OUTCOME_CATALOG).write_text("{", encoding="utf-8")
        self.assertFalse(catalogs_match_apk(data_directory, digest))

    def test_a_missing_toolchain_reports_the_cost_and_still_serves(self) -> None:
        """Best effort, like the banner derivations beside it.

        A host with no derivation toolchain is a reduced game, not a stopped
        one -- but the reduction has to name itself, because its symptom is a
        Network Error on an ordinary Companion equip.
        """
        data_directory = self.root / "state"
        data_directory.mkdir()
        apk = self.root / "client.apk"
        apk.write_bytes(b"not really an APK")
        with patch(
            "liminal_gate.server_setup.tester_setup.check_derivation_prerequisites",
            side_effect=TesterSetupError("Il2CppDumper is unavailable"),
        ), patch("builtins.print") as printed:
            derive_local_catalogs(apk, data_directory)
        reported = " ".join(str(call.args[0]) for call in printed.call_args_list)
        self.assertIn("Il2CppDumper is unavailable", reported)
        self.assertIn("equipping a Companion is refused", reported)
        self.assertIn("doctor --install-missing", reported)

    def test_current_catalogs_are_rederived_only_when_asked(self) -> None:
        """A corrected generator leaves the APK, and so the digests, untouched."""
        data_directory = self.root / "state"
        apk = self.root / "client.apk"
        apk.write_bytes(b"not really an APK")
        digest = hashlib.sha256(apk.read_bytes()).hexdigest()
        self.write_derived_catalogs(data_directory, digest)
        with patch(
            "liminal_gate.server_setup.tester_setup.check_derivation_prerequisites"
        ) as checked:
            derive_local_catalogs(apk, data_directory)
        checked.assert_not_called()
        with patch(
            "liminal_gate.server_setup.tester_setup.check_derivation_prerequisites",
            side_effect=TesterSetupError("Il2CppDumper is unavailable"),
        ) as checked:
            derive_local_catalogs(apk, data_directory, force=True)
        checked.assert_called_once()

    def _current_host_with_the_compendium_inputs(self, data_directory: Path) -> Path:
        """A host that derived its catalogs before the drop page existed."""
        apk = self.root / "client.apk"
        apk.write_bytes(b"not really an APK")
        self.write_derived_catalogs(data_directory, hashlib.sha256(apk.read_bytes()).hexdigest())
        derived = data_directory / "derived"
        derived.mkdir(parents=True, exist_ok=True)
        for name in ("native-encounters.json", "scenario-encounters.json"):
            (derived / name).write_text(json.dumps({"stages": []}), encoding="utf-8")
        return apk

    def test_a_current_host_still_gets_the_page_its_catalogs_predate(self) -> None:
        """The case the APK digest cannot see: same APK, newer generator.

        Every dedicated host set up before the drop reference existed reports
        its catalogs current and takes the short circuit, so without this it
        would answer `/local/compendium` with a permanent 404.
        """
        data_directory = self.root / "state"
        apk = self._current_host_with_the_compendium_inputs(data_directory)
        with patch(
            "liminal_gate.server_setup.tester_setup.reusable_il2cpp_dump",
            return_value=(data_directory / "il2cpp" / "DummyDll", data_directory / "il2cpp" / "dump.cs"),
        ), patch("liminal_gate.server_setup.load_master_trees", return_value={}), patch(
            "liminal_gate.server_setup.tester_setup.write_drop_compendium"
        ) as written, patch(
            "liminal_gate.server_setup.tester_setup.check_derivation_prerequisites"
        ) as rederived:
            derive_local_catalogs(apk, data_directory)
        # The expensive pass stays skipped; only the page is recovered.
        rederived.assert_not_called()
        written.assert_called_once()

    def test_a_host_that_already_has_the_page_does_not_rebuild_it(self) -> None:
        data_directory = self.root / "state"
        apk = self._current_host_with_the_compendium_inputs(data_directory)
        (data_directory / "drop-compendium.html").write_text("<html></html>", encoding="utf-8")
        with patch(
            "liminal_gate.server_setup.tester_setup.write_drop_compendium"
        ) as written:
            ensure_drop_compendium(apk, data_directory)
        written.assert_not_called()

    def test_a_host_missing_the_inputs_names_the_pass_that_rebuilds_them(self) -> None:
        """Best effort: it costs a reference page, and it says how to get it."""
        data_directory = self.root / "state"
        data_directory.mkdir(parents=True, exist_ok=True)
        apk = self.root / "client.apk"
        apk.write_bytes(b"not really an APK")
        with patch("builtins.print") as printed, patch(
            "liminal_gate.server_setup.tester_setup.write_drop_compendium"
        ) as written:
            ensure_drop_compendium(apk, data_directory)
        written.assert_not_called()
        reported = " ".join(str(call.args[0]) for call in printed.call_args_list)
        self.assertIn("/local/compendium", reported)
        self.assertIn("--rederive-catalogs", reported)

    def test_derivation_is_skipped_when_the_operator_manages_the_catalogs(self) -> None:
        apk = self.root / "client.apk"
        apk.write_bytes(b"not really an APK")
        with patch(
            "liminal_gate.server_setup.derive_local_catalogs"
        ) as derive, patch(
            "liminal_gate.server_setup.prepare_coin_creeps_cards"
        ):
            prepare_server(self.root, self.root / "state", apk, derive_catalogs=False)
        derive.assert_not_called()
        with patch(
            "liminal_gate.server_setup.derive_local_catalogs"
        ) as derive, patch(
            "liminal_gate.server_setup.prepare_coin_creeps_cards"
        ):
            prepare_server(self.root, self.root / "state", apk)
        derive.assert_called_once()

    def test_no_apk_names_the_catalogs_it_could_not_derive(self) -> None:
        """The dedicated host's oldest failure mode, said out loud."""
        with patch("builtins.print") as printed:
            prepare_server(self.root, self.root / "state", self.root / "absent.apk")
        reported = " ".join(str(call.args[0]) for call in printed.call_args_list)
        self.assertIn("Generated catalogs not derived", reported)
        self.assertIn("no APK", reported)

    def test_every_derived_catalog_is_one_the_launcher_passes(self) -> None:
        """A catalog derived but never passed reaches no player.

        The four names are read by three separate resolvers, so this is the one
        place that says they are the same four.
        """
        data_directory = (self.root / "state").resolve()
        data_directory.mkdir()
        for name in DERIVED_CATALOGS:
            (data_directory / name).write_text("{}", encoding="utf-8")
        arguments = server_arguments(
            self.resources.resolve(),
            data_directory,
            "0.0.0.0",
            8696,
            self.root / "profile.json",
            story_outcome_catalog=resolve_story_outcome_catalog(None, data_directory),
            companion_equipment_catalog=resolve_companion_equipment_catalog(
                None, data_directory,
            ),
            event_catalog=resolve_event_catalog(None, data_directory),
        )
        for name in DERIVED_CATALOGS:
            with self.subTest(name):
                self.assertIn(str(data_directory / name), arguments)

    def start_and_capture(self, *extra: str) -> str:
        """Run a prepare-only start and return everything it printed."""
        data_directory = self.root / "state"
        argv = [
            "server_setup",
            "--resource-root", str(self.resources),
            "--data-dir", str(data_directory),
            "--apk", str(self.root / "absent.apk"),
            "--prepare-only",
            *extra,
        ]
        with patch.object(sys, "argv", argv), patch("builtins.print") as printed:
            self.assertEqual(0, main())
        return "\n".join(str(call.args[0]) for call in printed.call_args_list if call.args)

    def test_a_reduced_host_ends_its_startup_with_every_shortfall(self) -> None:
        """The whole point: an operator should not have to read the scrollback.

        A first start derives for minutes and prints hundreds of lines. What is
        wrong with this host has to be at the end of it, in one place, in terms
        of what a player will hit.
        """
        output = self.start_and_capture()
        closing = output[output.rindex("!!  This host is serving a REDUCED game"):]
        self.assertIn("problems found at startup", closing)
        for expected in (
            DEFAULT_COMPANION_EQUIPMENT_CATALOG,
            DEFAULT_OUTCOME_CATALOG,
            DEFAULT_EVENT_CATALOG,
        ):
            with self.subTest(expected):
                self.assertIn(expected, closing)
        # Named by symptom, because that is what a player reports and what an
        # operator searches for after they report it.
        self.assertIn("Network Error", closing)
        # One cause, quoted against each thing it cost, rather than repeated as
        # a shortfall of its own.
        self.assertIn("no APK", closing)
        self.assertNotIn("!!  This host", closing[len("!!  This host"):])

    def test_a_complete_host_says_so_in_one_line(self) -> None:
        data_directory = (self.root / "state").resolve()
        digest = "a" * 64
        self.write_derived_catalogs(data_directory, digest)
        output = self.start_and_capture("--no-derive-catalogs")
        self.assertIn("Serving the complete local game", output)
        self.assertNotIn("REDUCED", output)

    def test_no_derive_catalogs_is_reported_as_the_reason(self) -> None:
        output = self.start_and_capture("--no-derive-catalogs")
        self.assertIn("--no-derive-catalogs was passed", output)

    def test_control_c_terminates_the_child_server_cleanly(self) -> None:
        process = Mock()
        process.wait.side_effect = [KeyboardInterrupt, 0]
        with patch("liminal_gate.server_setup.subprocess.Popen", return_value=process):
            run_server(["python", "-m", "liminal_gate.bootstrap_server"])
        process.terminate.assert_called_once_with()
        process.kill.assert_not_called()
        self.assertEqual(
            [call(), call(timeout=5)],
            process.wait.call_args_list,
        )

    def test_failed_child_server_is_reported(self) -> None:
        process = Mock()
        process.wait.return_value = 3
        with patch("liminal_gate.server_setup.subprocess.Popen", return_value=process):
            with self.assertRaises(subprocess.CalledProcessError):
                run_server(["python", "-m", "liminal_gate.bootstrap_server"])


if __name__ == "__main__":
    unittest.main()
