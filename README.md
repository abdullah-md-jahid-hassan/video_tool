# video-cliping

Cut a video on this computer by copying the original packets. The picture and the sound are not encoded again, so the quality stays the same and the bitrate does not go up.

PyAV (`av`) does the copy. It is installed inside the project `.venv`. A system `ffmpeg` is not required, and nothing is downloaded the first time you cut a file.

## What you can do

- Cut one time range from a local file.
- Keep every stream, or only the ones you name (`0:v:0`, `0:a:1`).
- Leave out a stream the destination container cannot store.
- Move the MP4 or MOV index to the front of the file (`--faststart`), so playback can start sooner. The packets stay the original packets.
- Do the same cut from the command line, from the local page, or from Python. All three call the same cutter.

## What this tool will not do

- Cut on an exact frame that is not a keyframe. That needs a new encode, so `--exact` is refused and no file is written.
- Join files, cut several ranges in one call, or split a file on a timer.
- Change the codec, the size, the frame rate, or the volume.

The cut can start a little before the time you asked for, because it has to start on a keyframe. The frames that are kept are still the original frames. A shorter range makes a smaller file. A partial clip that is not smaller than the source is deleted.

## Requirements

- Python 3.12 or newer.
- No system `ffmpeg` or `ffprobe`.

## Setup

From this folder:

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

That installs the package, PyAV 19.0.2, and pytest into `.venv`. The same PyAV wheels are pinned with hashes in `requirements.txt`. The test packages are pinned in `requirements-dev.txt`.

## Cut a clip

The destination folder must already exist. `outputs/` is created by the page, not by the command.

```bash
mkdir -p outputs
.venv/bin/video-clip INPUT.mp4 outputs/clip.mp4 --start 00:01:00 --end 00:02:00
```

`--start` and `--end` take seconds (`90`, `90.5`) or a clock (`00:01:30`, `00:01:30.500`). Leave `--start` off to begin at the start of the file. Leave `--end` off to keep going until the file ends.

| Flag | Meaning |
|---|---|
| `--map 0:v:0` | Keep one stream. Repeat the flag to keep more. The number counts streams of that kind, starting at 0. Default: every stream. |
| `--overwrite` | Replace the destination if it already exists. |
| `--faststart` | Put the index at the front. Only `.mp4` and `.mov`. |
| `--drop-rejected-streams` | If the container refuses a stream, write the clip without it. |
| `--exact` | Always refused. |

Exit `0` means the clip was written. Exit `2` means the request was refused (bad time, missing file, existing destination). Exit `1` means the copy or the output check failed. On a failed check, the new file is deleted.

## Open the page

From this folder:

```bash
.venv/bin/video-clip-web
```

Open http://127.0.0.1:8000/ . The page listens on this computer only. The only tool is Video clipping. Choose a video on this computer, then choose a destination folder, or tick the box to save the clip in the same folder as the video. If you do neither, the clip is written to `outputs/cliping`. The page creates that folder. A clip saved next to the video gets `-clip` in the name, so the original file stays. The other fields are the same options as the command. Exact frame is refused.

```bash
.venv/bin/video-clip-web --port 8765
```

`--host` other than `127.0.0.1`, `localhost`, or `::1` is refused.

## Use it from Python

```python
from pathlib import Path

from video_cliping import ClipRequest, clip

report = clip(ClipRequest(
    source=Path("INPUT.mp4"),
    dest=Path("outputs/clip.mp4"),
    start="00:01:00",
    end="00:02:00",
))
print(report.dest, report.output_duration_s, report.output_size_bytes)
```

`inspect(path)` reads the duration and the streams. `key_packets(path)` lists video packet times. A flags value of `K__` is a key packet. The destination folder must already exist.

## Checks

```bash
.venv/bin/pytest
```

## More detail

How the packet copy works, what it refuses, and the Python types are in [docs/core_engine](docs/core_engine/README.md).
