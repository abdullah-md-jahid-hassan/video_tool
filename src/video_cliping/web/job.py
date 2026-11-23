"""Turn a parsed form into one clip() call."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import parse_qs

from video_cliping.cut import clip as default_clip
from video_cliping.errors import EngineError
from video_cliping.models import ClipReport, ClipRequest
from video_cliping.web.page import DEFAULT_DEST_DIR, FormState, Notice
from video_cliping.web.upload import FormError

_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
_MAX_FIELDS = 30
_MAX_PATH = 4096


def parse_fields(raw: bytes) -> dict[str, str]:
    """Read one urlencoded form body.

    Raises:
        FormError: The body is not UTF-8 text.
    """
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FormError("The form could not be read.") from exc
    parsed = parse_qs(text, keep_blank_values=True, max_num_fields=_MAX_FIELDS)
    return {key: values[-1] for key, values in parsed.items()}


def form_state(fields: dict[str, str]) -> FormState:
    """Values to show on the form again."""
    return FormState(
        source=fields.get("source", ""),
        start=fields.get("start", ""),
        end=fields.get("end", ""),
        maps=fields.get("maps", ""),
        dest_dir=fields.get("dest_dir", ""),
        same_folder="same_folder" in fields,
        overwrite="overwrite" in fields,
        faststart="faststart" in fields,
        drop_rejected_streams="drop_rejected_streams" in fields,
        exact="exact" in fields,
    )


def clip_from_form(fields: dict[str, str], clip_fn=default_clip) -> ClipReport:
    """Copy the video the form named.

    The folder is the ticked same-folder box, otherwise the chosen folder,
    otherwise outputs/cliping.

    Raises:
        EngineError: The file, the folder, or the cut cannot be used.
    """
    state = form_state(fields)
    source = _source_file(state.source)
    folder = _destination_folder(source, state)
    _make_folder(folder)
    request = ClipRequest(
        source=source,
        dest=_output_path(source, folder),
        start=_blank(state.start),
        end=_blank(state.end),
        maps=_maps(state.maps),
        drop_rejected_streams=state.drop_rejected_streams,
        faststart=state.faststart,
        overwrite=state.overwrite,
        exact=state.exact,
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


def _source_file(text: str) -> Path:
    path = _plain_path(text, "Choose a video file.", "The video path is not valid.")
    if not path.is_file():
        raise EngineError("The video file was not found.")
    return path


def _destination_folder(source: Path, state: FormState) -> Path:
    if state.same_folder:
        return source.parent
    if state.dest_dir.strip():
        return _plain_path(state.dest_dir, "Choose a destination folder.", "The destination folder is not a valid path.")
    return _plain_path(DEFAULT_DEST_DIR, "Choose a destination folder.", "The destination folder is not a valid path.")


def _plain_path(text: str, empty: str, invalid: str) -> Path:
    if not text.strip():
        raise EngineError(empty)
    if len(text) > _MAX_PATH or "\n" in text or "\r" in text or "\x00" in text:
        raise EngineError(invalid)
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    try:
        return path.resolve()
    except OSError as exc:
        raise EngineError(invalid) from exc


def _make_folder(folder: Path) -> None:
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise EngineError("The destination folder could not be created.") from exc
    if not folder.is_dir():
        raise EngineError("The destination is not a folder.")


def _output_path(source: Path, folder: Path) -> Path:
    dest = folder / _safe_name(source.name)
    if dest.resolve() == source.resolve():
        named = Path(_safe_name(source.name))
        dest = folder / f"{named.stem}-clip{named.suffix}"
    return dest


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
