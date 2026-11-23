"""Turn a parsed form into one clip() call."""

from __future__ import annotations

import re
from pathlib import Path

from video_cliping.cut import clip as default_clip
from video_cliping.errors import EngineError
from video_cliping.models import ClipReport, ClipRequest
from video_cliping.web.page import DEFAULT_DEST_DIR, FormState, Notice
from video_cliping.web.upload import ParsedForm

_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def form_state(fields: dict[str, str]) -> FormState:
    """Values to show on the form again."""
    dest = fields.get("dest_dir", "").strip() or DEFAULT_DEST_DIR
    return FormState(
        start=fields.get("start", ""),
        end=fields.get("end", ""),
        maps=fields.get("maps", ""),
        dest_dir=dest,
        overwrite="overwrite" in fields,
        faststart="faststart" in fields,
        drop_rejected_streams="drop_rejected_streams" in fields,
    )


def clip_from_form(parsed: ParsedForm, clip_fn=default_clip) -> ClipReport:
    """Build the output path and copy the uploaded file.

    Raises:
        EngineError: The folder or the times cannot be used, or the cut fails.
    """
    state = form_state(parsed.fields)
    dest_dir = _dest_dir(state.dest_dir)
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise EngineError("The destination folder could not be created.") from exc
    if not dest_dir.is_dir():
        raise EngineError("The destination is not a folder.")
    request = ClipRequest(
        source=parsed.upload_path,
        dest=dest_dir / _safe_name(parsed.filename),
        start=_blank(state.start),
        end=_blank(state.end),
        maps=_maps(state.maps),
        drop_rejected_streams=state.drop_rejected_streams,
        faststart=state.faststart,
        overwrite=state.overwrite,
    )
    return clip_fn(request)


def success_notice(report: ClipReport) -> Notice:
    """The sentence shown after a cut that finished."""
    text = (
        f"Wrote {report.dest} ({report.output_duration_s:.3f} seconds, "
        f"{report.output_size_bytes} bytes)."
    )
    dropped = ""
    if report.streams_dropped:
        names = ", ".join(stream.codec_name for stream in report.streams_dropped)
        dropped = f"Left out: {names}"
    return Notice(True, text, dropped)


def failure_notice(exc: EngineError) -> Notice:
    """The sentence shown when a cut is refused or fails."""
    return Notice(False, str(exc), getattr(exc, "stderr", "") or "")


def _dest_dir(text: str) -> Path:
    if "\n" in text or "\r" in text or "\x00" in text:
        raise EngineError("The destination folder is not a valid path.")
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


def _safe_name(filename: str) -> str:
    cleaned = _NAME_RE.sub("_", Path(filename).name.replace("\x00", "")).strip("._")
    if not cleaned:
        return "clip.mp4"
    if Path(cleaned).suffix == "":
        return cleaned + ".mp4"
    return cleaned


def _blank(value: str) -> str | None:
    text = value.strip()
    return text or None


def _maps(text: str) -> tuple[str, ...] | None:
    parts = [item for item in re.split(r"[\s,]+", text.strip()) if item]
    return tuple(parts) or None
