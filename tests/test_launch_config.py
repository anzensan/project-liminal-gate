"""Cover the command-line entry point the guided setup actually invokes.

Every test in this suite builds a `BootstrapServer` directly, so nothing
exercised `parse_args` or `load_launch_config`. A launch option added to one
without the other therefore crashed only when a real tester started the server,
which is exactly what happened: `--hunting-catalog` was read by
`load_launch_config` but never defined by the parser, and every guided
invocation died with `AttributeError` before serving a single request.
"""

from __future__ import annotations

from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

from liminal_gate.bootstrap_server import load_launch_config, parse_args
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
        for name in ("core_story", "pacts", "hunting", "jobs", "rebirth", "status_items",
                     "companion_draw", "companion_sale", "companion_strengthen", "companion_evolution",
                     "trading_post"):
            with self.subTest(name):
                self.assertTrue(getattr(config, name), f"{name} was not enabled by the guided flags")

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
