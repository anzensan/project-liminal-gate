from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

from liminal_gate.release_preflight import inspect_release_tree
from liminal_gate.server import LiminalGateServer


class PublicServerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.server = LiminalGateServer(("127.0.0.1", 0), Path(self.temporary_directory.name))
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()
        self.temporary_directory.cleanup()

    def request(self, method: str, path: str) -> tuple[int, dict[str, str]]:
        return self.request_to(self.server, method, path)

    def request_to(
        self, server: LiminalGateServer, method: str, path: str
    ) -> tuple[int, dict[str, str]]:
        connection = HTTPConnection(*server.server_address)
        connection.request(method, path)
        response = connection.getresponse()
        body = json.loads(response.read())
        connection.close()
        return response.status, body

    def test_health_endpoint_starts_without_private_data(self) -> None:
        status, body = self.request("GET", "/healthz")
        self.assertEqual(200, status)
        self.assertEqual({"service": "project-liminal-gate", "status": "ok"}, body)

    def test_empty_data_directory_has_no_imported_datasets(self) -> None:
        status, body = self.request("GET", "/data-status")
        self.assertEqual(200, status)
        self.assertEqual({"data": "empty", "manifest": "absent"}, body)

    def test_user_manifest_is_metadata_only(self) -> None:
        data_directory = Path(self.temporary_directory.name) / "user-data"
        data_directory.mkdir()
        (data_directory / "liminal-gate-data.json").write_text(json.dumps({
            "schema_version": 1,
            "provenance": "user-supplied",
            "datasets": [{
                "id": "local-data",
                "path": "datasets/local-data.bin",
                "sha256": "0" * 64,
            }],
        }), encoding="utf-8")
        server = LiminalGateServer(("127.0.0.1", 0), data_directory)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            status, body = self.request_to(server, "GET", "/data-status")
        finally:
            server.shutdown()
            thread.join()
            server.server_close()
        self.assertEqual(200, status)
        self.assertEqual({"data": "metadata_accepted", "datasets": "1"}, body)

    def test_unsafe_user_manifest_is_rejected_before_server_start(self) -> None:
        data_directory = Path(self.temporary_directory.name) / "unsafe-user-data"
        data_directory.mkdir()
        (data_directory / "liminal-gate-data.json").write_text(json.dumps({
            "schema_version": 1,
            "provenance": "user-supplied",
            "datasets": [{
                "id": "local-data",
                "path": "../outside.bin",
                "sha256": "0" * 64,
            }],
        }), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "safe relative"):
            LiminalGateServer(("127.0.0.1", 0), data_directory)

    def test_unknown_get_route_is_explicitly_unsupported(self) -> None:
        status, body = self.request("GET", "/compatibility/unknown")
        self.assertEqual(501, status)
        self.assertEqual("route_not_implemented", body["error"])

    def test_mutation_route_is_explicitly_unsupported(self) -> None:
        status, body = self.request("POST", "/compatibility/unknown")
        self.assertEqual(501, status)
        self.assertEqual("/compatibility/unknown", body["path"])

    def test_release_preflight_rejects_local_material(self) -> None:
        root = Path(self.temporary_directory.name) / "release"
        (root / "input").mkdir(parents=True)
        (root / "input" / "client.apk").write_bytes(b"not an APK")
        (root / "notes.bin").write_bytes(b"not distributable")
        findings = inspect_release_tree(root)
        self.assertEqual(
            [
                (Path("input"), "prohibited directory: input"),
                (Path("input/client.apk"), "prohibited directory: input"),
                (Path("notes.bin"), "prohibited file type: .bin"),
            ],
            [(finding.path, finding.reason) for finding in findings],
        )
