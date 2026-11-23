"""Decide if a finished copy matches the range that was asked for.

Key packets are not scanned on the cut path. The lead-in allowance is
therefore 30 seconds, which is the contract for an unscanned cut.
"""

from __future__ import annotations

from video_cliping.errors import OutputCheckFailed
from video_cliping.models import MediaInfo, StreamInfo

PACKET_SLACK_S = 0.5
UNSCANNED_LEAD_IN_S = 30.0


def assert_output_ok(
    source: MediaInfo,
    output: MediaInfo,
    start_s: float,
    end_s: float | None,
    kept: tuple[StreamInfo, ...],
    command: list[str],
) -> None:
    """Raise OutputCheckFailed when duration, size, or streams are wrong."""
    duration = output.duration_s
    if duration is None or duration <= 0:
        raise OutputCheckFailed("Output duration is missing or zero.", command)
    _check_duration(duration, start_s, end_s, source.duration_s, command)
    _check_size(source, output, start_s, end_s, command)
    _check_types(kept, output, command)


def is_partial_range(start_s: float, end_s: float | None, duration_s: float | None) -> bool:
    """True when the ask is not the whole file."""
    if duration_s is None:
        return False
    if start_s > PACKET_SLACK_S:
        return True
    if end_s is None:
        return False
    return end_s < duration_s - PACKET_SLACK_S


def _check_duration(
    actual: float,
    start_s: float,
    end_s: float | None,
    source_duration: float | None,
    command: list[str],
) -> None:
    asked = _asked_length(start_s, end_s, source_duration)
    if asked is None:
        return
    if actual < asked - PACKET_SLACK_S:
        raise OutputCheckFailed("Output is shorter than the requested range.", command)
    if actual > asked + UNSCANNED_LEAD_IN_S:
        raise OutputCheckFailed("Output is longer than the keyframe allowance.", command)


def _check_size(
    source: MediaInfo,
    output: MediaInfo,
    start_s: float,
    end_s: float | None,
    command: list[str],
) -> None:
    if output.size_bytes <= 0:
        raise OutputCheckFailed("Output file is empty.", command)
    partial = is_partial_range(start_s, end_s, source.duration_s)
    if partial and output.size_bytes >= source.size_bytes:
        raise OutputCheckFailed("Output is not smaller than the source.", command)


def _check_types(
    kept: tuple[StreamInfo, ...],
    output: MediaInfo,
    command: list[str],
) -> None:
    have = {stream.codec_type for stream in output.streams}
    missing = sorted({stream.codec_type for stream in kept} - have)
    if missing:
        raise OutputCheckFailed("Output is missing stream types: " + ", ".join(missing) + ".", command)


def _asked_length(start_s: float, end_s: float | None, duration_s: float | None) -> float | None:
    if end_s is None:
        if duration_s is None:
            return None
        return duration_s - start_s
    return end_s - start_s
