"""ffprobe output becomes MediaInfo and key packets. No real ffprobe is required."""

import json
from pathlib import Path

import pytest

from video_cliping.errors import FfmpegFailed, InputNotFound, ToolMissing
from video_cliping.proc import CommandResult
from video_cliping.probe import inspect, key_packets


def _ok(stdout: str) -> CommandResult:
    return CommandResult(returncode=0, stdout=stdout, stderr="")


def test_inspect_reads_streams(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "in.mp4"
    source.write_bytes(b"fake")
    monkeypatch.setattr("video_cliping.probe.tool_path", lambda name: name)
    payload = {
        "format": {"format_name": "mov,mp4,m4a", "duration": "12.5", "size": "1000"},
        "streams": [
            {
                "index": 0,
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1920,
                "height": 1080,
            },
            {
                "index": 1,
                "codec_type": "audio",
                "codec_name": "aac",
                "sample_rate": "48000",
                "channels": 2,
                "tags": {"language": "eng"},
            },
        ],
    }

    def runner(argv: list[str], *, timeout: float | None) -> CommandResult:
        assert argv[0] == "ffprobe"
        assert "-show_format" in argv
        assert argv[-1] == str(source.resolve())
        assert timeout == 60.0
        return _ok(json.dumps(payload))

    info = inspect(source, runner=runner)
    assert info.duration_s == 12.5
    assert info.size_bytes == 1000
    assert info.streams[0].codec_name == "h264"
    assert info.streams[0].width == 1920
    assert info.streams[1].language == "eng"
    assert info.streams[1].sample_rate == 48000
    assert info.streams[1].channels == 2


def test_missing_duration_is_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "in.mp4"
    source.write_bytes(b"fake")
    monkeypatch.setattr("video_cliping.probe.tool_path", lambda name: name)
    payload = {"format": {"duration": "N/A", "size": "10"}, "streams": []}

    info = inspect(source, runner=lambda argv, timeout: _ok(json.dumps(payload)))
    assert info.duration_s is None


def test_missing_file_does_not_call_ffprobe(tmp_path: Path) -> None:
    def runner(argv: list[str], *, timeout: float | None) -> CommandResult:
        raise AssertionError("runner should not be called")

    with pytest.raises(InputNotFound):
        inspect(tmp_path / "missing.mp4", runner=runner)


def test_ffprobe_error_keeps_stderr_tail(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "in.mp4"
    source.write_bytes(b"fake")
    monkeypatch.setattr("video_cliping.probe.tool_path", lambda name: name)
    stderr = "\n".join(f"line {i}" for i in range(250))

    def runner(argv: list[str], *, timeout: float | None) -> CommandResult:
        return CommandResult(returncode=1, stdout="", stderr=stderr)

    with pytest.raises(FfmpegFailed) as caught:
        inspect(source, runner=runner)
    assert "line 249" in caught.value.stderr
    assert "line 0\n" not in caught.value.stderr
    assert caught.value.command[0] == "ffprobe"


def test_bad_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "in.mp4"
    source.write_bytes(b"fake")
    monkeypatch.setattr("video_cliping.probe.tool_path", lambda name: name)
    with pytest.raises(FfmpegFailed):
        inspect(source, runner=lambda argv, timeout: _ok("not-json"))


def test_key_packets_keep_flag_text(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "in.mp4"
    source.write_bytes(b"fake")
    monkeypatch.setattr("video_cliping.probe.tool_path", lambda name: name)
    payload = {"packets": [{"pts_time": "0.000", "flags": "K__"}, {"pts_time": "1.0", "flags": "___"}]}

    def runner(argv: list[str], *, timeout: float | None) -> CommandResult:
        assert "-select_streams" in argv
        assert "v:0" in argv
        assert "packet=pts_time,flags" in argv
        return _ok(json.dumps(payload))

    packets = key_packets(source, runner=runner)
    assert packets[0].time_s == 0.0
    assert "K" in packets[0].flags
    assert "K" not in packets[1].flags


def test_tool_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "in.mp4"
    source.write_bytes(b"fake")

    def missing(name: str) -> str:
        raise ToolMissing("ffprobe is not on PATH.")

    monkeypatch.setattr("video_cliping.probe.tool_path", missing)
    with pytest.raises(ToolMissing):
        inspect(source, runner=lambda argv, timeout: _ok("{}"))
