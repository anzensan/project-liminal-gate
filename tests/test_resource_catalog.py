from __future__ import annotations

import hashlib
from http.client import HTTPConnection
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from liminal_gate.bootstrap_server import BootstrapState, load_profile
from liminal_gate.resource_catalog import (
    IOS_RESOURCE_URL_PREFIX, ResourceCatalogError, combine_resource_catalogs, load_resource_catalog,
)
from liminal_gate.resource_catalog_builder import build_resource_manifest
from tests.support import start_server, stop_server, write_json


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
        write_json(self.manifest, {"schema_version": 1, "resources": [
            {"path": "/resources/packs/entry.bin", "file": "packs/entry.bin", "sha256": digest,
             "content_type": "application/x-local-resource"},
            {"path": "/resources/Profile/profile_1.bin", "file": "Profile/profile_1.bin", "sha256": profile_digest,
             "content_type": "application/octet-stream"},
        ]})
        profile = self.root / "profile.json"
        write_json(profile, {"schema_version": 1, "routes": {
            "time": "/local/time", "status": "/local/status", "signup": "/local/signup",
            "login": "/local/login", "userdata": "/local/userdata",
        }, "response_signing": {"algorithm": "md5-uppercase-slice", "salt": "test-salt", "digest_start": 16, "digest_end": 32},
            "account_binding": {"signup_response_field": "id", "login_query_field": "uuid"},
            "responses": {"signup": {"success": True, "id": "account"}, "login": {"success": True}, "status": {"success": True}},
            "userdata_seed": {} })
        self.server, self.thread = start_server(("127.0.0.1", 0), load_profile(profile), BootstrapState(self.root / "state.json"), resource_catalog=load_resource_catalog(self.manifest, self.resource_root))

    def tearDown(self) -> None:
        stop_server(self.server, self.thread)
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

    def test_a_file_replaced_after_load_is_not_served_under_its_manifest(self) -> None:
        """Validating at load and reopening per request trusted a stale result."""
        entry = self.resource_root / "packs" / "entry.bin"
        # Same length, so nothing about the response framing would give it away.
        entry.write_bytes(b"X" * len(self.payload))
        status, body, _ = self.request("GET", "/resources/packs/entry.bin")
        self.assertEqual(503, status)
        self.assertEqual("resource_changed_on_disk", json.loads(body)["error"])
        # Non-latching: putting the manifested file back serves it again.
        entry.write_bytes(self.payload)
        status, body, _ = self.request("GET", "/resources/packs/entry.bin")
        self.assertEqual((200, self.payload), (status, body))

    def test_a_resized_file_is_refused_rather_than_mismatching_content_length(self) -> None:
        # The sharper half: Content-Length comes from the manifest, so serving
        # a resized file would frame a body the client cannot read to the end.
        entry = self.resource_root / "packs" / "entry.bin"
        entry.write_bytes(self.payload + b"-and-then-some")
        status, body, headers = self.request("GET", "/resources/packs/entry.bin")
        self.assertEqual(503, status)
        self.assertEqual(str(len(body)), headers["Content-Length"])
        self.assertIn("changed size on disk", json.loads(body)["detail"])

    def test_a_head_request_also_refuses_a_changed_file(self) -> None:
        # HEAD sends the manifest's Content-Length and no body, so it has to
        # answer from the same check the body path uses.
        (self.resource_root / "packs" / "entry.bin").write_bytes(b"X" * len(self.payload))
        status, _body, _ = self.request("HEAD", "/resources/packs/entry.bin")
        self.assertEqual(503, status)

    def test_rejects_unknown_and_traversal_paths(self) -> None:
        for path in ("/resources/packs/missing.bin", "/resources/%2e%2e/state.json"):
            status, body, _ = self.request("GET", path)
            self.assertEqual(404, status)
            self.assertEqual({"error": "resource_not_found"}, json.loads(body))

    def test_rejects_stale_or_unsafe_manifest(self) -> None:
        stale = json.loads(self.manifest.read_text(encoding="utf-8"))
        stale["resources"][0]["sha256"] = "0" * 64
        write_json(self.manifest, stale)
        with self.assertRaises(ResourceCatalogError):
            load_resource_catalog(self.manifest, self.resource_root)
        stale["resources"][0]["sha256"] = hashlib.sha256(self.payload).hexdigest()
        stale["resources"][0]["file"] = "../state.json"
        write_json(self.manifest, stale)
        with self.assertRaises(ResourceCatalogError):
            load_resource_catalog(self.manifest, self.resource_root)

    def test_schema_v2_streams_a_zip_stored_apk_member_and_releases_it_on_close(self) -> None:
        apk = self.root / "combined.apk"
        member = "assets/liminal_gate/resources/packs/entry.bin"
        with zipfile.ZipFile(apk, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr(member, self.payload)
        write_json(self.manifest, {"schema_version": 2, "resources": [{
            "path": "/resources/packs/entry.bin", "member": member,
            "sha256": hashlib.sha256(self.payload).hexdigest(),
            "size": len(self.payload),
            "content_type": "application/x-local-resource",
        }]})
        catalog = load_resource_catalog(self.manifest, apk)
        server, thread = start_server(
            ("127.0.0.1", 0), self.server.profile, BootstrapState(self.root / "apk-state.json"), resource_catalog=catalog,
        )
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
            stop_server(server, thread)
        with self.assertRaises(ResourceCatalogError):
            catalog.open(catalog.resolve("/resources/packs/entry.bin"))

    def test_schema_v2_refuses_compressed_or_unmapped_apk_members(self) -> None:
        apk = self.root / "compressed.apk"
        member = "assets/liminal_gate/resources/packs/entry.bin"
        with zipfile.ZipFile(apk, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(member, self.payload)
        write_json(self.manifest, {"schema_version": 2, "resources": [{
            "path": "/resources/packs/entry.bin", "member": member,
            "sha256": hashlib.sha256(self.payload).hexdigest(),
            "size": len(self.payload),
        }]})
        with self.assertRaisesRegex(ResourceCatalogError, "ZIP_STORED"):
            load_resource_catalog(self.manifest, apk)


class TwoPlatformCatalogTest(unittest.TestCase):
    """One server answers both clients, and must never cross the two trees.

    The 32-hex filename prefix hashes the asset's logical name rather than its
    bytes, so the Android and iOS trees spell every filename identically while
    holding different bundles.  Serving them from one URL base would hand a
    client the other platform's bundle; these tests hold the bases apart.
    """

    #: The exact name and both spellings a real client asked for, taken from a
    #: packet capture of the iOS build rather than invented here.
    ASSET = "BG/52329f63eb2827d0fa6c9d1ad9f1fad4stage_back_9000.bin"
    LOGICAL = "BG/stage_back_9000.bin"

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.android_payload = b"android-bundle-bytes"
        self.ios_payload = b"ios-bundle-bytes-which-are-longer-and-different"
        self.android_root = self.root / "android"
        self.ios_root = self.root / "iOS_2"
        for tree, payload in (
            (self.android_root, self.android_payload), (self.ios_root, self.ios_payload),
        ):
            (tree / "BG").mkdir(parents=True)
            (tree / self.ASSET).write_bytes(payload)
        android_manifest = self.root / "resources.json"
        ios_manifest = self.root / "ios-resources.json"
        write_json(android_manifest, build_resource_manifest(self.android_root))
        write_json(ios_manifest, build_resource_manifest(
            self.ios_root, url_prefix=IOS_RESOURCE_URL_PREFIX,
        ))
        catalog = combine_resource_catalogs(
            load_resource_catalog(android_manifest, self.android_root),
            load_resource_catalog(ios_manifest, self.ios_root),
        )
        profile = self.root / "profile.json"
        write_json(profile, {"schema_version": 1, "routes": {
            "time": "/local/time", "status": "/local/status", "signup": "/local/signup",
            "login": "/local/login", "userdata": "/local/userdata",
        }, "response_signing": {"algorithm": "md5-uppercase-slice", "salt": "test-salt", "digest_start": 16, "digest_end": 32},
            "account_binding": {"signup_response_field": "id", "login_query_field": "uuid"},
            "responses": {"signup": {"success": True, "id": "account"}, "login": {"success": True}, "status": {"success": True}},
            "userdata_seed": {}})
        self.server, self.thread = start_server(
            ("127.0.0.1", 0), load_profile(profile),
            BootstrapState(self.root / "state.json"), resource_catalog=catalog,
        )

    def tearDown(self) -> None:
        stop_server(self.server, self.thread)
        self.temporary_directory.cleanup()

    def get(self, path: str) -> tuple[int, bytes]:
        connection = HTTPConnection(*self.server.server_address)
        connection.request("GET", path)
        response = connection.getresponse()
        body = response.read()
        connection.close()
        return response.status, body

    def test_each_client_receives_its_own_platform_bundle(self) -> None:
        status, body = self.get("/resources/" + self.ASSET)
        self.assertEqual((200, self.android_payload), (status, body))
        status, body = self.get(IOS_RESOURCE_URL_PREFIX + self.ASSET)
        self.assertEqual((200, self.ios_payload), (status, body))

    def test_the_ios_unhashed_retry_reaches_the_same_ios_file(self) -> None:
        """The client asks for the hashed name, then this one 300ms later."""
        status, body = self.get(IOS_RESOURCE_URL_PREFIX + self.LOGICAL)
        self.assertEqual((200, self.ios_payload), (status, body))

    def test_overlapping_catalogs_are_refused_rather_than_resolved(self) -> None:
        """Two manifests claiming one URL have no correct answer to pick."""
        manifest = self.root / "duplicate.json"
        write_json(manifest, build_resource_manifest(self.ios_root))
        with self.assertRaisesRegex(ResourceCatalogError, "both map /resources/"):
            combine_resource_catalogs(
                load_resource_catalog(self.root / "resources.json", self.android_root),
                load_resource_catalog(manifest, self.ios_root),
            )
