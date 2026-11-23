"""HTML for the video clipping page."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape

DEFAULT_DEST_DIR = "outputs/cliping"


@dataclass(frozen=True)
class FormState:
    """Values to show again after a cut."""

    start: str = ""
    end: str = ""
    maps: str = ""
    dest_dir: str = DEFAULT_DEST_DIR
    overwrite: bool = False
    faststart: bool = False
    drop_rejected_streams: bool = False


@dataclass(frozen=True)
class Notice:
    """A result or an error shown above the form."""

    ok: bool
    text: str
    detail: str = ""


def home_page() -> str:
    """The front page. It has one tool."""
    body = """
    <h1>Video clipping</h1>
    <p>Cut a video on this computer. The picture is copied, not encoded again.</p>
    <a class="tool" href="/clip">Video clipping</a>
    """
    return _document("Video clipping", body)


def clip_page(token: str, state: FormState | None = None, notice: Notice | None = None) -> str:
    """The form for one cut."""
    form = state or FormState()
    body = f"""
    <p><a href="/">Back</a></p>
    <h1>Video clipping</h1>
    {_notice(notice)}
    <form action="/clip" method="post" enctype="multipart/form-data">
      <input type="hidden" name="csrf" value="{escape(token, quote=True)}">
      <label>Video file
        <span class="hint">Choose a file on this computer. It is not uploaded anywhere else.</span>
        <input type="file" name="video" accept="video/*,.mp4,.mkv,.mov,.webm,.m4v" required>
      </label>
      <label>Start
        <span class="hint">Optional. Seconds, such as 90, or a clock, such as 00:01:30. Empty starts at the beginning.</span>
        <input type="text" name="start" value="{escape(form.start, quote=True)}" autocomplete="off">
      </label>
      <label>End
        <span class="hint">Optional. Empty stops at the end of the file.</span>
        <input type="text" name="end" value="{escape(form.end, quote=True)}" autocomplete="off">
      </label>
      <label>Streams to keep
        <span class="hint">Optional. One spec per line, such as 0:v:0 or 0:a:1. Empty keeps every stream.</span>
        <textarea name="maps" rows="3">{escape(form.maps)}</textarea>
      </label>
      <label>Destination folder
        <span class="hint">A folder on this computer. Empty uses outputs/cliping, next to where you started the server.</span>
        <input type="text" name="dest_dir" value="{escape(form.dest_dir, quote=True)}">
      </label>
      <label class="check"><input type="checkbox" name="overwrite" {_checked(form.overwrite)}>Replace the output file if it is already there</label>
      <label class="check"><input type="checkbox" name="faststart" {_checked(form.faststart)}>Put the MP4 or MOV index at the front of the file</label>
      <label class="check"><input type="checkbox" name="drop_rejected_streams" {_checked(form.drop_rejected_streams)}>If the container cannot hold a stream, leave that stream out</label>
      <button type="submit">Clip the video</button>
    </form>
    <p class="hint">The cut can start a little early, on a keyframe. The frames that are kept are the original frames.</p>
    """
    return _document("Video clipping", body)


def message_page(text: str) -> str:
    """A short page with one sentence."""
    return _document("Video clipping", f"<h1>Video clipping</h1><p>{escape(text)}</p><p><a href=\"/\">Back</a></p>")


def _notice(notice: Notice | None) -> str:
    if notice is None:
        return ""
    kind = "ok" if notice.ok else "error"
    detail = f"<pre>{escape(notice.detail)}</pre>" if notice.detail else ""
    return f'<div class="{kind}"><p>{escape(notice.text)}</p>{detail}</div>'


def _checked(on: bool) -> str:
    return "checked" if on else ""


def _document(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>
    body {{ margin: 0; background: #f6f3ee; color: #1c1915;
      font: 1rem/1.45 system-ui, sans-serif; }}
    main {{ max-width: 36rem; margin: 0 auto; padding: 2rem 1rem 4rem; }}
    a {{ color: #1d4e39; }}
    a.tool {{ display: block; margin-top: 1.5rem; padding: 1.1rem 1.2rem;
      background: #fff; border: 1px solid #d9d3c8; border-radius: 8px;
      color: inherit; text-decoration: none; font-weight: 650; }}
    a.tool:hover {{ border-color: #1d4e39; }}
    label {{ display: block; margin-top: 1rem; font-weight: 650; }}
    .hint {{ display: block; margin: 0.2rem 0 0.35rem; font-weight: 400; color: #5c564c; }}
    input[type="text"], input[type="file"], textarea {{
      width: 100%; box-sizing: border-box; font: inherit; padding: 0.45rem 0.5rem;
      background: #fff; border: 1px solid #cfc8bc; border-radius: 6px; }}
    label.check {{ font-weight: 400; }}
    label.check input {{ margin-right: 0.4rem; }}
    button {{ margin-top: 1.25rem; font: inherit; padding: 0.55rem 0.9rem;
      background: #1d4e39; color: #fff; border: 0; border-radius: 6px; cursor: pointer; }}
    .ok, .error {{ padding: 0.75rem 1rem; border-radius: 8px; }}
    .ok {{ background: #e5f4ea; }}
    .error {{ background: #fde8e4; }}
    pre {{ white-space: pre-wrap; margin: 0.5rem 0 0; font-size: 0.9rem; }}
  </style>
</head>
<body>
  <main>
    {body}
  </main>
</body>
</html>
"""
