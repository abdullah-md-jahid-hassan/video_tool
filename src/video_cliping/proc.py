"""Run ffmpeg and ffprobe. The command is a list, never a shell string."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass

from video_cliping.errors import FfmpegFailed

STDERR_LINE_LIMIT = 200


@dataclass(frozen=True)
class CommandResult:
    """One finished process."""

    returncode: int
    stdout: str
    stderr: str


def run_command(argv: list[str], *, timeout: float | None) -> CommandResult:
    """Run argv and capture text. timeout None waits until the process ends.

    Raises:
        FfmpegFailed: The process did not finish before timeout.
    """
    try:
        completed = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            timeout=timeout,
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise FfmpegFailed("The command timed out.", list(argv), "") from exc
    return CommandResult(
        returncode=completed.returncode,
        stdout=_text(completed.stdout),
        stderr=_text(completed.stderr),
    )


def stderr_tail(text: str, limit: int = STDERR_LINE_LIMIT) -> str:
    """Keep the last lines of a process log."""
    lines = text.splitlines()
    return "\n".join(lines[-limit:])


def _text(raw: bytes | str | None) -> str:
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    return raw.decode("utf-8", errors="replace")
