"""Read a media file with ffprobe. This does not write a new file."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from video_cliping.errors import FfmpegFailed, InputNotFound
from video_cliping.models import KeyPacket, MediaInfo, StreamInfo
from video_cliping.proc import CommandResult, run_command, stderr_tail
from video_cliping.tools import tool_path

PROBE_TIMEOUT_S = 60.0
Runner = Callable[..., CommandResult]


def inspect(
    path: Path,
    *,
    runner: Runner = run_command,
    timeout: float | None = PROBE_TIMEOUT_S,
) -> MediaInfo:
    """Return container and stream facts for path.

    Raises:
        InputNotFound: path is missing or is not a file.
        ToolMissing: ffprobe is not on PATH.
        FfmpegFailed: ffprobe failed or did not return JSON.
    """
    source = _existing_file(path)
    argv = [
        tool_path("ffprobe"),
        "-v",
        "error",
        "-hide_banner",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(source),
    ]
    result = runner(argv, timeout=timeout)
    _raise_if_failed(result, argv, "ffprobe failed.")
    return _media_from_json(source, result.stdout, argv)


def key_packets(
    path: Path,
    video_stream: int = 0,
    *,
    runner: Runner = run_command,
    timeout: float | None = PROBE_TIMEOUT_S,
) -> tuple[KeyPacket, ...]:
    """Return packet headers for one video stream.

    A packet whose flags contain K is a seek point. This reads headers, not pixels.

    Raises:
        InputNotFound: path is missing or is not a file.
        FfmpegFailed: ffprobe failed or did not return JSON.
    """
    if video_stream < 0:
        raise FfmpegFailed("video_stream must be zero or more.", [], "")
    source = _existing_file(path)
    argv = [
        tool_path("ffprobe"),
        "-v",
        "error",
        "-hide_banner",
        "-print_format",
        "json",
        "-select_streams",
        f"v:{video_stream}",
        "-show_packets",
        "-show_entries",
        "packet=pts_time,flags",
        str(source),
    ]
    result = runner(argv, timeout=timeout)
    _raise_if_failed(result, argv, "ffprobe failed while reading packets.")
    return _packets_from_json(result.stdout, argv)


def _existing_file(path: Path) -> Path:
    if "\n" in str(path) or "\r" in str(path):
        raise InputNotFound("Path must not contain a newline.")
    source = path.expanduser().resolve()
    if not source.is_file():
        raise InputNotFound(f"Input file not found: {source}")
    return source


def _raise_if_failed(result: CommandResult, argv: list[str], message: str) -> None:
    if result.returncode != 0:
        raise FfmpegFailed(message, argv, stderr_tail(result.stderr))


def _media_from_json(path: Path, raw: str, argv: list[str]) -> MediaInfo:
    payload = _load_json(raw, argv)
    fmt = payload.get("format") or {}
    streams = tuple(_stream(item) for item in payload.get("streams") or [])
    return MediaInfo(
        path=path,
        format_name=str(fmt.get("format_name") or ""),
        duration_s=_optional_float(fmt.get("duration")),
        size_bytes=_optional_int(fmt.get("size")) or 0,
        streams=streams,
    )


def _packets_from_json(raw: str, argv: list[str]) -> tuple[KeyPacket, ...]:
    payload = _load_json(raw, argv)
    packets = [
        KeyPacket(time_s=_optional_float(item.get("pts_time")), flags=str(item.get("flags") or ""))
        for item in payload.get("packets") or []
    ]
    return tuple(packets)


def _load_json(raw: str, argv: list[str]) -> dict:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise FfmpegFailed("ffprobe did not return JSON.", argv, stderr_tail(raw)) from exc
    if not isinstance(payload, dict):
        raise FfmpegFailed("ffprobe JSON was not an object.", argv, "")
    return payload


def _stream(item: dict) -> StreamInfo:
    tags = item.get("tags") or {}
    language = tags.get("language") if isinstance(tags, dict) else None
    return StreamInfo(
        index=int(item.get("index") or 0),
        codec_type=str(item.get("codec_type") or ""),
        codec_name=str(item.get("codec_name") or ""),
        width=_optional_int(item.get("width")),
        height=_optional_int(item.get("height")),
        sample_rate=_optional_int(item.get("sample_rate")),
        channels=_channel_count(item),
        language=str(language) if language else None,
    )


def _channel_count(item: dict) -> int | None:
    direct = _optional_int(item.get("channels"))
    if direct is not None:
        return direct
    layout = item.get("ch_layout")
    if isinstance(layout, dict):
        return _optional_int(layout.get("nb_channels"))
    return None


def _optional_float(value: object) -> float | None:
    if value is None or value == "" or value == "N/A":
        return None
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if number != number or number == float("inf"):
        return None
    return number


def _optional_int(value: object) -> int | None:
    number = _optional_float(value)
    if number is None:
        return None
    return int(number)
