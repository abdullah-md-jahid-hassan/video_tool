"""Facts about a file, and the request a caller makes for one cut."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from video_cliping.times import Time


@dataclass(frozen=True)
class StreamInfo:
    """One stream inside a media file."""

    index: int
    codec_type: str
    codec_name: str
    width: int | None = None
    height: int | None = None
    sample_rate: int | None = None
    channels: int | None = None
    language: str | None = None


@dataclass(frozen=True)
class MediaInfo:
    """What a read of one file reported."""

    path: Path
    format_name: str
    duration_s: float | None
    size_bytes: int
    streams: tuple[StreamInfo, ...]


@dataclass(frozen=True)
class KeyPacket:
    """One video packet header. A flags string containing K is a seek point."""

    time_s: float | None
    flags: str


@dataclass(frozen=True)
class ClipRequest:
    """One cut. start None means 0. end None means the end of the file.

    maps None means every stream. exact True is refused: an exact frame
    needs a new encode.
    """

    source: Path
    dest: Path
    start: Time | None = None
    end: Time | None = None
    maps: tuple[str, ...] | None = None
    drop_rejected_streams: bool = False
    faststart: bool = False
    overwrite: bool = False
    exact: bool = False


@dataclass(frozen=True)
class ClipReport:
    """What one successful cut wrote."""

    source: Path
    dest: Path
    requested_start_s: float
    requested_end_s: float | None
    output_duration_s: float
    output_size_bytes: int
    streams_copied: tuple[StreamInfo, ...]
    streams_dropped: tuple[StreamInfo, ...]
    bitstream_filters: tuple[str, ...]
    command: tuple[str, ...]
