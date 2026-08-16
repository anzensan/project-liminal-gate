"""Answer the iOS client's two retired hostnames on behalf of a local server.

The Android client is patched at build time, so it reaches this project by
being told a new address.  The iOS client cannot be: its URLs live in a
FairPlay-encrypted binary that nothing here decrypts.  It will therefore only
ever ask for the two hostnames the retired service used --
`gdappserver.appspot.com` over TLS for the API, and `storage.googleapis.com`
over cleartext HTTP for resources -- and the only place left to intervene is
the network.  An operator points both names at this host with a DNS rewrite
scoped to the phone, and this program answers them.

It is a transport shim and nothing else.  It parses no game request, holds no
account state, and makes no policy decision: every request is relayed to the
compatibility server unchanged, and that server remains the single authority
for what the client is allowed to do.  Both listeners forward to the same
upstream, so the one server answers both platforms at once.

Two details are load-bearing and neither is obvious.

The client offers TLS 1.0 and negotiates `AES128-SHA`, which every current
OpenSSL build refuses by default.  The context below re-enables exactly that,
which is safe only because this listener is meant for a private network
carrying one 2017 game client.

It also validates no certificate at all -- a captured handshake completed
against a leaf signed by a CA that was never installed on the phone.  So a
self-signed certificate is enough, and no trust needs to be established on the
device:

    openssl req -x509 -newkey rsa:2048 -nodes -days 825 \\
      -keyout gdappserver.key.pem -out gdappserver.pem \\
      -subj "/CN=gdappserver.appspot.com"

That is a statement about what this client does, not a recommendation.
"""

from __future__ import annotations

import argparse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
import http.client
from pathlib import Path
import socketserver
import ssl
import sys
import threading

#: The hostnames the client asks for, which an operator redirects here.
API_HOST = "gdappserver.appspot.com"
RESOURCE_HOST = "storage.googleapis.com"

#: What the retired service used, and therefore what the client dials.
DEFAULT_HTTPS_PORT = 443
DEFAULT_HTTP_PORT = 80

#: Relayed responses are re-framed with a measured length, so the upstream's
#: own framing headers must not be copied onto a different connection.
_HOP_BY_HOP = frozenset({
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailer", "transfer-encoding", "upgrade", "content-length",
})


class FrontEndError(RuntimeError):
    """The front end cannot be started as configured."""


class _ThreadingServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], handler: type, upstream: tuple[str, int]) -> None:
        self.upstream = upstream
        super().__init__(address, handler)


class _RelayHandler(BaseHTTPRequestHandler):
    """Relay one request to the compatibility server and return its answer.

    `BaseHTTPRequestHandler` is used for its parsing only.  The request line,
    headers, and body are passed on as they arrived, because the client signs
    and digests its own requests and any tidying here would be a change the
    server cannot see the original of.
    """

    protocol_version = "HTTP/1.1"
    #: The client sends `Expect: 100-continue` on some POSTs, and the base
    #: class already answers it correctly. It is named here so that behaviour
    #: is understood to be relied on rather than incidental.
    server_version = "LiminalGateFrontEnd"
    sys_version = ""

    def log_message(self, format: str, *args: object) -> None:
        # One line per request, on stdout, so a service log shows the traffic
        # without the default's separate stderr stream.
        print(f"{self.address_string()} {format % args}", flush=True)

    def _relay(self) -> None:
        length = self.headers.get("Content-Length")
        try:
            body = self.rfile.read(int(length)) if length is not None else b""
        except (ValueError, OSError):
            self.send_error(HTTPStatus.BAD_REQUEST, "unreadable request body")
            return
        headers = {
            key: value for key, value in self.headers.items()
            if key.lower() not in _HOP_BY_HOP
        }
        host, port = self.server.upstream
        try:
            connection = http.client.HTTPConnection(host, port, timeout=30)
            connection.request(self.command, self.path, body=body, headers=headers)
            response = connection.getresponse()
            payload = response.read()
        except OSError as error:
            # The upstream being down is the operator's most likely mistake,
            # and the client renders any failure as one generic message, so it
            # is said here where it can actually be read.
            print(f"upstream {host}:{port} did not answer: {error}", flush=True)
            self.send_error(HTTPStatus.BAD_GATEWAY, "compatibility server unavailable")
            return
        finally:
            try:
                connection.close()
            except (NameError, OSError):
                pass
        # `send_response` would add its own `Server` and `Date` on top of the
        # ones being relayed, so the client would receive each twice. The
        # upstream's headers are the answer being carried; ours are noise.
        self.log_request(response.status)
        self.send_response_only(response.status)
        for key, value in response.getheaders():
            if key.lower() not in _HOP_BY_HOP:
                self.send_header(key, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = _relay
    do_POST = _relay
    do_HEAD = _relay
    do_PUT = _relay


def tls_context(certificate: Path, key: Path) -> ssl.SSLContext:
    """A server context this 2017 client can actually complete a handshake with.

    The client offers TLS 1.0 and `AES128-SHA`; a default context offers
    neither, and the failure is silent from the phone's side -- the handshake
    is refused and the player sees the same `Network Error` as for every other
    fault.  `@SECLEVEL=0` is what makes OpenSSL willing to consider the suite
    at all.
    """
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1
    context.set_ciphers("AES128-SHA:DEFAULT:@SECLEVEL=0")
    try:
        context.load_cert_chain(certfile=str(certificate), keyfile=str(key))
    except (OSError, ssl.SSLError) as error:
        raise FrontEndError(f"could not load the certificate and key: {error}") from error
    return context


def build_servers(
    bind: str, http_port: int, https_port: int, upstream: tuple[str, int],
    certificate: Path | None, key: Path | None,
) -> list[_ThreadingServer]:
    """Create the cleartext resource listener and, if configured, the TLS one."""
    servers: list[_ThreadingServer] = []
    try:
        resources = _ThreadingServer((bind, http_port), _RelayHandler, upstream)
    except OSError as error:
        raise FrontEndError(
            f"could not listen on {bind}:{http_port} for {RESOURCE_HOST}: {error}"
        ) from error
    servers.append(resources)
    if certificate is None or key is None:
        return servers
    try:
        api = _ThreadingServer((bind, https_port), _RelayHandler, upstream)
    except OSError as error:
        resources.server_close()
        # Worth naming: a host running Tailscale already holds 443 on its own
        # interface, so binding every address fails while binding the LAN
        # address alone succeeds.
        raise FrontEndError(
            f"could not listen on {bind}:{https_port} for {API_HOST}: {error}; "
            "if another service holds this port, bind the LAN address explicitly"
        ) from error
    api.socket = tls_context(certificate, key).wrap_socket(api.socket, server_side=True)
    servers.append(api)
    return servers


def serve(servers: list[_ThreadingServer]) -> None:
    """Run every listener until interrupted."""
    threads = [
        threading.Thread(target=server.serve_forever, daemon=True)
        for server in servers
    ]
    for thread in threads:
        thread.start()
    try:
        for thread in threads:
            thread.join()
    except KeyboardInterrupt:
        pass
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()


def _upstream(value: str) -> tuple[str, int]:
    host, separator, port = value.rpartition(":")
    if not separator or not host:
        raise argparse.ArgumentTypeError("upstream must be host:port")
    try:
        return host, int(port)
    except ValueError:
        raise argparse.ArgumentTypeError("upstream port must be a number") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--upstream", type=_upstream, required=True,
        help="the running compatibility server, as host:port",
    )
    parser.add_argument(
        "--bind", default="0.0.0.0",
        help="address to listen on; name the LAN address if another service holds 443",
    )
    parser.add_argument("--http-port", type=int, default=DEFAULT_HTTP_PORT, help=f"cleartext port for {RESOURCE_HOST}")
    parser.add_argument("--https-port", type=int, default=DEFAULT_HTTPS_PORT, help=f"TLS port for {API_HOST}")
    parser.add_argument("--certificate", type=Path, help=f"certificate presented for {API_HOST}")
    parser.add_argument("--key", type=Path, help="private key for that certificate")
    args = parser.parse_args(argv)
    if (args.certificate is None) != (args.key is None):
        parser.error("--certificate and --key must be supplied together")
    try:
        servers = build_servers(
            args.bind, args.http_port, args.https_port, args.upstream,
            args.certificate, args.key,
        )
    except FrontEndError as error:
        print(error, file=sys.stderr)
        return 1
    host, port = args.upstream
    print(f"Relaying to {host}:{port}.", flush=True)
    for server in servers:
        listening = server.socket.getsockname()
        print(f"Listening on {listening[0]}:{listening[1]}.", flush=True)
    if args.certificate is None:
        print(f"No certificate given, so {API_HOST} is not being answered.", flush=True)
    serve(servers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
