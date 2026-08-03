"""Cover the command-line entry point the guided setup actually invokes.

Every test in this suite builds a `BootstrapServer` directly, so nothing
exercised `parse_args` or `load_launch_config`. A launch option added to one
without the other therefore crashed only when a real tester started the server,
which is exactly what happened: `--hunting-catalog` was read by
`load_launch_config` but never defined by the parser, and every guided
invocation died with `AttributeError` before serving a single request.
"""

from __future__ import annotations

from dataclasses import fields
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

from liminal_gate import on_device_setup
from liminal_gate.bootstrap_server import build_server, load_launch_config, parse_args
from liminal_gate.server_config import ServerConfig
from liminal_gate.server_setup import STANDARD_POLICY_FLAGS
from liminal_gate.tester_setup import server_arguments


PUBLIC_ROOT = Path(__file__).resolve().parents[1]
SOURCE = (PUBLIC_ROOT / "liminal_gate" / "bootstrap_server.py").read_text(encoding="utf-8")


def _arguments(*extra: str) -> list[str]:
    return ["--profile", str(PUBLIC_ROOT / "profiles" / "legacy-client-bootstrap.json"), *extra]


class LaunchConfigTest(unittest.TestCase):
    def parse(self, *extra: str):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(sys, "argv", ["bootstrap_server", *_arguments("--state-file", str(Path(directory) / "s.json"), *extra)]):
                return load_launch_config(parse_args())

    def test_the_parser_defines_every_option_the_launcher_reads(self) -> None:
        """A structural check, so the next missing option fails here first."""
        tail = SOURCE[SOURCE.index("def load_launch_config("):]
        referenced = set(re.findall(r"args\.([a-z_]+)", tail))
        referenced |= set(re.findall(r"getattr\(args, ['\"]([a-z_]+)['\"]", tail))
        with patch.object(sys, "argv", ["bootstrap_server", *_arguments("--state-file", "s.json")]):
            defined = set(vars(parse_args()))
        self.assertEqual(set(), referenced - defined, "launcher reads options the parser never defines")

    def test_the_launch_config_carries_every_option_main_reads_from_it(self) -> None:
        """The same structural check one level further along.

        `load_launch_config` returns a `ServerConfig`, not the parsed namespace,
        so a flag the parser defines and the launcher forwards can still be
        dropped in between -- and `main` then reads an attribute that does not
        exist.  That is exactly how `--daily-quests` broke every command-line
        launch: defined, handled by `main`, absent from `ServerConfig`.
        """
        tail = SOURCE[SOURCE.index("def main("):]
        referenced = set(re.findall(r"args\.([a-z_]+)", tail))
        referenced |= set(re.findall(r"getattr\(args, ['\"]([a-z_]+)['\"]", tail))
        carried = {field.name for field in fields(ServerConfig)}
        self.assertEqual(
            set(), referenced - carried, "main reads launch options the configuration does not carry",
        )

    def test_the_guided_setup_command_line_launches(self) -> None:
        """The exact command `tester_setup` builds must parse and resolve."""
        with tempfile.TemporaryDirectory() as directory:
            # Everything after the interpreter and `-m module`; the launcher
            # resolves these paths but does not read them.
            command = server_arguments(Path("resources"), Path(directory), 8696)[3:]
            with patch.object(sys, "argv", ["bootstrap_server", *command]):
                config = load_launch_config(parse_args())
            self.assertEqual(
                Path(directory).resolve() / "companion-equipment.json",
                config.companion_equipment_catalog,
            )
        for name in ("core_story", "pacts", "hunting", "daily_quests", "jobs", "rebirth", "status_items",
                     "companion_draw", "companion_sale", "companion_strengthen", "companion_evolution",
                     "trading_post"):
            with self.subTest(name):
                self.assertTrue(getattr(config, name), f"{name} was not enabled by the guided flags")

    def test_outcome_strict_can_audit_hunting_without_a_story_catalog(self) -> None:
        """Hunting owns a complete bundled audit catalog of its own."""
        config = self.parse("--hunting", "--outcome-strict")
        self.assertIsNone(config.story_outcome_catalog)
        with (
            patch("liminal_gate.bootstrap_server.BootstrapState"),
            patch("liminal_gate.bootstrap_server.BootstrapServer") as constructor,
        ):
            build_server(config)
        options = constructor.call_args.kwargs
        self.assertTrue(options["outcome_strict"])
        self.assertIsNotNone(options["hunting_catalog"])

    def test_both_launchers_enable_the_same_gameplay_policies(self) -> None:
        """A feature enabled for testers must also be enabled on a dedicated host.

        These two lists are built independently -- guided setup composes flags
        from `LocalServerOptions`, the dedicated server carries a literal tuple
        -- so a feature added to one and forgotten in the other silently reaches
        only half the operators.  That is how Daily Quests shipped complete and
        unreachable: implemented, tested, documented, and passed by neither
        launcher.  Flags that are genuinely one-sided are named here with the
        reason, so the exemption is a decision rather than an omission.
        """
        one_sided = {
            # Guided setup only: an interactive tester can be offered a
            # user-local catalog the always-on host has no operator to choose.
            "--event-catalog", "--character-catalog", "--story-outcome-catalog",
            "--companion-equipment-catalog", "--resource-manifest", "--resource-root",
            "--public-data-root", "--profile", "--state-file", "--event-log",
            "--host", "--port",
        }
        with tempfile.TemporaryDirectory() as directory:
            guided = {
                argument for argument in server_arguments(Path("resources"), Path(directory), 8696)
                if argument.startswith("--")
            }
        dedicated = set(STANDARD_POLICY_FLAGS)
        self.assertEqual(
            set(), (guided - dedicated) - one_sided,
            "guided setup enables gameplay policies the dedicated server does not",
        )
        self.assertEqual(
            set(), dedicated - guided,
            "the dedicated server enables gameplay policies guided setup does not",
        )

    def test_the_on_device_runtime_enables_the_same_gameplay_policies(self) -> None:
        """The Android host is a third launcher, and the quietest of the three.

        The other two compose a command line, so a forgotten policy at least
        shows up in a printed argument list.  This one writes a config document
        that `android_entrypoint` hands straight to `ServerConfig`, where every
        policy defaults to False -- so a feature the two command-line launchers
        enable and this document omits reaches on-device players turned off,
        with nothing anywhere reporting it.
        """
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / "server.json"
            on_device_setup.write_server_runtime(
                runtime, "a" * 64,
                {name: Path(directory) / name for name in on_device_setup.REQUIRED_CATALOGS},
            )
            config = json.loads(runtime.read_text(encoding="utf-8"))["config"]

        enabled = {name for name, value in config.items() if isinstance(value, bool) and value}
        dedicated = {flag.removeprefix("--").replace("-", "_") for flag in STANDARD_POLICY_FLAGS}
        self.assertEqual(
            dedicated, enabled,
            "the Android host and the dedicated server disagree about which policies are on",
        )
        # Every key it writes must be a field `ServerConfig` actually carries;
        # the entrypoint refuses the whole document otherwise, on the device,
        # where the failure costs a rebuild rather than a test run.
        self.assertEqual(
            set(), set(config) - {field.name for field in fields(ServerConfig)},
            "the Android runtime document names configuration the server does not accept",
        )

    def test_each_bundled_policy_refuses_its_catalog_counterpart(self) -> None:
        pairs = (
            ("--hunting", "--hunting-catalog"),
            ("--jobs", "--job-catalog"),
            ("--rebirth", "--rebirth-catalog"),
            ("--status-items", "--statusup-catalog"),
            ("--companion-draw", "--companion-draw-catalog"),
            ("--companion-sale", "--companion-catalog"),
            ("--companion-strengthen", "--companion-strengthen-catalog"),
            ("--companion-evolution", "--companion-evolution-catalog"),
            ("--trading-post", "--exchange-catalog"),
            ("--pacts", "--pact-draw-catalog"),
            ("--core-story", "--story-progression-catalog"),
        )
        for flag, catalog_flag in pairs:
            with self.subTest(flag=flag):
                # The launcher resolves paths but does not read them, so a
                # nonexistent file still reaches the mutual-exclusion check.
                config = self.parse(flag, catalog_flag, "unused.json")
                self.assertTrue(getattr(config, flag[2:].replace("-", "_")))
                self.assertIsNotNone(getattr(config, catalog_flag[2:].replace("-", "_")))


if __name__ == "__main__":
    unittest.main()
