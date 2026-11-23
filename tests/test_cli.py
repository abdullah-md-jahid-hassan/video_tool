"""The command line passes a path and clip settings into clip()."""

from pathlib import Path

import pytest

from video_cliping.cli import main
from video_cliping.errors import BadRange, FfmpegFailed
from video_cliping.models import ClipReport, ClipRequest, StreamInfo


def _report(dest: Path) -> ClipReport:
    return ClipReport(
        source=Path("in.mp4"),
        dest=dest,
        requested_start_s=1,
        requested_end_s=2,
        output_duration_s=1.5,
        output_size_bytes=10,
        streams_copied=(StreamInfo(0, "video", "h264"),),
        streams_dropped=(),
        bitstream_filters=(),
        command=("ffmpeg",),
    )


def test_cli_passes_clip_settings(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    seen: dict[str, ClipRequest] = {}

    def fake(request: ClipRequest) -> ClipReport:
        seen["request"] = request
        return _report(request.dest)

    monkeypatch.setattr("video_cliping.cli.clip", fake)
    code = main(
        [
            "in.mp4",
            "out.mp4",
            "--start",
            "00:00:01",
            "--end",
            "2",
            "--map",
            "0:v:0",
            "--map",
            "0:a:0",
            "--overwrite",
            "--faststart",
            "--drop-rejected-streams",
        ]
    )
    assert code == 0
    request = seen["request"]
    assert request.source == Path("in.mp4")
    assert request.dest == Path("out.mp4")
    assert request.start == "00:00:01"
    assert request.end == "2"
    assert request.maps == ("0:v:0", "0:a:0")
    assert request.overwrite is True
    assert request.faststart is True
    assert request.drop_rejected_streams is True
    assert "wrote" in capsys.readouterr().out


def test_bad_request_exits_2(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    def fake(request: ClipRequest) -> ClipReport:
        raise BadRange("Start must be before end.")

    monkeypatch.setattr("video_cliping.cli.clip", fake)
    code = main(["in.mp4", "out.mp4", "--start", "5", "--end", "1"])
    assert code == 2
    assert "Start must be before end." in capsys.readouterr().err


def test_ffmpeg_failure_exits_1(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(request: ClipRequest) -> ClipReport:
        raise FfmpegFailed("ffmpeg failed.", ["ffmpeg"], "boom")

    monkeypatch.setattr("video_cliping.cli.clip", fake)
    assert main(["in.mp4", "out.mp4"]) == 1


def test_missing_paths_exit(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as caught:
        main(["only-one"])
    assert caught.value.code == 2
    assert "usage" in capsys.readouterr().err.lower()
