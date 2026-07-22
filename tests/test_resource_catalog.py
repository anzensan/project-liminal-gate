from __future__ import annotations

import hashlib
from http.client import HTTPConnection
import json
from pathlib import Path
import tempfile
import threading
import unittest

from liminal_gate.bootstrap_server import BootstrapServer, BootstrapState, load_profile
from liminal_gate.resource_catalog import ResourceCatalogError, load_resource_catalog


class ResourceCatalogTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.resource_root = self.root / "resources"
        (self.resource_root / "packs").mkdir(parents=True)
        self.payload = b"user-owned-local-resource"
        (self.resource_root / "packs" / "entry.bin").write_bytes(self.payload)
        digest = hashlib.sha256(self.payload).hexdigest()
        self.manifest = self.root / "resources.json"
        self.manifest.write_text(json.dumps({"schema_version": 1, "resources": [{
            "path": "/resources/packs/entry.bin", "file": "packs/entry.bin", "sha256": digest,
            "content_type": "application/x-local-resource",
        }]}), encoding="utf-8")
        profile = self.root / "profile.json"
        profile.write_text(json.dumps({"schema_version": 1, "routes": {
            "time": "/local/time", "status": "/local/status", "signup": "/local/signup",
            "login": "/local/login", "userdata": "/local/userdata",
        }, "response_signing": {"algorithm": "md5-uppercase-slice", "salt": "test-salt", "digest_start": 16, "digest_end": 32},
            "account_binding": {"signup_response_field": "id", "login_query_field": "uuid"},
            "responses": {"signup": {"success": True, "id": "account"}, "login": {"success": True}, "status": {"success": True}},
            "userdata_seed": {} }), encoding="utf-8")
        self.server = BootstrapServer(("127.0.0.1", 0), load_profile(profile), BootstrapState(self.root / "state.json"), resource_catalog=load_resource_catalog(self.manifest, self.resource_root))
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()
        self.temporary_directory.cleanup()

    def request(self, method: str, path: str) -> tuple[int, bytes, dict[str, str]]:
        connection = HTTPConnection(*self.server.server_address)
        connection.request(method, path)
        response = connection.getresponse()
        body = response.read()
        headers = dict(response.getheaders())
        connection.close()
        return response.status, body, headers

    def test_serves_only_explicitly_mapped_user_file(self) -> None:
        status, body, headers = self.request("GET", "/resources/packs/entry.bin")
        self.assertEqual(200, status)
        self.assertEqual(self.payload, body)
        self.assertEqual("application/x-local-resource", headers["Content-Type"])
        status, body, _ = self.request("HEAD", "/resources/packs/entry.bin")
        self.assertEqual(200, status)
        self.assertEqual(b"", body)

    def test_rejects_unknown_and_traversal_paths(self) -> None:
        for path in ("/resources/packs/missing.bin", "/resources/%2e%2e/state.json"):
            status, body, _ = self.request("GET", path)
            self.assertEqual(404, status)
            self.assertEqual({"error": "resource_not_found"}, json.loads(body))

    def test_rejects_stale_or_unsafe_manifest(self) -> None:
        stale = json.loads(self.manifest.read_text(encoding="utf-8"))
        stale["resources"][0]["sha256"] = "0" * 64
        self.manifest.write_text(json.dumps(stale), encoding="utf-8")
        with self.assertRaises(ResourceCatalogError):
            load_resource_catalog(self.manifest, self.resource_root)
        stale["resources"][0]["sha256"] = hashlib.sha256(self.payload).hexdigest()
        stale["resources"][0]["file"] = "../state.json"
        self.manifest.write_text(json.dumps(stale), encoding="utf-8")
        with self.assertRaises(ResourceCatalogError):
            load_resource_catalog(self.manifest, self.resource_root)
