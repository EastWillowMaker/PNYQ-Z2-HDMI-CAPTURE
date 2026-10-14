#!/usr/bin/env python3
"""Bounded read/pause/disconnect/reconnect check; saves no captured images."""

import argparse
import json
import math
from pathlib import Path
import time

from hdmi_capture import CaptureClient, ProtocolError
try:
    from .hdmi_pattern import verify
except ImportError:
    from hdmi_pattern import verify


def positive(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be finite and positive")
    return number


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("host", help="Board IP; scoped IPv6 supports %%interface")
    result.add_argument("--port", type=int, default=9020)
    result.add_argument("--timeout", type=positive, default=5)
    result.add_argument("--pause-seconds", type=positive, default=8)
    result.add_argument("--sender-timeout", type=positive, default=5,
                        help="Configured sender timeout, used only for reporting")
    result.add_argument("--reconnect-frames", type=int, default=5)
    result.add_argument("--hard-deadline", type=positive, default=45)
    result.add_argument("--output", type=Path, required=True, help="New JSON report")
    return result


def run(args, *, client_factory=CaptureClient, clock=time.monotonic, sleep=time.sleep):
    if args.reconnect_frames < 1 or args.pause_seconds >= args.hard_deadline:
        raise ValueError("reconnect-frames must be positive; pause must fit hard deadline")
    report = dict(configuration=dict(host=args.host, port=args.port, timeout=args.timeout,
                  pause_seconds=args.pause_seconds, configured_sender_timeout=args.sender_timeout,
                  reconnect_frames=args.reconnect_frames, hard_deadline_seconds=args.hard_deadline),
                  frames=[], reconnect_attempts=[], detected_errors=0, pixel_failures=0,
                  mixed_frames=0, repeated_optical_frames=0, passed=False,
                  network_error_counter_semantics="Normal client close/timeouts can increment this; not corruption",
                  pause_proof_limit="Unread bytes can remain in TCP buffers; pause alone does not prove backpressure",
                  host_clock="host_monotonic")
    started = clock()
    deadline = started + args.hard_deadline
    report["host_start_monotonic_seconds"] = started
    seen = set()

    def new_client():
        remaining = deadline-clock()
        if remaining <= 0:
            raise TimeoutError("hard deadline expired")
        return client_factory(args.host, args.port, timeout=min(args.timeout, remaining))

    def check(frame, phase):
        received = clock()
        try:
            result = verify(frame.rgb)
        except ValueError as error:
            result = dict(exact_match=False, mixed_optical_ids=False, error=str(error))
        report["pixel_failures"] += not result["exact_match"]
        report["mixed_frames"] += bool(result["mixed_optical_ids"])
        if result["exact_match"]:
            optical = result["expected_id"]
            if optical in seen:
                report["repeated_optical_frames"] += 1
            seen.add(optical)
        report["frames"].append(dict(phase=phase, host_received_monotonic_seconds=received,
                                     metadata=frame.metadata, verification=result))

    # Reserve evidence before connecting; never replace an existing report.
    with args.output.open("x") as output:
        try:
            with new_client() as client:
                check(client.read(deadline=deadline), "before_pause")
                report["pause_start_monotonic_seconds"] = clock()
                sleep(min(args.pause_seconds, max(0, deadline-clock())))
                report["pause_end_monotonic_seconds"] = clock()
            report["first_client_closed_monotonic_seconds"] = clock()
            completed = False
            while clock() < deadline and not completed:
                try:
                    with new_client() as client:
                        first = client.read(deadline=deadline)
                        report["reconnect_attempts"].append(dict(status="connected",
                            host_monotonic_seconds=clock()))
                        check(first, "after_reconnect")
                        for _ in range(args.reconnect_frames-1):
                            check(client.read(deadline=deadline), "after_reconnect")
                        completed = True
                except ProtocolError:
                    raise  # Invalid framing/checksum is never a retriable normal close.
                except (OSError, EOFError) as error:
                    report["reconnect_attempts"].append(dict(status="failed",
                        host_monotonic_seconds=clock(), error=f"{type(error).__name__}: {error}"))
                    # A partially accepted stream is a failed check, not a guard retry.
                    if any(frame["phase"] == "after_reconnect" for frame in report["frames"]):
                        raise
                    sleep(min(0.25, max(0, deadline-clock())))
            if not completed:
                raise TimeoutError("no complete reconnect check before hard deadline")
            report["passed"] = not any(report[key] for key in
                ("pixel_failures", "mixed_frames", "repeated_optical_frames"))
        except (OSError, EOFError, ValueError, RuntimeError) as error:
            report["detected_errors"] += 1
            report["error"] = f"{type(error).__name__}: {error}"
        except KeyboardInterrupt:
            report["detected_errors"] += 1
            report["error"] = "interrupted"
        report["elapsed_seconds"] = clock()-started
        report["delivered_frames"] = len(report["frames"])
        report["reconnect_retry_failures"] = sum(
            attempt["status"] == "failed" for attempt in report["reconnect_attempts"])
        report["real_hdmi_origin_reported"] = bool(report["frames"]) and all(
            frame["metadata"].get("source_origin") == "hdmi" for frame in report["frames"])
        if not report["real_hdmi_origin_reported"]:
            report["passed"] = False
        report["distinct_exact_optical_frames"] = len(seen)
        if "pause_end_monotonic_seconds" in report:
            report["actual_pause_seconds"] = (report["pause_end_monotonic_seconds"] -
                                               report["pause_start_monotonic_seconds"])
            report["pause_exceeds_configured_sender_timeout"] = (
                report["actual_pause_seconds"] > args.sender_timeout)
            if not report["pause_exceeds_configured_sender_timeout"]:
                report["passed"] = False
        if len(report["frames"]) > 1:
            before = report["frames"][0]["metadata"]
            after = report["frames"][-1]["metadata"]
            same = before.get("session_id") is not None and before.get("session_id") == after.get("session_id")
            report["same_sender_session"] = same
            report["counter_deltas"] = {}
            if same:
                for key, initial in before.get("counters", {}).items():
                    final = after.get("counters", {}).get(key)
                    if type(initial) is int and type(final) is int:
                        report["counter_deltas"][key] = final-initial
            else:
                report["counter_delta_limit"] = "Sender session changed or unavailable; deltas not comparable"
        json.dump(report, output, indent=2)
        output.write("\n")
    return report


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        report = run(args)
    except (OSError, ValueError) as error:
        print(str(error))
        return 2
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
