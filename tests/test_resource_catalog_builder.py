from __future__ import annotations

from http.client import HTTPConnection
import json
from pathlib import Path
import tempfile
import threading
import unittest

from liminal_gate.bootstrap_server import BootstrapServer, BootstrapState, load_profile
from liminal_gate.resource_catalog import ResourceCatalogError, load_resource_catalog
from liminal_gate.resource_catalog_builder import build_resource_manifest, write_resource_manifest


class ResourceCatalogBuilderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.resources = self.root / "resources"
        (self.resources / "data_u2017" / "nested").mkdir(parents=True)
        (self.resources / "data_u2017" / "nested" / "entry.bin").write_bytes(b"local bytes")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_builds_mirrored_manifest_loaded_and_served_by_existing_transport(self) -> None:
        manifest = build_resource_manifest(self.resources)
        self.assertEqual("/resources/data_u2017/nested/entry.bin", manifest["resources"][0]["path"])
        manifest_path = self.root / "generated" / "resources.json"
        write_resource_manifest(manifest_path, manifest)
        profile_path = self.root / "profile.json"
        profile_path.write_text(json.dumps({
            "schema_version": 1, "routes": {"time": "/time", "status": "/status"},
            "response_signing": {"algorithm": "md5-uppercase-slice", "salt": "test", "digest_start": 16, "digest_end": 32},
            "account_binding": {}, "responses": {"status": {"success": True}}, "userdata_seed": {},
        }), encoding="utf-8")
        server = BootstrapServer(
            ("127.0.0.1", 0), load_profile(profile_path), BootstrapState(self.root / "state.json"),
            resource_catalog=load_resource_catalog(manifest_path, self.resources),
        )
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            connection = HTTPConnection(*server.server_address)
            connection.request("GET", "/resources/data_u2017/nested/entry.bin")
            response = connection.getresponse()
            body = response.read()
            connection.close()
        finally:
            server.shutdown()
            thread.join()
            server.server_close()
        self.assertEqual(200, response.status)
        self.assertEqual(b"local bytes", body)

    def test_rejects_symlink_and_empty_tree(self) -> None:
        empty = self.root / "empty"
        empty.mkdir()
        with self.assertRaisesRegex(ResourceCatalogError, "no regular"):
            build_resource_manifest(empty)
        (self.resources / "link.bin").symlink_to(self.resources / "data_u2017" / "nested" / "entry.bin")
        with self.assertRaisesRegex(ResourceCatalogError, "symbolic"):
            build_resource_manifest(self.resources)
