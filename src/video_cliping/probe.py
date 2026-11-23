"""Read a media file with PyAV. This does not write a new file."""

from __future__ import annotations

from pathlib import Path

import av

from video_cliping.errors import EngineError, FfmpegFailed, InputNotFound
from video_cliping.models import KeyPacket, MediaInfo, StreamInfo


def inspect(path: Path) -> MediaInfo:
    """Return container and stream facts for path.

    Raises:
        InputNotFound: path is missing or is not a file.
        FfmpegFailed: The file is not a readable media file.
    """
    source = _existing_file(path)
    try:
        with av.open(source) as container:
            return _media(source, container)
    except av.error.FFmpegError as exc:
        raise FfmpegFailed("The file could not be read.", ["av", str(source)], str(exc)) from exc


def key_packets(path: Path, video_stream: int = 0) -> tuple[KeyPacket, ...]:
    """Return video packet headers. A flags string containing K is a key packet.

    Raises:
        InputNotFound: path is missing or is not a file.
        EngineError: video_stream does not exist.
        FfmpegFailed: The file is not a readable media file.
    """
    source = _existing_file(path)
    try:
        with av.open(source) as container:
            return _keys(container, video_stream)
    except av.error.FFmpegError as exc:
        raise FfmpegFailed("The file could not be read.", ["av", str(source)], str(exc)) from exc


def _existing_file(path: Path) -> Path:
    if "\n" in str(path) or "\r" in str(path):
        raise EngineError("Path must not contain a newline.")
    source = path.expanduser().resolve()
    if not source.is_file():
        raise InputNotFound(f"Input file not found: {source}")
    return source


def _media(source: Path, container: av.container.InputContainer) -> MediaInfo:
    duration = container.duration
    seconds = None if duration is None or duration <= 0 else duration / av.time_base
    return MediaInfo(
        path=source,
        format_name=container.format.name,
        duration_s=seconds,
        size_bytes=source.stat().st_size,
        streams=tuple(_stream(stream) for stream in container.streams),
    )


def _stream(stream: av.stream.Stream) -> StreamInfo:
    context = stream.codec_context
    name = context.name if context is not None else ""
    width = height = rate = channels = None
    if stream.type == "video" and context is not None:
        width, height = context.width, context.height
    if stream.type == "audio" and context is not None:
        rate = context.sample_rate
        layout = context.layout
        channels = None if layout is None else layout.nb_channels
    language = None if stream.metadata is None else stream.metadata.get("language")
    return StreamInfo(stream.index, stream.type, name, width, height, rate, channels, language)


def _keys(container: av.container.InputContainer, video_stream: int) -> tuple[KeyPacket, ...]:
    videos = [stream for stream in container.streams if stream.type == "video"]
    if video_stream < 0 or video_stream >= len(videos):
        raise EngineError(f"Video stream {video_stream} is not in the file.")
    chosen = videos[video_stream]
    packets: list[KeyPacket] = []
    for packet in container.demux(chosen):
        if packet.size == 0:
            continue
        stamp = packet.pts if packet.pts is not None else packet.dts
        seconds = None if stamp is None else float(stamp * chosen.time_base)
        flags = "K__" if packet.is_keyframe else "___"
        packets.append(KeyPacket(seconds, flags))
    return tuple(packets)
