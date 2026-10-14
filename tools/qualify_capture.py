#!/usr/bin/env python3
"""Bounded real-HDMI analytic-pattern qualification; never starts board services."""

import argparse
from contextlib import ExitStack
import json
import math
import re
from pathlib import Path
import time

import numpy as np

from hdmi_capture import CaptureClient
try:
    from .hdmi_pattern import verify
except ImportError:
    from hdmi_pattern import verify


def positive(value):
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise argparse.ArgumentTypeError("must be finite and positive")
    return result


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("host", help="Board IP; scoped IPv6 uses %%interface")
    result.add_argument("--port", type=int, default=9020)
    result.add_argument("--timeout", type=positive, default=5)
    result.add_argument("--duration", type=positive, default=600,
                        help="Minimum observation window in seconds")
    result.add_argument("--min-frames", type=int, default=600,
                        help="Minimum exact, distinct optical frames")
    result.add_argument("--min-fps", type=positive, default=1)
    result.add_argument("--hard-deadline", type=positive, default=660,
                        help="Maximum run duration in seconds")
    result.add_argument("--require-litex", action=argparse.BooleanOptionalAction, default=True)
    result.add_argument("--log", type=Path, required=True, help="New per-frame JSONL file")
    result.add_argument("--summary", type=Path, help="New summary JSON; defaults beside log")
    result.add_argument("--save-endpoints", type=Path, help="New directory for first/last NPY+JSON")
    return result


def _save_endpoint(directory, name, frame):
    with (directory / f"{name}.npy").open("xb") as handle:
        np.save(handle, frame.rgb, allow_pickle=False)
    with (directory / f"{name}.json").open("x") as handle:
        json.dump(frame.metadata, handle, indent=2)
        handle.write("\n")


def _health_errors(metadata):
    """Require source-health observations without attributing them to a buffer."""
    current = metadata.get("litex_counters")
    startup = metadata.get("litex_startup_counters")
    if not isinstance(current, dict) or not isinstance(startup, dict):
        return ["required LiteX current/startup source-health snapshots absent"]
    errors = []
    for label, snapshot in (("current", current), ("startup", startup)):
        for name in ("frontend_overflow_episodes", "frontend_underflow_episodes",
                     "native_vsync_edges", "invalid_frames"):
            value = snapshot.get(name)
            if type(value) is not int or not 0 <= value < 2**32:
                errors.append(f"{label} {name} is not an observed uint32 counter")
        if snapshot.get("overflow_units") != "assertion_episodes_not_lost_frames":
            errors.append(f"{label} source-health overflow units absent or unsupported")
    # Baseline GPIO reads stay non-atomic, but capture remains disabled through
    # every read. Reset-default zero plus zero selected SOFs prevents earlier
    # selected output; geometry counters also include unselected startup input.
    if type(metadata.get("capture_enable_reset")) is not int or metadata["capture_enable_reset"] != 0:
        errors.append("verified capture-enable reset default zero absent")
    if startup.get("enabled") is not False:
        errors.append("startup baseline was not taken with capture held disabled")
    if type(startup.get("selected_frames")) is not int or startup["selected_frames"] != 0:
        errors.append("startup baseline does not establish zero selected frames")
    if startup.get("sample_point") != "sequential_gpio_reads_after_dma_start_before_capture_enable":
        errors.append("startup baseline was not taken before capture enable")
    for name in ("frontend_overflow_episodes", "frontend_underflow_episodes"):
        if startup.get(name) != 0:
            errors.append(f"startup {name} is nonzero or unknown")
    for name in ("invalid_frames", "frontend_overflow_episodes", "frontend_underflow_episodes"):
        if current.get(name) != startup.get(name):
            errors.append(f"{name} changed since startup; frame association unknown")
    if metadata.get("integrity_policy") != "disabled_zero_selected_baseline_then_stop_on_integrity_change":
        errors.append("required fail-stop source integrity policy absent")
    provenance = metadata.get("source_health_provenance")
    if not isinstance(provenance, dict):
        errors.append("source-health provenance absent")
    else:
        digest = provenance.get("source_health_sha256")
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            errors.append("source-health SHA256 provenance absent or invalid")
        for key, expected in (("source_health_counters_lifetime", "fpga_load"),
                              ("source_health_overruns_unit", "overflow_episodes"),
                              ("receiver_source_reset_policy", "shared_per_clock")):
            if provenance.get(key) != expected:
                errors.append(f"unsupported or missing {key}")
    initial_edges, current_edges = startup.get("native_vsync_edges"), current.get("native_vsync_edges")
    if type(initial_edges) is int and type(current_edges) is int and current_edges < initial_edges:
        errors.append("native VSYNC counter rolled back since startup")
    return errors


def run(args, *, client_factory=CaptureClient, clock=time.monotonic):
    """Preserve every received result, including failures, until bounded completion."""
    if args.min_frames < 1 or args.hard_deadline < args.duration:
        raise ValueError("min-frames must be positive; hard-deadline must cover duration")
    summary_path = args.summary or args.log.with_suffix(".summary.json")
    if summary_path == args.log:
        raise ValueError("log and summary must be separate files")
    summary = dict(configuration=dict(host=args.host, port=args.port, timeout=args.timeout,
                   minimum_duration_seconds=args.duration, minimum_distinct_frames=args.min_frames,
                   minimum_fps=args.min_fps, hard_deadline_seconds=args.hard_deadline,
                   require_litex=args.require_litex),
                   delivered_frames=0, exact_frames=0, pixel_failures=0, mixed_frames=0,
                   repeated_optical_frames=0, distinct_exact_optical_frames=0,
                   metadata_failures=0, transport_errors=0, storage_errors=0, payload_bytes=0,
                   transport_frame_id_gaps=0, stop_reason=None, error=None,
                   physical_source_sequence_verified=False,
                   source_health_required=args.require_litex,
                   litex_snapshot_association="Sequential non-atomic snapshots; no per-frame association")
    seen = set()
    previous_id = None
    previous_vsync = None
    first = last = None
    started = clock()
    summary.update(host_start_monotonic_seconds=started, host_clock="host_monotonic")
    with ExitStack() as stack:
        log = stack.enter_context(args.log.open("x"))
        output = stack.enter_context(summary_path.open("x"))
        if args.save_endpoints:
            args.save_endpoints.mkdir(parents=True, exist_ok=False)
        try:
            with client_factory(args.host, args.port,
                                timeout=min(args.timeout, args.hard_deadline)) as client:
                # Includes connection setup in the measurement and maximum deadline.
                deadline = started + args.hard_deadline
                while clock() < deadline:
                    try:
                        frame = client.read(deadline=deadline)
                    except TimeoutError:
                        if clock() >= deadline:
                            summary["stop_reason"] = "hard_deadline"
                            summary["incomplete_frame_at_deadline"] = True
                            break
                        raise
                    now = clock()
                    summary["delivered_frames"] += 1
                    summary["payload_bytes"] += frame.rgb.nbytes
                    meta = frame.metadata
                    frame_id = meta["frame_id"]
                    if previous_id is not None:
                        summary["transport_frame_id_gaps"] += frame_id - previous_id - 1
                    previous_id = frame_id
                    if first is None:
                        first = frame
                        summary["first_metadata"] = meta
                    last = frame
                    summary["last_metadata"] = meta
                    reasons = []
                    if meta.get("source_origin") != "hdmi":
                        reasons.append("source is not real HDMI")
                    if args.require_litex and (meta.get("baseline_only") is not False or
                            meta.get("capture_implementation") != "litex_video_gate" or
                            "litex_capture" not in meta.get("flags", [])):
                        reasons.append("required LiteX capture metadata missing or baseline-only")
                    if args.require_litex:
                        reasons.extend(_health_errors(meta))
                        snapshot = meta.get("litex_counters")
                        vsync = snapshot.get("native_vsync_edges") if isinstance(snapshot, dict) else None
                        if type(vsync) is int:
                            if previous_vsync is not None and vsync < previous_vsync:
                                reasons.append("native VSYNC counter rolled back since preceding snapshot")
                            previous_vsync = vsync
                        startup = meta.get("litex_startup_counters")
                        if isinstance(startup, dict):
                            summary["startup_invalid_frames"] = startup.get("invalid_frames")
                            summary["startup_invalid_scope"] = (
                                "Unselected input before capture enable only when disabled baseline proof passes")
                            summary["startup_frontend_overflow_episodes"] = startup.get(
                                "frontend_overflow_episodes")
                            summary["startup_frontend_underflow_episodes"] = startup.get(
                                "frontend_underflow_episodes")
                    summary["metadata_failures"] += bool(reasons)
                    try:
                        checked = verify(frame.rgb)
                    except ValueError as error:
                        checked = dict(exact_match=False, mixed_optical_ids=False,
                                       expected_id=None, error=str(error))
                    summary["mixed_frames"] += bool(checked["mixed_optical_ids"])
                    if checked["exact_match"]:
                        summary["exact_frames"] += 1
                        optical_id = checked["expected_id"]
                        if optical_id in seen:
                            summary["repeated_optical_frames"] += 1
                        else:
                            seen.add(optical_id)
                            summary["distinct_exact_optical_frames"] += 1
                    else:
                        summary["pixel_failures"] += 1
                    log.write(json.dumps(dict(event="frame", index=summary["delivered_frames"],
                              host_elapsed_seconds=now-started,
                              host_received_monotonic_seconds=now, metadata=meta,
                              metadata_errors=reasons, verification=checked)) + "\n")
                    log.flush()
                    if args.save_endpoints and summary["delivered_frames"] == 1:
                        try:
                            _save_endpoint(args.save_endpoints, "first", frame)
                        except OSError:
                            summary["storage_errors"] += 1
                            raise
                    if reasons:
                        summary["stop_reason"] = "metadata_rejection"
                        break
                    if now-started >= args.duration and len(seen) >= args.min_frames:
                        summary["stop_reason"] = "minimum_window_and_frames"
                        break
                else:
                    summary["stop_reason"] = "hard_deadline"
        except (OSError, EOFError, ValueError, RuntimeError) as error:
            if not summary["storage_errors"]:
                summary["transport_errors"] += 1
            summary["error"] = f"{type(error).__name__}: {error}"
            summary["stop_reason"] = "error"
            log.write(json.dumps(dict(event="error", error=summary["error"],
                                     host_elapsed_seconds=clock()-started)) + "\n")
            log.flush()
        except KeyboardInterrupt:
            summary["stop_reason"] = "interrupted"
        elapsed = max(clock()-started, 1e-9)
        summary.update(elapsed_seconds=elapsed,
                       delivered_fps=summary["delivered_frames"]/elapsed,
                       distinct_exact_fps=len(seen)/elapsed,
                       payload_goodput_mbps=summary["payload_bytes"]*8/elapsed/1e6)
        if args.save_endpoints and last is not None:
            try:
                _save_endpoint(args.save_endpoints, "last", last)
            except OSError as error:
                summary["storage_errors"] += 1
                summary["error"] = f"{type(error).__name__}: {error}"
        summary["passed"] = (elapsed >= args.duration and len(seen) >= args.min_frames
                             and summary["distinct_exact_fps"] >= args.min_fps
                             and not any(summary[key] for key in
                             ("pixel_failures", "mixed_frames", "repeated_optical_frames",
                              "metadata_failures", "transport_errors", "storage_errors"))
                             and summary["stop_reason"] != "interrupted")
        summary["qualification_scope"] = "M1 exact HDMI path" if args.require_litex else "M0 baseline exact HDMI path"
        json.dump(summary, output, indent=2)
        output.write("\n")
    return summary


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        summary = run(args)
    except (OSError, ValueError) as error:
        print(str(error))
        return 2
    print(json.dumps(summary, indent=2))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
