#!/usr/bin/env python3
"""Correlate local synthetic HDMI evidence without opening captured images."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

import numpy as np


def load_jsonl(path, live=False):
    data = path.read_bytes()
    rows, ignored = [], 0
    lines = data.splitlines()
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except (ValueError, UnicodeDecodeError):
            if live and index == len(lines) - 1 and not data.endswith(b"\n"):
                ignored = 1
                break
            raise ValueError(f"Invalid JSONL in {path} at line {index + 1}")
        if not isinstance(row, dict):
            raise ValueError(f"Expected object in {path} at line {index + 1}")
        rows.append(row)
    return rows, {"path": str(path), "bytes_read": len(data),
                  "sha256_of_read_snapshot": hashlib.sha256(data).hexdigest(),
                  "records": len(rows), "ignored_partial_final_lines": ignored}


def distribution(values, units="seconds"):
    if not values:
        return {"count": 0, "units": units}
    array = np.asarray(values, dtype=np.float64)
    return {"count": len(values), "units": units, "min": float(array.min()),
            "p50": float(np.percentile(array, 50, method="linear")),
            "p95": float(np.percentile(array, 95, method="linear")),
            "max": float(array.max()), "mean": float(array.mean()),
            "percentile_method": "linear interpolation"}


def optical_id(frame):
    verification = frame.get("verification", {})
    optical = verification.get("optical_ids", {})
    height = frame.get("metadata", {}).get("height")
    if len(optical) != 1 or verification.get("invalid_marker_rows") \
            or verification.get("mixed_optical_ids") or height is None:
        return None
    identifier, rows = next(iter(optical.items()))
    if rows != height or verification.get("valid_marker_rows") != height:
        return None
    return int(identifier)


def gap_counts(ids, bits=32):
    repeated, skipped, regressions, maximum = 0, 0, 0, 0
    for previous, current in zip(ids, ids[1:]):
        difference = (current - previous) & ((1 << bits) - 1)
        if difference == 0:
            repeated += 1
        elif difference > (1 << (bits - 1)) - 1:
            regressions += 1
        else:
            skipped += difference - 1
            maximum = max(maximum, difference)
    return {"adjacent_repeats": repeated, "unobserved_intermediate_ids": skipped,
            "regressions": regressions, "max_positive_id_step": maximum,
            "interpretation": "Observed ID gaps alone do not identify hardware/network drops; source holding and intentional sampling apply."}


def analyze(capture, source, scanout, final=False, capture_summary=None):
    frames = [row for row in capture if row.get("event") == "frame"]
    source_rows = [row for row in source if row.get("event") == "source_pre_swap"]
    source_by_id = {}
    for row in source_rows:
        source_by_id.setdefault(int(row["frame_id"]), []).append(row)
    samples = [row for row in scanout if row.get("event") == "scanout_sample"]
    samples.sort(key=lambda row: row["sample_started_monotonic_ns"])
    source_starts = [row for row in source if row.get("event") == "source_start"]
    matched, unmatched, ambiguous, incoherent = [], 0, 0, 0
    optical_ids, received = [], []
    for frame in frames:
        receipt = float(frame["host_received_monotonic_seconds"])
        received.append(receipt)
        identifier = optical_id(frame)
        if identifier is None:
            incoherent += 1
            continue
        optical_ids.append(identifier)
        candidates = source_by_id.get(identifier, [])
        if not candidates:
            unmatched += 1
            continue
        if len(candidates) != 1:
            ambiguous += 1
            continue
        event = candidates[0]
        generated = int(event["frame_generated_monotonic_ns"]) / 1e9
        pre_swap = int(event["monotonic_ns"]) / 1e9
        if generated > receipt or pre_swap > receipt:
            unmatched += 1
            continue
        matched.append({"capture_index": frame.get("index"), "optical_id": identifier,
                        "host_generation_to_receipt_seconds": receipt - generated,
                        "host_pre_swap_to_receipt_seconds": receipt - pre_swap,
                        "generated_monotonic_seconds": generated,
                        "received_monotonic_seconds": receipt,
                        "source_self_check_passed": event.get("framebuffer_self_check_passed"),
                        "captured_exact_match": frame.get("verification", {}).get("exact_match")})
    start, finish = (min(received), max(received)) if received else (None, None)
    formats, modes = Counter(), Counter()
    frame_sample_coverage = Counter()
    for frame in matched:
        lo, hi = frame["generated_monotonic_seconds"], frame["received_monotonic_seconds"]
        covered = [sample for sample in samples
                   if sample["sample_started_monotonic_ns"] / 1e9 <= hi
                   and sample["sample_finished_monotonic_ns"] / 1e9 >= lo]
        good = [row for row in covered if row.get("error") is None and row.get("state")]
        observed = {row["state"].get("framebuffer", {}).get("format") for row in good}
        observed.discard(None)
        frame["sampled_scanout_formats_in_generation_receipt_interval"] = sorted(observed)
        frame["scanout_samples_in_interval"] = len(covered)
        if not covered:
            frame_sample_coverage["no_samples"] += 1
        elif observed == {"XR24"} and all(row.get("state", {}).get("crtc_fb_unchanged_during_sample") for row in good) and len(good) == len(covered):
            frame_sample_coverage["samples_only_xr24_consistent"] += 1
        else:
            frame_sample_coverage["mixed_other_or_error_samples"] += 1
    window = [row for row in samples if start is not None
              and start <= row["sample_started_monotonic_ns"] / 1e9 <= finish]
    for row in window:
        state = row.get("state") or {}
        formats[str(state.get("framebuffer", {}).get("format"))] += 1
        mode = state.get("mode")
        if mode:
            modes[json.dumps(mode, sort_keys=True)] += 1
    sample_times = [row["sample_started_monotonic_ns"] / 1e9 for row in window]
    frame_errors = sum(bool(frame.get("metadata_errors")) for frame in frames)
    exact = sum(frame.get("verification", {}).get("exact_match") is True for frame in frames)
    report = {
        "analysis_status": "final_evidence_analysis" if final else "provisional_live_preview",
        "qualification_verdict": "Not assigned by this correlation helper; assess capture summary and all risks separately.",
        "metric_definition": "HOST synthetic image generation completion to HOST complete-frame receipt, matched by coherent optical ID; includes image hold age, rendering, presentation, acquisition and transport. Not HDMI wire latency and not board/host clock synchronization.",
        "frames": len(frames), "exact_pixel_frames": exact,
        "capture_non_frame_event_counts": dict(Counter(row.get("event", "missing") for row in capture if row.get("event") != "frame")),
        "failed_or_missing_pixel_verification_frames": len(frames) - exact,
        "frames_with_metadata_errors": frame_errors,
        "coherent_optical_frames": len(optical_ids), "distinct_optical_ids": len(set(optical_ids)),
        "incoherent_or_missing_optical_frames": incoherent,
        "matched_source_frames": len(matched), "unmatched_source_frames": unmatched,
        "ambiguous_source_id_frames": ambiguous,
        "matched_source_self_checks_true": sum(row["source_self_check_passed"] is True for row in matched),
        "host_generation_to_receipt": distribution([row["host_generation_to_receipt_seconds"] for row in matched]),
        "host_pre_swap_to_receipt": distribution([row["host_pre_swap_to_receipt_seconds"] for row in matched]),
        "optical_id_gaps": gap_counts(optical_ids),
        "transport_frame_id_gaps": gap_counts([int(frame["metadata"]["frame_id"]) for frame in frames], bits=64),
        "host_receipt_intervals": distribution([b - a for a, b in zip(received, received[1:])]),
        "capture_receipt_window_monotonic_seconds": {"first": start, "last": finish},
        "source_log": {"start_records": source_starts, "source_ids_logged": len(source_rows),
                       "self_check_false_records": sum(row.get("framebuffer_self_check_passed") is False for row in source_rows),
                       "stop_record_present": any(row.get("event") == "source_stop" for row in source)},
        "scanout_capture_receipt_window": {
            "samples": len(window), "formats": dict(formats),
            "modes": [{"mode": json.loads(mode), "samples": count} for mode, count in modes.items()],
            "read_errors": sum(row.get("error") is not None for row in window),
            "inactive_or_missing_state_samples": sum(not (row.get("state") or {}).get("active") for row in window),
            "inconsistent_crtc_samples": sum((row.get("state") or {}).get("crtc_fb_unchanged_during_sample") is False for row in window),
            "sample_intervals": distribution([b - a for a, b in zip(sample_times, sample_times[1:])]),
            "matched_frame_interval_coverage": dict(frame_sample_coverage)},
        "scanout_entire_read_log": {"samples": len(samples),
                                    "read_errors": sum(row.get("error") is not None for row in samples),
                                    "formats": dict(Counter(str((row.get("state") or {}).get("framebuffer", {}).get("format")) for row in samples)),
                                    "summary_record_present": any(row.get("event") == "scanout_summary" for row in scanout)},
        "matched_frames": matched,
        "limits": ["Periodic metadata samples can miss transitions between samples; XR24 samples do not prove continuous direct scanout.",
                   "A source pre-swap event or swap return is not measured HDMI presentation time.",
                   "The board monotonic timestamp is not subtracted from the host monotonic clock.",
                   "Host optical ID gaps can include intentional sampling and are not attributed to network or hardware loss.",
                   "Live file snapshots may cover different end times; hashes identify only the bytes read."]}
    if capture_summary is not None:
        report["capture_summary"] = capture_summary
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--source-events", type=Path, required=True)
    parser.add_argument("--scanout", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--final", action="store_true", help="Only after the operator confirms the run finished")
    parser.add_argument("--capture-summary", type=Path)
    args = parser.parse_args(argv)
    if args.final and args.capture_summary is None:
        parser.error("--final requires the completed --capture-summary")
    try:
        loaded = [load_jsonl(path, live=not args.final)
                  for path in [args.capture, args.source_events, args.scanout]]
        summary = json.loads(args.capture_summary.read_text()) if args.capture_summary else None
        report = analyze(*(rows for rows, _ in loaded), final=args.final, capture_summary=summary)
        report["input_snapshots"] = [snapshot for _, snapshot in loaded]
        with args.output.open("x") as output:
            json.dump(report, output, indent=2)
            output.write("\n")
        print(json.dumps({key: report[key] for key in ["analysis_status", "frames", "exact_pixel_frames",
                         "matched_source_frames", "host_generation_to_receipt", "scanout_capture_receipt_window"]}, indent=2))
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
