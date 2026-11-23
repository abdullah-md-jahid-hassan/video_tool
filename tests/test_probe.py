"""PyAV reads become MediaInfo and key packets."""

from pathlib import Path

import pytest

from sample_media import write_sample
from video_cliping.errors import EngineError, FfmpegFailed, InputNotFound
from video_cliping.probe import inspect, key_packets


def test_inspect_reads_streams(tmp_path: Path) -> None:
    source = tmp_path / "in.mp4"
    write_sample(source, seconds=2)
    info = inspect(source)
    assert info.duration_s == pytest.approx(2, abs=0.2)
    assert info.size_bytes == source.stat().st_size
    kinds = {stream.codec_type: stream for stream in info.streams}
    assert kinds["video"].codec_name == "h264"
    assert kinds["video"].width == 320
    assert kinds["audio"].codec_name == "aac"
    assert kinds["audio"].sample_rate == 48000
    assert kinds["audio"].channels == 2


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(InputNotFound):
        inspect(tmp_path / "missing.mp4")


def test_garbage_file(tmp_path: Path) -> None:
    source = tmp_path / "in.mp4"
    source.write_bytes(b"not a video")
    with pytest.raises(FfmpegFailed):
        inspect(source)


def test_key_packets_mark_keyframes(tmp_path: Path) -> None:
    source = tmp_path / "in.mp4"
    write_sample(source, seconds=2)
    packets = key_packets(source)
    assert packets
    assert any("K" in packet.flags for packet in packets)
    assert packets[0].time_s == pytest.approx(0, abs=0.05)


def test_missing_video_stream(tmp_path: Path) -> None:
    source = tmp_path / "in.mp4"
    write_sample(source)
    with pytest.raises(EngineError):
        key_packets(source, video_stream=3)
