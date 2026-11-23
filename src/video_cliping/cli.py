"""Command line: a video path plus the clip settings."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from video_cliping.cut import clip
from video_cliping.errors import EngineError, FfmpegFailed, OutputCheckFailed
from video_cliping.models import ClipReport, ClipRequest


def main(argv: list[str] | None = None) -> int:
    """Cut one file. Return 0 on success, 2 for a bad request, 1 if ffmpeg fails."""
    args = _parser().parse_args(argv)
    try:
        report = clip(_request(args))
    except EngineError as exc:
        print(exc, file=sys.stderr)
        if isinstance(exc, (FfmpegFailed, OutputCheckFailed)):
            return 1
        return 2
    _print_report(report)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Cut a local video by copying packets. The picture is not encoded again.",
    )
    parser.add_argument("source", help="Video file to read")
    parser.add_argument("dest", help="File to write")
    parser.add_argument("--start", help="Start as seconds (90) or clock text (00:01:30). Default: start of file.")
    parser.add_argument("--end", help="End as seconds or clock text. Default: end of file.")
    parser.add_argument(
        "--map",
        dest="maps",
        action="append",
        default=[],
        help="Stream to keep, like 0:v:0. Repeat to keep more. Default: every stream.",
    )
    parser.add_argument("--overwrite", action="store_true", help="Replace dest if it exists.")
    parser.add_argument("--faststart", action="store_true", help="Put the MP4 or MOV index at the front of the file.")
    parser.add_argument(
        "--drop-rejected-streams",
        action="store_true",
        help="If the container refuses a stream, write the clip without that stream.",
    )
    parser.add_argument("--exact", action="store_true", help="Refused. An exact frame would encode the video.")
    return parser


def _request(args: argparse.Namespace) -> ClipRequest:
    maps = tuple(args.maps) if args.maps else None
    return ClipRequest(
        source=Path(args.source),
        dest=Path(args.dest),
        start=args.start,
        end=args.end,
        maps=maps,
        drop_rejected_streams=args.drop_rejected_streams,
        faststart=args.faststart,
        overwrite=args.overwrite,
        exact=args.exact,
    )


def _print_report(report: ClipReport) -> None:
    print(f"wrote {report.dest} ({report.output_duration_s:.3f}s)")
    if report.streams_dropped:
        names = ", ".join(stream.codec_name for stream in report.streams_dropped)
        print(f"dropped streams: {names}")


if __name__ == "__main__":
    raise SystemExit(main())
