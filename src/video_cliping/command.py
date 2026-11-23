"""Build the ffmpeg argument list for one stream-copy cut."""

from __future__ import annotations

import re
from pathlib import Path

from video_cliping.errors import EngineError
from video_cliping.times import Time, ffmpeg_time

# 0:v:0 is the first video stream. Anything else could smuggle extra flags.
_MAP_RE = re.compile(r"^0:(v|a|s|d|t):\d+$")
_BSF_FLAG = {
    "aac_adtstoasc": ("-bsf:a", "aac_adtstoasc"),
    "h264_mp4toannexb": ("-bsf:v", "h264_mp4toannexb"),
    "hevc_mp4toannexb": ("-bsf:v", "hevc_mp4toannexb"),
}


def validate_maps(maps: tuple[str, ...] | None) -> None:
    """Reject a map list that is not a stream spec.

    Raises:
        EngineError: The list is empty or a spec is not `0:v:0` style.
    """
    if maps is None:
        return
    if not maps:
        raise EngineError("maps is empty.")
    for spec in maps:
        if _MAP_RE.fullmatch(spec) is None:
            raise EngineError(f"Map must look like 0:v:0, not {spec!r}.")


def build_clip_command(
    ffmpeg: str,
    source: Path,
    dest: Path,
    start: Time | None,
    end: Time | None,
    maps: tuple[str, ...] | None,
    *,
    faststart: bool,
    bitstream_filters: tuple[str, ...] = (),
) -> list[str]:
    """Return the argv for one copy cut. start None is treated as 0."""
    argv = [ffmpeg, "-hide_banner", "-nostdin", "-y"]
    argv.extend(["-ss", "0" if start is None else ffmpeg_time(start)])
    if end is not None:
        argv.extend(["-to", ffmpeg_time(end)])
    argv.extend(["-i", str(source)])
    argv.extend(_map_args(maps))
    argv.extend(["-c", "copy", "-avoid_negative_ts", "make_zero"])
    for name in bitstream_filters:
        flag, value = _BSF_FLAG[name]
        argv.extend([flag, value])
    if faststart:
        argv.extend(["-movflags", "+faststart"])
    argv.append(str(dest))
    return argv


def _map_args(maps: tuple[str, ...] | None) -> list[str]:
    if maps is None:
        return ["-map", "0"]
    args: list[str] = []
    for spec in maps:
        args.extend(["-map", spec])
    return args
