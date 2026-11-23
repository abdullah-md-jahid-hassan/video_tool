# How it works

This page is the mechanism. The commands are in [commands.md](commands.md). The function list is in [functionality.md](functionality.md).

## The pieces inside a video file

A video file is a **container** (MP4, MKV, MOV, WebM, MPEG-TS) holding one or more **streams**:

| Stream | What it carries |
|---|---|
| Video | Compressed pictures, one **packet** per frame or slice. |
| Audio | Compressed sound packets. A file can have more than one audio stream (languages, commentary). |
| Subtitle | Text or bitmap captions. |
| Data | Extra timed data. |
| Attachment | Files stored inside the container, such as a subtitle font in MKV. |

Each packet already contains the compressed bytes. The engine moves those bytes. It does not open them into pixels.

`ffprobe` reads the container and the stream headers. `ffmpeg` does the copy.

## Stream copy

`-c copy` tells FFmpeg that the output stream is **not re-encoded**. The manual's words: `copy` (output only) means the stream is not to be re-encoded.

What that gives you:

- The CPU does almost no codec work. Time is spent reading and writing.
- Memory stays small, because frames are not turned into images.
- Each kept video packet is byte-for-byte the source packet.
- Each kept audio packet is byte-for-byte the source packet.
- The bitrate of the kept media stays the bitrate of the source.

A **bitstream filter** is a different step. It can rewrite the packet wrapper (headers around the same compressed data) so another container will accept it. That is still not a new encode. The engine may use one only for that reason. See [Limits](limits.md).

A **filter** (`scale`, `crop`, `overlay`, `volume`, `atrim` as a filter, and the rest of libavfilter) needs decoded frames or samples. The engine does not use filters. A filter forces a new encode, which leaves the rules.

## Keyframes

A compressed video is stored in groups:

- A **keyframe** (also called an I-frame, or a seek point) can be decoded by itself.
- The frames after it store only the difference from nearby frames. They cannot be decoded alone.

Players and FFmpeg can jump to a keyframe. They cannot jump to the middle of a group and still copy packets, because the first copied frame would have nothing to build on.

From the `ffmpeg` manual, `-ss` used **before** `-i` seeks to the closest seek point **before** the time you asked for. Two different things happen next:

| Mode | What happens to the gap between the seek point and your time |
|---|---|
| New encode, accurate seek (the default when encoding) | That gap is decoded and thrown away. The output can start on the exact time. |
| Stream copy | That gap is **kept**. The clip starts at the seek point, which is at your time or earlier. |

So a stream-copy clip is exact only when the start time is already a keyframe. Otherwise it starts early, by up to one group of pictures. On many internet MP4 files that group is about 1–2 seconds. On some camera and screen files it is 5–10 seconds, or longer. The pictures inside the clip are still the original pictures.

The end behaves the same way in spirit: FFmpeg stops at the requested end time, on a packet boundary. The last picture is still an original packet.

This is the whole accuracy limit of the engine. An exact-frame cut needs a new encode, and that cut is outside the engine.

## Where the flags sit

FFmpeg cares whether a flag is before `-i` (it applies to the input) or before the output path (it applies to the output).

The engine's cut puts `-ss` and `-to` **before** `-i`:

```text
ffmpeg -ss START -to END -i INPUT -map 0 -c copy -avoid_negative_ts make_zero OUTPUT
```

- `-ss START` as an input option seeks to the seek point at or before `START`, and stream copy keeps the packets from there.
- `-to END` as an input option stops reading the input at `END`.
- `-t` and `-to` are mutually exclusive. If both are present, `-t` wins. The engine uses `-to` for a cut with a known end, and does not also pass `-t`.

Why both flags are on the input, and not "seek, then keep N seconds":

If `-ss` is before `-i` and `-t DURATION` is on the output, the lead-in from the previous keyframe is part of those N seconds. The clip then ends early by about the length of that lead-in. Putting `-to END` on the input stops at the source's end time, and the lead-in is extra time at the front, which matches the manual.

## Timestamps

After a seek, the first packets can carry a negative timestamp or a timestamp from the middle of the source. Players then show a wrong clock, or wait, or drop the start.

`-avoid_negative_ts` is an output option. The engine uses `make_zero`, which shifts timestamps so the first timestamp is 0. The manual states:

- The same shift is applied to every output timestamp.
- Audio, video, and subtitles stay in the same relationship they had before the shift.

`make_non_negative` only fixes leading negative timestamps. `auto` shifts when the destination format requires it. `disabled` leaves timestamps alone. `make_zero` is the one that makes a clip start at 0.

`-copyts` keeps the source timestamps, including the start offset. The engine does **not** use `-copyts` for a clip. A clip should start at 0. `-start_at_zero` only matters together with `-copyts`, so the engine does not use it either.

## Which streams get copied

With no `-map`, FFmpeg picks streams for you. From the manual, for each type the destination can hold, it picks:

- one video: the one with the highest resolution
- one audio: the one with the most channels
- one subtitle: the first subtitle whose type (text or bitmap) matches what the destination prefers

Data streams and attachments are not picked unless you map them.

That default drops extra languages and extra camera angles. The engine's default is `-map 0`, which takes **every** stream from the first input, including data and attachments.

If the destination container cannot store one of those streams, the engine drops that stream, writes the rest, and reports what it dropped. It does not encode the stream into a different codec to force it in. Details are in [Limits](limits.md).

Per-stream skips exist and stay inside stream copy, because they only choose packets:

| Flag | Effect |
|---|---|
| `-vn` | No video. |
| `-an` | No audio. |
| `-sn` | No subtitles. |
| `-dn` | No data. |

`-map 0:v:0 -map 0:a:1` is the precise form: first video stream, second audio stream.

## Containers

The container is the box. The codec is the contents. Stream copy can put the same contents in a new box when the box allows that codec.

Examples that usually work:

| From | To | Typical codecs |
|---|---|---|
| MKV | MP4 | H.264 or H.265 video, AAC audio |
| MP4 | MKV | Same, and MKV also accepts many subtitle codecs MP4 refuses |
| MOV | MP4 | H.264 / AAC |

Examples that fail until something is encoded, which the engine will not do:

| Case | Why |
|---|---|
| VP9 or AV1 in WebM into a normal MP4 | The MP4 muxer often rejects those codecs unless a specific brand of MP4 is used. If the muxer rejects them, the engine stops. |
| TrueHD or DTS-HD into MP4 | MP4 does not accept those audio codecs. |
| DVD bitmap subtitles into MP4 | MP4 wants a text subtitle codec (`mov_text`), and converting is a new subtitle encode. |

`-movflags +faststart` on MP4 or MOV moves the packet index from the end of the file to the start. The manual describes that index as metadata about packets, normally written at the end, moved to the front so playback can start before the whole file is downloaded. The media packets are still copied. This is a layout change, not a new encode. Size stays the same aside from container bookkeeping.

## Joining clips

The **concat demuxer** reads a text list and demuxes the files one after another, as if their packets had been muxed together. Timestamps are adjusted so the first file starts at 0 and the next file starts where the previous one ended.

The manual's requirement: **all files must have the same streams** (same codecs, same time base, and the rest). If the reported duration of a file is wrong, the join can show a gap or a glitch. The engine uses this only after it has checked that the streams match.

The concat demuxer's `inpoint` and `outpoint` seek inside each file. The manual says they work best with intra-frame codecs (every frame is a keyframe). On normal long-GOP video you still get extra packets. The engine does **not** use `inpoint` / `outpoint` to do an exact cut. It cuts each piece with the normal clip command, then joins the pieces.

`safe` defaults to 1. In that mode a path must be relative and use only letters, digits, period, underscore, and hyphen. Absolute paths need `safe` set to 0. The engine writes the list file itself and passes absolute paths, so it sets `-safe 0`. It does not accept a concat script from outside.

`auto_convert` defaults to 1. The only conversion the manual names is adding the `h264_mp4toannexb` bitstream filter on H.264-in-MP4, which is needed in particular when the resolution changes between files. That filter changes the packet wrapper, not the picture.

## Splitting on a clock

The **segment muxer** writes the output as several files of nearly fixed duration. Every segment starts with a keyframe of the reference stream. The manual says accurate splitting needs the input keyframes to sit on the split times you want. Otherwise the next file starts at the next keyframe after the time you asked for. It also works best with a single constant-frame-rate video.

The engine can use this to chop a file into pieces. The pieces follow keyframes. They are "about" N seconds, which is the manual's own word ("nearly fixed duration").

## Size

Stream copy keeps the source bitrate, so size follows duration.

| Output | Expected size |
|---|---|
| A clip of part of a file | About `(copied duration / source duration) × source size`, plus a small container header. Copied duration includes the keyframe lead-in, so a short clip can be a little bigger than `asked duration × bitrate`. It stays smaller than the source unless the asked range is almost the whole file. |
| Remux of the whole file | About the same size as the source. Header layout can differ by kilobytes. |
| Several clips joined | About the sum of the clips. |
| `+faststart` | Same media bytes, index moved to the front. |
| Bitstream filter required by the container | Same compressed picture and sound. Header bytes around packets can change the file by a small amount. |

A new encode is the path that can make a file much larger or much smaller. That path is outside the engine.

## What the engine does around FFmpeg

FFmpeg is the cutter. The engine is the guard around it.

1. Reject a missing input, a bad time range, or an output path that is the same file as the input.
2. Run `ffprobe` and remember duration, codecs, and stream indexes.
3. Build an argument list. Never build a shell string.
4. Run `ffmpeg`. On a non-zero exit, keep the tail of stderr and raise.
5. Run `ffprobe` on the output. Check that the file exists, that expected streams are present, and that the duration is plausible for the range that was asked.
6. Return a report: paths, requested times, output duration, output size, streams copied, streams dropped.

The duration check is how the engine catches a cut that "succeeded" with an empty or tiny file. The check does not decode the picture.
