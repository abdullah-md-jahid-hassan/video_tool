"""Read a clip time and turn it into seconds.

A caller may pass a number of seconds, or clock text FFmpeg already accepts.
Numbers are checked here. Clock text is checked here and then passed through
to FFmpeg unchanged.
"""

from __future__ import annotations

from video_cliping.errors import BadRange

Time = int | float | str


def parse_seconds(value: Time) -> float:
    """Return the time as seconds.

    Raises:
        BadRange: The value is empty, negative, or not a time.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise BadRange("Time must be seconds or clock text.")
    if isinstance(value, str):
        return _parse_clock(value.strip())
    return _finite_seconds(float(value))


def ffmpeg_time(value: Time) -> str:
    """Return the text to put in the ffmpeg command.

    A string is returned unchanged after it parses. A number becomes seconds.
    """
    if isinstance(value, str):
        text = value.strip()
        _parse_clock(text)
        return text
    seconds = parse_seconds(value)
    if seconds.is_integer():
        return str(int(seconds))
    text = f"{seconds:.6f}".rstrip("0").rstrip(".")
    return text or "0"


def _parse_clock(text: str) -> float:
    if not text:
        raise BadRange("Time is empty.")
    if ":" not in text:
        try:
            seconds = float(text)
        except ValueError:
            raise BadRange(f"Cannot read time {text!r}.") from None
        return _finite_seconds(seconds)
    parts = text.split(":")
    if len(parts) not in (2, 3):
        raise BadRange(f"Cannot read time {text!r}.")
    try:
        numbers = _clock_numbers(parts)
    except ValueError:
        raise BadRange(f"Cannot read time {text!r}.") from None
    return numbers


def _clock_numbers(parts: list[str]) -> float:
    if len(parts) == 2:
        # "90:00" is 90 minutes. FFmpeg accepts that two-field form.
        minutes = int(parts[0])
        seconds = float(parts[1])
        hours = 0
    else:
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = float(parts[2])
        if minutes > 59:
            raise BadRange("Minutes in HH:MM:SS must be under 60.")
    if hours < 0 or minutes < 0 or seconds < 0 or seconds >= 60:
        raise BadRange("Clock time has a negative part or seconds past 59.")
    return hours * 3600 + minutes * 60 + seconds


def _finite_seconds(seconds: float) -> float:
    if seconds < 0 or seconds != seconds or seconds == float("inf"):
        raise BadRange("Time must be a finite number of seconds, zero or more.")
    return seconds
