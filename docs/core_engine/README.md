# Core engine

The core engine cuts a video on this computer. The file stays local. The picture and the sound are not encoded again, so quality stays the same and the bitrate stays the same.

The library under the engine is **PyAV** (`av`). Its wheel, installed inside the project `.venv`, carries the media libraries. A system `ffmpeg` program is not required, and nothing is downloaded on first use.

PyAV opens the file, copies the compressed packets, and writes them into a new file. It does not decode the movie into pictures, and it does not build new frames.

## The rules

A function that breaks one of these rules is outside the engine.

| Rule | What it means in practice |
|---|---|
| Fast | Copy packets. Do not decode the movie. A long file should finish in about the time it takes to read and write the clip. |
| Local | PyAV runs inside this project's virtualenv. No upload, no clip API, no account. |
| Same quality | The video packets and the audio packets in the output are the packets from the source. |
| Same bitrate | The engine must not start a new encode. A new encode is what makes a file fatter or thinner. |
| Small install | One pinned Python package, `av`, installed in `.venv`. No system media tools. |

## The picture

A packet copy is like tearing a chapter out of a printed book. You do not retype the words. You can tear at the start of a saved full page, called a **keyframe**. The tear can start a little before the second you asked for. Every frame you keep is the original frame.

## Read in this order

1. [How it works](how-it-works.md) — packets, keyframes, timestamps, size.
2. [Functionality](functionality.md) — what the package does, and what it refuses.
3. [The cut steps](commands.md) — the PyAV steps one cut takes. There is no shell command.
4. [Limits](limits.md) — where a cut lands, and what fails.
5. [Python contract](python-contract.md) — the functions, inputs, results, and errors.

## What the engine does

- Read a media file and report its streams.
- List video packet times, and mark key packets.
- Cut one time range by copying packets.
- Keep every stream, or only the streams you name.
- Drop a stream the destination container refuses, when you ask for that.
- Move the MP4 or MOV index to the front of the file, when you ask for that.
- Check the output file before calling the job done. A failed check deletes the new file.

## What stays outside the engine

Joining clips, cutting several ranges, splitting on a timer, pixel edits, a new codec, and a cut on an exact frame. Exact-frame mode raises `OutsideEngine` and does not run. The other jobs are not in this package.
