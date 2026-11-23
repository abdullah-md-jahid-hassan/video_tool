"""Packet-copy cuts through PyAV. No system ffmpeg."""

from pathlib import Path

import av
import pytest

from sample_media import write_sample
from video_cliping.cut import clip
from video_cliping.errors import (
    BadRange,
    ContainerRejected,
    EngineError,
    Exists,
    FfmpegFailed,
    OutsideEngine,
    SamePath,
)
from video_cliping.models import ClipRequest


def test_copy_keeps_codecs_and_is_smaller(tmp_path: Path) -> None:
    source = tmp_path / "in.mp4"
    write_sample(source)
    dest = tmp_path / "out.mp4"
    report = clip(ClipRequest(source=source, dest=dest, start=1, end=2))
    assert report.output_duration_s == pytest.approx(1, abs=0.5)
    assert report.output_size_bytes < source.stat().st_size
    names = {stream.codec_type: stream.codec_name for stream in report.streams_copied}
    assert names["video"] == "h264"
    assert names["audio"] == "aac"
    assert report.bitstream_filters == ()
    assert dest.is_file()


def test_open_end_keeps_the_tail(tmp_path: Path) -> None:
    source = tmp_path / "in.mp4"
    write_sample(source, seconds=2)
    dest = tmp_path / "out.mp4"
    report = clip(ClipRequest(source=source, dest=dest, start="00:00:01"))
    assert report.requested_end_s is None
    assert report.output_duration_s == pytest.approx(1, abs=0.5)


def test_exact_does_not_run(tmp_path: Path) -> None:
    source = tmp_path / "in.mp4"
    source.write_bytes(b"s")
    with pytest.raises(OutsideEngine):
        clip(ClipRequest(source=source, dest=tmp_path / "out.mp4", exact=True))
    assert not (tmp_path / "out.mp4").exists()


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
def test_refused_before_open(tmp_path: Path, change: str, error: type[Exception]) -> None:
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
        clip(ClipRequest(source=source, dest=dest, start=1, end=2, **kwargs))  # type: ignore[arg-type]


def test_backwards_range(tmp_path: Path) -> None:
    source = tmp_path / "in.mp4"
    write_sample(source)
    with pytest.raises(BadRange):
        clip(ClipRequest(source=source, dest=tmp_path / "out.mp4", start=30, end=10))


def test_garbage_file_fails(tmp_path: Path) -> None:
    source = tmp_path / "in.mp4"
    source.write_bytes(b"not a video")
    dest = tmp_path / "out.mp4"
    with pytest.raises(FfmpegFailed):
        clip(ClipRequest(source=source, dest=dest, start=0, end=1))
    assert not dest.exists()


def test_drop_rejected_audio(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "in.mp4"
    write_sample(source)
    dest = tmp_path / "out.mp4"
    original = av.container.OutputContainer.add_stream_from_template

    def refuse_audio(self, template, *args, **kwargs):
        if template.type == "audio":
            raise av.error.FFmpegError(1, "refused")
        return original(self, template, *args, **kwargs)

    monkeypatch.setattr(av.container.OutputContainer, "add_stream_from_template", refuse_audio)
    report = clip(ClipRequest(source=source, dest=dest, start=0, end=1, drop_rejected_streams=True))
    assert report.streams_dropped[0].codec_name == "aac"
    assert {stream.codec_type for stream in report.streams_copied} == {"video"}


def test_refused_stream_raises_and_deletes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "in.mp4"
    write_sample(source)
    dest = tmp_path / "out.mp4"
    original = av.container.OutputContainer.add_stream_from_template

    def refuse_audio(self, template, *args, **kwargs):
        if template.type == "audio":
            raise av.error.FFmpegError(1, "refused")
        return original(self, template, *args, **kwargs)

    monkeypatch.setattr(av.container.OutputContainer, "add_stream_from_template", refuse_audio)
    with pytest.raises(ContainerRejected):
        clip(ClipRequest(source=source, dest=dest, start=0, end=1))
    assert not dest.exists()
