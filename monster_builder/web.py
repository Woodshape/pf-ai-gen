"""Local stdlib HTTP transport for the Guided-Rail browser UI."""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .engine import Engine


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
MAX_BODY_BYTES = 1 << 20
# Readable aliases for callers that want to tune or document the limit.
MAX_REQUEST_BODY = MAX_BODY_BYTES
WEB_DIST_PATH = Path(__file__).resolve().parent / "web" / "dist"
INDEX_PATH = WEB_DIST_PATH / "index.html"
ASSET_PATH = WEB_DIST_PATH / "assets"
CATALOG_PATH = Path(__file__).resolve().parents[1] / "catalog" / "catalog.json"
JSON_CONTENT_TYPE = "application/json; charset=utf-8"
HTML_CONTENT_TYPE = "text/html; charset=utf-8"


def _error_response(code: str, message: str, *, request_id: Any = None, path: str = "") -> dict[str, Any]:
    return {
        "ok": False,
        "requestId": request_id,
        "error": {
            "code": code,
            "kind": "boundary",
            "message": message,
            "path": path,
        },
    }


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant: {value}")


class GuidedRailHandler(BaseHTTPRequestHandler):
    """Serve the built local UI/catalog and forward one JSON request at a time."""

    protocol_version = "HTTP/1.1"
    server_version = "MonsterBuilder"
    sys_version = ""

    def do_GET(self) -> None:
        self._serve_asset(self._request_path(), head=False)

    def do_HEAD(self) -> None:
        self._serve_asset(self._request_path(), head=True)

    def do_POST(self) -> None:
        path = self._request_path()
        if path != "/api/execute":
            self._send_error(404, "protocol.not-found", "resource not found")
            return

        request = self._read_request()
        if request is None:
            return
        response = self._server_engine().execute(request)
        self._send_json(response)

    def _request_path(self) -> str | None:
        try:
            target = urlsplit(self.path)
        except ValueError:
            return None
        # Only origin-form request targets are routes.  In particular, never
        # normalize or join a client path with an on-disk directory.
        if target.scheme or target.netloc:
            return None
        return target.path

    def _serve_asset(self, path: str | None, *, head: bool) -> None:
        server = self.server
        if path == "/":
            asset = Path(getattr(server, "index_path", INDEX_PATH))
            content_type = HTML_CONTENT_TYPE
        elif path == "/catalog.json":
            asset = Path(getattr(server, "catalog_path", CATALOG_PATH))
            content_type = JSON_CONTENT_TYPE
        elif path and path.startswith("/assets/") and Path(path.removeprefix("/assets/")).name == path.removeprefix("/assets/"):
            asset = Path(getattr(server, "asset_path", ASSET_PATH)) / path.removeprefix("/assets/")
            content_type = mimetypes.guess_type(asset.name)[0] or "application/octet-stream"
        else:
            self._send_error(404, "protocol.not-found", "resource not found", head=head)
            return

        try:
            body = asset.read_bytes()
        except FileNotFoundError:
            self._send_error(404, "protocol.not-found", "resource not found", head=head)
            return
        except OSError:
            self._send_error(500, "web.resource-read-failed", "resource could not be read", head=head)
            return
        self._send_bytes(body, content_type, head=head)

    def _read_request(self) -> Any | None:
        length_header = self.headers.get("Content-Length")
        if length_header is None:
            self.close_connection = True
            self._send_error(411, "protocol.content-length-required", "Content-Length is required")
            return None
        try:
            length = int(length_header)
        except (TypeError, ValueError):
            self.close_connection = True
            self._send_error(400, "protocol.content-length-invalid", "Content-Length must be an integer")
            return None
        if length < 0:
            self.close_connection = True
            self._send_error(400, "protocol.content-length-invalid", "Content-Length must not be negative")
            return None

        maximum = getattr(self.server, "max_body_bytes", MAX_BODY_BYTES)
        if length > maximum:
            # The oversized body is deliberately not read; close the connection
            # so its remaining bytes cannot become a second HTTP request.
            self.close_connection = True
            self._send_error(413, "protocol.body-too-large", "request body is too large")
            return None

        body = self.rfile.read(length)
        if len(body) != length:
            self.close_connection = True
            self._send_error(400, "protocol.body-incomplete", "request body ended before Content-Length")
            return None
        try:
            text = body.decode("utf-8")
            return json.loads(text, parse_constant=_reject_json_constant)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
            self._send_json(
                _error_response("protocol.invalid-json", str(exc)),
                status=400,
            )
            return None

    def _server_engine(self) -> Engine:
        engine = getattr(self.server, "engine", None)
        if engine is None:
            raise RuntimeError("GuidedRailHandler requires a server with an engine")
        return engine

    def _send_error(self, status: int, code: str, message: str, *, head: bool = False) -> None:
        self._send_json(_error_response(code, message), status=status, head=head)

    def _send_json(self, value: Any, *, status: int = 200, head: bool = False) -> None:
        body = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self._send_bytes(body, JSON_CONTENT_TYPE, status=status, head=head)

    def _send_bytes(self, body: bytes, content_type: str, *, status: int = 200, head: bool = False) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if not head:
            self.wfile.write(body)


class GuidedRailServer(ThreadingHTTPServer):
    """ThreadingHTTPServer carrying the single Engine shared by its handlers."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        server_address: tuple[str, int],
        engine: Engine,
        *,
        index_path: str | Path = INDEX_PATH,
        catalog_path: str | Path = CATALOG_PATH,
        asset_path: str | Path = ASSET_PATH,
        max_body_bytes: int = MAX_BODY_BYTES,
    ) -> None:
        if isinstance(max_body_bytes, bool) or not isinstance(max_body_bytes, int) or max_body_bytes <= 0:
            raise ValueError("max_body_bytes must be a positive integer")
        self.engine = engine
        self.index_path = Path(index_path)
        self.catalog_path = Path(catalog_path)
        self.asset_path = Path(asset_path)
        self.max_body_bytes = max_body_bytes
        super().__init__(server_address, GuidedRailHandler)


def make_server(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    workspace: str | Path | None = None,
    *,
    engine: Engine | None = None,
    index_path: str | Path = INDEX_PATH,
    catalog_path: str | Path = CATALOG_PATH,
    asset_path: str | Path = ASSET_PATH,
    max_body_bytes: int = MAX_BODY_BYTES,
) -> GuidedRailServer:
    """Build a server whose handlers all use one Engine instance."""

    if engine is None:
        engine = Engine(workspace=workspace)
    return GuidedRailServer(
        (host, port),
        engine,
        index_path=index_path,
        catalog_path=catalog_path,
        asset_path=asset_path,
        max_body_bytes=max_body_bytes,
    )


# ``create_server`` is a small discoverability alias for embedding callers.
create_server = make_server


def _port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("port must be an integer") from exc
    if not 0 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be between 0 and 65535")
    return port


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serve the local Guided-Rail monster builder UI")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"bind address (default: {DEFAULT_HOST})")
    parser.add_argument("--port", type=_port, default=DEFAULT_PORT, help=f"bind port (default: {DEFAULT_PORT})")
    parser.add_argument("--workspace", type=Path, default=None, help="directory for persistent drafts and monsters")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    server = make_server(args.host, args.port, args.workspace)
    host, port = server.server_address[:2]
    print(f"Guided-Rail UI: http://{host}:{port}/", file=sys.stderr, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
