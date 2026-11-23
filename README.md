# video-cliping

Cut a piece out of a video on this computer. The tool copies the original video and audio packets with FFmpeg. It does not encode the picture again, so the quality stays the same and the bitrate stays the same.

A short clip of a long file is about as big as that slice of the file, plus a small container header. It does not come out fatter than the source.

## What you need

- Python 3.11 or newer
- `ffmpeg` and `ffprobe` on your `PATH`

The Python package has no runtime dependencies. It does not download FFmpeg.

On Ubuntu or Debian:

```bash
sudo apt install ffmpeg
```

That package includes both `ffmpeg` and `ffprobe`.

## Install

From the project folder, using the local virtualenv:

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

`.[dev]` also installs pytest. For the tool only:

```bash
.venv/bin/pip install -e .
```

## Cut a clip

The destination folder must already exist. `outputs/` is gitignored, so create it once:

```bash
mkdir -p outputs
.venv/bin/video-clip INPUT.mp4 outputs/clip.mp4 --start 00:01:00 --end 00:02:00
```

On success the command prints the file it wrote and how long that file is:

```text
wrote /absolute/path/outputs/clip.mp4 (61.200s)
```

The length can be a little longer than the times you asked for. See [Where the cut starts](#where-the-cut-starts).

### Times

`--start` and `--end` accept either form:

| Form | Example | Meaning |
|---|---|---|
| Seconds | `90` or `90.5` | 90 seconds, or 90.5 seconds |
| Clock | `01:30` or `00:01:30.500` | minutes:seconds, or hours:minutes:seconds |

Leave `--start` off to begin at the start of the file. Leave `--end` off to stop at the end of the file. Leave both off to copy the whole file into a new container, still without encoding.

### Options

```text
video-clip SOURCE DEST [--start TIME] [--end TIME] [options]
```

| Option | What it does |
|---|---|
| `--map 0:v:0` | Keep one stream. `v` is video, `a` is audio, `s` is subtitles. The last number is which stream of that kind, starting at 0. Repeat the flag to keep more than one. The default is every stream. |
| `--overwrite` | Replace `DEST` if it is already there. Without this flag, an existing file is left untouched. |
| `--faststart` | Move the MP4 or MOV index to the front of the file so a player can start sooner. Allowed only when `DEST` ends in `.mp4` or `.mov`. This does not re-encode. |
| `--drop-rejected-streams` | If the new container cannot hold a stream (for example bitmap subtitles inside MP4), write the clip without that stream and print which codec was dropped. Without this flag, the cut fails and the partial file is removed. |
| `--exact` | Always refused. A cut on an exact frame would encode the video. This tool will not do that quietly. |

`--map` examples:

```bash
# Picture and the second audio track only
.venv/bin/video-clip INPUT.mp4 outputs/clip.mp4 --start 10 --end 40 --map 0:v:0 --map 0:a:1

# Picture only
.venv/bin/video-clip INPUT.mp4 outputs/silent.mp4 --start 10 --end 40 --map 0:v:0
```

`SOURCE` and `DEST` must not be the same file. A path cannot contain a newline.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | The clip was written and the checks passed. |
| 2 | The request was refused before a finished file: missing file, bad time, same path, dest already exists, missing `ffmpeg`/`ffprobe`, container refused a stream, or `--exact`. |
| 1 | `ffmpeg` failed, or the new file failed the duration or size check. A bad output file is deleted. |

The error text goes to stderr. It does not include a Python traceback.

## Where the cut starts

Compressed video can only be copied from a **keyframe** (a full saved picture). Frames between keyframes store only the difference from that picture, so a copy cannot start in the middle of them.

If you ask for `00:01:00` and the previous keyframe is at `00:00:58.400`, the clip starts at `00:00:58.400`. The end still stops at the time you asked for. Every frame that is kept is an original frame.

On many MP4 files the gap is about 1–2 seconds. On some camera files it is longer. After the cut, the tool checks that the new file is not more than 30 seconds longer than you asked. If it is, the cut is treated as a failure and the file is removed.

## What this tool will not do

These all need a new encode, which can change quality and file size:

- a cut on an exact frame
- scale, crop, rotate, text, watermark, or fade
- a new codec, a new frame rate, or a smaller bitrate
- volume or speed changes

Joining several files, cutting a hole out of the middle, and splitting one file into many pieces are described in `docs/core_engine/` and are not in this version.

## Use it from Python

```python
from pathlib import Path

from video_cliping import ClipRequest, clip, inspect

info = inspect(Path("INPUT.mp4"))
print(info.duration_s, info.streams)

report = clip(
    ClipRequest(
        source=Path("INPUT.mp4"),
        dest=Path("outputs/clip.mp4"),
        start="00:01:00",
        end="00:02:00",
    )
)
print(report.dest, report.output_duration_s, report.output_size_bytes)
```

`start` and `end` take the same values as the command line. `start=None` means the start of the file. `end=None` means the end of the file.

`clip` raises `video_cliping.errors.EngineError` (or a subclass) when the cut does not finish. It does not return a half-written success.

`key_packets(path)` returns video packet headers. A flags string that contains `K` is a keyframe, which is where a later cut can start.

## Tests

```bash
.venv/bin/pytest
```

The tests do not need a real video or a real `ffmpeg`. They check the command that would be run, and the checks that accept or delete the output.

## Design notes

`docs/core_engine/` is the design the code follows: how stream copy works, the commands, the limits, and the Python contract.

## Layout

```text
src/video_cliping/    the package
tests/                pytest
docs/core_engine/     design
requirements-dev.txt  pinned pytest and its dependencies, with hashes
```
