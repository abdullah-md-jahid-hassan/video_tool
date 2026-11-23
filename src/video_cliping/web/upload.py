"""Read a multipart form and write the video to a file."""

from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

MAX_UPLOAD_BYTES = 32 * 1024 * 1024 * 1024
_TEXT_LIMIT = 64 * 1024
_CHUNK = 64 * 1024
_NAME_RE = re.compile(r"""(?:^|;)\s*name\s*=\s*(?:"([^"]*)"|([^";]+))""", re.IGNORECASE)
_FILE_RE = re.compile(r"""(?:^|;)\s*filename\s*=\s*(?:"([^"]*)"|([^";]+))""", re.IGNORECASE)
_FILE_STAR_RE = re.compile(r"""filename\*\s*=\s*(?:UTF-8|utf-8)''([^;\s]+)""", re.IGNORECASE)


class FormError(Exception):
    """The form body could not be used."""


@dataclass(frozen=True)
class ParsedForm:
    """Text fields plus the saved video."""

    fields: dict[str, str]
    filename: str
    upload_path: Path


def parse_form(stream, content_type: str, length: int, directory: Path) -> ParsedForm:
    """Parse one multipart body. The video is written under directory.

    Raises:
        FormError: The body is not a usable form, or it has no video.
    """
    if length < 0:
        raise FormError("The form has no length.")
    if length > MAX_UPLOAD_BYTES:
        raise FormError("That video is too large for this page.")
    boundary = _boundary(content_type)
    source = _Source(stream, length)
    return _parts(source, boundary, directory)


def _boundary(content_type: str) -> bytes:
    match = re.search(r"boundary=([^;]+)", content_type, re.IGNORECASE)
    if match is None:
        raise FormError("The form was not sent as a file upload.")
    raw = match.group(1).strip().strip('"')
    try:
        boundary = raw.encode("ascii")
    except UnicodeEncodeError as exc:
        raise FormError("The upload boundary is not valid.") from exc
    if not boundary or len(boundary) > 200:
        raise FormError("The upload boundary is not valid.")
    return boundary


def _parts(source: _Source, boundary: bytes, directory: Path) -> ParsedForm:
    marker = b"--" + boundary
    source.skip_until(marker)
    fields: dict[str, str] = {}
    upload: tuple[str, Path] | None = None
    while True:
        line = source.read_line()
        if line.startswith(b"--"):
            break
        headers = _headers(source)
        name, filename = _disposition(headers)
        if filename is None:
            fields[name] = _text_part(source, marker)
            continue
        path = _file_part(source, marker, directory, filename)
        upload = (filename, path)
    if upload is None or upload[1].stat().st_size == 0:
        raise FormError("Choose a video file.")
    return ParsedForm(fields, upload[0], upload[1])


def _headers(source: _Source) -> dict[str, str]:
    headers: dict[str, str] = {}
    while True:
        line = source.read_line().decode("utf-8", "replace").rstrip("\r\n")
        if line == "":
            return headers
        if ":" not in line:
            raise FormError("A form header is not valid.")
        key, value = line.split(":", 1)
        headers[key.lower()] = value.strip()


def _disposition(headers: dict[str, str]) -> tuple[str, str | None]:
    header = headers.get("content-disposition", "")
    name_match = _NAME_RE.search(header)
    if name_match is None:
        raise FormError("A form field has no name.")
    name = name_match.group(1) if name_match.group(1) is not None else name_match.group(2)
    star = _FILE_STAR_RE.search(header)
    if star is not None:
        from urllib.parse import unquote

        return name, unquote(star.group(1))
    file_match = _FILE_RE.search(header)
    if file_match is None:
        return name, None
    filename = file_match.group(1) if file_match.group(1) is not None else file_match.group(2)
    return name, filename


def _text_part(source: _Source, marker: bytes) -> str:
    chunks: list[bytes] = []
    size = 0

    def sink(data: bytes) -> None:
        nonlocal size
        size += len(data)
        if size > _TEXT_LIMIT:
            raise FormError("A form field is too long.")
        chunks.append(bytes(data))

    source.read_until(b"\r\n" + marker, sink)
    return b"".join(chunks).decode("utf-8", "replace")


def _file_part(source: _Source, marker: bytes, directory: Path, filename: str) -> Path:
    suffix = Path(filename).suffix.lower()
    if not re.fullmatch(r"\.[a-z0-9]{1,8}", suffix):
        suffix = ".bin"
    handle = tempfile.NamedTemporaryFile(delete=False, dir=directory, suffix=suffix)
    path = Path(handle.name)
    try:
        source.read_until(b"\r\n" + marker, handle.write)
    finally:
        handle.close()
    return path


class _Source:
    """A content-length limited stream with a small lookahead buffer."""

    def __init__(self, raw, length: int) -> None:
        self.raw = raw
        self.left = length
        self.buf = bytearray()

    def skip_until(self, marker: bytes) -> None:
        """Drop bytes up to and including the first marker."""
        while True:
            index = self.buf.find(marker)
            if index >= 0:
                del self.buf[: index + len(marker)]
                return
            if not self.left and len(self.buf) >= len(marker):
                raise FormError("The form is not a file upload.")
            if not self._fill():
                raise FormError("The form is not a file upload.")

    def read_line(self, limit: int = 8192) -> bytes:
        """Return one line, including its newline."""
        while b"\n" not in self.buf and len(self.buf) < limit:
            if not self._fill():
                break
        newline = self.buf.find(b"\n")
        if newline < 0:
            raise FormError("A form header is too long.")
        line = bytes(self.buf[: newline + 1])
        del self.buf[: newline + 1]
        return line

    def read_until(self, marker: bytes, sink) -> None:
        """Pass bytes before marker to sink, then consume marker."""
        keep = len(marker) - 1
        while True:
            index = self.buf.find(marker)
            if index >= 0:
                sink(self.buf[:index])
                del self.buf[: index + len(marker)]
                return
            if len(self.buf) > keep:
                sink(self.buf[:-keep])
                del self.buf[:-keep]
            if not self._fill():
                raise FormError("The form ended early.")

    def _fill(self) -> bool:
        if self.left <= 0:
            return False
        piece = self.raw.read(min(_CHUNK, self.left))
        if not piece:
            self.left = 0
            return False
        self.left -= len(piece)
        self.buf.extend(piece)
        return True
