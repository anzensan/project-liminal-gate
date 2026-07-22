"""Minimal public server boundary with no bundled client data or assets."""

from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from liminal_gate.data_manifest import DataManifest, ManifestError, load_data_manifest


class LiminalGateServer(ThreadingHTTPServer):
    """HTTP server that owns only a user-selected, initially empty data directory."""

    def __init__(self, address: tuple[str, int], data_directory: Path) -> None:
        self.data_directory = data_directory.resolve()
        self.data_directory.mkdir(parents=True, exist_ok=True)
        self.data_manifest = load_data_manifest(self.data_directory)
        super().__init__(address, LiminalGateHandler)

    def data_status(self) -> dict[str, str]:
        manifest: DataManifest | None = self.data_manifest
        if manifest is None:
            return {"data": "empty", "manifest": "absent"}
        return {"data": "metadata_accepted", "datasets": str(manifest.dataset_count)}


class LiminalGateHandler(BaseHTTPRequestHandler):
    server: LiminalGateServer

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/healthz":
            self._json(HTTPStatus.OK, {
                "service": "project-liminal-gate",
                "status": "ok",
            })
            return
        if path == "/data-status":
            self._json(HTTPStatus.OK, self.server.data_status())
            return
        self._unsupported(path)

    def do_POST(self) -> None:
        self._unsupported(urlsplit(self.path).path)

    def _unsupported(self, path: str) -> None:
        self._json(HTTPStatus.NOT_IMPLEMENTED, {
            "error": "route_not_implemented",
            "path": path,
        })

    def _json(self, status: HTTPStatus, body: dict[str, str]) -> None:
        payload = json.dumps(body, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        return


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--data-dir", type=Path, default=Path("user-data"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        server = LiminalGateServer((args.host, args.port), args.data_dir)
    except ManifestError as error:
        raise SystemExit(f"invalid user-data manifest: {error}") from error
    print(f"Project Liminal Gate listening on http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
