"""The iOS front end must relay exactly, and say so when it cannot."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler
import json
from pathlib import Path
import socketserver
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

from liminal_gate.ios_front_end import FrontEndError, _upstream, build_servers, tls_context
from liminal_gate.resource_catalog import IOS_RESOURCE_URL_PREFIX
from liminal_gate.server_setup import ServerSetupError, prepare_ios_resources
from liminal_gate.tester_setup import REQUIRED_RESOURCE_CATEGORIES


class _RecordingUpstream(BaseHTTPRequestHandler):
    """Stand in for the compatibility server and remember what arrived."""

    protocol_version = "HTTP/1.1"
    received: list[tuple[str, str, bytes, dict[str, str]]] = []

    def log_message(self, format: str, *args: object) -> None:
        pass

    def _record(self) -> None:
        length = self.headers.get("Content-Length")
        body = self.rfile.read(int(length)) if length is not None else b""
        type(self).received.append(
            (self.command, self.path, body, dict(self.headers.items()))
        )
        payload = b'{"success":true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-Marker", "upstream")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = _record
    do_POST = _record


class _Threading(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


class RelayTest(unittest.TestCase):
    def setUp(self) -> None:
        _RecordingUpstream.received = []
        self.upstream = _Threading(("127.0.0.1", 0), _RecordingUpstream)
        threading.Thread(target=self.upstream.serve_forever, daemon=True).start()
        self.addCleanup(self.upstream.server_close)
        self.addCleanup(self.upstream.shutdown)
        upstream_port = self.upstream.socket.getsockname()[1]
        self.servers = build_servers(
            "127.0.0.1", 0, 0, ("127.0.0.1", upstream_port), None, None,
        )
        self.front_end = self.servers[0]
        threading.Thread(target=self.front_end.serve_forever, daemon=True).start()
        self.addCleanup(self.front_end.server_close)
        self.addCleanup(self.front_end.shutdown)
        self.port = self.front_end.socket.getsockname()[1]

    def test_a_resource_path_reaches_the_server_unchanged(self) -> None:
        """The iOS resource URL carries its own base, which must survive intact."""
        path = "/gdresources/data_u2017/iOS_2/BG/52329f63eb2827d0fa6c9d1ad9f1fad4stage_back_9000.bin"
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}") as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers["X-Marker"], "upstream")
        command, arrived, body, _ = _RecordingUpstream.received[0]
        self.assertEqual((command, arrived, body), ("GET", path, b""))

    def test_a_signed_post_body_and_query_are_relayed_byte_for_byte(self) -> None:
        """The client digests its own request, so nothing here may tidy it."""
        path = "/gd/start_quest?otk=0D8AE1BB7FE584EE&digest2=51549418405444CD&requestID=13EEA89B"
        body = b"stamina=1&coins=0&chapter=1&section=1&lastUpdate=1"
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(request) as response:
            self.assertEqual(response.read(), b'{"success":true}')
        command, arrived, relayed, headers = _RecordingUpstream.received[0]
        self.assertEqual((command, arrived, relayed), ("POST", path, body))
        self.assertEqual(headers["Content-Type"], "application/x-www-form-urlencoded")

    def test_the_relayed_response_carries_one_set_of_headers(self) -> None:
        """Adding our own Server/Date on top of the upstream's sends each twice."""
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/gd/userdata") as response:
            headers = response.headers
        self.assertEqual(len(headers.get_all("Server") or []), 1)
        self.assertEqual(len(headers.get_all("Date") or []), 1)
        self.assertEqual(len(headers.get_all("Content-Length") or []), 1)

    def test_an_unavailable_server_is_a_gateway_error_not_a_crash(self) -> None:
        self.upstream.shutdown()
        self.upstream.server_close()
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(f"http://127.0.0.1:{self.port}/gd/get_current_time")
        self.assertEqual(caught.exception.code, 502)


class ConfigurationTest(unittest.TestCase):
    def test_the_upstream_must_carry_a_port(self) -> None:
        self.assertEqual(_upstream("127.0.0.1:8642"), ("127.0.0.1", 8642))
        with self.assertRaises(Exception):
            _upstream("127.0.0.1")

    def test_a_missing_certificate_is_refused_by_name(self) -> None:
        with self.assertRaises(FrontEndError) as caught:
            tls_context(Path("no-such-certificate.pem"), Path("no-such-key.pem"))
        self.assertIn("could not load the certificate and key", str(caught.exception))

    def test_the_cleartext_listener_runs_without_a_certificate(self) -> None:
        """An operator serving only resources should not need to make one."""
        servers = build_servers("127.0.0.1", 0, 0, ("127.0.0.1", 1), None, None)
        try:
            self.assertEqual(len(servers), 1)
        finally:
            for server in servers:
                server.server_close()




class IosResourcesAreOptionalTest(unittest.TestCase):
    """An Android-only host must start, whatever the iOS directory looks like.

    Most hosts have no iOS tree at all, and one that has a half-extracted one
    never asked to serve it.  Neither may stop the server that every Android
    tester is waiting on; only an operator who named a tree explicitly is owed
    a failure.
    """

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.data = self.root / "data"
        self.data.mkdir()

    def test_a_host_with_no_ios_directory_serves_android_only(self) -> None:
        self.assertIsNone(
            prepare_ios_resources(self.root / "absent", self.data, explicit=False)
        )

    def test_a_half_extracted_tree_is_declined_rather_than_fatal(self) -> None:
        """An interrupted copy leaves a directory that is present but unusable."""
        partial = self.root / "iOS_2"
        (partial / "BG").mkdir(parents=True)
        self.assertIsNone(prepare_ios_resources(partial, self.data, explicit=False))

    def test_an_empty_tree_is_declined_rather_than_fatal(self) -> None:
        empty = self.root / "iOS_2"
        empty.mkdir()
        self.assertIsNone(prepare_ios_resources(empty, self.data, explicit=False))

    def test_an_explicitly_named_tree_that_is_wrong_still_fails(self) -> None:
        """A mistyped path must not be mistaken for a host that has no iOS files."""
        partial = self.root / "iOS_2"
        (partial / "BG").mkdir(parents=True)
        with self.assertRaises(ServerSetupError):
            prepare_ios_resources(partial, self.data, explicit=True)

    def test_a_complete_tree_is_served_under_the_ios_base(self) -> None:
        tree = self.root / "iOS_2"
        for category in REQUIRED_RESOURCE_CATEGORIES:
            (tree / category).mkdir(parents=True)
            (tree / category / "asset.bin").write_bytes(b"payload-" + category.encode())
        prepared = prepare_ios_resources(tree, self.data, explicit=False)
        self.assertIsNotNone(prepared)
        resolved, manifest_path = prepared
        self.assertEqual(resolved, tree.resolve())
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertTrue(
            all(entry["path"].startswith(IOS_RESOURCE_URL_PREFIX) for entry in manifest["resources"])
        )


if __name__ == "__main__":
    unittest.main()
