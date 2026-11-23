"""Cut one time range by copying packets. No new encode."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from video_cliping.checks import assert_output_ok
from video_cliping.command import build_clip_command, validate_maps
from video_cliping.errors import (
    BadRange,
    ContainerRejected,
    EngineError,
    Exists,
    FfmpegFailed,
    InputNotFound,
    OutsideEngine,
    SamePath,
)
from video_cliping.models import ClipReport, ClipRequest, MediaInfo, StreamInfo
from video_cliping.probe import PROBE_TIMEOUT_S, Runner, inspect
from video_cliping.proc import CommandResult, run_command, stderr_tail
from video_cliping.times import Time, parse_seconds
from video_cliping.tools import require_tools

_KIND = {"v": "video", "a": "audio", "s": "subtitle", "d": "data", "t": "attachment"}
_LETTER = {value: key for key, value in _KIND.items()}
_REJECT_MARKERS = (
    "codec not currently supported in container",
    "could not find tag for codec",
    "incorrect codec parameters",
)
_OUTPUT_STREAM_RE = re.compile(r"output stream\s+\d+:(\d+)", re.IGNORECASE)
_CODEC_RE = re.compile(r"Could not find tag for codec\s+(\w+)", re.IGNORECASE)
_FASTSTART_SUFFIXES = {".mp4", ".mov"}


@dataclass(frozen=True)
class _Rejection:
    indexes: tuple[int, ...]
    codecs: tuple[str, ...]


def clip(
    request: ClipRequest,
    *,
    runner: Runner = run_command,
    probe_timeout: float | None = PROBE_TIMEOUT_S,
    ffmpeg_timeout: float | None = None,
) -> ClipReport:
    """Copy one range from request.source to request.dest.

    Raises:
        OutsideEngine: request.exact is true.
        InputNotFound: The source is missing.
        SamePath: Source and dest are the same file.
        Exists: Dest exists and overwrite is false.
        BadRange: The times are empty, backwards, or past the file.
        ContainerRejected: The container refused a stream.
        FfmpegFailed: ffmpeg exited non-zero for another reason.
        OutputCheckFailed: The new file failed the duration or size check.
    """
    if request.exact:
        raise OutsideEngine("An exact frame needs a new encode. This package copies packets only.")
    source, dest = _paths(request)
    validate_maps(request.maps)
    _faststart_ok(request.faststart, dest)
    ffmpeg, _ffprobe = require_tools()
    info = inspect(source, runner=runner, timeout=probe_timeout)
    start_s, end_s = _range(request.start, request.end, info.duration_s)
    kept = _select(info, request.maps)
    return _copy(
        request,
        info,
        kept,
        ffmpeg,
        start_s,
        end_s,
        runner,
        probe_timeout,
        ffmpeg_timeout,
    )


def _paths(request: ClipRequest) -> tuple[Path, Path]:
    source = _plain_path(request.source)
    dest = _plain_path(request.dest)
    if not source.is_file():
        raise InputNotFound(f"Input file not found: {source}")
    if source == dest:
        raise SamePath("Output path is the same file as the input.")
    if dest.is_dir():
        raise EngineError("Output path is a folder.")
    if not dest.parent.is_dir():
        raise EngineError(f"Destination folder does not exist: {dest.parent}")
    if dest.exists() and not request.overwrite:
        raise Exists(f"Output already exists: {dest}")
    return source, dest


def _plain_path(path: Path) -> Path:
    if "\n" in str(path) or "\r" in str(path):
        raise EngineError("Path must not contain a newline.")
    return path.expanduser().resolve()


def _faststart_ok(faststart: bool, dest: Path) -> None:
    if faststart and dest.suffix.lower() not in _FASTSTART_SUFFIXES:
        raise EngineError("faststart applies to .mp4 and .mov output only.")


def _range(start: Time | None, end: Time | None, duration: float | None) -> tuple[float, float | None]:
    start_s = 0.0 if start is None else parse_seconds(start)
    end_s = None if end is None else parse_seconds(end)
    if end_s is not None and start_s >= end_s:
        raise BadRange("Start must be before end.")
    _range_inside_file(start, end, start_s, end_s, duration)
    return start_s, end_s


def _range_inside_file(
    start: Time | None,
    end: Time | None,
    start_s: float,
    end_s: float | None,
    duration: float | None,
) -> None:
    timed = start_s > 0 or end is not None
    if duration is None or duration <= 0:
        if timed:
            raise BadRange("The file has no duration, so a time range cannot be checked.")
        return
    if start_s >= duration or (end_s is not None and end_s > duration):
        raise BadRange("The time range is outside the file.")


def _select(info: MediaInfo, maps: tuple[str, ...] | None) -> tuple[StreamInfo, ...]:
    if maps is None:
        return info.streams
    chosen: list[StreamInfo] = []
    for spec in maps:
        _kind, ordinal = _spec_parts(spec)
        matches = [stream for stream in info.streams if stream.codec_type == _kind]
        if ordinal >= len(matches):
            raise EngineError(f"Stream {spec} is not in the file.")
        chosen.append(matches[ordinal])
    return tuple(chosen)


def _spec_parts(spec: str) -> tuple[str, int]:
    _file, letter, ordinal = spec.split(":")
    return _KIND[letter], int(ordinal)


def _copy(
    request: ClipRequest,
    info: MediaInfo,
    kept: tuple[StreamInfo, ...],
    ffmpeg: str,
    start_s: float,
    end_s: float | None,
    runner: Runner,
    probe_timeout: float | None,
    ffmpeg_timeout: float | None,
) -> ClipReport:
    outcome = _run(request, info, kept, ffmpeg, (), runner, ffmpeg_timeout)
    outcome = _maybe_retry(request, info, outcome, ffmpeg, runner, ffmpeg_timeout)
    if outcome.result.returncode != 0:
        _delete(outcome.dest)
        _raise_failure(outcome)
    return _checked_report(request, info, outcome, start_s, end_s, runner, probe_timeout)


@dataclass(frozen=True)
class _Run:
    dest: Path
    command: list[str]
    result: CommandResult
    kept: tuple[StreamInfo, ...]
    dropped: tuple[StreamInfo, ...]
    filters: tuple[str, ...]
    tried_filter: bool
    tried_drop: bool


def _run(
    request: ClipRequest,
    info: MediaInfo,
    kept: tuple[StreamInfo, ...],
    ffmpeg: str,
    filters: tuple[str, ...],
    runner: Runner,
    timeout: float | None,
    *,
    maps: tuple[str, ...] | None = None,
    dropped: tuple[StreamInfo, ...] = (),
    tried_filter: bool = False,
    tried_drop: bool = False,
) -> _Run:
    dest = _plain_path(request.dest)
    chosen_maps = request.maps if maps is None else maps
    command = build_clip_command(
        ffmpeg,
        info.path,
        dest,
        request.start,
        request.end,
        chosen_maps,
        faststart=request.faststart,
        bitstream_filters=filters,
    )
    result = runner(command, timeout=timeout)
    return _Run(dest, command, result, kept, dropped, filters, tried_filter, tried_drop)


def _maybe_retry(
    request: ClipRequest,
    info: MediaInfo,
    outcome: _Run,
    ffmpeg: str,
    runner: Runner,
    timeout: float | None,
) -> _Run:
    if outcome.result.returncode == 0:
        return outcome
    rejection = _rejection(outcome.result.stderr)
    if rejection is None:
        return outcome
    if not outcome.tried_filter:
        filters = _filters_for(rejection, info.streams, outcome.dest)
        if filters:
            _delete(outcome.dest)
            outcome = _run(
                request,
                info,
                outcome.kept,
                ffmpeg,
                filters,
                runner,
                timeout,
                dropped=outcome.dropped,
                tried_filter=True,
            )
            if outcome.result.returncode == 0:
                return outcome
            rejection = _rejection(outcome.result.stderr) or rejection
    if request.drop_rejected_streams and not outcome.tried_drop:
        return _drop_and_rerun(request, info, outcome, rejection, ffmpeg, runner, timeout)
    return outcome


def _drop_and_rerun(
    request: ClipRequest,
    info: MediaInfo,
    outcome: _Run,
    rejection: _Rejection,
    ffmpeg: str,
    runner: Runner,
    timeout: float | None,
) -> _Run:
    kept, dropped_now = _without_rejected(outcome.kept, rejection)
    if not kept or len(kept) == len(outcome.kept):
        return outcome
    _delete(outcome.dest)
    maps = tuple(_spec_for(stream, info.streams) for stream in kept)
    retried = _run(
        request,
        info,
        kept,
        ffmpeg,
        outcome.filters,
        runner,
        timeout,
        maps=maps,
        dropped=outcome.dropped + dropped_now,
        tried_filter=True,
        tried_drop=True,
    )
    return retried


def _checked_report(
    request: ClipRequest,
    info: MediaInfo,
    outcome: _Run,
    start_s: float,
    end_s: float | None,
    runner: Runner,
    probe_timeout: float | None,
) -> ClipReport:
    try:
        output = inspect(outcome.dest, runner=runner, timeout=probe_timeout)
        assert_output_ok(info, output, start_s, end_s, outcome.kept, outcome.command)
    except Exception:
        _delete(outcome.dest)
        raise
    return ClipReport(
        source=info.path,
        dest=outcome.dest,
        requested_start_s=start_s,
        requested_end_s=end_s,
        output_duration_s=output.duration_s or 0.0,
        output_size_bytes=output.size_bytes,
        streams_copied=output.streams,
        streams_dropped=outcome.dropped,
        bitstream_filters=outcome.filters,
        command=tuple(outcome.command),
    )


def _raise_failure(outcome: _Run) -> None:
    tail = stderr_tail(outcome.result.stderr)
    if _rejection(outcome.result.stderr) is not None:
        raise ContainerRejected("The destination container refused a stream.", outcome.command, tail)
    raise FfmpegFailed("ffmpeg failed.", outcome.command, tail)


def _rejection(stderr: str) -> _Rejection | None:
    if not any(marker in stderr.lower() for marker in _REJECT_MARKERS):
        return None
    indexes = tuple(int(match) for match in _OUTPUT_STREAM_RE.findall(stderr))
    codecs = tuple(_CODEC_RE.findall(stderr))
    return _Rejection(indexes, codecs)


def _filters_for(rejection: _Rejection, streams: tuple[StreamInfo, ...], dest: Path) -> tuple[str, ...]:
    codecs = {name.lower() for name in rejection.codecs}
    suffix = dest.suffix.lower()
    present = {stream.codec_name.lower() for stream in streams}
    chosen: list[str] = []
    if "aac" in codecs and "aac" in present and suffix in {".mp4", ".mov", ".m4a", ".flv"}:
        chosen.append("aac_adtstoasc")
    if "h264" in codecs and "h264" in present and suffix in {".ts", ".m2ts", ".mts"}:
        chosen.append("h264_mp4toannexb")
    if {"hevc", "h265"} & codecs and {"hevc", "h265"} & present and suffix in {".ts", ".m2ts", ".mts"}:
        chosen.append("hevc_mp4toannexb")
    return tuple(chosen)


def _without_rejected(
    kept: tuple[StreamInfo, ...],
    rejection: _Rejection,
) -> tuple[tuple[StreamInfo, ...], tuple[StreamInfo, ...]]:
    indexes = set(rejection.indexes)
    codecs = {name.lower() for name in rejection.codecs}
    dropped = [
        stream
        for index, stream in enumerate(kept)
        if index in indexes or stream.codec_name.lower() in codecs
    ]
    rejected = {stream.index for stream in dropped}
    return tuple(stream for stream in kept if stream.index not in rejected), tuple(dropped)


def _spec_for(stream: StreamInfo, streams: tuple[StreamInfo, ...]) -> str:
    letter = _LETTER[stream.codec_type]
    same = [item for item in streams if item.codec_type == stream.codec_type]
    return f"0:{letter}:{same.index(stream)}"


def _delete(path: Path) -> None:
    path.unlink(missing_ok=True)
