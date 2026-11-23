# Limits

What stream copy will and will not do, and how the engine should fail. The mechanism is in [how it works](how-it-works.md).

## The cut starts on a seek point

`-ss` before `-i` seeks to the closest seek point **before** the time you asked for. In stream copy, the packets between that point and your time are kept.

| Asked start | Nearest earlier keyframe | Clip actually starts |
|---|---|---|
| 30.0 s, and 30.0 s is a keyframe | 30.0 s | 30.0 s |
| 30.0 s, previous keyframe at 28.4 s | 28.4 s | 28.4 s |
| 0 | start of file | 0 |

The end time stops the read at the asked end. The start is the side that grows.

Consequences:

- A 2-second clip can come out several seconds long when the previous keyframe is far away.
- Two different asked starts inside the same group of pictures produce the same clip start.
- "Cut exactly on this frame" is outside the engine. The engine returns an error for an exact-frame request. It does not encode to hide the gap.

Callers that need to show the real start can ask for key-packet times first ([commands](commands.md)).

## Files that seek slowly or not at all

MP4, MOV, and MKV have an index. `-ss` before `-i` jumps. A raw MPEG elementary stream, or a file with a broken index, may still be read from the beginning. The copy is still a copy. It is just less fast. The engine does not switch to a new encode to "fix" a slow seek.

## Duration in the headers can be wrong

The concat demuxer uses each file's duration to place the next file. The manual warns that a duration computed from bitrate, or a truncated file, can cause artifacts at the join.

The engine probes each piece and passes files whose probed duration is missing or zero only as a hard error, not as a guess.

## Streams must match before a join

The concat demuxer requires the same streams: same codecs, same time base, and the rest. The engine checks the measurable parts before it writes the list:

- same number of video, audio, and subtitle streams
- same codec name on each matched stream
- same width and height on video
- same sample rate and channel count on audio

A mismatch is an error. The engine does not scale, resample, or re-encode to force a match.

Time base still matters, and `ffprobe` does not always make it obvious. If `ffmpeg` then fails, that failure is the result. There is no second try that encodes.

Variable frame rate is a known sore spot. The `ffmpeg` manual says copying variable-frame-rate video sometimes needs the demuxer time base (`-copytb 1`) to avoid timestamps that go backwards. The engine's default is to leave `-copytb` unset (FFmpeg's default is `-1`, choose automatically). If a copied file has timestamps that go backwards, the retry is `-copytb 1` with `-c copy` still set. That retry is still a copy.

## Containers reject some codecs

`-map 0` asks for every stream. The muxer can refuse.

| Destination | Often refused |
|---|---|
| MP4 / MOV | DVD and Blu-ray bitmap subtitles, MKV attachments, some lossless audio |
| MP4 | VP9 or AV1, unless the muxer is told a brand that accepts them. The engine does not guess brands. A refusal fails or drops that stream. |
| WebM | H.264, AAC. WebM expects VP8/VP9/AV1 and Vorbis/Opus. |

Two caller choices, picked on the call, not guessed per file:

- `drop_rejected_streams=False` (default): the call fails, the partial output is removed, the error names the stream.
- `drop_rejected_streams=True`: retry without the refused streams, and list them on the report.

The engine never "fixes" a refusal by encoding that stream.

## Bitstream filters are narrow

Allowed only for the cases in [functionality](functionality.md): `aac_adtstoasc`, `h264_mp4toannexb`, `hevc_mp4toannexb`.

They change packet framing. They are not a license to add other bitstream filters (metadata editors, crop filters, and the rest).

## Subtitles and chapters

Text subtitles copy when the destination codec matches (`subrip` into MKV, `mov_text` into MP4). Converting SubRip into `mov_text` is a subtitle encode. The engine does not do that conversion. With `drop_rejected_streams=True` the subtitles are omitted and named in the report.

Chapters copied through a time cut keep source times. The engine does not advertise working chapters on a clip.

## Players and the first frames

Starting at a real keyframe is what makes the first frame decodable. That is why the engine uses input `-ss` plus stream copy, which keeps the seek point, rather than dropping packets in front of the keyframe.

A file can still fail in a picky player because of a bad source timestamp or a codec the player does not support. That is a source or player limit. The engine's probe check catches an empty file. It does not play the file.

## Size

The engine treats these as success:

- clip size `<` source size, for a range that is not the whole file
- remux size close to source size

The engine treats these as failure:

- a clip of a partial range whose file is larger than the source
- an output that is only a container header (no real duration)

Keyframe lead-in makes the clip larger than `asked seconds × bitrate`. That extra is still source packets, and it is allowed. It is not a new encode.

## Overwrite and paths

- The output path must not be the input path. FFmpeg would destroy the source while reading it.
- Overwrite of an existing output file happens only when the caller set overwrite.
- Concat list paths are written by the engine. A path with a newline is rejected.
- Arguments are passed as a list. The engine does not call the shell.

## What a failed run leaves behind

- Non-zero `ffmpeg` exit: delete the partial output, return the stderr tail.
- Probe check failed: delete the output, return the probe facts that failed.
- Join failed after temporary clips were made: delete the temps and the partial join.

A clip-many call keeps the clips that already passed. It does not roll back earlier ranges.

## Work the engine refuses

| Request | Result |
|---|---|
| Exact frame, scale, crop, text, speed, volume, new codec, compress | Error `OutsideEngine`. No `ffmpeg` encode command is run. |
| Start `>=` end, negative duration, times the probe says are past the end | Error `BadRange`, before `ffmpeg`. |
| Missing `ffmpeg` or `ffprobe` on `PATH` | Error `ToolMissing`, before any file is written. |
| Input missing or unreadable | Error `InputNotFound`. |
| Concat inputs that do not match | Error `StreamMismatch`. |

Times past the end: the engine compares against the probed duration. A duration of 0 or missing is `BadRange` for a time cut, because the end cannot be checked. Remux of a file with no duration is still allowed. The probe of the output is the check.
