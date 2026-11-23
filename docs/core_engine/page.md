# The local page

`video-clip-web` serves one page on this computer. The address must be `127.0.0.1`, `localhost`, or `::1`. The front page has one tool, Video clipping. That tool opens the form.

The form calls the same `clip` function as the command. It does not encode the video, and it does not send the file to another computer. It reads a path on this computer.

## Choosing the video

Type a path, or use **Choose a file**. The chooser lists folders on this computer. Names that start with `.` are not listed. A hidden path still works if you type it.

## Where the clip is written

The form picks the folder in this order:

1. If **Save in the same folder as the video** is ticked, the clip is written next to the video. A chosen folder is ignored.
2. Otherwise, if the destination box is filled in, the clip is written there. **Choose a folder** fills that box and clears the same-folder tick.
3. If you do neither, the clip goes to `outputs/cliping`, next to the folder where you started the server.

The page creates the destination folder when it is missing. The command line does not.

The file name comes from the video name. Characters other than letters, numbers, `.`, `_`, and `-` become `_`. If that path is the source file, `-clip` is added before the extension, so the original file stays. That happens for the same-folder box, and also when the folder you chose is the video's own folder.

## The other fields

| Field | Meaning |
|---|---|
| Start | Seconds or a clock. Empty starts at the beginning. |
| End | Seconds or a clock. Empty stops at the end of the file. |
| Streams to keep | One spec per line, such as `0:v:0`. Empty keeps every stream. |
| Replace the output file | The cutter's `overwrite` flag. |
| Put the MP4 or MOV index at the front | The cutter's `faststart` flag. Only `.mp4` and `.mov`. |
| Leave a refused stream out | The cutter's `drop_rejected_streams` flag. |
| Cut on an exact frame | Refused. Nothing is written. An exact frame would encode the video. |

Each form is valid once. Submit it again and the page asks you to open Video clipping again.
