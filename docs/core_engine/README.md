# Core engine

The core engine cuts video on this computer. The file stays local. The picture and the sound are not encoded again, so quality stays the same and the bitrate stays the same.

The program under the engine is **FFmpeg**, in **stream copy** mode (`-c copy`). Stream copy lifts the compressed packets out of the source file and writes them into a new file. It does not decode frames, and it does not build new frames.

This folder is the design of that engine. The repository does not have the Python package yet. Code added later has to follow these pages.

Checked against the Debian testing manuals for `ffmpeg`, `ffmpeg-formats`, and `ffprobe` on 2026-11-23.

## The rules

The engine exists to keep these rules. A function that breaks one of them is outside the engine, even if FFmpeg can do it.

| Rule | What it means in practice |
|---|---|
| Fast | Copy packets. Do not decode the movie. A long file should finish in about the time it takes to read and write the clip. |
| Local | `ffmpeg` and `ffprobe` run on this machine. No upload, no clip API, no account. |
| Same quality | The video packets and the audio packets in the output are the packets from the source. |
| Same bitrate | The engine must not start a new encode. A new encode is what makes a file fatter or thinner. |
| Small install (optional) | Python uses the standard library. The only outside programs are `ffmpeg` and `ffprobe`. |

## The picture

A stream-copy cut is like tearing a chapter out of a printed book. You do not retype the words. You can tear at the start of a saved full page, called a **keyframe**. The tear can start a little before the second you asked for. Every frame you keep is the original frame.

## Read in this order

1. [How it works](how-it-works.md) — packets, keyframes, containers, timestamps, size.
2. [Functionality](functionality.md) — every operation, and which rule it sits under.
3. [Commands](commands.md) — the exact `ffmpeg` and `ffprobe` commands.
4. [Limits](limits.md) — where a cut lands, which files can be joined, what fails.
5. [Python contract](python-contract.md) — the functions, inputs, results, and errors the code must grow into.

## What the engine is responsible for

- Read a media file and report its streams.
- Cut one time range, or many ranges, by copying packets.
- Drop or keep streams (extra audio, subtitles) without encoding.
- Change the container when the codecs already fit in the new container.
- Join clips that already match, still by copying packets.
- Check the output file before calling the job done.

## What stays outside the engine

Pixel edits, audio edits, a new codec, a new frame rate, and a cut on an exact frame. Those need a decode and a new encode. They can change quality and size. They are listed in [Functionality](functionality.md) so the boundary is visible, and they are not part of the default path.
