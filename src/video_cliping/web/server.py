"""Serve the video clipping page on this computer only."""

from __future__ import annotations

import argparse
import secrets
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from video_cliping.cut import clip as default_clip
from video_cliping.errors import EngineError
from video_cliping.web.browse import BrowseError, list_directory, open_directory, start_directory
from video_cliping.web.job import clip_from_form, failure_notice, form_state, parse_fields, success_notice
from video_cliping.web.page import browse_page, browse_target, clip_page, home_page, message_page
from video_cliping.web.upload import FormError

_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
_MAX_TOKENS = 50
_MAX_FORM_BYTES = 64 * 1024


class ClipServer(ThreadingHTTPServer):
    """HTTP server that remembers the form tokens for this process."""

    def __init__(self, address: tuple[str, int], handler: type[BaseHTTPRequestHandler]) -> None:
        super().__init__(address, handler)
        self.tokens: list[str] = []
        self.token_lock = threading.Lock()
        self.clip_fn = default_clip

    def issue_token(self) -> str:
        """Return a new token and forget tokens older than the last 50."""
        token = secrets.token_urlsafe(32)
        with self.token_lock:
            self.tokens.append(token)
            del self.tokens[:-_MAX_TOKENS]
        return token

    def take_token(self, token: str) -> bool:
        """Accept a token once. Return False when it is missing or reused."""
        with self.token_lock:
            if token not in self.tokens:
                return False
            self.tokens.remove(token)
        return True


class ClipHandler(BaseHTTPRequestHandler):
    """GET / shows the tool. GET /clip shows the form. POST /clip runs one cut."""

    server: ClipServer

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        fields = _query_fields(parsed.query)
        if parsed.path == "/":
            self._html(200, home_page())
            return
        if parsed.path == "/clip":
            self._html(200, clip_page(self.server.issue_token(), form_state(fields)))
            return
        if parsed.path == "/browse":
            self._show_browse(fields)
            return
        self._html(404, message_page("That page is not here."))

    def do_POST(self) -> None:  # noqa: N802
        self.close_connection = True
        path = urlparse(self.path).path
        if path not in {"/clip", "/browse"}:
            self._html(404, message_page("That page is not here."))
            return
        if not _same_computer(self.headers.get("Host", ""), self.headers.get("Origin")):
            self._html(403, message_page("This page is only for this computer."))
            return
        raw = self._body()
        if raw is None:
            return
        try:
            fields = parse_fields(raw)
        except FormError as exc:
            self._html(400, message_page(str(exc)))
            return
        if not self.server.take_token(fields.get("csrf", "")):
            self._html(403, message_page("The form expired. Open Video clipping again."))
            return
        if path == "/browse":
            self._redirect_browse(fields)
            return
        self._finish_clip(fields)

    def log_message(self, fmt: str, *args: object) -> None:
        """Write one request line to stderr. The body is not logged."""
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _body(self) -> bytes | None:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None or not raw_length.isdigit():
            self._html(400, message_page("The form has no length."))
            return None
        length = int(raw_length)
        if length > _MAX_FORM_BYTES:
            self._html(400, message_page("The form is too large."))
            return None
        return self.rfile.read(length)

    def _show_browse(self, fields: dict[str, str]) -> None:
        kind = fields.get("kind", "")
        if kind not in {"file", "folder"}:
            self._html(400, message_page("Choose a file or a folder."))
            return
        state = form_state(fields)
        try:
            folder = open_directory(fields["dir"]) if fields.get("dir") else start_directory(kind, state.source, state.dest_dir)
            entries, truncated = list_directory(folder)
        except BrowseError as exc:
            self._html(400, message_page(str(exc)))
            return
        self._html(200, browse_page(kind, folder, entries, truncated, state))

    def _redirect_browse(self, fields: dict[str, str]) -> None:
        kind = fields.get("kind", "")
        if kind not in {"file", "folder"}:
            self._html(400, message_page("Choose a file or a folder."))
            return
        state = form_state(fields)
        folder = start_directory(kind, state.source, state.dest_dir)
        self.send_response(303)
        self.send_header("Location", browse_target(kind, folder, state))
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _finish_clip(self, fields: dict[str, str]) -> None:
        state = form_state(fields)
        try:
            report = clip_from_form(fields, self.server.clip_fn)
        except EngineError as exc:
            self._html(400, clip_page(self.server.issue_token(), state, failure_notice(exc)))
            return
        except Exception:
            traceback.print_exc()
            self._html(500, message_page("The cut did not finish."))
            return
        self._html(200, clip_page(self.server.issue_token(), state, success_notice(report)))

    def _html(self, status: int, body: str) -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(data)


def _query_fields(query: str) -> dict[str, str]:
    parsed = parse_qs(query, keep_blank_values=True, max_num_fields=30)
    return {key: values[-1] for key, values in parsed.items()}


def _same_computer(host: str, origin: str | None) -> bool:
    if _host_name(host) not in _LOCAL_HOSTS:
        return False
    if origin is None or origin == "null":
        # A local form can arrive with no origin. The one-time token still has to match.
        return True
    return origin == f"http://{host}"


def _host_name(value: str) -> str:
    host = value.strip().lower()
    if host.startswith("["):
        return host.split("]", 1)[0].removeprefix("[")
    if host.count(":") == 1:
        return host.split(":", 1)[0]
    return host


def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Listen until the process is stopped. host must be this computer."""
    if host not in _LOCAL_HOSTS:
        raise ValueError("The page listens on this computer only.")
    httpd = ClipServer((host, port), ClipHandler)
    print(f"Video clipping: http://{host}:{port}/", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print(flush=True)
    finally:
        httpd.server_close()


def main(argv: list[str] | None = None) -> int:
    """Start the page. Return 0, or 2 when the address is refused."""
    parser = argparse.ArgumentParser(description="Open the video clipping page on this computer.")
    parser.add_argument("--host", default="127.0.0.1", help="Default: 127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    if args.host not in _LOCAL_HOSTS:
        print("The page listens on this computer only.", file=sys.stderr)
        return 2
    serve(args.host, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
