"""Submitting the form calls clip() with the engine's options."""

from __future__ import annotations

import re
import threading
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

import pytest

from video_cliping.errors import BadRange
from video_cliping.models import ClipReport, ClipRequest, StreamInfo
from video_cliping.web.server import ClipHandler, ClipServer
from video_cliping.web.upload import parse_form

_OPENER = build_opener(ProxyHandler({}))
_BOUNDARY = "----clipboundary"


@pytest.fixture
def page_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    httpd = ClipServer(("127.0.0.1", 0), ClipHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def test_parse_form_keeps_the_video_bytes(tmp_path: Path) -> None:
    body = _body({"start": "00:00:01"}, "holiday.mp4", b"video-bytes")
    parsed = parse_form(BytesIO(body), f"multipart/form-data; boundary={_BOUNDARY}", len(body), tmp_path)
    assert parsed.fields["start"] == "00:00:01"
    assert parsed.filename == "holiday.mp4"
    assert parsed.upload_path.read_bytes() == b"video-bytes"


def test_post_uses_default_folder_and_engine_options(page_server: ClipServer, tmp_path: Path) -> None:
    seen: dict[str, ClipRequest] = {}

    def fake(request: ClipRequest) -> ClipReport:
        seen["request"] = request
        assert request.source.is_file()
        return _report(request.dest)

    page_server.clip_fn = fake
    status, body = _post(
        page_server,
        {
            "start": "00:00:01",
            "end": "2",
            "maps": "0:v:0\n0:a:1",
            "dest_dir": "",
            "overwrite": "on",
            "faststart": "on",
            "drop_rejected_streams": "on",
        },
        "my clip.mp4",
        b"abcd",
    )
    assert status == 200
    request = seen["request"]
    assert request.dest == (tmp_path / "outputs" / "cliping" / "my_clip.mp4").resolve()
    assert request.start == "00:00:01"
    assert request.end == "2"
    assert request.maps == ("0:v:0", "0:a:1")
    assert request.overwrite is True
    assert request.faststart is True
    assert request.drop_rejected_streams is True
    assert "Wrote" in body
    assert request.dest.is_dir() is False
    assert request.dest.parent.is_dir()


def test_bad_time_is_shown_on_the_form(page_server: ClipServer) -> None:
    def fake(request: ClipRequest) -> ClipReport:
        raise BadRange("Start must be before end.")

    page_server.clip_fn = fake
    status, body = _post(page_server, {"start": "5", "end": "1"}, "holiday.mp4", b"abcd")
    assert status == 400
    assert "Start must be before end." in body
    assert 'value="5"' in body


def test_reused_token_is_refused(page_server: ClipServer) -> None:
    token = _token(page_server)
    fields = {"csrf": token}
    first = _post(page_server, fields, "holiday.mp4", b"abcd", token=token)
    assert first[0] == 400
    status, body = _post(page_server, fields, "holiday.mp4", b"abcd", token=token)
    assert status == 403
    assert "expired" in body


def test_empty_file_asks_for_a_video(page_server: ClipServer) -> None:
    status, body = _post(page_server, {}, "holiday.mp4", b"")
    assert status == 400
    assert "Choose a video file." in body


def test_foreign_origin_is_refused(page_server: ClipServer) -> None:
    status, body = _post(page_server, {}, "holiday.mp4", b"abcd", origin="http://evil.example")
    assert status == 403
    assert "this computer" in body


def _post(
    httpd: ClipServer,
    fields: dict[str, str],
    filename: str,
    payload: bytes,
    *,
    token: str | None = None,
    origin: str | None = None,
) -> tuple[int, str]:
    if token is None:
        token = _token(httpd)
    body = _body({**fields, "csrf": token}, filename, payload)
    port = httpd.server_address[1]
    headers = {"Content-Type": f"multipart/form-data; boundary={_BOUNDARY}"}
    if origin is not None:
        headers["Origin"] = origin
    request = Request(f"http://127.0.0.1:{port}/clip", data=body, headers=headers, method="POST")
    try:
        with _OPENER.open(request, timeout=5) as response:
            return response.status, response.read().decode()
    except HTTPError as exc:
        return exc.code, exc.read().decode()


def _token(httpd: ClipServer) -> str:
    port = httpd.server_address[1]
    with _OPENER.open(f"http://127.0.0.1:{port}/clip", timeout=5) as response:
        body = response.read().decode()
    match = re.search(r'name="csrf" value="([^"]+)"', body)
    assert match is not None
    return match.group(1)


def _body(fields: dict[str, str], filename: str, payload: bytes) -> bytes:
    chunks: list[bytes] = []
    boundary = _BOUNDARY.encode()
    for name, value in fields.items():
        chunks.append(b"--" + boundary + b"\r\n")
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        chunks.append(value.encode() + b"\r\n")
    chunks.append(b"--" + boundary + b"\r\n")
    header = f'Content-Disposition: form-data; name="video"; filename="{filename}"\r\n'
    chunks.append(header.encode())
    chunks.append(b"Content-Type: application/octet-stream\r\n\r\n")
    chunks.append(payload)
    chunks.append(b"\r\n--" + boundary + b"--\r\n")
    return b"".join(chunks)


def _report(dest: Path) -> ClipReport:
    return ClipReport(
        source=Path("in.mp4"),
        dest=dest,
        requested_start_s=1,
        requested_end_s=2,
        output_duration_s=1.5,
        output_size_bytes=10,
        streams_copied=(StreamInfo(0, "video", "h264"),),
        streams_dropped=(),
        bitstream_filters=(),
        command=("ffmpeg",),
    )
