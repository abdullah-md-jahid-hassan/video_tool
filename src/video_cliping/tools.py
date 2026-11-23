"""Find ffmpeg and ffprobe on PATH. Nothing is downloaded."""

from __future__ import annotations

import shutil

from video_cliping.errors import ToolMissing


def tool_path(name: str) -> str:
    """Return the absolute path of one tool.

    Raises:
        ToolMissing: The name is not on PATH.
    """
    found = shutil.which(name)
    if not found:
        raise ToolMissing(f"{name} is not on PATH.")
    return found


def require_tools() -> tuple[str, str]:
    """Return (ffmpeg, ffprobe). Both must be present.

    Raises:
        ToolMissing: One or both tools are missing.
    """
    missing = [name for name in ("ffmpeg", "ffprobe") if shutil.which(name) is None]
    if missing:
        raise ToolMissing("Missing on PATH: " + ", ".join(missing) + ".")
    return tool_path("ffmpeg"), tool_path("ffprobe")
