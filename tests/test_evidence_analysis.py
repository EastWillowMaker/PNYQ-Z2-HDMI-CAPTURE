import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "analyze_hdmi_evidence", Path(__file__).parents[1] / "tools" / "analyze_hdmi_evidence.py"
)
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)


def frame(identifier=5, receipt=1.5, exact=True):
    return {"event": "frame", "index": 1, "host_received_monotonic_seconds": receipt,
            "metadata": {"height": 480, "frame_id": 20, "timestamp_ns": 999999999999999},
            "metadata_errors": [], "verification": {"exact_match": exact,
                "optical_ids": {str(identifier): 480}, "valid_marker_rows": 480,
                "invalid_marker_rows": [], "mixed_optical_ids": False}}


def source(identifier=5):
    return {"event": "source_pre_swap", "frame_id": identifier,
            "frame_generated_monotonic_ns": 1000000000,
            "monotonic_ns": 1100000000, "framebuffer_self_check_passed": True}


def test_host_generation_interval_does_not_use_board_clock():
    sample = {"event": "scanout_sample", "sample_started_monotonic_ns": 1200000000,
              "sample_finished_monotonic_ns": 1200000001, "error": None,
              "state": {"active": True, "framebuffer": {"format": "XR24"},
                        "crtc_fb_unchanged_during_sample": True}}
    report = analysis.analyze([frame()], [source()], [sample])
    assert report["analysis_status"] == "provisional_live_preview"
    assert report["host_generation_to_receipt"]["p95"] == 0.5
    assert report["host_pre_swap_to_receipt"]["max"] == pytest.approx(0.4)
    assert report["scanout_capture_receipt_window"]["matched_frame_interval_coverage"] == {
        "samples_only_xr24_consistent": 1}
    assert report["matched_source_self_checks_true"] == 1


def test_duplicate_source_ids_and_missing_markers_not_assumed_matched():
    broken = frame(6)
    broken["verification"]["invalid_marker_rows"] = [20]
    report = analysis.analyze([frame(), broken], [source(), source()], [])
    assert report["matched_source_frames"] == 0
    assert report["ambiguous_source_id_frames"] == 1
    assert report["incoherent_or_missing_optical_frames"] == 1


def test_body_failure_does_not_become_a_qualification_pass():
    report = analysis.analyze([frame(exact=False)], [source()], [], final=True)
    assert report["failed_or_missing_pixel_verification_frames"] == 1
    assert report["matched_frames"][0]["captured_exact_match"] is False
    assert "Not assigned" in report["qualification_verdict"]


def test_id_gaps_wrap_repeats_and_regressions():
    assert analysis.gap_counts([0xFFFFFFFF, 0])["unobserved_intermediate_ids"] == 0
    report = analysis.gap_counts([5, 5, 8, 7])
    assert report["adjacent_repeats"] == 1
    assert report["unobserved_intermediate_ids"] == 2
    assert report["regressions"] == 1


def test_live_partial_line_is_visible_but_final_parse_rejects_it(tmp_path):
    path = tmp_path / "growing.jsonl"
    path.write_text(json.dumps(source()) + '\n{"event":')
    rows, snapshot = analysis.load_jsonl(path, live=True)
    assert len(rows) == 1
    assert snapshot["ignored_partial_final_lines"] == 1
    with pytest.raises(ValueError, match="line 2"):
        analysis.load_jsonl(path)
