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

    def test_maps_cache_prefixed_android_bundle_to_the_client_resource_path(self) -> None:
        bundle = self.resources / "SE" / "bdb3334db029db0ef76e06637e4de9b9sun3.bin"
        sun_hm = self.resources / "SE" / "33050eb51335cc0e0a868bcf80100e4fsunhm.bin"
        bundle.parent.mkdir()
        bundle.write_bytes(b"local unity bundle")
        sun_hm.write_bytes(b"local unity bundle")
        manifest = build_resource_manifest(self.resources)
        paths = {item["path"] for item in manifest["resources"] if item["file"] == "SE/bdb3334db029db0ef76e06637e4de9b9sun3.bin"}
        self.assertEqual({"/resources/SE/bdb3334db029db0ef76e06637e4de9b9sun3.bin", "/resources/SE/sun3.bin"}, paths)
        manifest_path = self.root / "generated" / "resources.json"
        write_resource_manifest(manifest_path, manifest)
        catalog = load_resource_catalog(manifest_path, self.resources)
        resolved = catalog.resolve("/resources/SE/sun3.bin")
        self.assertIsNotNone(resolved)
        self.assertEqual(bundle.resolve(), resolved.file)
        case_variant = catalog.resolve("/resources/SE/sunHM.bin")
        self.assertIsNotNone(case_variant)
        self.assertEqual(sun_hm.resolve(), case_variant.file)

    def test_rejects_symlink_and_empty_tree(self) -> None:
        empty = self.root / "empty"
        empty.mkdir()
        with self.assertRaisesRegex(ResourceCatalogError, "no regular"):
            build_resource_manifest(empty)
        (self.resources / "link.bin").symlink_to(self.resources / "data_u2017" / "nested" / "entry.bin")
        with self.assertRaisesRegex(ResourceCatalogError, "symbolic"):
            build_resource_manifest(self.resources)
