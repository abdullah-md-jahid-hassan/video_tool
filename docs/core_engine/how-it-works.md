# How it works

A video file is a container. Inside it, each stream (picture, sound, subtitles) is a row of compressed packets. A packet is a small piece of the already-encoded stream. Copying a packet keeps the original bytes.

## Keyframes

Most video codecs store a full picture only every so often. That packet is a keyframe. The packets after it describe changes from that picture. A player cannot start in the middle of those changes.

When you ask for a start time, PyAV seeks backward to a keyframe. The output can therefore begin a little before the second you asked for. The extra lead-in is original packets, not a new encode. The end stops at the first packet whose time is at or after the end you asked for.

`key_packets` can list those times. The cut itself does not scan them first. The safety check allows up to 30 seconds of lead-in for that reason. See [Limits](limits.md).

## One cut

1. Open the source with PyAV and read the duration and the streams.
2. Check the times, the paths, and the stream map.
3. Open the destination. For `.mp4` and `.mov`, `faststart` sets the container option `movflags=+faststart`, which puts the index at the front.
4. Add one output stream per kept input stream, using the source stream as the template. The codec is copied, not chosen again.
5. If the container refuses a stream and `drop_rejected_streams` is true, that stream is left out. If the flag is false, the cut stops and the new file is deleted.
6. If the start is after 0, seek to that time in `av.time_base` units (microseconds), backward, and only to a keyframe.
7. Read packets from the kept streams. Skip an empty packet. Skip a packet at or after the end. Stop once every kept stream has passed the end, so the rest of a long file is not read.
8. Shift each stream so its first kept timestamp is 0. Write the packet.

## Size

The bitrate of the kept packets does not change. The new file is smaller when the range is shorter than the source, plus a small container header and any keyframe lead-in. A partial clip that is not smaller than the source fails the check, and the file is deleted.

## What is not happening

There is no filter, no scale, no new codec, and no shell call to `ffmpeg` or `ffprobe`.
