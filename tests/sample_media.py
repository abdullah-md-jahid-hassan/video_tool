"""A short real video used by the cutter tests. PyAV writes it. No system ffmpeg."""

from pathlib import Path

import av


def write_sample(path: Path, seconds: float = 3.0) -> None:
    """Write a small H.264 and AAC file of about `seconds`."""
    with av.open(path, "w") as out:
        video = out.add_stream("libx264", rate=30)
        video.width = 320
        video.height = 240
        video.pix_fmt = "yuv420p"
        video.options = {"g": "30"}
        audio = out.add_stream("aac", rate=48000)
        audio.layout = "stereo"
        video_packets = _encode_video(video, int(seconds * 30))
        audio_packets = _encode_audio(audio, int(seconds * 48000 / 1024) + 1)
        for packet in video_packets:
            out.mux(packet)
        for packet in audio_packets:
            out.mux(packet)


def _encode_video(video: av.VideoStream, frames: int) -> list[av.Packet]:
    packets: list[av.Packet] = []
    for index in range(frames):
        frame = av.VideoFrame(320, 240, "yuv420p")
        frame.pts = index
        for plane in frame.planes:
            plane.update(b"\x00" * plane.buffer_size)
        packets.extend(video.encode(frame))
    packets.extend(video.encode(None))
    return packets


def _encode_audio(audio: av.AudioStream, frames: int) -> list[av.Packet]:
    packets: list[av.Packet] = []
    for index in range(frames):
        sound = av.AudioFrame(format="fltp", layout="stereo", samples=1024)
        sound.sample_rate = 48000
        sound.pts = index * 1024
        for plane in sound.planes:
            plane.update(b"\x00" * plane.buffer_size)
        packets.extend(audio.encode(sound))
    packets.extend(audio.encode(None))
    return packets
