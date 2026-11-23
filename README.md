This is a video clipping tool.

It cuts a video on this computer by copying the original packets. The picture is not encoded again, so the quality stays the same and the file does not get a higher bitrate.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

PyAV is installed inside `.venv` with the package. A system `ffmpeg` is not required.

## Cut a clip

```bash
.venv/bin/video-clip INPUT.mp4 outputs/clip.mp4 --start 00:01:00 --end 00:02:00
```

`--start` and `--end` take seconds (`90`) or a clock (`00:01:30`). Leave `--end` off to keep going until the file ends.

The cut starts on a keyframe, so it can begin a little before the time you asked for. The frames that are kept are the original frames.

## Open the page

From the project folder:

```bash
.venv/bin/video-clip-web
```

Open http://127.0.0.1:8000/ . The only tool is Video clipping. Choose a video, set the start and end, and the other copy options. If you leave the destination folder empty, the clip is written to `outputs/cliping`.

## Checks

```bash
.venv/bin/pytest
```
