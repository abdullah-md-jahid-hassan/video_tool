# Python contract

This is the public surface of the package. Behavior that disagrees with this page is a bug.

The package depends on Python 3.12+ and `av==19.0.2`, installed in `.venv`. It does not shell out to `ffmpeg` or `ffprobe`.

## Time values

A time argument is one of:

- a `float` or `int`, meaning seconds (`90`, `90.5`)
- a string `SS`, `MM:SS`, or `HH:MM:SS`, with an optional fractional part (`.500`)

The engine converts every value to seconds before the cut. It does not pass the original text to PyAV.

## Types

```text
MediaInfo
  path
  format_name
  duration_s          # None when the container has no duration
  size_bytes
  streams             # tuple of StreamInfo

StreamInfo
  index               # container index
  codec_type          # video, audio, subtitle, data, attachment
  codec_name
  width, height       # video, else None
  sample_rate         # audio, else None
  channels            # audio, else None
  language            # None when the tag is absent

KeyPacket
  time_s              # None if the packet has no pts and no dts
  flags               # "K__" for a key packet, otherwise "___"

ClipRequest
  source
  dest
  start               # None means 0
  end                 # None means through the end of the file
  maps                # None means every stream
  drop_rejected_streams   # default False
  faststart           # default False; only .mp4 and .mov
  overwrite           # default False
  exact               # default False; True raises OutsideEngine

ClipReport
  source
  dest
  requested_start_s
  requested_end_s
  output_duration_s
  output_size_bytes
  streams_copied
  streams_dropped
  bitstream_filters   # always empty; packet copy does not add a filter
  command             # ("av", source, dest)
```

`maps` entries look like `0:v:0`. The letter is the kind. The number counts streams of that kind, starting at 0. A free-form argument string is rejected.

## Functions

Paths are filesystem paths. The functions are synchronous. A function returns its result or raises one of the errors below.

### `inspect(path) -> MediaInfo`

Read the file. Does not write.

### `key_packets(path, video_stream=0) -> tuple[KeyPacket, ...]`

Packet times for that video stream. `video_stream` counts video streams, starting at 0.

### `clip(request: ClipRequest) -> ClipReport`

Copy one range. The steps are in [The cut steps](commands.md). Checks before any write:

- source is a file
- dest is not the source, not a folder, and its parent folder exists
- if dest exists, `overwrite` is true
- paths do not contain a newline
- maps are valid, and each named stream exists
- `faststart` is false, or the dest suffix is `.mp4` or `.mov`
- `exact` is false
- start is before end, and the range sits inside the duration when the duration is known

After the copy, read the dest:

- duration is at least the asked length minus 0.5 s
- duration is at most the asked length plus 30 s
- a duration of 0 fails
- size is smaller than the source when the asked range is not the whole file
- every copied stream type is present

A failed check deletes dest.

## Errors

```text
EngineError
  InputNotFound
  BadRange
  SamePath
  Exists
  OutsideEngine        # exact=True
  ContainerRejected    # muxer refused a stream and drops are not allowed
  FfmpegFailed         # PyAV could not read or write; the message is on the exception
  OutputCheckFailed
```

`ToolMissing` and `StreamMismatch` are still subclasses, so an older caller can catch them. The current cutter does not raise them.

`FfmpegFailed`, `ContainerRejected`, and `OutputCheckFailed` keep a `command` list. `FfmpegFailed` and `ContainerRejected` also keep `stderr` with the library message. They do not keep the media bytes.

## What a caller does for an exact frame

The caller sets `exact=True`. The engine raises `OutsideEngine` and does not open the destination. There is no silent encode path in this package.
