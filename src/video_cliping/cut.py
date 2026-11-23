"""Cut one time range by copying packets with PyAV. No new encode."""

from __future__ import annotations

import re
from pathlib import Path

import av

from video_cliping.checks import assert_output_ok
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
from video_cliping.probe import inspect
from video_cliping.times import Time, parse_seconds

_KIND = {"v": "video", "a": "audio", "s": "subtitle", "d": "data", "t": "attachment"}
_MAP_RE = re.compile(r"^0:(v|a|s|d|t):\d+$")
_FASTSTART_SUFFIXES = {".mp4", ".mov"}


def clip(request: ClipRequest) -> ClipReport:
    """Copy one range from request.source to request.dest.

    Raises:
        OutsideEngine: request.exact is true.
        InputNotFound: The source is missing.
        SamePath: Source and dest are the same file.
        Exists: Dest exists and overwrite is false.
        BadRange: The times are empty, backwards, or past the file.
        ContainerRejected: The container refused a stream.
        FfmpegFailed: The copy failed.
        OutputCheckFailed: The new file failed the duration or size check.
    """
    if request.exact:
        raise OutsideEngine("An exact frame needs a new encode. This package copies packets only.")
    source, dest = _paths(request)
    _validate_maps(request.maps)
    _faststart_ok(request.faststart, dest)
    info = inspect(source)
    start_s, end_s = _range(request.start, request.end, info.duration_s)
    kept = _select(info, request.maps)
    copied, dropped = _remux(request, source, dest, start_s, end_s, kept)
    return _report(request, info, dest, start_s, end_s, copied, dropped)


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


def _validate_maps(maps: tuple[str, ...] | None) -> None:
    if maps is None:
        return
    if not maps:
        raise EngineError("maps is empty.")
    for spec in maps:
        if _MAP_RE.fullmatch(spec) is None:
            raise EngineError(f"Map must look like 0:v:0, not {spec!r}.")


def _faststart_ok(faststart: bool, dest: Path) -> None:
    if faststart and dest.suffix.lower() not in _FASTSTART_SUFFIXES:
        raise EngineError("faststart applies to .mp4 and .mov output only.")


def _range(start: Time | None, end: Time | None, duration: float | None) -> tuple[float, float | None]:
    start_s = 0.0 if start is None else parse_seconds(start)
    end_s = None if end is None else parse_seconds(end)
    if end_s is not None and start_s >= end_s:
        raise BadRange("Start must be before end.")
    if duration is None or duration <= 0:
        if start_s > 0 or end is not None:
            raise BadRange("The file has no duration, so a time range cannot be checked.")
        return start_s, end_s
    if start_s >= duration or (end_s is not None and end_s > duration):
        raise BadRange("The time range is outside the file.")
    return start_s, end_s


def _select(info: MediaInfo, maps: tuple[str, ...] | None) -> tuple[StreamInfo, ...]:
    if maps is None:
        return info.streams
    chosen: list[StreamInfo] = []
    for spec in maps:
        _file, letter, number = spec.split(":")
        kind = _KIND[letter]
        matches = [stream for stream in info.streams if stream.codec_type == kind]
        ordinal = int(number)
        if ordinal >= len(matches):
            raise EngineError(f"Stream {spec} is not in the file.")
        chosen.append(matches[ordinal])
    return tuple(chosen)


def _remux(
    request: ClipRequest,
    source: Path,
    dest: Path,
    start_s: float,
    end_s: float | None,
    kept: tuple[StreamInfo, ...],
) -> tuple[tuple[StreamInfo, ...], tuple[StreamInfo, ...]]:
    options = {"movflags": "+faststart"} if request.faststart else None
    try:
        with av.open(source) as inp, av.open(dest, "w", options=options) as out:
            by_index = {stream.index: stream for stream in inp.streams}
            chosen = [by_index[info.index] for info in kept]
            mapping, copied, dropped = _add_outputs(out, chosen, kept, request.drop_rejected_streams)
            _mux_range(inp, out, mapping, start_s, end_s)
            return copied, dropped
    except ContainerRejected:
        dest.unlink(missing_ok=True)
        raise
    except av.error.FFmpegError as exc:
        dest.unlink(missing_ok=True)
        raise FfmpegFailed("The cut failed.", ["av", str(source), str(dest)], str(exc)) from exc


def _add_outputs(
    output: av.container.OutputContainer,
    streams: list[av.stream.Stream],
    infos: tuple[StreamInfo, ...],
    drop: bool,
) -> tuple[dict[av.stream.Stream, av.stream.Stream], tuple[StreamInfo, ...], tuple[StreamInfo, ...]]:
    mapping: dict[av.stream.Stream, av.stream.Stream] = {}
    copied: list[StreamInfo] = []
    dropped: list[StreamInfo] = []
    for stream, info in zip(streams, infos, strict=True):
        try:
            mapping[stream] = output.add_stream_from_template(stream)
        except av.error.FFmpegError as exc:
            if not drop:
                raise ContainerRejected(
                    "The destination container refused a stream.",
                    ["av", info.codec_name],
                    str(exc),
                ) from exc
            dropped.append(info)
            continue
        copied.append(info)
    if not copied:
        raise ContainerRejected("The destination container refused every stream.", ["av"], "")
    return mapping, tuple(copied), tuple(dropped)


def _mux_range(
    inp: av.container.InputContainer,
    out: av.container.OutputContainer,
    mapping: dict[av.stream.Stream, av.stream.Stream],
    start_s: float,
    end_s: float | None,
) -> None:
    streams = list(mapping)
    if start_s > 0:
        inp.seek(int(start_s * av.time_base), backward=True, any_frame=False)
    zeros: dict[int, int] = {}
    finished: set[int] = set()
    for packet in inp.demux(*streams):
        if packet.size == 0:
            continue
        if _past_end(packet, end_s, finished):
            if len(finished) == len(streams):
                break
            continue
        _shift(packet, zeros)
        packet.stream = mapping[packet.stream]
        out.mux(packet)


def _past_end(packet: av.packet.Packet, end_s: float | None, finished: set[int]) -> bool:
    if end_s is None:
        return False
    seconds = _seconds(packet)
    if seconds is None or seconds < end_s:
        return False
    finished.add(packet.stream.index)
    return True


def _seconds(packet: av.packet.Packet) -> float | None:
    stamp = packet.pts if packet.pts is not None else packet.dts
    if stamp is None:
        return None
    return float(stamp * packet.stream.time_base)


def _shift(packet: av.packet.Packet, zeros: dict[int, int]) -> None:
    stamp = packet.pts if packet.pts is not None else packet.dts
    if stamp is None:
        return
    origin = zeros.setdefault(packet.stream.index, stamp)
    if packet.pts is not None:
        packet.pts -= origin
    if packet.dts is not None:
        packet.dts -= origin


def _report(
    request: ClipRequest,
    info: MediaInfo,
    dest: Path,
    start_s: float,
    end_s: float | None,
    copied: tuple[StreamInfo, ...],
    dropped: tuple[StreamInfo, ...],
) -> ClipReport:
    command = ["av", str(info.path), str(dest)]
    try:
        output = inspect(dest)
        assert_output_ok(info, output, start_s, end_s, copied, command)
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    return ClipReport(
        source=info.path,
        dest=dest,
        requested_start_s=start_s,
        requested_end_s=end_s,
        output_duration_s=output.duration_s or 0.0,
        output_size_bytes=output.size_bytes,
        streams_copied=output.streams,
        streams_dropped=dropped,
        bitstream_filters=(),
        command=tuple(command),
    )
