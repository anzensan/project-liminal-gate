"""Shared scaffolding for the transport-boundary tests.

Every helper here replaces a block that used to be copied into each test file:
one bundled-profile loader, one server start/stop discipline, one HTTP
round-trip shape, one catalog-to-disk idiom, and one plausible account seed.
Assertions stay in the test files; only the plumbing lives here.
"""

from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from http.client import HTTPConnection
from pathlib import Path
from typing import Any, Iterator

from liminal_gate.bootstrap_server import BootstrapProfile, BootstrapServer, load_profile

#: The repository root, the anchor for bundled profiles and fixtures.
PUBLIC_ROOT = Path(__file__).resolve().parents[1]
#: The bundled profile nearly every transport test loads.
DEFAULT_PROFILE_PATH = PUBLIC_ROOT / "profiles" / "legacy-client-bootstrap.json"


def bootstrap_profile(path: Path | None = None) -> BootstrapProfile:
    """Load the bundled bootstrap profile (or another one) for a test server."""
    return load_profile(DEFAULT_PROFILE_PATH if path is None else path)


def start_server(*args: Any, **kwargs: Any) -> tuple[BootstrapServer, threading.Thread]:
    """Construct a `BootstrapServer` and serve it on a daemon-free thread.

    Callers own the shutdown; prefer `running_server` unless the test restarts
    the server mid-flight.
    """
    server = BootstrapServer(*args, **kwargs)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    return server, thread


def stop_server(server: BootstrapServer, thread: threading.Thread) -> None:
    """The full stop discipline: shutdown, join, close the socket."""
    server.shutdown()
    thread.join()
    server.server_close()


@contextmanager
def running_server(*args: Any, **kwargs: Any) -> Iterator[BootstrapServer]:
    """One served `BootstrapServer`, stopped however the test exits."""
    server, thread = start_server(*args, **kwargs)
    try:
        yield server
    finally:
        stop_server(server, thread)


def request(
    server: BootstrapServer, method: str, path: str,
    body: bytes | str | None = None, headers: dict[str, str] | None = None,
) -> tuple[int, Any]:
    """One HTTP round-trip against a served test server, decoded as JSON."""
    connection = HTTPConnection(*server.server_address[:2])
    connection.request(method, path, body=body, headers=headers or {})
    response = connection.getresponse()
    payload = json.loads(response.read())
    connection.close()
    return response.status, payload


def get(server: BootstrapServer, path: str) -> tuple[int, Any]:
    return request(server, "GET", path)


def post(
    server: BootstrapServer, path: str, request_id: str, body: bytes | str,
    token: str = "token", headers: dict[str, str] | None = None,
) -> tuple[int, Any]:
    """POST one mutation with the transport's `otk`/`requestID` identity."""
    return request(server, "POST", f"{path}?otk={token}&requestID={request_id}", body, headers)


def write_json(path: Path, document: Any) -> Path:
    """Materialize one JSON document (usually a catalog) for a loader to read."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")
    return path
