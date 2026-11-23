"""List folders on this computer so the form can store a real path."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_MAX_ENTRIES = 400
_MAX_PATH = 4096


class BrowseError(Exception):
    """The folder cannot be listed."""


@dataclass(frozen=True)
class BrowseEntry:
    """One name inside a folder."""

    name: str
    path: Path
    is_dir: bool


def start_directory(kind: str, source: str, dest_dir: str) -> Path:
    """Pick the folder the chooser opens first."""
    if kind == "folder":
        found = _folder_or_parent(dest_dir)
        if found is not None:
            return found
    found = _folder_or_parent(source)
    if found is not None:
        return found
    return Path.home().resolve()


def open_directory(text: str) -> Path:
    """Return a real folder.

    Raises:
        BrowseError: The path is empty, too long, or not a folder.
    """
    if not text.strip() or len(text) > _MAX_PATH or _bad_text(text):
        raise BrowseError("That folder is not a valid path.")
    path = Path(text).expanduser()
    try:
        resolved = path.resolve()
        is_dir = resolved.is_dir()
    except OSError as exc:
        raise BrowseError("That folder could not be opened.") from exc
    if not is_dir:
        raise BrowseError("That path is not a folder.")
    return resolved


def list_directory(folder: Path) -> tuple[tuple[BrowseEntry, ...], bool]:
    """Return names in folder, and True when the list was cut off.

    Raises:
        BrowseError: The folder cannot be read.
    """
    try:
        names = list(folder.iterdir())
    except OSError as exc:
        raise BrowseError("That folder could not be opened.") from exc
    names.sort(key=lambda path: path.name.casefold())
    visible = [path for path in names if not path.name.startswith(".")]
    truncated = len(visible) > _MAX_ENTRIES
    entries: list[BrowseEntry] = []
    for path in visible[:_MAX_ENTRIES]:
        entry = _entry(path)
        if entry is not None:
            entries.append(entry)
    entries.sort(key=lambda item: (not item.is_dir, item.name.casefold()))
    return tuple(entries), truncated


def _folder_or_parent(text: str) -> Path | None:
    if not text.strip() or len(text) > _MAX_PATH or _bad_text(text):
        return None
    path = Path(text).expanduser()
    try:
        if path.is_dir():
            return path.resolve()
        if path.is_file():
            return path.resolve().parent
    except OSError:
        return None
    return None


def _entry(path: Path) -> BrowseEntry | None:
    try:
        resolved = path.resolve()
        return BrowseEntry(path.name, resolved, resolved.is_dir())
    except OSError:
        return None


def _bad_text(text: str) -> bool:
    return "\n" in text or "\r" in text or "\x00" in text
