"""Stream-copy cuts. ffmpeg and ffprobe are stand-ins that return JSON."""

import json
from pathlib import Path

import pytest

from video_cliping.cut import clip
from video_cliping.errors import (
    BadRange,
    ContainerRejected,
    EngineError,
    Exists,
    FfmpegFailed,
    OutsideEngine,
    OutputCheckFailed,
    SamePath,
)
from video_cliping.models import ClipRequest
from video_cliping.proc import CommandResult


def _media(duration: str, size: str, streams: list[dict]) -> str:
    return json.dumps({"format": {"format_name": "mp4", "duration": duration, "size": size}, "streams": streams})


VIDEO = {"index": 0, "codec_type": "video", "codec_name": "h264", "width": 320, "height": 240}
AUDIO = {"index": 1, "codec_type": "audio", "codec_name": "aac", "sample_rate": "48000", "channels": 2}
SUB = {"index": 2, "codec_type": "subtitle", "codec_name": "hdmv_pgs_subtitle"}


class StandIn:
    """Return probe JSON, and record every ffmpeg command."""

    def __init__(self, source: Path, output_json: str, codes: list[int], stderr: str = "") -> None:
        self.source = str(source.resolve())
        self.output_json = output_json
        self.codes = list(codes)
        self.stderr = stderr
        self.commands: list[list[str]] = []

    def __call__(self, argv: list[str], *, timeout: float | None) -> CommandResult:
        self.commands.append(list(argv))
        if argv[0] == "ffprobe":
            payload = _media("100", "10000", [VIDEO, AUDIO]) if argv[-1] == self.source else self.output_json
            return CommandResult(0, payload if isinstance(payload, str) else payload, "")
        code = self.codes.pop(0) if self.codes else 0
        dest = Path(argv[-1])
        dest.write_bytes(b"partial" if code else b"clip")
        text = self.stderr if code else ""
        return CommandResult(code, "", text)

    def ffmpeg_commands(self) -> list[list[str]]:
        return [argv for argv in self.commands if argv[0] == "ffmpeg"]


def _patch_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("video_cliping.cut.require_tools", lambda: ("ffmpeg", "ffprobe"))
    monkeypatch.setattr("video_cliping.probe.tool_path", lambda name: name)


def _request(source: Path, dest: Path, **kwargs: object) -> ClipRequest:
    return ClipRequest(source=source, dest=dest, start=10, end=20, **kwargs)  # type: ignore[arg-type]


def test_copy_command_and_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_tools(monkeypatch)
    source = tmp_path / "in.mp4"
    source.write_bytes(b"source-bytes")
    dest = tmp_path / "out.mp4"
    stand_in = StandIn(source, _media("11", "1500", [VIDEO, AUDIO]), codes=[0])
    report = clip(_request(source, dest), runner=stand_in)

    command = stand_in.ffmpeg_commands()[0]
    assert command[:8] == ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-ss", "10", "-to", "20"]
    assert command[command.index("-i") + 1] == str(source.resolve())
    assert command[command.index("-map") + 1] == "0"
    assert "-c" in command and command[command.index("-c") + 1] == "copy"
    assert "libx264" not in command
    assert command[-1] == str(dest.resolve())
    assert report.output_duration_s == 11
    assert report.output_size_bytes == 1500
    assert report.requested_start_s == 10
    assert report.requested_end_s == 20
    assert report.bitstream_filters == ()
    assert dest.is_file()


def test_open_end_omits_to(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_tools(monkeypatch)
    source = tmp_path / "in.mp4"
    source.write_bytes(b"s")
    dest = tmp_path / "out.mp4"
    stand_in = StandIn(source, _media("90", "4000", [VIDEO, AUDIO]), codes=[0])
    clip(ClipRequest(source=source, dest=dest, start="00:00:10"), runner=stand_in)
    command = stand_in.ffmpeg_commands()[0]
    assert "-to" not in command
    assert command[command.index("-ss") + 1] == "00:00:10"


def test_maps_and_faststart(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_tools(monkeypatch)
    source = tmp_path / "in.mp4"
    source.write_bytes(b"s")
    dest = tmp_path / "out.mp4"
    stand_in = StandIn(source, _media("11", "1500", [VIDEO, AUDIO]), codes=[0])
    clip(
        _request(source, dest, maps=("0:v:0", "0:a:0"), faststart=True),
        runner=stand_in,
    )
    command = stand_in.ffmpeg_commands()[0]
    assert command[command.index("-movflags") + 1] == "+faststart"
    assert "0:v:0" in command and "0:a:0" in command


def test_exact_does_not_run(tmp_path: Path) -> None:
    source = tmp_path / "in.mp4"
    source.write_bytes(b"s")
    called = False

    def runner(argv: list[str], *, timeout: float | None) -> CommandResult:
        nonlocal called
        called = True
        return CommandResult(0, "", "")

    with pytest.raises(OutsideEngine):
        clip(_request(source, tmp_path / "out.mp4", exact=True), runner=runner)
    assert called is False


@pytest.mark.parametrize(
    ("change", "error"),
    [
        ("same", SamePath),
        ("exists", Exists),
        ("faststart-mkv", EngineError),
        ("bad-map", EngineError),
        ("newline", EngineError),
    ],
)
def test_refused_before_ffmpeg(tmp_path: Path, change: str, error: type[Exception]) -> None:
    source = tmp_path / "in.mp4"
    source.write_bytes(b"s")
    dest = tmp_path / "out.mp4"
    kwargs: dict[str, object] = {}
    if change == "same":
        dest = source
    elif change == "exists":
        dest.write_bytes(b"old")
    elif change == "faststart-mkv":
        dest = tmp_path / "out.mkv"
        kwargs["faststart"] = True
    elif change == "bad-map":
        kwargs["maps"] = ("-vf",)
    elif change == "newline":
        dest = Path(str(tmp_path / "out.mp4") + "\n")
    with pytest.raises(error):
        clip(_request(source, dest, **kwargs), runner=lambda argv, timeout: CommandResult(0, "", ""))


def test_backwards_range_does_not_encode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_tools(monkeypatch)
    source = tmp_path / "in.mp4"
    source.write_bytes(b"s")
    stand_in = StandIn(source, _media("11", "1500", [VIDEO, AUDIO]), codes=[0])
    with pytest.raises(BadRange):
        clip(ClipRequest(source=source, dest=tmp_path / "out.mp4", start=30, end=10), runner=stand_in)
    assert stand_in.ffmpeg_commands() == []


def test_failed_ffmpeg_deletes_partial(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_tools(monkeypatch)
    source = tmp_path / "in.mp4"
    source.write_bytes(b"s")
    dest = tmp_path / "out.mp4"
    stderr = "\n".join(f"line {i}" for i in range(220))
    stand_in = StandIn(source, _media("11", "1500", [VIDEO, AUDIO]), codes=[1], stderr=stderr)
    with pytest.raises(FfmpegFailed) as caught:
        clip(_request(source, dest), runner=stand_in)
    assert not dest.exists()
    assert "line 219" in caught.value.stderr
    assert "line 0\n" not in caught.value.stderr
    assert caught.value.command[0] == "ffmpeg"


def test_oversized_output_is_removed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_tools(monkeypatch)
    source = tmp_path / "in.mp4"
    source.write_bytes(b"s")
    dest = tmp_path / "out.mp4"
    stand_in = StandIn(source, _media("11", "10000", [VIDEO, AUDIO]), codes=[0])
    with pytest.raises(OutputCheckFailed):
        clip(_request(source, dest), runner=stand_in)
    assert not dest.exists()


def test_container_reject_can_drop_a_stream(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_tools(monkeypatch)
    source = tmp_path / "in.mp4"
    source.write_bytes(b"s")
    dest = tmp_path / "out.mp4"
    stderr = (
        "Could not find tag for codec hdmv_pgs_subtitle in stream #0, "
        "codec not currently supported in container\n"
        "Error initializing output stream 0:2 --\n"
    )
    stand_in = StandIn(source, _media("11", "1500", [VIDEO, AUDIO]), codes=[1, 0], stderr=stderr)
    stand_in.source_streams = [VIDEO, AUDIO, SUB]

    def runner(argv: list[str], *, timeout: float | None) -> CommandResult:
        if argv[0] == "ffprobe" and argv[-1] == str(source.resolve()) and "-show_packets" not in argv:
            payload = _media("100", "10000", [VIDEO, AUDIO, SUB])
            stand_in.commands.append(list(argv))
            return CommandResult(0, payload, "")
        return stand_in(argv, timeout=timeout)

    report = clip(_request(source, dest, drop_rejected_streams=True), runner=runner)
    second = stand_in.ffmpeg_commands()[1]
    assert "0:v:0" in second and "0:a:0" in second
    assert "0:s:0" not in second
    assert report.streams_dropped[0].codec_name == "hdmv_pgs_subtitle"


def test_aac_rejection_retries_with_bitstream_filter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_tools(monkeypatch)
    source = tmp_path / "in.mp4"
    source.write_bytes(b"s")
    dest = tmp_path / "out.mp4"
    stderr = "Could not find tag for codec aac, codec not currently supported in container\n"
    stand_in = StandIn(source, _media("11", "1500", [VIDEO, AUDIO]), codes=[1, 0], stderr=stderr)
    report = clip(_request(source, dest), runner=stand_in)
    second = stand_in.ffmpeg_commands()[1]
    assert second[second.index("-bsf:a") + 1] == "aac_adtstoasc"
    assert report.bitstream_filters == ("aac_adtstoasc",)


def test_container_rejection_without_drop_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_tools(monkeypatch)
    source = tmp_path / "in.mp4"
    source.write_bytes(b"s")
    dest = tmp_path / "out.mp4"
    stderr = "codec not currently supported in container\nError initializing output stream 0:1 --\n"
    stand_in = StandIn(source, _media("11", "1500", [VIDEO, AUDIO]), codes=[1], stderr=stderr)
    with pytest.raises(ContainerRejected):
        clip(_request(source, dest), runner=stand_in)
    assert not dest.exists()
