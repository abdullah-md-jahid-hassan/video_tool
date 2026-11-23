"""Serve the video clipping page on this computer only."""

from __future__ import annotations

import argparse
import secrets
import sys
import tempfile
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from video_cliping.cut import clip as default_clip
from video_cliping.errors import EngineError
from video_cliping.web.job import clip_from_form, failure_notice, form_state, success_notice
from video_cliping.web.page import clip_page, home_page, message_page
from video_cliping.web.upload import MAX_UPLOAD_BYTES, FormError, ParsedForm, parse_form

_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
_MAX_TOKENS = 50


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
        path = urlparse(self.path).path
        if path == "/":
            self._html(200, home_page())
            return
        if path == "/clip":
            self._html(200, clip_page(self.server.issue_token()))
            return
        self._html(404, message_page("That page is not here."))

    def do_POST(self) -> None:  # noqa: N802
        self.close_connection = True
        if urlparse(self.path).path != "/clip":
            self._html(404, message_page("That page is not here."))
            return
        if not _same_computer(self.headers.get("Host", ""), self.headers.get("Origin")):
            self._html(403, message_page("This page is only for this computer."))
            return
        length = self._content_length()
        if length is None:
            return
        self._run_clip(length)

    def log_message(self, fmt: str, *args: object) -> None:
        """Write one request line to stderr. The body is not logged."""
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _content_length(self) -> int | None:
        raw = self.headers.get("Content-Length")
        if raw is None or not raw.isdigit():
            self._html(400, message_page("The form has no length."))
            return None
        length = int(raw)
        if length > MAX_UPLOAD_BYTES:
            self._html(400, message_page("That video is too large for this page."))
            return None
        return length

    def _run_clip(self, length: int) -> None:
        try:
            with tempfile.TemporaryDirectory(prefix="video-clip-") as folder:
                parsed = parse_form(
                    self.rfile,
                    self.headers.get("Content-Type", ""),
                    length,
                    Path(folder),
                )
                self._finish_clip(parsed)
        except FormError as exc:
            self._html(400, message_page(str(exc)))
        except Exception:
            traceback.print_exc()
            self._html(500, message_page("The cut did not finish."))

    def _finish_clip(self, parsed: ParsedForm) -> None:
        if not self.server.take_token(parsed.fields.get("csrf", "")):
            self._html(403, message_page("The form expired. Open Video clipping again."))
            return
        state = form_state(parsed.fields)
        try:
            report = clip_from_form(parsed, self.server.clip_fn)
        except EngineError as exc:
            self._html(400, clip_page(self.server.issue_token(), state, failure_notice(exc)))
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


def _same_computer(host: str, origin: str | None) -> bool:
    if _host_name(host) not in _LOCAL_HOSTS:
        return False
    if origin is None:
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
