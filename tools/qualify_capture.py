#!/usr/bin/env python3
"""Bounded real-HDMI delivered-image criterion; never starts board services."""

import argparse
from contextlib import ExitStack
import json
import math
import re
from pathlib import Path
import time

import numpy as np

from hdmi_capture import CaptureClient
from hdmi_capture.modes import get_mode
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
    result.add_argument("--mode", choices=("vga", "1080p30", "1080p60"), default="vga",
                        help="Expected source profile for full-image verification")
    result.add_argument("--hard-deadline", type=positive, default=660,
                        help="Maximum run duration in seconds")
    result.add_argument("--require-litex", action=argparse.BooleanOptionalAction, default=True)
    result.add_argument("--legacy-delivered-image-criterion", action="store_true",
                        help="Reproduce legacy image/health checks without source accounting")
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


def _health_errors(metadata, *, allow_legacy=False):
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
    startup_point = ("sequential_gpio_reads_after_dma_start_before_capture_enable" if allow_legacy
                     else "before_first_credit_while_gate_disabled_dma_halted")
    if startup.get("sample_point") != startup_point:
        errors.append("startup baseline was not taken before capture enable")
    for name in ("frontend_overflow_episodes", "frontend_underflow_episodes"):
        if startup.get(name) != 0:
            errors.append(f"startup {name} is nonzero or unknown")
    for name in ("invalid_frames", "frontend_overflow_episodes", "frontend_underflow_episodes"):
        if current.get(name) != startup.get(name):
            errors.append(f"{name} changed since startup; frame association unknown")
    policies = {"single_credit_parked_auto_halt_fail_closed_v1"}
    if allow_legacy:
        policies.add("disabled_zero_selected_baseline_then_stop_on_integrity_change")
    if metadata.get("integrity_policy") not in policies:
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


def _accounting_errors(metadata, previous=None):
    """Validate the producer's frozen identity and reconciled cumulative counts.

    This checks metadata invariants. The producer's single-credit RTL, parked
    DMA and release/ACK implementation establish the claimed buffer association.
    Native startup accounting remains unknown; it is never synthesized here.
    """
    record = metadata.get("source_accounting")
    if not isinstance(record, dict):
        return ["required single-credit source accounting absent"]
    errors = []

    def integer(container, name, minimum=0, maximum=2**32-1):
        value = container.get(name)
        if type(value) is not int or not minimum <= value <= maximum:
            errors.append(f"{name} must be an observed integer in [{minimum}, {maximum}]")
            return None
        return value

    for key, expected in (("abi", "single_credit_parked_v1"),
                          ("dma_completion_mode", "parked_frame_count_halt_v1"),
                          ("vdma_fsync_mode", "free_run"),
                          ("gate_completion_policy", "next_sof_after_selected_output_drain_v1")):
        if record.get(key) != expected:
            errors.append(f"unsupported or missing {key}")
    for key in ("dma_auto_halted", "buffer_stable_until_release", "credit_busy",
                "credit_done", "native_armed", "identity_snapshot_coherent"):
        if record.get(key) is not True:
            errors.append(f"{key} must be true")
    for key in ("credit_failed", "source_sequence_fault"):
        if record.get(key) is not False:
            errors.append(f"{key} must be false")
    for key in ("buffer_slot", "command_errors", "source_sequence_faults"):
        if integer(record, key) != 0:
            errors.append(f"{key} must be zero")
    integer(record, "request_seen", maximum=1)
    integer(record, "ack_seen", maximum=1)
    status = integer(record, "raw_dma_status")
    if status is not None and (status & 0xC9F0 or not status & 1 or not status & 0x1000):
        errors.append("DMA status must be HALTED with frame IRQ and no 0xC9F0 errors")
    sequence = integer(metadata, "source_sequence")
    sof = integer(metadata, "frame_source_id")
    native = integer(record, "selected_native_vsync_id")
    selected_sof = integer(record, "selected_sof_id")
    if sequence != native or sof != selected_sof:
        errors.append("top-level source identities do not match frozen credit identities")
    if metadata.get("source_sequence_domain") != "native_vsync_edge_counter":
        errors.append("source sequence domain must be native_vsync_edge_counter")
    if type(metadata.get("source_sequence_bits")) is not int or metadata["source_sequence_bits"] != 32:
        errors.append("source sequence width must be 32 bits")
    if metadata.get("source_sequence_policy") != "reject_wrap_or_reset":
        errors.append("source sequence wrap/reset must fail closed")
    session = metadata.get("session_id")
    if type(session) is not str or not session:
        errors.append("source accounting requires a nonempty session ID")
    acquired = integer(record, "acquired_frames_total", minimum=1)
    completed = integer(record, "selected_completed", minimum=1)
    acquisition_id = integer(metadata, "acquisition_id", minimum=1)
    if acquired != completed or acquired != acquisition_id:
        errors.append("acquired total, completed credit count and acquisition ID must agree")
    total = integer(record, "source_intentional_sampling_total", maximum=2**64-1)
    public = metadata.get("counters")
    if not isinstance(public, dict):
        errors.append("public source counters absent")
    else:
        public_skips = integer(public, "source_skips", maximum=2**64-1)
        if public_skips != total:
            errors.append("public source_skips must equal cumulative native intentional sampling")
        for key in ("source_overruns", "source_invalid_frames", "source_errors", "source_cleanup_errors"):
            if integer(public, key) != 0:
                errors.append(f"public {key} must be observed zero for the fail-closed owned buffer")
    first_id = integer(record, "first_acquired_source_id")
    first_sof = integer(record, "startup_intentional_accepted_sof_skips")
    if "startup_native_skips" not in record or record["startup_native_skips"] is not None:
        errors.append("native startup skips must remain explicitly unknown")
    if all(value is not None for value in (sequence, first_id, acquired, total)):
        if sequence < first_id or sequence-first_id != acquired-1+total:
            errors.append("native source sequence does not reconcile with acquired and intentional totals")
    if sof is not None and first_sof is not None and sof < first_sof:
        errors.append("accepted SOF identity precedes the first selected SOF")
    if all(value is not None for value in (sequence, first_id, sof, first_sof)):
        if sequence-first_id != sof-first_sof:
            errors.append("native and accepted-SOF identity deltas must retain a constant offset")
    skip = record.get("intentional_skips_since_previous")
    if acquired == 1:
        if skip is not None or "intentional_skips_since_previous" not in record:
            errors.append("first acquisition must have unknown previous-acquisition skips")
        if total != 0 or sequence != first_id or sof != first_sof:
            errors.append("first acquisition must establish zero cumulative skips and matching first identities")
    else:
        skip = integer(record, "intentional_skips_since_previous", maximum=2**32-1)
        if skip is not None and total is not None and skip > total:
            errors.append("previous-acquisition skips exceed cumulative intentional skips")
    if previous is not None:
        old = previous["source_accounting"]
        if session != previous.get("session_id"):
            errors.append("source-accounting session changed during qualification")
        for key in ("first_acquired_source_id", "startup_intentional_accepted_sof_skips"):
            if record.get(key) != old.get(key):
                errors.append(f"{key} changed within the source-accounting session")
        if all(value is not None for value in (sequence, sof, acquired, total)):
            native_delta = sequence-previous["source_sequence"]
            acquired_delta = acquired-old["acquired_frames_total"]
            intentional_delta = total-old["source_intentional_sampling_total"]
            if native_delta <= 0 or sof <= previous["frame_source_id"] or acquired_delta <= 0 or intentional_delta < 0:
                errors.append("source identities/acquired totals must increase without wrap or reset")
            if native_delta != acquired_delta+intentional_delta:
                errors.append("delivered native delta does not reconcile with acquired and intentional deltas")
            if native_delta != sof-previous["frame_source_id"]:
                errors.append("delivered native and accepted-SOF identity deltas disagree")
            # The per-acquisition field is comparable only for adjacent acquisitions.
            if acquired_delta == 1 and skip != native_delta-1:
                errors.append("adjacent acquisition skips do not match native sequence delta")
    return errors


def run(args, *, client_factory=CaptureClient, clock=time.monotonic):
    """Preserve every received result, including failures, until bounded completion."""
    if args.min_frames < 1 or args.hard_deadline < args.duration:
        raise ValueError("min-frames must be positive; hard-deadline must cover duration")
    if args.legacy_delivered_image_criterion and not args.require_litex:
        raise ValueError("legacy image criterion requires --require-litex")
    mode = get_mode(getattr(args, "mode", "vga"))
    accounting_required = args.require_litex and not args.legacy_delivered_image_criterion
    summary_path = args.summary or args.log.with_suffix(".summary.json")
    if summary_path == args.log:
        raise ValueError("log and summary must be separate files")
    summary = dict(configuration=dict(host=args.host, port=args.port, timeout=args.timeout,
                   minimum_duration_seconds=args.duration, minimum_distinct_frames=args.min_frames,
                   minimum_fps=args.min_fps, hard_deadline_seconds=args.hard_deadline,
                   expected_mode=mode.name, expected_width=mode.width,
                   expected_height=mode.height, expected_pixel_clock_hz=mode.pixel_clock_hz,
                   expected_refresh_hz=mode.refresh_hz,
                   expected_h_total=mode.h_total, expected_v_total=mode.v_total,
                   expected_h_front_porch=mode.h_front_porch,
                   expected_h_sync_width=mode.h_sync_width,
                   expected_h_back_porch=mode.h_back_porch,
                   expected_h_sync_positive=mode.h_sync_positive,
                   expected_v_front_porch=mode.v_front_porch,
                   expected_v_sync_width=mode.v_sync_width,
                   expected_v_back_porch=mode.v_back_porch,
                   expected_v_sync_positive=mode.v_sync_positive,
                   require_litex=args.require_litex,
                   legacy_delivered_image_criterion=args.legacy_delivered_image_criterion),
                   delivered_frames=0, exact_frames=0, pixel_failures=0, mixed_frames=0,
                   repeated_optical_frames=0, distinct_exact_optical_frames=0,
                   metadata_failures=0, transport_errors=0, storage_errors=0, payload_bytes=0,
                   longest_interframe_gap_seconds=None,
                   transport_frame_id_gaps=0, stop_reason=None, error=None,
                   physical_source_sequence_verified=False,
                   full_m1_qualification=False,
                   unmet_m1_requirements=[
                       "Physical source frame sequence and per-frame DMA association are unverified",
                       "Exact source-frame sampling/drop accounting is unverified",
                       "Complete M1 requires separate interruption, mode and resource evidence"],
                   source_health_required=args.require_litex,
                   source_accounting_required=accounting_required,
                   source_accounting_metadata_validated=False,
                   source_accounting_validated_frames=0,
                   legacy_delivered_image_criterion=args.legacy_delivered_image_criterion,
                   litex_snapshot_association="Sequential non-atomic snapshots; no per-frame association")
    seen = set()
    previous_id = None
    previous_vsync = None
    previous_accounting = None
    previous_received_at = None
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
                    interframe_gap = (None if previous_received_at is None
                                      else now - previous_received_at)
                    if interframe_gap is not None:
                        current_max = summary["longest_interframe_gap_seconds"]
                        summary["longest_interframe_gap_seconds"] = (
                            interframe_gap if current_max is None
                            else max(current_max, interframe_gap))
                    previous_received_at = now
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
                    if "capture_mode" not in meta:
                        if mode.name != "vga":
                            reasons.append(
                                f"capture_mode metadata is required for {mode.name}")
                    elif meta["capture_mode"] != mode.name:
                        reasons.append(
                            f"capture_mode metadata {meta['capture_mode']!r} does not match "
                            f"expected {mode.name}")
                    implementation = ("litex_video_gate" if args.legacy_delivered_image_criterion
                                      else "litex_single_credit_gate")
                    if args.require_litex and (meta.get("baseline_only") is not False or
                            meta.get("capture_implementation") != implementation or
                            "litex_capture" not in meta.get("flags", [])):
                        reasons.append("required LiteX capture metadata missing or baseline-only")
                    if args.require_litex:
                        reasons.extend(_health_errors(meta, allow_legacy=args.legacy_delivered_image_criterion))
                        if accounting_required:
                            accounting_errors = _accounting_errors(meta, previous_accounting)
                            reasons.extend(accounting_errors)
                            if not accounting_errors:
                                summary["source_accounting_validated_frames"] += 1
                                previous_accounting = meta
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
                        checked = verify(frame.rgb, mode=mode.name)
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
                              host_received_monotonic_seconds=now,
                              interframe_gap_seconds=interframe_gap, metadata=meta,
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
        # Keep passed and the CLI exit status as the existing image criterion.
        # This runner does not validate physical-source sequencing or complete M1.
        summary["criterion_passed"] = summary["passed"]
        summary["source_accounting_metadata_validated"] = (
            accounting_required and summary["delivered_frames"] > 0 and
            summary["source_accounting_validated_frames"] == summary["delivered_frames"])
        if summary["source_accounting_metadata_validated"]:
            initial = first.metadata["source_accounting"]
            final = last.metadata["source_accounting"]
            acquired_delta = final["acquired_frames_total"]-initial["acquired_frames_total"]
            summary["source_accounting_received_window"] = dict(
                first_native_source_id=first.metadata["source_sequence"],
                last_native_source_id=last.metadata["source_sequence"],
                native_frame_intervals=last.metadata["source_sequence"]-first.metadata["source_sequence"],
                acquired_frame_intervals=acquired_delta,
                intentional_skips=final["source_intentional_sampling_total"]-initial["source_intentional_sampling_total"],
                acquired_frames_not_delivered=acquired_delta-(summary["delivered_frames"]-1),
                native_startup_skips=None)
            summary["unmet_m1_requirements"] = [
                "Single-credit metadata checks require separate hardware buffer-association evidence",
                "Native startup skips remain unknown at the phase boundary",
                "Complete M1 requires separate interruption, mode and resource evidence"]
        summary["qualification_scope"] = (
            "Sustained delivered-image and single-credit accounting criteria with LiteX health checks"
            if accounting_required else
            "Legacy sustained delivered-image criterion with LiteX health checks" if args.require_litex
            else "Sustained delivered-image criterion for the M0 baseline")
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
