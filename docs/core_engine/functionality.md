# Functionality

## Inside the rules

These are the operations the package implements. Each one copies packets or only reads the file.

| Operation | What you get |
|---|---|
| Inspect | Duration, container name, size, and one record per stream (codec, size or sample rate, language tag). |
| Key packets | Every video packet time for one video stream. `K` in the flags means a key packet. |
| Clip a range | A new file from start to end. Start defaults to 0. End defaults to the end of the file. |
| Choose streams | `maps` like `0:v:0` and `0:a:1`. Empty means every stream. The number is the count of that kind, not the container index. |
| Drop a refused stream | `drop_rejected_streams` writes the clip without a stream the container cannot store. |
| Fast start | `faststart` on a `.mp4` or `.mov` moves the index to the front. Playback can start before the whole file is read. The packets are still the original packets. |
| Overwrite | Off by default. On replaces an existing destination. |

The command line and the web form call this same `clip` function.

## Refused

| Request | Result |
|---|---|
| `exact=True` | `OutsideEngine`. No file is written. |
| Start not before end | `BadRange`. |
| Range outside the file, or a range on a file with no duration | `BadRange`. |
| Same path for source and dest | `SamePath`. |
| Dest exists and overwrite is off | `Exists`. |
| A map that is not `0:v:0` style, or names a missing stream | `EngineError`. |
| `faststart` on a file that is not `.mp4` or `.mov` | `EngineError`. |
| A newline in a path | `EngineError`. |
| The container refuses a stream and drops are off | `ContainerRejected`. The new file is deleted. |
| The output fails the duration or size check | `OutputCheckFailed`. The new file is deleted. |

## Not in this package

These need a different tool, or a new encode. They are not functions here:

- Several ranges in one call, the last N seconds, or cutting a hole out of the middle.
- Joining files, or splitting a file on a timer.
- A new codec, a new frame size, a new frame rate, burned-in subtitles, or a volume change.
- An exact frame that is not a keyframe.
