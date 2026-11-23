"""Clock text and plain seconds both become a number of seconds."""

from pathlib import Path

import pytest

from video_cliping.errors import BadRange
from video_cliping.models import ClipRequest
from video_cliping.times import ffmpeg_time, parse_seconds


@pytest.mark.parametrize(
    ("value", "seconds"),
    [
        (90, 90.0),
        (90.5, 90.5),
        ("90", 90.0),
        ("90.5", 90.5),
        ("01:30", 90.0),
        ("01:30.5", 90.5),
        ("01:02:03", 3723.0),
        ("01:02:03.500", 3723.5),
        ("90:00", 5400.0),
    ],
)
def test_parse_seconds(value: object, seconds: float) -> None:
    assert parse_seconds(value) == seconds  # type: ignore[arg-type]


def test_clock_string_is_passed_through() -> None:
    assert ffmpeg_time("01:02:03.500") == "01:02:03.500"


def test_number_becomes_seconds_text() -> None:
    assert ffmpeg_time(90) == "90"
    assert ffmpeg_time(90.5) == "90.5"


@pytest.mark.parametrize(
    "value",
    [-1, -0.1, "", "nope", "01:60:00", "01:02:60", True, "1:2:3:4"],
)
def test_bad_times(value: object) -> None:
    with pytest.raises(BadRange):
        parse_seconds(value)  # type: ignore[arg-type]


def test_clip_request_defaults() -> None:
    request = ClipRequest(source=Path("in.mp4"), dest=Path("out.mp4"))
    assert request.start is None
    assert request.end is None
    assert request.maps is None
    assert request.exact is False
    assert request.overwrite is False
