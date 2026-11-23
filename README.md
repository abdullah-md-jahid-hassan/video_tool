This is a video clipping tool.

It cuts a video on this computer by copying the original packets. The picture is not encoded again, so the quality stays the same and the file does not get a higher bitrate.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

`ffmpeg` and `ffprobe` must be on your PATH. The package does not download them.

## Cut a clip

```bash
.venv/bin/video-clip INPUT.mp4 outputs/clip.mp4 --start 00:01:00 --end 00:02:00
```

`--start` and `--end` take seconds (`90`) or a clock (`00:01:30`). Leave `--end` off to keep going until the file ends.

The cut starts on a keyframe, so it can begin a little before the time you asked for. The frames that are kept are the original frames.

## Checks

```bash
.venv/bin/pytest
```
