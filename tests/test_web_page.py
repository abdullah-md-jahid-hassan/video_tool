"""The local page lists one tool and shows the clip form."""

from __future__ import annotations

import threading
from urllib.request import Request, build_opener, ProxyHandler

import pytest

from video_cliping.web.page import DEFAULT_DEST_DIR
from video_cliping.web.server import ClipHandler, ClipServer

_OPENER = build_opener(ProxyHandler({}))


@pytest.fixture
def page_server():
    httpd = ClipServer(("127.0.0.1", 0), ClipHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def _get(httpd: ClipServer, path: str) -> tuple[int, str]:
    port = httpd.server_address[1]
    request = Request(f"http://127.0.0.1:{port}{path}")
    try:
        with _OPENER.open(request, timeout=5) as response:
            return response.status, response.read().decode()
    except Exception as exc:
        status = getattr(exc, "code", None)
        body = exc.read().decode() if hasattr(exc, "read") else ""
        if status is None:
            raise
        return status, body


def test_home_has_one_tool(page_server: ClipServer) -> None:
    status, body = _get(page_server, "/")
    assert status == 200
    assert body.count('href="/clip"') == 1
    assert "Video clipping" in body


def test_clip_form_has_the_engine_choices(page_server: ClipServer) -> None:
    status, body = _get(page_server, "/clip")
    assert status == 200
    assert 'name="source"' in body
    assert "Choose a file" in body
    assert "Choose a folder" in body
    assert 'name="start"' in body
    assert 'name="end"' in body
    assert 'name="maps"' in body
    assert 'name="dest_dir" value=""' in body
    assert 'name="same_folder"' in body
    assert DEFAULT_DEST_DIR in body
    assert 'name="overwrite"' in body
    assert 'name="faststart"' in body
    assert 'name="drop_rejected_streams"' in body
    assert 'name="exact"' in body
    assert 'name="csrf"' in body
    assert page_server.tokens


def test_unknown_page_is_404(page_server: ClipServer) -> None:
    status, body = _get(page_server, "/other")
    assert status == 404
    assert "not here" in body


def test_server_refuses_a_public_host() -> None:
    from video_cliping.web.server import main

    assert main(["--host", "0.0.0.0"]) == 2
