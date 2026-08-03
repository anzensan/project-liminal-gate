from __future__ import annotations

import hashlib
from http.client import HTTPConnection
import json
from pathlib import Path
import tempfile
from threading import Thread
import unittest
from unittest.mock import MagicMock, patch
import zipfile

import liminal_gate.android_entrypoint as entrypoint
from liminal_gate.android_entrypoint import (
    LOOPBACK_HOST,
    LOOPBACK_PORT,
    PACKAGED_MANIFEST_MEMBER,
    RUNTIME_SEED_MEMBER,
    RUNTIME_SERVER_MEMBER,
    retry,
    start,
    stop,
)


class AndroidEntrypointTest(unittest.TestCase):
    def setUp(self) -> None:
        stop()
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.apk = self.root / "combined.apk"
        self.files_dir = self.root / "files"
        self.build_id = "a" * 64
        payload = b"packaged-resource"
        profile = {
            "schema_version": 1,
            "routes": {"time": "/local/time", "status": "/local/status", "signup": "/local/signup", "login": "/local/login", "userdata": "/local/userdata"},
            "response_signing": {"algorithm": "md5-uppercase-slice", "salt": "test", "digest_start": 0, "digest_end": 16},
            "account_binding": {"signup_response_field": "id", "login_query_field": "uuid"},
            "responses": {"signup": {"success": True, "id": "account"}, "login": {"success": True}, "status": {"success": True}},
            "userdata_seed": {},
        }
        runtime = {"schema_version": 1, "config": {"profile": profile}}
        runtime_bytes = json.dumps(runtime).encode()
        self.seed_bytes = b'{"accounts":{},"tokens":{}}\n'
        manifest = {"schema_version": 2, "build_id": self.build_id, "resources": [{
            "path": "/resources/packs/entry.bin", "member": "assets/liminal_gate/resources/entry.bin",
            "size": len(payload), "sha256": hashlib.sha256(payload).hexdigest(),
        }], "catalogs": [], "runtime": [{
            "name": "server.json", "member": RUNTIME_SERVER_MEMBER,
            "size": len(runtime_bytes), "sha256": hashlib.sha256(runtime_bytes).hexdigest(),
        }], "seed": {
            "member": RUNTIME_SEED_MEMBER, "size": len(self.seed_bytes), "sha256": hashlib.sha256(self.seed_bytes).hexdigest(),
        }}
        with zipfile.ZipFile(self.apk, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr(RUNTIME_SERVER_MEMBER, runtime_bytes)
            archive.writestr(PACKAGED_MANIFEST_MEMBER, json.dumps(manifest))
            archive.writestr(RUNTIME_SEED_MEMBER, self.seed_bytes)
            archive.writestr("assets/liminal_gate/resources/entry.bin", payload)

    def tearDown(self) -> None:
        stop()
        self.temporary_directory.cleanup()

    def test_start_is_loopback_idempotent_and_health_reports_the_expected_build(self) -> None:
        # Android app-private storage refused the old hard-link publication
        # path. The full startup and real HTTP health boundary must not need it.
        with patch.object(entrypoint.os, "link", side_effect=PermissionError(13, "Permission denied")):
            server = start(self.apk, self.files_dir, self.build_id)
        self.assertEqual(self.seed_bytes, (self.files_dir / "state.json").read_bytes())
        self.assertEqual((LOOPBACK_HOST, LOOPBACK_PORT), server.server_address)
        self.assertIs(server, start(self.apk, self.files_dir, self.build_id))
        connection = HTTPConnection(LOOPBACK_HOST, LOOPBACK_PORT)
        connection.request("GET", "/healthz")
        response = connection.getresponse()
        self.assertEqual(200, response.status)
        self.assertEqual(
            {"service": "project-liminal-gate", "status": "ok", "build_id": self.build_id},
            json.loads(response.read()),
        )
        connection.close()

    def test_interrupted_seed_publication_leaves_retryable_absence(self) -> None:
        manifest = entrypoint._load_packaged_manifest(self.apk, self.build_id)
        state = self.files_dir / "state.json"
        with patch.object(entrypoint.os, "replace", side_effect=PermissionError(13, "Permission denied")):
            with self.assertRaises(PermissionError):
                entrypoint._seed_state_once(self.apk, self.files_dir, manifest)
        self.assertFalse(state.exists())

        entrypoint._seed_state_once(self.apk, self.files_dir, manifest)
        self.assertEqual(self.seed_bytes, state.read_bytes())

    def test_seed_never_replaces_an_existing_save(self) -> None:
        self.files_dir.mkdir()
        state = self.files_dir / "state.json"
        existing = b'{"accounts":{},"tokens":{},"marker":"kept"}\n'
        state.write_bytes(existing)
        manifest = entrypoint._load_packaged_manifest(self.apk, self.build_id)
        with patch.object(entrypoint, "_write_atomic", side_effect=AssertionError("existing state was rewritten")):
            entrypoint._seed_state_once(self.apk, self.files_dir, manifest)
        self.assertEqual(existing, state.read_bytes())

    def test_retry_preserves_existing_durable_state_instead_of_reseeding(self) -> None:
        start(self.apk, self.files_dir, self.build_id)
        state = self.files_dir / "state.json"
        state.write_text('{"accounts":{},"tokens":{},"marker":"kept"}\n', encoding="utf-8")
        retry(self.apk, self.files_dir, self.build_id)
        self.assertEqual("kept", json.loads(state.read_text(encoding="utf-8"))["marker"])

    def test_manifest_materializes_verified_catalogs_and_rejects_wrong_build_or_unsafe_name(self) -> None:
        catalog = b'{"generated":true}\n'
        member = "assets/liminal_gate/catalogs/example.json"
        with zipfile.ZipFile(self.apk, "a", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr(member, catalog)
        manifest = entrypoint._load_packaged_manifest(self.apk, self.build_id)
        manifest["catalogs"] = [{
            "name": "example.json", "member": member, "size": len(catalog),
            "sha256": hashlib.sha256(catalog).hexdigest(),
        }]
        entrypoint._materialize_runtime_files(self.apk, self.files_dir, manifest)
        self.assertEqual(catalog, (self.files_dir / "catalogs" / "example.json").read_bytes())
        with self.assertRaisesRegex(Exception, "another build"):
            entrypoint._load_packaged_manifest(self.apk, "b" * 64)
        with zipfile.ZipFile(self.apk) as archive:
            with self.assertRaisesRegex(Exception, "safe relative"):
                entrypoint._verified_small_member(archive, {
                    "name": "../escape.json", "member": member, "size": len(catalog),
                    "sha256": hashlib.sha256(catalog).hexdigest(),
                })
            with self.assertRaisesRegex(Exception, "digest"):
                entrypoint._verified_small_member(archive, {
                    "name": "example.json", "member": member, "size": len(catalog),
                    "sha256": "0" * 64,
                })

    def test_stop_does_not_wait_on_a_server_whose_thread_already_failed(self) -> None:
        server = MagicMock()
        entrypoint._supervisor = entrypoint._Supervisor(
            server, Thread(), self.apk.resolve(), self.files_dir.resolve(), self.build_id,
            failure=RuntimeError("serve failed"),
        )
        stop()
        server.shutdown.assert_not_called()
        server.server_close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
