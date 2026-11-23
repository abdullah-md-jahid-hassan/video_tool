# The cut steps

The engine does not build a shell command. `clip` calls PyAV in this order. The report's `command` field is only a short label, `("av", source, dest)`, so a failure can name the file. It is not a command you run.

## Read

`av.open(source)` then:

- duration is `container.duration / av.time_base` when the container duration is above 0, otherwise unknown
- each stream records its codec name, kind, video width and height, or audio sample rate and channel count
- the language tag comes from the stream metadata when it is present

`key_packets` demuxes one video stream and stores `K__` when `packet.is_keyframe` is true, otherwise `___`.

## Write

```text
av.open(dest, "w", options={"movflags": "+faststart"})   # only when faststart is set
output.add_stream_from_template(input_stream)            # once per kept stream
input.seek(start_microseconds, backward=True, any_frame=False)   # only when start > 0
input.demux(kept_streams)
output.mux(packet)                                       # after the timestamp shift
```

`start_microseconds` is `int(start_seconds * av.time_base)`. `av.time_base` is 1000000.

A packet with size 0 is skipped. A packet whose time is at or after the end is not written. The first timestamp of each stream becomes 0 by subtracting it from later `pts` and `dts` values on that stream.

## After the write

The new file is opened again with the same read path. The checks are in [Limits](limits.md). Any failure deletes the destination.

## The command line

`video-clip` only fills a `ClipRequest` and calls `clip`. It does not add its own media flags.

```bash
.venv/bin/video-clip INPUT.mp4 outputs/clip.mp4 --start 00:01:00 --end 00:02:00
```

Optional flags: `--map 0:v:0` (repeatable), `--overwrite`, `--faststart`, `--drop-rejected-streams`, `--exact` (always refused).
