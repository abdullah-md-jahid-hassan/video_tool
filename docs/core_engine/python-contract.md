# Python contract

The public surface the package should grow into. Nothing here is implemented yet. Names are the contract. Behavior that disagrees with this page is a bug.

Rules and mechanism: [README](README.md), [how it works](how-it-works.md). Operations: [functionality](functionality.md). Process arguments: [commands](commands.md).

The package depends on the Python standard library plus the `ffmpeg` and `ffprobe` executables. It does not depend on MoviePy, PyAV, NumPy, or a downloaded FFmpeg binary.

## Time values

A time argument is one of:

- a `float` or `int`, meaning seconds (`90`, `90.5`)
- a string FFmpeg accepts: `SS`, `MM:SS`, `HH:MM:SS`, with an optional fractional part (`.500`)

The engine converts numbers to seconds for its own checks, and passes strings through. It does not invent a time format of its own.

## Types

```text
MediaInfo
  path
  format_name
  duration_s          # None when the container has no duration
  size_bytes
  streams: list[StreamInfo]

StreamInfo
  index
  codec_type          # video, audio, subtitle, data, attachment
  codec_name
  width, height       # video, else None
  sample_rate         # audio, else None
  channels            # audio, else None
  language            # None when the tag is absent

KeyPacket
  time_s              # None if the packet has no pts_time
  flags               # ffprobe flags string; "K" means a key packet

ClipRequest
  source
  dest
  start               # None means 0, except for clip_last
  end                 # None means "through the end of the file"
  maps                # None means -map 0
  drop_rejected_streams   # default False
  faststart           # default False; only meaningful for MP4/MOV
  overwrite           # default False

ClipReport
  source
  dest
  requested_start_s
  requested_end_s
  output_duration_s
  output_size_bytes
  streams_copied: list[StreamInfo]
  streams_dropped: list[StreamInfo]
  bitstream_filters: list[str]    # empty when none were needed
  command: list[str]
```

`maps` is a list of stream specs in FFmpeg's own syntax: `0:v:0`, `0:a:1`, `0:s:0`. The engine does not accept a free-form FFmpeg argument string from the caller.

## Functions

All paths are filesystem paths. All functions are synchronous. A function either returns its result or raises one of the errors below. It does not return a half-success without saying so, except `clip_many`, which returns one result per range.

### `inspect(path) -> MediaInfo`

Probe the file. Read-only.

### `key_packets(path, video_stream=0) -> list[KeyPacket]`

Packet times for that video stream. A key packet has `K` in `flags`.

### `clip(request: ClipRequest) -> ClipReport`

The canonical cut. Implements [commands](commands.md) "Clip one range", "to the end", and stream maps.

Checks before `ffmpeg`:

- `ffmpeg` and `ffprobe` exist on `PATH`
- source exists and is a file
- dest is not the same file as source
- dest's parent directory exists
- if dest exists, `overwrite` is true
- `start < end` when both are known
- `start` and `end` fall inside the probed duration when the duration is known
- `faststart` is false, or the dest suffix is `.mp4` or `.mov`

After `ffmpeg`, probe the dest:

- duration is at least the asked length minus 0.5 s (packet boundaries can end a little early)
- duration is at most the asked length plus the keyframe lead-in
- when key packets were not scanned, the lead-in allowance is 30 s, and a duration of 0 fails
- when key packets were scanned, the lead-in allowance is `(requested_start - actual_key_time) + 0.5 s`
- size is less than the source size when the asked range is not the whole file
- every requested stream type that was not dropped is present

A failed check deletes dest.

### `clip_many(source, ranges, dest_dir, **same options) -> list[ClipReport | RangeError]`

One clip per `(start, end, dest_name)`. A bad range becomes a `RangeError` in the list. Later ranges still run. Dest paths that already succeeded are left in place.

### `clip_last(source, dest, seconds, **options) -> ClipReport`

Last N seconds, via `-sseof`.

### `cut_out(source, dest, holes, **options) -> ClipReport`

`holes` is a list of `(start, end)` ranges to drop, in source time, not overlapping, in order. The engine clips the kept spans and joins them. Temporary files live in a directory the engine creates and always deletes.

### `concat(sources, dest, **options) -> ClipReport`

Join with the concat demuxer after the stream-match check in [limits](limits.md). `sources` has at least two files.

### `remux(source, dest, **options) -> ClipReport`

Whole-file copy into a new container. `faststart` follows the same rule as `clip`.

### `split(source, dest_pattern, segment_seconds, **options) -> list[ClipReport]`

Segment muxer. `dest_pattern` contains a printf-style index (`piece-%03d.mp4`). Each created file is probed. A file that fails the probe is deleted, and the call raises. Files that passed stay, and the error names the index that failed.

## Errors

```text
EngineError
  ToolMissing          # ffmpeg or ffprobe not on PATH
  InputNotFound
  BadRange             # empty, backwards, or outside the probed duration
  SamePath             # dest is the source
  Exists               # dest exists and overwrite is false
  OutsideEngine        # caller asked for a filter, a new codec, or an exact frame
  StreamMismatch       # concat inputs do not match
  ContainerRejected    # muxer refused a stream and drops are not allowed
  FfmpegFailed         # non-zero exit; stderr tail is on the exception
  OutputCheckFailed    # ffmpeg exited 0, probe did not match the request
```

`FfmpegFailed` and `OutputCheckFailed` include the command list. They do not include the media bytes.

Stderr stored on the error is the last 200 lines, not the whole log of a long run.

## Process rules

- `shell=False`. The argument vector is the command in [commands](commands.md).
- Timeout is the caller's, default 60 seconds for `ffprobe` and no timeout for `ffmpeg` copy of a large file. A copy of a big file is I/O bound and can be slow on a spinning disk or a network mount. The caller can pass a timeout.
- The engine does not read `FFMPEG_*` wrappers that change codecs. It calls the binary it found on `PATH`.
- Working directory does not matter. Paths passed to FFmpeg are absolute.

## What a caller does for an exact frame

The caller asks `clip`. If they also set a flag such as `exact=True`, the engine raises `OutsideEngine` and does not run. There is no silent encode path in this package.

A different package can offer an encode later. It must not reuse these function names for that behavior.
