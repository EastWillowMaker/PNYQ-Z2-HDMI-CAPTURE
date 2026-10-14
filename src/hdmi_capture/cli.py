"""Snapshot, bounded capture and non-saving transport measurements."""

import argparse
import json
import sys
import time
from contextlib import ExitStack
from pathlib import Path

import numpy as np

from .client import CaptureClient
from .protocol import Frame, ProtocolError


def _positive(value: str) -> float:
    result = float(value)
    if not 0 < result < float("inf"):
        raise argparse.ArgumentTypeError("must be finite and positive")
    return result


def _count(value: str) -> int:
    result = int(value)
    if result < 1:
        raise argparse.ArgumentTypeError("must be at least one")
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("snapshot", "capture", "stats", "benchmark"):
        cmd = sub.add_parser(name)
        cmd.add_argument("host", help="Board hostname/IP (IPv6 supports %%interface)")
        cmd.add_argument("--port", type=int, default=9020)
        cmd.add_argument("--timeout", type=_positive, default=5.0)
        if name == "snapshot":
            cmd.add_argument("--output", type=Path, required=True, help="New .npy file")
        elif name == "capture":
            cmd.add_argument("--output", type=Path, required=True, help="New directory")
        if name in ("snapshot", "capture"):
            cmd.add_argument("--png", action="store_true", help="Also save lossless PNG")
        if name != "snapshot":
            cmd.add_argument("--count", type=_count)
            cmd.add_argument("--duration", type=_positive, help="Seconds; stops at first limit")
    return parser


def _save(frame: Frame, path: Path, png: bool) -> None:
    """Reserve every output exclusively; remove incomplete outputs on failure."""
    outputs = [path, path.with_suffix(".json")]
    if png:
        from PIL import Image

        outputs.append(path.with_suffix(".png"))
    created: list[Path] = []
    try:
        with ExitStack() as stack:
            handles = []
            for output in outputs:
                handle = stack.enter_context(output.open("xb"))
                handles.append(handle)
                created.append(output)
            np.save(handles[0], frame.rgb, allow_pickle=False)
            handles[1].write((json.dumps(frame.metadata, indent=2) + "\n").encode())
            if png:
                Image.fromarray(frame.rgb).save(handles[2], format="PNG")
    except Exception:
        for output in created:
            output.unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command != "snapshot" and args.count is None and args.duration is None:
        parser.error("provide --count or --duration to bound the run")
    if args.command == "snapshot" and args.output.suffix != ".npy":
        parser.error("snapshot --output must end in .npy")
    if getattr(args, "png", False):
        try:
            import PIL  # noqa: F401
        except ImportError:
            parser.error("PNG requires pip install '.[png]'")
    started = time.monotonic()
    report = {"delivered_frames": 0, "payload_bytes": 0, "detected_errors": 0,
              "observed_frame_id_gaps": 0, "error": None, "stop_reason": None}
    previous_id = None
    frame = None
    try:
        if args.command == "capture":
            args.output.mkdir(parents=True, exist_ok=False)
        elif args.command == "snapshot":
            for suffix in (".npy", ".json", ".png"):
                if args.output.with_suffix(suffix).exists():
                    raise FileExistsError(f"output already exists: {args.output.with_suffix(suffix)}")
        with CaptureClient(args.host, args.port, timeout=args.timeout) as client:
            started = time.monotonic()
            duration = getattr(args, "duration", None)
            deadline = started + duration if duration is not None else None
            count = 1 if args.command == "snapshot" else args.count
            while count is None or report["delivered_frames"] < count:
                if deadline is not None and time.monotonic() >= deadline:
                    report["stop_reason"] = "duration"
                    break
                try:
                    frame = client.read(deadline=deadline)
                except TimeoutError:
                    if deadline is not None and time.monotonic() >= deadline:
                        # A deadline inside a frame prevents certification of that frame.
                        report["stop_reason"] = "duration"
                        report["incomplete_frame_at_deadline"] = True
                        break
                    raise
                frame_id = frame.metadata["frame_id"]
                if previous_id is not None:
                    report["observed_frame_id_gaps"] += frame_id - previous_id - 1
                previous_id = frame_id
                report["delivered_frames"] += 1
                report["payload_bytes"] += frame.rgb.nbytes
                if args.command == "snapshot":
                    _save(frame, args.output, args.png)
                elif args.command == "capture":
                    _save(frame, args.output / f"frame-{report['delivered_frames']:06d}.npy", args.png)
            else:
                report["stop_reason"] = "count"
    except (OSError, EOFError, ProtocolError, ValueError, RuntimeError) as exc:
        report["detected_errors"] += 1
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["stop_reason"] = "error"
    elapsed = max(time.monotonic() - started, 1e-9)
    report.update(elapsed_seconds=elapsed,
                  delivered_fps=report["delivered_frames"] / elapsed,
                  payload_goodput_mbps=report["payload_bytes"] * 8 / elapsed / 1e6)
    if frame is not None:
        report["last_metadata"] = frame.metadata
    print(json.dumps(report, indent=2))
    return 1 if report["detected_errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
