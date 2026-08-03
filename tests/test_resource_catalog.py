from __future__ import annotations

import hashlib
from http.client import HTTPConnection
import json
from pathlib import Path
import tempfile
import threading
import unittest
import zipfile

from liminal_gate.bootstrap_server import BootstrapServer, BootstrapState, load_profile
from liminal_gate.resource_catalog import ResourceCatalogError, load_resource_catalog


class ResourceCatalogTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.resource_root = self.root / "resources"
        (self.resource_root / "packs").mkdir(parents=True)
        (self.resource_root / "Profile").mkdir()
        self.payload = b"user-owned-local-resource"
        (self.resource_root / "packs" / "entry.bin").write_bytes(self.payload)
        self.profile_payload = b"user-owned-profile-resource"
        (self.resource_root / "Profile" / "profile_1.bin").write_bytes(self.profile_payload)
        digest = hashlib.sha256(self.payload).hexdigest()
        profile_digest = hashlib.sha256(self.profile_payload).hexdigest()
        self.manifest = self.root / "resources.json"
        self.manifest.write_text(json.dumps({"schema_version": 1, "resources": [
            {"path": "/resources/packs/entry.bin", "file": "packs/entry.bin", "sha256": digest,
             "content_type": "application/x-local-resource"},
            {"path": "/resources/Profile/profile_1.bin", "file": "Profile/profile_1.bin", "sha256": profile_digest,
             "content_type": "application/octet-stream"},
        ]}), encoding="utf-8")
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

    def test_serves_direct_cdn_resource_alias_only_when_manifested(self) -> None:
        status, body, headers = self.request("GET", "/Profile/profile_1.bin")
        self.assertEqual(200, status)
        self.assertEqual(self.profile_payload, body)
        self.assertEqual("application/octet-stream", headers["Content-Type"])
        status, body, _ = self.request("GET", "/Profile/not-in-manifest.bin")
        self.assertEqual(501, status)
        self.assertEqual({"error": "route_not_implemented"}, json.loads(body))

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

    def test_schema_v2_streams_a_zip_stored_apk_member_and_releases_it_on_close(self) -> None:
        apk = self.root / "combined.apk"
        member = "assets/liminal_gate/resources/packs/entry.bin"
        with zipfile.ZipFile(apk, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr(member, self.payload)
        self.manifest.write_text(json.dumps({"schema_version": 2, "resources": [{
            "path": "/resources/packs/entry.bin", "member": member,
            "sha256": hashlib.sha256(self.payload).hexdigest(),
            "size": len(self.payload),
            "content_type": "application/x-local-resource",
        }]}), encoding="utf-8")
        catalog = load_resource_catalog(self.manifest, apk)
        server = BootstrapServer(
            ("127.0.0.1", 0), self.server.profile, BootstrapState(self.root / "apk-state.json"), resource_catalog=catalog,
        )
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            connection = HTTPConnection(*server.server_address)
            connection.request("GET", "/resources/packs/entry.bin")
            response = connection.getresponse()
            self.assertEqual(200, response.status)
            self.assertEqual(str(len(self.payload)), response.getheader("Content-Length"))
            self.assertEqual(self.payload, response.read())
            connection.close()
            connection = HTTPConnection(*server.server_address)
            connection.request("HEAD", "/resources/packs/entry.bin")
            response = connection.getresponse()
            self.assertEqual(200, response.status)
            self.assertEqual(str(len(self.payload)), response.getheader("Content-Length"))
            self.assertEqual(b"", response.read())
            connection.close()
        finally:
            server.shutdown()
            thread.join()
            server.server_close()
        with self.assertRaises(ResourceCatalogError):
            catalog.open(catalog.resolve("/resources/packs/entry.bin"))

    def test_schema_v2_refuses_compressed_or_unmapped_apk_members(self) -> None:
        apk = self.root / "compressed.apk"
        member = "assets/liminal_gate/resources/packs/entry.bin"
        with zipfile.ZipFile(apk, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(member, self.payload)
        self.manifest.write_text(json.dumps({"schema_version": 2, "resources": [{
            "path": "/resources/packs/entry.bin", "member": member,
            "sha256": hashlib.sha256(self.payload).hexdigest(),
            "size": len(self.payload),
        }]}), encoding="utf-8")
        with self.assertRaisesRegex(ResourceCatalogError, "ZIP_STORED"):
            load_resource_catalog(self.manifest, apk)
