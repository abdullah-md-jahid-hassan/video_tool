# Functionality

Every operation the engine can be asked to do. "Inside the rules" means fast, local, original packets, and no new bitrate.

The planned Python names are in [python-contract.md](python-contract.md). The commands are in [commands.md](commands.md).

## Inside the rules

These are the engine. Each one uses `-c copy` (or is a read-only `ffprobe` call).

### 1. Inspect a file

Read the container and the streams. No output media file.

Reports:

- container format and duration
- file size
- for each stream: index, type, codec, and, when the headers have them, width, height, frame rate, sample rate, channels, language, bitrate
- whether the file looks seekable enough to cut (a duration and at least one video or audio stream)

Used before every cut, and as its own call when a caller only wants the facts.

### 2. List video key packets

Read packet headers for one video stream and return the times of packets marked as key packets. This is a read. It does not write a video.

The caller uses the list to see where a later cut will really start. The greatest key time that is still `<=` the asked start is the start the clip will keep.

Scanning packets does not decode pixels. Decoding every frame just to find keyframes is slower and is not the default.

### 3. Clip one range

Copy the packets from a start time to an end time into a new file.

- Start snaps to the seek point at or before the asked start (see [how it works](how-it-works.md)).
- End stops at the asked end, on a packet boundary.
- Default: every stream (`-map 0`).
- Timestamps are shifted so the file starts at 0 (`-avoid_negative_ts make_zero`).
- Optional: keep only some streams, by index or by type.

The output is a normal media file. Players open it on its own.

### 4. Clip many ranges

Run clip once per range. Ranges come from one source and go to separate files. One failure does not delete clips that already succeeded. The result lists each range as success or error.

Ranges may overlap. The engine does not merge them unless the caller asked for a join.

### 5. Clip from a time to the end

Same as a clip whose end is the source duration from `ffprobe`.

### 6. Clip the first N seconds

Same as a clip from `0` to `N`. A start at 0 is already the first seek point, so this one has no lead-in.

### 7. Clip the last N seconds

Uses `-sseof`, which is `-ss` measured from the end of the file. Negative values are earlier in the file. `0` is the end. The same keyframe rule applies at that seek point.

### 8. Cut a middle piece out

Keep the head and the tail, drop the middle, as one file.

Steps:

1. Clip from 0 to the start of the hole.
2. Clip from the end of the hole to the end of the file.
3. Join those two clips with the concat demuxer.
4. Delete the temporary clips after the join is checked.

Both edges snap to seek points, so the hole can be a bit shorter or longer than asked, by up to one group of pictures on each edge. The packets that remain are original.

More than one hole is the same idea: keep the ranges that are not holes, in order, then join them.

### 9. Join matching files

Concat demuxer, then `-c copy`. Allowed only when `ffprobe` says the inputs share the same stream layout: same number of streams, same codec on each, same width and height for video, same sample rate and channel count for audio.

If they do not match, the engine stops. It does not encode them into a common format.

### 10. Copy a single stream out

| Ask | Result |
|---|---|
| One video stream, no audio | Video file. Player shows silent picture. |
| One audio stream, no video | Audio file, and only if the destination container accepts that audio codec. |
| One subtitle stream | A subtitle file only when the destination format can take that subtitle codec as a copy. |

"Extract audio to MP3" from AAC is a new encode. That ask is outside the engine. "Copy the AAC stream into an `.m4a`" is inside the engine.

### 11. Choose streams

Keep a listed set, drop the rest, still with `-c copy`.

Examples:

- first video + second audio (a commentary track)
- video + all audio, no subtitles
- all audio languages, no video

Language and disposition flags travel with the stream. The `ffmpeg` manual copies disposition flags from the input stream by default.

### 12. Change the container

Remux the whole timeline, or a clipped timeline, into a new container. Codecs stay. If the new container rejects a codec, the engine fails that call or, when the caller allowed it, drops the rejected stream and says so. It does not transcode.

Optional on MP4 and MOV: `-movflags +faststart`, so the index sits at the front of the file.

### 13. Split into pieces of about N seconds

Segment muxer, `-c copy`. Each piece starts on a keyframe of the reference stream. Piece length is near N seconds, not exact, unless keyframes already sit on those times.

### 14. Edit container metadata

Set or clear a metadata key (`title`, `comment`, and similar) while copying packets. This changes tags, not pictures.

The engine does not promise that chapter times are still correct after a time cut. Chapter times belong to the source timeline. After a cut they need a rewrite that has been tested on that file. Until then, a clip does not claim valid chapters.

### 15. Check the output

After every write, `ffprobe` the new file.

- The file exists and is larger than an empty header.
- Duration is in a plausible band for the range that was asked (see [python-contract.md](python-contract.md)).
- A video stream is present when one was requested, and the same for audio.
- Output size is reported. A clip of a strict sub-range that comes out larger than the source is a failure.

## On the boundary

These keep the compressed picture and sound, but they are not a plain copy. The engine may use them only so a container will accept the packets. Each use is recorded on the result.

| Filter | When it shows up | What changes |
|---|---|---|
| `aac_adtstoasc` | AAC audio stored as ADTS (common in MPEG-TS and some FLV) is copied into MP4, MOV, or FLV. | The framing of AAC packets. The audio samples stay. Size can move by header bytes. |
| `h264_mp4toannexb` | H.264 stored in MP4 (AVCC) is copied into MPEG-TS, or the concat demuxer inserts it (`auto_convert`, default on), in particular when resolution changes between files. | The H.264 bitstream wrapper. The picture stays. |
| `hevc_mp4toannexb` | The same situation for H.265 / HEVC. | The HEVC bitstream wrapper. The picture stays. |

If the copy works with no bitstream filter, the engine adds none.

## Outside the rules

FFmpeg can do all of these. The engine does not call them on the default path. They decode and encode, so quality and size can change, and they are slow on a long file.

| Operation | Why it leaves the rules |
|---|---|
| Cut on an exact frame | The frames between the previous keyframe and the cut must be decoded and encoded again. |
| Scale, crop, pad, rotate pixels | Filters need raw frames. A display-matrix tag copied with the file is metadata. Changing pixels is an encode. |
| Burned-in text, watermark, blur, color | Same: filters, then a new video encode. |
| Change speed, reverse, new frame rate | New timestamps and new frames. |
| Volume, loudness, resample, mix audio | New audio encode. |
| Change codec (H.264 to H.265, AAC to MP3) | That is an encode by definition. |
| CRF / bitrate compress | A new encode chosen to be smaller. It also throws the "same quality" rule away. |
| GIF, thumbnail strip, waveform image | New pictures, not a copy of the video. |
| Fade in / fade out | New frames at the edges. |

A future "exact frame" mode would be a separate engine with its own rules, and it would be named as a re-encode. It is not a silent fallback of this engine. If a caller needs an exact frame, this engine fails the request with a clear error rather than encoding behind their back.

## What "all streams" includes

| Source contents | Default `-map 0` | If the destination refuses a stream |
|---|---|---|
| One video, one audio | Both copied. | Fail, or drop the refused stream if the caller allowed drops. |
| Several audio languages | All copied. | Same. |
| Text subtitles the container accepts | Copied. | — |
| Bitmap subtitles into MP4 | The MP4 muxer rejects them. | Drop subtitles and report that, or fail if drops are not allowed. |
| Attachments (MKV fonts) into MKV | Copied, because `-map 0` includes them. | Into MP4, dropped or failed the same way. |
| Chapters | Not treated as reliable after a time cut. | See metadata above. |
