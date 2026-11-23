# Limits

## The cut starts on a keyframe

Seek lands on a keyframe at or before the start you asked for. The output can be longer than the range by that lead-in. The kept frames are still the original frames. An exact frame that is not a keyframe needs a new encode, so `exact=True` raises `OutsideEngine` and writes nothing.

## The safety check is loose on purpose

The cut does not scan key packets before copying. The duration check therefore allows:

- up to 0.5 seconds shorter than the asked length (a packet can end a little early)
- up to 30 seconds longer than the asked length

A duration of 0 fails. A partial clip must be smaller than the source. A failed check deletes the new file.

## Containers

The destination must be able to store the source codecs. PyAV raises when it cannot. With `drop_rejected_streams`, that stream is omitted and the others are copied. Without it, the cut raises `ContainerRejected` and deletes the new file.

`faststart` is only for `.mp4` and `.mov`. Other suffixes are refused before the file is opened.

## Paths

The source must be a file. The destination's folder must already exist. The destination cannot be the source. An existing destination is kept unless `overwrite` is set. A path with a newline is refused.

## Time

Start must be before end. Both must fall inside the file when the file has a duration. A file with no duration cannot take a time range. Times are seconds, or `SS`, `MM:SS`, `HH:MM:SS`, with an optional fraction.

## What this package will not paper over

Joining files, several ranges, and a timer split are not implemented. A caller that needs them has to make separate `clip` calls, and only when the streams already match. This package does not check that match for you.
