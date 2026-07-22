from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from liminal_gate.bootstrap_profile_importer import import_profile


class BootstrapProfileImporterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.routes = {
            "time": "/time",
            "status": "/status",
            "signup": "/signup",
            "login": "/login",
            "userdata": "/userdata",
        }

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_imports_capture_without_token_or_digest(self) -> None:
        token = "capture-token"
        payloads = {
            "time": {"success": True, "timestamp": 123.0, "digest": "D" * 16},
            "status": {"success": True, "token": token, "digest": "D" * 16},
            "signup": {"success": True, "id": "local-account", "digest": "D" * 16},
            "login": {"success": True, "token": token, "digest": "D" * 16},
            "userdata": {"success": True, "coins": 7, "digest": "D" * 16},
        }
        capture = self.root / "capture.jsonl"
        capture.write_text("".join(
            json.dumps({
                "path": self.routes[role],
                "query": (
                    [{"name": "otk", "value": token}]
                    if role == "signup"
                    else ([{"name": "uuid", "value": "local-account"}] if role == "login" else [])
                ),
                "response_body_utf8": json.dumps(payload),
                "response_status": 200,
            }) + "\n"
            for role, payload in payloads.items()
        ), encoding="utf-8")
        output = import_profile(capture, self.root / "user-data", self.routes, "local-salt", 16, 32)
        profile = json.loads(output.read_text(encoding="utf-8"))
        text = output.read_text(encoding="utf-8")
        self.assertEqual("local-account", profile["responses"]["signup"]["id"])
        self.assertEqual(7, profile["userdata_seed"]["coins"])
        self.assertNotIn(token, text)
        self.assertNotIn("D" * 16, text)
