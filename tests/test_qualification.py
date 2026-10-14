import json
import pytest

from hdmi_capture.protocol import Frame
from tools.hdmi_pattern import pattern
from tools.qualify_capture import parser, run


def setup_run(tmp_path, frames, *, require_litex=True):
    now = [0.0]
    args = parser().parse_args(["unused", "--duration", "3", "--min-frames", "3",
                              "--hard-deadline", "6", "--log", str(tmp_path / "frames.jsonl"),
                              *([] if require_litex else ["--no-require-litex"])])

    class Client:
        def __init__(self, *a, **k):
            self.frames = iter(frames)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def read(self, **kwargs):
            now[0] += 1
            try:
                return next(self.frames)
            except StopIteration:
                raise EOFError("fixture ended")

    return args, Client, lambda: now[0]


def frame(i, *, optical=None, origin="hdmi", baseline=False):
    health = dict(snapshot_atomic=False, frontend_overflow_episodes=0,
                  frontend_underflow_episodes=0,
                  native_vsync_edges=i+100, invalid_frames=0,
                  overflow_units="assertion_episodes_not_lost_frames")
    return Frame(pattern(i if optical is None else optical), dict(
        frame_id=i, session_id="fixture", source_origin=origin, baseline_only=baseline,
        capture_implementation="litex_video_gate", flags=["litex_capture"],
        litex_counters=health, litex_startup_counters=dict(health, native_vsync_edges=90,
            enabled=False, selected_frames=0,
            sample_point="sequential_gpio_reads_after_dma_start_before_capture_enable"),
        capture_enable_reset=0,
        integrity_policy="disabled_zero_selected_baseline_then_stop_on_integrity_change",
        source_health_provenance=dict(source_health_sha256="a"*64,
            source_health_counters_lifetime="fpga_load",
            source_health_overruns_unit="overflow_episodes",
            receiver_source_reset_policy="shared_per_clock"),
        counters={"source_overruns": None}))


def test_requires_both_window_and_distinct_exact_frames(tmp_path):
    args, factory, clock = setup_run(tmp_path, [frame(i) for i in range(3)])
    report = run(args, client_factory=factory, clock=clock)
    assert report["passed"]
    assert report["elapsed_seconds"] == 3
    assert report["distinct_exact_optical_frames"] == 3
    assert report["physical_source_sequence_verified"] is False
    assert report["host_clock"] == "host_monotonic"
    assert report["host_start_monotonic_seconds"] == 0
    entries = [json.loads(line) for line in args.log.read_text().splitlines()]
    assert len(entries) == 3
    assert all(entry["verification"]["exact_match"] for entry in entries)
    assert [entry["host_received_monotonic_seconds"] for entry in entries] == [1, 2, 3]


def test_legacy_013_delivered_images_do_not_claim_full_m1(tmp_path):
    samples = [frame(i) for i in range(3)]
    for sample in samples:
        sample.metadata.update(source_sequence=None, frame_source_id=None,
            capture_artifact_sha256="33f6a640cf2a6e068515f8a4e8e85ff60d4015d323a6ce67b5332479cd0e7a73")
        sample.metadata["counters"].update(source_skips=None, source_overruns=None,
                                           source_invalid_frames=None)
    args, factory, clock = setup_run(tmp_path, samples)
    report = run(args, client_factory=factory, clock=clock)
    assert report["passed"] is True
    assert report["criterion_passed"] is True
    assert report["full_m1_qualification"] is False
    assert report["physical_source_sequence_verified"] is False
    assert report["qualification_scope"] == "Sustained delivered-image criterion with LiteX health checks"
    assert any("sampling/drop accounting" in item for item in report["unmet_m1_requirements"])
    assert report["first_metadata"]["source_sequence"] is None
    assert report["last_metadata"]["counters"]["source_skips"] is None


def test_pixel_failure_logged_and_continues(tmp_path):
    bad = frame(1)
    bad.rgb[80, 250, 0] ^= 1
    args, factory, clock = setup_run(tmp_path, [frame(0), bad, frame(2), frame(3)])
    args.min_fps = 0.5
    report = run(args, client_factory=factory, clock=clock)
    assert not report["passed"]
    assert report["pixel_failures"] == 1
    assert report["delivered_frames"] == 4
    entries = [json.loads(line) for line in args.log.read_text().splitlines()]
    assert entries[1]["verification"]["mismatched_bytes"] == 1
    assert entries[3]["verification"]["exact_match"]


def test_baseline_and_synthetic_rejected(tmp_path):
    for origin, baseline in (("hdmi", True), ("synthetic", False)):
        directory = tmp_path / origin
        directory.mkdir()
        args, factory, clock = setup_run(directory, [frame(0, origin=origin, baseline=baseline)])
        report = run(args, client_factory=factory, clock=clock)
        assert not report["passed"]
        assert report["metadata_failures"] == 1
        assert report["stop_reason"] == "metadata_rejection"


def test_repeated_optical_frames_never_count_as_new(tmp_path):
    args, factory, clock = setup_run(tmp_path, [frame(i, optical=0) for i in range(6)])
    report = run(args, client_factory=factory, clock=clock)
    assert not report["passed"]
    assert report["distinct_exact_optical_frames"] == 1
    assert report["repeated_optical_frames"] == 5
    assert report["stop_reason"] == "hard_deadline"


def test_early_eof_and_endpoint_arrays(tmp_path):
    args, factory, clock = setup_run(tmp_path, [frame(0)])
    args.save_endpoints = tmp_path / "endpoints"
    report = run(args, client_factory=factory, clock=clock)
    assert report["transport_errors"] == 1
    assert not report["passed"]
    assert {path.name for path in args.save_endpoints.iterdir()} == {
        "first.npy", "first.json", "last.npy", "last.json"}
    entries = [json.loads(line) for line in args.log.read_text().splitlines()]
    assert entries[-1]["event"] == "error"


def test_mixed_optical_rows_are_counted(tmp_path):
    mixed = frame(0)
    mixed.rgb[240:] = pattern(99)[240:]
    args, factory, clock = setup_run(tmp_path, [mixed, frame(1), frame(2), frame(3)])
    report = run(args, client_factory=factory, clock=clock)
    assert report["mixed_frames"] == 1
    assert report["pixel_failures"] == 1
    assert report["delivered_frames"] == 4
    assert not report["passed"]


def test_refuses_overwriting_evidence(tmp_path):
    args, factory, clock = setup_run(tmp_path, [frame(0)])
    args.log.write_text("existing evidence\n")
    with pytest.raises(FileExistsError):
        run(args, client_factory=factory, clock=clock)
    assert args.log.read_text() == "existing evidence\n"


@pytest.mark.parametrize("change", ["missing", "null", "startup_invalid", "overflow_change",
                                    "underflow_change", "missing_provenance", "bad_reset_policy"])
def test_litex_requires_observed_health_and_clean_integrity(tmp_path, change):
    sample = frame(0)
    if change == "missing":
        sample.metadata.pop("litex_counters")
    elif change == "null":
        sample.metadata["litex_counters"]["frontend_overflow_episodes"] = None
        sample.metadata["litex_counters"]["native_vsync_edges"] = None
    elif change == "startup_invalid":
        sample.metadata["litex_startup_counters"]["invalid_frames"] = 1
    elif change == "overflow_change":
        sample.metadata["litex_counters"]["frontend_overflow_episodes"] = 1
    elif change == "underflow_change":
        sample.metadata["litex_counters"]["frontend_underflow_episodes"] = 1
    elif change == "missing_provenance":
        sample.metadata.pop("source_health_provenance")
    else:
        sample.metadata["source_health_provenance"]["receiver_source_reset_policy"] = "legacy"
    args, factory, clock = setup_run(tmp_path, [sample])
    report = run(args, client_factory=factory, clock=clock)
    assert not report["passed"]
    assert report["metadata_failures"] == 1
    assert report["delivered_frames"] == 1
    entry = json.loads(args.log.read_text())
    assert entry["verification"]["exact_match"]
    assert entry["metadata_errors"]


def test_startup_overflow_disclosed_and_rejected_without_frame_loss_inference(tmp_path):
    samples = [frame(i) for i in range(3)]
    for sample in samples:
        sample.metadata["litex_counters"]["frontend_overflow_episodes"] = 2
        sample.metadata["litex_startup_counters"]["frontend_overflow_episodes"] = 2
    args, factory, clock = setup_run(tmp_path, samples)
    report = run(args, client_factory=factory, clock=clock)
    assert not report["passed"]
    assert report["startup_frontend_overflow_episodes"] == 2
    assert report["physical_source_sequence_verified"] is False


def test_unselected_pre_enable_startup_invalid_is_preserved_and_disclosed(tmp_path):
    samples = [frame(i) for i in range(3)]
    for sample in samples:
        sample.metadata["litex_startup_counters"]["invalid_frames"] = 1
        sample.metadata["litex_counters"]["invalid_frames"] = 1
    args, factory, clock = setup_run(tmp_path, samples)
    report = run(args, client_factory=factory, clock=clock)
    assert report["passed"]
    assert report["startup_invalid_frames"] == 1
    assert report["pixel_failures"] == 0
    assert report["first_metadata"]["litex_startup_counters"]["invalid_frames"] == 1


@pytest.mark.parametrize("missing_proof", ["reset", "enabled", "selected", "point", "policy"])
def test_startup_invalid_exception_requires_every_pre_enable_proof(tmp_path, missing_proof):
    sample = frame(0)
    sample.metadata["litex_startup_counters"]["invalid_frames"] = 1
    sample.metadata["litex_counters"]["invalid_frames"] = 1
    if missing_proof == "reset":
        sample.metadata.pop("capture_enable_reset")
    elif missing_proof == "enabled":
        sample.metadata["litex_startup_counters"]["enabled"] = True
    elif missing_proof == "selected":
        sample.metadata["litex_startup_counters"]["selected_frames"] = 1
    elif missing_proof == "point":
        sample.metadata["litex_startup_counters"]["sample_point"] = "sequential_gpio_reads_after_dma_start_before_first_read"
    else:
        sample.metadata["integrity_policy"] = "stop_on_counter_change_no_buffer_association"
    args, factory, clock = setup_run(tmp_path, [sample])
    report = run(args, client_factory=factory, clock=clock)
    assert not report["passed"]
    assert report["metadata_failures"] == 1


def test_old_after_enable_baseline_still_rejected(tmp_path):
    sample = frame(0)
    sample.metadata.pop("capture_enable_reset")
    sample.metadata["litex_counters"]["invalid_frames"] = 1
    sample.metadata["litex_startup_counters"].update(invalid_frames=1, enabled=True,
        selected_frames=0, sample_point="sequential_gpio_reads_after_dma_start_before_first_read")
    sample.metadata["integrity_policy"] = "stop_on_counter_change_no_buffer_association"
    args, factory, clock = setup_run(tmp_path, [sample])
    report = run(args, client_factory=factory, clock=clock)
    assert not report["passed"]
    assert report["metadata_failures"] == 1


def test_native_vsync_rollback_rejects_nonassociated_snapshot(tmp_path):
    first, second = frame(0), frame(1)
    first.metadata["litex_counters"]["native_vsync_edges"] = 110
    second.metadata["litex_counters"]["native_vsync_edges"] = 100
    args, factory, clock = setup_run(tmp_path, [first, second])
    report = run(args, client_factory=factory, clock=clock)
    assert not report["passed"]
    assert report["metadata_failures"] == 1
    assert "rollback" in args.log.read_text() or "rolled back" in args.log.read_text()
