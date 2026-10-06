from __future__ import annotations

import argparse
import json
import queue
import sys
import threading
import time
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Mapping
from urllib.parse import urlsplit

from .. import __version__
from .assets import Asset, AssetNotFoundError, AssetStore
from .payloads import event_envelope
from .presets import PRESETS
from .service import InvalidRequestError, SearchService

_MAX_BODY_BYTES = 1024 * 1024
_HEARTBEAT_SECONDS = 8.0
_STREAM_QUEUE_LIMIT = 256
_CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'none'; "
    "form-action 'none'; "
    "manifest-src 'self'"
)


class EventStreamWriter:
    def __init__(self, wfile: Any) -> None:
        self._wfile = wfile
        self._closed = False

    def _write_chunk(self, payload: bytes) -> None:
        self._wfile.write(b"%x\r\n" % len(payload))
        self._wfile.write(payload)
        self._wfile.write(b"\r\n")

    def send(self, event_type: str, data: Mapping[str, Any]) -> None:
        if self._closed:
            return
        body = json.dumps(dict(data), ensure_ascii=False, separators=(",", ":"), sort_keys=False)
        frame = "event: " + str(event_type) + "\ndata: " + body + "\n\n"
        self._write_chunk(frame.encode("utf-8"))
        self._wfile.flush()

    def comment(self, text: str) -> None:
        if self._closed:
            return
        self._write_chunk((": " + str(text) + "\n\n").encode("utf-8"))
        self._wfile.flush()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._wfile.write(b"0\r\n\r\n")
            self._wfile.flush()
        except Exception:
            pass


class ExactFormulaSearchServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], handler: type[BaseHTTPRequestHandler], service: SearchService, store: AssetStore) -> None:
        super().__init__(address, handler)
        self.service = service
        self.assets = store
        self.environment_hash = store.environment_hash()
        self.started_at = time.time()

    def server_bind(self) -> None:
        import socket

        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        super().server_bind()


class SearchRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "exact-formula-search/" + __version__
    sys_version = ""
    timeout = 120

    def log_message(self, format_string: str, *args: Any) -> None:
        if not args:
            sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), format_string))
            return
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), format_string % args))
        sys.stderr.flush()

    def log_error(self, format_string: str, *args: Any) -> None:
        if not args:
            sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), format_string))
            return
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), format_string % args))
        sys.stderr.flush()

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        try:
            if path == "/api/health":
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "status": "ok",
                        "version": __version__,
                        "assets": self.server.environment_hash,
                        "uptime_seconds": round(max(0.0, time.time() - self.server.started_at), 3),
                    },
                )
                return
            if path == "/api/presets":
                self._send_json(HTTPStatus.OK, {"presets": [dict(item) for item in PRESETS]})
                return
            if path.startswith("/api/"):
                self._send_json(
                    HTTPStatus.NOT_FOUND,
                    {"error": "unknown_endpoint", "detail": "no handler for " + path},
                )
                return
            self._serve_asset(path, head_only=False)
        except Exception:
            self._handle_internal_error("GET " + path)

    def do_HEAD(self) -> None:
        path = urlsplit(self.path).path
        try:
            if path.startswith("/api/"):
                self._send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "method_not_allowed", "detail": "HEAD is only available for static assets"})
                return
            self._serve_asset(path, head_only=True)
        except Exception:
            self._handle_internal_error("HEAD " + path)

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Allow", "GET, HEAD, POST, OPTIONS")
        self.send_header("Content-Length", "0")
        self._send_security_headers()
        self.end_headers()

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        try:
            if path == "/api/formalize":
                self._handle_formalize()
                return
            if path == "/api/search/stream":
                self._handle_search_stream()
                return
            self._drain_body()
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "unknown_endpoint", "detail": "no handler for " + path})
        except Exception:
            self._handle_internal_error("POST " + path)

    def _handle_internal_error(self, context: str) -> None:
        sys.stderr.write("[%s] internal error while handling %s\n" % (self.log_date_time_string(), context))
        traceback.print_exc(file=sys.stderr)
        sys.stderr.flush()
        try:
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "internal_error", "detail": "the server failed to process the request"})
        except Exception:
            self.close_connection = True

    def _send_security_headers(self) -> None:
        self.send_header("Content-Security-Policy", _CONTENT_SECURITY_POLICY)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "geolocation=(), camera=(), microphone=(), usb=(), serial=()")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")

    def _send_json(self, status: HTTPStatus, payload: Mapping[str, Any]) -> None:
        body = json.dumps(dict(payload), ensure_ascii=False, separators=(",", ":"), sort_keys=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._send_security_headers()
        self.end_headers()
        try:
            self.wfile.write(body)
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    def _drain_body(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError:
            length = 0
        if length > 0:
            try:
                self.rfile.read(min(length, _MAX_BODY_BYTES))
            except Exception:
                pass

    def _read_json_body(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError as exception:
            self.close_connection = True
            raise InvalidRequestError("invalid_content_length") from exception
        if length <= 0:
            raise InvalidRequestError("empty_request_body")
        if length > _MAX_BODY_BYTES:
            self.close_connection = True
            raise InvalidRequestError("request_body_too_large")
        content_type = str(self.headers.get("Content-Type", "")).split(";", 1)[0].strip().lower()
        if content_type not in ("application/json", "text/json"):
            self._drain_body()
            raise InvalidRequestError("unsupported_content_type:" + (content_type or "missing"))
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception as exception:
            raise InvalidRequestError("invalid_json_body") from exception
        if not isinstance(payload, dict):
            raise InvalidRequestError("json_body_not_an_object")
        return payload

    def _serve_asset(self, path: str, head_only: bool) -> None:
        if path == "/favicon.ico":
            path = "/icons/icon-192.png"
        try:
            asset = self.server.assets.resolve(path)
        except AssetNotFoundError:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "asset_not_found", "detail": "no static asset for " + path})
            return
        accept_encoding = str(self.headers.get("Accept-Encoding", ""))
        encoding = ""
        body = asset.payload
        if asset.compressible and "gzip" in accept_encoding.lower():
            body = self.server.assets.compressed_payload(asset)
            encoding = "gzip"
        etag = asset.header_etag(encoding)
        if self.headers.get("If-None-Match") == etag:
            self.send_response(HTTPStatus.NOT_MODIFIED)
            self.send_header("ETag", etag)
            self.send_header("Cache-Control", self._cache_control(asset))
            self._send_security_headers()
            self.end_headers()
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", asset.content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("ETag", etag)
        self.send_header("Cache-Control", self._cache_control(asset))
        self.send_header("Vary", "Accept-Encoding")
        if encoding:
            self.send_header("Content-Encoding", encoding)
        self._send_security_headers()
        self.end_headers()
        if head_only:
            return
        try:
            self.wfile.write(body)
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    def _cache_control(self, asset: Asset) -> str:
        if asset.path.endswith(".html") or asset.path.endswith("sw.js"):
            return "no-cache, must-revalidate"
        if asset.immutable:
            return "public, max-age=31536000, immutable"
        return "public, max-age=3600, must-revalidate"

    def _handle_formalize(self) -> None:
        try:
            payload = self._read_json_body()
        except InvalidRequestError as exception:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exception)})
            return
        query = payload.get("query", payload.get("request", payload.get("text", "")))
        budget = payload.get("budget")
        try:
            described = self.server.service.formalize(str(query), budget if isinstance(budget, Mapping) else None)
        except InvalidRequestError as exception:
            code = str(exception)
            status = HTTPStatus.SERVICE_UNAVAILABLE if code.endswith(("formalization_timeout", "formalization_queue_full")) else HTTPStatus.BAD_REQUEST
            self._send_json(status, {"error": code, "query": str(query)})
            return
        self._send_json(HTTPStatus.OK, described)

    def _handle_search_stream(self) -> None:
        try:
            payload = self._read_json_body()
        except InvalidRequestError as exception:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exception)})
            return
        query = payload.get("query", payload.get("request", payload.get("text", "")))
        budget = payload.get("budget")
        service: SearchService = self.server.service
        try:
            plan = service.prepare(str(query), budget if isinstance(budget, Mapping) else None)
        except InvalidRequestError as exception:
            code = str(exception)
            status = HTTPStatus.SERVICE_UNAVAILABLE if code.endswith(("formalization_timeout", "formalization_queue_full")) else HTTPStatus.BAD_REQUEST
            self._send_json(status, {"error": code, "query": str(query)})
            return
        if not service.acquire_search_slot():
            self._send_json(
                HTTPStatus.TOO_MANY_REQUESTS,
                {"error": "search_concurrency_limit", "detail": "another search is already occupying every worker slot"},
            )
            return
        cancel = threading.Event()
        writer: EventStreamWriter | None = None
        try:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Accel-Buffering", "no")
            self.send_header("Transfer-Encoding", "chunked")
            self._send_security_headers()
            self.end_headers()
            writer = EventStreamWriter(self.wfile)
            writer.comment("stream open")
            self._pump_events(plan, cancel, writer)
        except (BrokenPipeError, ConnectionResetError):
            cancel.set()
        finally:
            if writer is not None:
                writer.close()
            service.release_search_slot()

    def _pump_events(self, plan: Any, cancel: threading.Event, writer: EventStreamWriter) -> None:
        events: "queue.Queue[dict[str, Any] | None]" = queue.Queue(maxsize=_STREAM_QUEUE_LIMIT)
        service: SearchService = self.server.service

        def produce() -> None:
            try:
                for event in service.stream(plan, cancel):
                    if cancel.is_set():
                        break
                    events.put(event)
            except Exception as exception:
                traceback.print_exc(file=sys.stderr)
                events.put(
                    event_envelope(
                        "error",
                        0,
                        {"message": "the search engine failed: " + repr(exception)[:500], "error": type(exception).__name__},
                    )
                )
            finally:
                events.put(None)

        worker = threading.Thread(target=produce, name="exact-formula-search", daemon=True)
        worker.start()
        while True:
            if cancel.is_set():
                break
            try:
                item = events.get(timeout=_HEARTBEAT_SECONDS)
            except queue.Empty:
                writer.comment("heartbeat")
                continue
            if item is None:
                break
            event_type = str(item.get("type", "message"))
            writer.send(event_type, item)
        worker.join(timeout=1.0)


def create_server(
    host: str = "0.0.0.0",
    port: int = 8000,
    service: SearchService | None = None,
    assets: AssetStore | None = None,
) -> ExactFormulaSearchServer:
    active_service = service if service is not None else SearchService()
    active_assets = assets if assets is not None else AssetStore()
    return ExactFormulaSearchServer((host, int(port)), SearchRequestHandler, active_service, active_assets)


def serve(host: str = "0.0.0.0", port: int = 8000) -> int:
    server = create_server(host, port)
    bound_host, bound_port = server.server_address[0], server.server_address[1]
    sys.stderr.write("exact formula search interface listening on http://%s:%s\n" % (bound_host, bound_port))
    sys.stderr.flush()
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        sys.stderr.write("shutting down\n")
        sys.stderr.flush()
    finally:
        server.shutdown()
        server.server_close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="exact-formula-search-web", description="Serve the exact formula search interface and JSON API")
    parser.add_argument("--host", default="0.0.0.0", help="interface to bind (default 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="port to bind (default 8000)")
    parser.add_argument("--concurrency", type=int, default=4, help="maximum simultaneous searches (default 4)")
    parser.add_argument("--version", action="version", version="exact-formula-search " + __version__)
    arguments = parser.parse_args(argv)
    service = SearchService(concurrency=int(arguments.concurrency))
    server = create_server(arguments.host, int(arguments.port), service=service)
    bound_host, bound_port = server.server_address[0], server.server_address[1]
    sys.stderr.write("exact formula search interface listening on http://%s:%s\n" % (bound_host, bound_port))
    sys.stderr.flush()
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        sys.stderr.write("shutting down\n")
        sys.stderr.flush()
    finally:
        server.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
