"""Serve the video clipping page on this computer only."""

from __future__ import annotations

import argparse
import secrets
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from video_cliping.web.page import clip_page, home_page, message_page

_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
_MAX_TOKENS = 50


class ClipServer(ThreadingHTTPServer):
    """HTTP server that remembers the form tokens for this process."""

    def __init__(self, address: tuple[str, int], handler: type[BaseHTTPRequestHandler]) -> None:
        super().__init__(address, handler)
        self.tokens: list[str] = []
        self.token_lock = threading.Lock()

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
    """GET / shows the tool. GET /clip shows the form."""

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
        self._html(404, message_page("That page is not here."))

    def log_message(self, fmt: str, *args: object) -> None:
        """Write one request line to stderr. The body is not logged."""
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

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
