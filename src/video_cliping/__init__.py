"""Cut a local video by copying the original packets."""

from video_cliping.cut import clip
from video_cliping.models import ClipReport, ClipRequest, MediaInfo
from video_cliping.probe import inspect, key_packets

__version__ = "0.1.0"

__all__ = [
    "ClipReport",
    "ClipRequest",
    "MediaInfo",
    "clip",
    "inspect",
    "key_packets",
    "__version__",
]
