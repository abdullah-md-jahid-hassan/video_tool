# Commands

These are the only `ffmpeg` and `ffprobe` shapes the engine builds. Arguments are a list, never a shell string. Paths are separate arguments.

Flags come from the `ffmpeg` and `ffmpeg-formats` manuals. See [how it works](how-it-works.md) for why they are in this order.

Replace `START`, `END`, `INPUT`, and `OUTPUT`. Times are seconds (`90.5`) or `HH:MM:SS.mmm` (`00:01:30.500`).

## Inspect

```text
ffprobe -v error -hide_banner -print_format json -show_format -show_streams INPUT
```

- `-v error` keeps the JSON free of progress logs.
- `-print_format json` is the form the engine parses.
- `-show_format` is the container: duration, size, tags.
- `-show_streams` is one object per stream.

The engine reads duration, size, and each stream's `index`, `codec_type`, `codec_name`, `width`, `height`, `avg_frame_rate` or `r_frame_rate`, `sample_rate`, `channels`, and `tags.language` when present.

## List key packets for one video stream

```text
ffprobe -v error -hide_banner -print_format json -select_streams v:0 -show_packets -show_entries packet=pts_time,flags INPUT
```

- `-select_streams v:0` is the first video stream. Use `v:1` for the next.
- `-show_packets` reads packet headers.
- The packet `flags` field is three characters. `K` means a key packet, `D` means discard, `C` means corrupt. A `_` in that slot means the flag is off. Key-packet times are the seek points a clip can start on.

This can be large on a long file. The engine may stream the JSON or stop once it has the key time at or before the asked start plus the next one.

## Clip one range

Canonical cut:

```text
ffmpeg -hide_banner -nostdin -y -ss START -to END -i INPUT -map 0 -c copy -avoid_negative_ts make_zero OUTPUT
```

| Argument | Role |
|---|---|
| `-hide_banner` | Skip the build banner. The stderr tail stays useful. |
| `-nostdin` | Do not read the terminal. Stops ffmpeg waiting on stdin in a pipeline. |
| `-y` | Overwrite `OUTPUT`. The engine passes this only after its own overwrite check. |
| `-ss START` | Input seek. On stream copy, packets from the previous seek point are kept. |
| `-to END` | Stop reading the input at `END`. Do not also pass `-t`. |
| `-map 0` | Every stream from the input. |
| `-c copy` | Do not re-encode. |
| `-avoid_negative_ts make_zero` | First timestamp becomes 0. All streams shift by the same amount. |

## Clip from a time to the end of the file

Leave `-to` off. The read runs until the input ends.

```text
ffmpeg -hide_banner -nostdin -y -ss START -i INPUT -map 0 -c copy -avoid_negative_ts make_zero OUTPUT
```

## Clip the last N seconds

`-sseof` is an input option. It is `-ss` measured from the end. The value is negative when the start is before the end.

```text
ffmpeg -hide_banner -nostdin -y -sseof -30 -i INPUT -map 0 -c copy -avoid_negative_ts make_zero OUTPUT
```

That asks for the last 30 seconds, still snapped to a seek point.

## Keep only some streams

Replace `-map 0` with the maps you want. `-map` still pairs with `-c copy`.

First video and second audio:

```text
ffmpeg -hide_banner -nostdin -y -ss START -to END -i INPUT -map 0:v:0 -map 0:a:1 -c copy -avoid_negative_ts make_zero OUTPUT
```

Video only:

```text
ffmpeg -hide_banner -nostdin -y -ss START -to END -i INPUT -map 0:v:0 -c copy -avoid_negative_ts make_zero OUTPUT
```

Audio only, codec unchanged, into a container that accepts it:

```text
ffmpeg -hide_banner -nostdin -y -ss START -to END -i INPUT -map 0:a:0 -c copy -avoid_negative_ts make_zero OUTPUT.m4a
```

Drop subtitles and data, keep everything else that `-map 0` selected:

```text
ffmpeg -hide_banner -nostdin -y -ss START -to END -i INPUT -map 0 -sn -dn -c copy -avoid_negative_ts make_zero OUTPUT
```

`-vn`, `-an`, `-sn`, and `-dn` skip video, audio, subtitles, and data.

## Remux the whole file

No `-ss` and no `-to`. Packets are copied from start to end.

```text
ffmpeg -hide_banner -nostdin -y -i INPUT -map 0 -c copy OUTPUT
```

MP4 or MOV, index at the front:

```text
ffmpeg -hide_banner -nostdin -y -i INPUT -map 0 -c copy -movflags +faststart OUTPUT.mp4
```

## Bitstream filter, only when the container needs it

AAC ADTS into MP4:

```text
ffmpeg -hide_banner -nostdin -y -i INPUT -map 0 -c copy -bsf:a aac_adtstoasc OUTPUT.mp4
```

H.264 in MP4 into MPEG-TS:

```text
ffmpeg -hide_banner -nostdin -y -i INPUT -map 0 -c copy -bsf:v h264_mp4toannexb OUTPUT.ts
```

H.265 in MP4 into MPEG-TS uses `-bsf:v hevc_mp4toannexb`.

The engine tries the plain copy first. It adds a bitstream filter only after a container rejection that this filter is known to fix, then probes the result.

## Join files

List file, written by the engine. The first line is exactly `ffconcat version 1.0` so FFmpeg can recognize the script. Each path is escaped.

```text
ffconcat version 1.0
file '/absolute/path/part-1.mp4'
file '/absolute/path/part-2.mp4'
```

```text
ffmpeg -hide_banner -nostdin -y -f concat -safe 0 -i LIST.txt -map 0 -c copy OUTPUT
```

- `-f concat` selects the concat demuxer.
- `-safe 0` allows the absolute paths the engine writes. The manual's default `safe=1` rejects them.
- The engine does not turn on extra concat conversions beyond the demuxer default.

## Cut out a middle range

Two clips, then one join.

```text
ffmpeg -hide_banner -nostdin -y -ss 0 -to HOLE_START -i INPUT -map 0 -c copy -avoid_negative_ts make_zero HEAD
ffmpeg -hide_banner -nostdin -y -ss HOLE_END -i INPUT -map 0 -c copy -avoid_negative_ts make_zero TAIL
ffmpeg -hide_banner -nostdin -y -f concat -safe 0 -i LIST.txt -map 0 -c copy OUTPUT
```

`HEAD` and `TAIL` are temporary files. The engine deletes them after `OUTPUT` passes the probe check. A hole that starts at 0 is only the tail. A hole that ends at the end of the file is only the head.

## Split into pieces

```text
ffmpeg -hide_banner -nostdin -y -i INPUT -map 0 -c copy -f segment -segment_time 60 -reset_timestamps 1 OUTPUT-%03d.mp4
```

- `-f segment` is the segment muxer.
- `-segment_time 60` asks for pieces of about 60 seconds.
- Each piece starts on a keyframe. The manual: if you need the split on an exact time, the source keyframes have to sit on that time.
- `-reset_timestamps 1` makes each piece start with near-zero timestamps. The manual says this may not work with some muxer and codec combinations, and the default is off. The engine turns it on so each piece plays on its own, and the output probe is what decides the piece is good.

## Set a metadata tag

```text
ffmpeg -hide_banner -nostdin -y -i INPUT -map 0 -c copy -metadata title=TITLE OUTPUT
```

An empty value clears a key. Tags do not change packets.

## Check the output

Same inspect command, pointed at `OUTPUT`. The engine compares:

- `format.duration` against the asked range
- `format.size` against the source size
- stream `codec_name` values against the streams it meant to copy

## Commands the engine does not build

These all start a decode/encode or a filter graph. Listed so a later change is obvious in review.

```text
ffmpeg -i INPUT -ss START -to END -c:v libx264 -c:a aac OUTPUT
ffmpeg -i INPUT -vf scale=1280:720 OUTPUT
ffmpeg -i INPUT -filter_complex "[0:v]trim=start=1:end=5,setpts=PTS-STARTPTS[v]" OUTPUT
```

`-ss` placed after `-i` is the output form. The manual describes that form as decoding and discarding until the timestamp. That is the encode path's accurate seek, not this engine's copy path.
