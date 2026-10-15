import json
import pytest

from hdmi_capture.protocol import Frame
from tools.hdmi_pattern import pattern
from tools.qualify_capture import _accounting_errors, parser, run


def setup_run(tmp_path, frames, *, require_litex=True, legacy=False):
    now = [0.0]
    args = parser().parse_args(["unused", "--duration", "3", "--min-frames", "3",
                              "--hard-deadline", "6", "--log", str(tmp_path / "frames.jsonl"),
                              *([] if require_litex else ["--no-require-litex"]),
                              *(["--legacy-delivered-image-criterion"] if legacy else [])])

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
        acquisition_id=i+1, source_sequence=100+i, frame_source_id=i,
        source_sequence_domain="native_vsync_edge_counter", source_sequence_bits=32,
        source_sequence_policy="reject_wrap_or_reset",
        capture_implementation="litex_single_credit_gate", flags=["litex_capture"],
        litex_counters=health, litex_startup_counters=dict(health, native_vsync_edges=90,
            enabled=False, selected_frames=0,
            sample_point="before_first_credit_while_gate_disabled_dma_halted"),
        capture_enable_reset=0,
        integrity_policy="single_credit_parked_auto_halt_fail_closed_v1",
        source_accounting=dict(abi="single_credit_parked_v1",
            dma_completion_mode="parked_frame_count_halt_v1", vdma_fsync_mode="free_run",
            gate_completion_policy="next_sof_after_selected_output_drain_v1", buffer_slot=0,
            dma_auto_halted=True, raw_dma_status=0x1001, buffer_stable_until_release=True,
            credit_busy=True, credit_done=True, credit_failed=False, request_seen=1,
            ack_seen=0, selected_completed=i+1, command_errors=0, source_sequence_faults=0,
            source_sequence_fault=False, native_armed=True, identity_snapshot_coherent=True,
            selected_sof_id=i, selected_native_vsync_id=100+i,
            intentional_skips_since_previous=None if i == 0 else 0,
            first_acquired_source_id=100, startup_intentional_accepted_sof_skips=0,
            startup_native_skips=None, acquired_frames_total=i+1,
            source_intentional_sampling_total=0),
        source_health_provenance=dict(source_health_sha256="a"*64,
            source_health_counters_lifetime="fpga_load",
            source_health_overruns_unit="overflow_episodes",
            receiver_source_reset_policy="shared_per_clock"),
        counters={"source_overruns": 0, "source_skips": 0, "source_invalid_frames": 0,
                  "source_errors": 0, "source_cleanup_errors": 0}))


def test_requires_both_window_and_distinct_exact_frames(tmp_path):
    args, factory, clock = setup_run(tmp_path, [frame(i) for i in range(3)])
    report = run(args, client_factory=factory, clock=clock)
    assert report["passed"]
    assert report["elapsed_seconds"] == 3
    assert report["distinct_exact_optical_frames"] == 3
    assert report["physical_source_sequence_verified"] is False
    assert report["source_accounting_metadata_validated"] is True
    assert report["source_accounting_validated_frames"] == 3
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
        sample.metadata.pop("source_accounting")
        sample.metadata["capture_implementation"] = "litex_video_gate"
        sample.metadata["litex_startup_counters"]["sample_point"] = "sequential_gpio_reads_after_dma_start_before_capture_enable"
        sample.metadata["integrity_policy"] = "disabled_zero_selected_baseline_then_stop_on_integrity_change"
    args, factory, clock = setup_run(tmp_path, samples, legacy=True)
    report = run(args, client_factory=factory, clock=clock)
    assert report["passed"] is True
    assert report["criterion_passed"] is True
    assert report["full_m1_qualification"] is False
    assert report["physical_source_sequence_verified"] is False
    assert report["qualification_scope"] == "Legacy sustained delivered-image criterion with LiteX health checks"
    assert report["source_accounting_required"] is False
    assert report["source_accounting_metadata_validated"] is False
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


def test_formal_default_rejects_legacy_013_accounting_gap(tmp_path):
    sample = frame(0)
    sample.metadata.pop("source_accounting")
    sample.metadata.update(source_sequence=None, frame_source_id=None,
        integrity_policy="disabled_zero_selected_baseline_then_stop_on_integrity_change")
    args, factory, clock = setup_run(tmp_path, [sample])
    report = run(args, client_factory=factory, clock=clock)
    assert report["source_accounting_required"] is True
    assert report["metadata_failures"] == 1
    assert report["exact_frames"] == 1
    assert not report["passed"]


@pytest.mark.parametrize("key,value", [
    ("identity_snapshot_coherent", False), ("buffer_stable_until_release", False),
    ("dma_auto_halted", False), ("credit_busy", False), ("credit_done", False),
    ("credit_failed", True), ("source_sequence_fault", True), ("native_armed", False),
    ("command_errors", 1), ("source_sequence_faults", 1), ("buffer_slot", 1),
    ("request_seen", 2), ("ack_seen", True), ("abi", "legacy"),
    ("dma_completion_mode", "irq_only"), ("selected_native_vsync_id", 99),
    ("selected_sof_id", 1), ("selected_completed", 2),
    ("acquired_frames_total", 2), ("source_intentional_sampling_total", 1),
    ("startup_native_skips", 0), ("raw_dma_status", 0x1000), ("raw_dma_status", 1)])
def test_invalid_single_credit_evidence_rejected(key, value):
    sample = frame(0)
    sample.metadata["source_accounting"][key] = value
    assert _accounting_errors(sample.metadata)


@pytest.mark.parametrize("bit", [4, 5, 6, 7, 8, 11, 14, 15])
def test_each_dma_error_bit_rejects_auto_halted_frame(bit):
    sample = frame(0)
    sample.metadata["source_accounting"]["raw_dma_status"] |= 1 << bit
    assert _accounting_errors(sample.metadata)


def test_accounting_reconciles_host_delivery_gaps_without_misattributing_skips():
    previous = frame(0).metadata
    current = frame(3).metadata
    # Acquisitions 2 and 3 were not delivered. Nine native inputs were skipped
    # across those three acquisition intervals; the final interval skipped two.
    current["source_sequence"] = 112
    current["frame_source_id"] = 12
    current["source_accounting"].update(selected_native_vsync_id=112, selected_sof_id=12,
        source_intentional_sampling_total=9, intentional_skips_since_previous=2)
    current["counters"]["source_skips"] = 9
    assert _accounting_errors(current, previous) == []
    current["source_accounting"]["source_intentional_sampling_total"] = 8
    assert _accounting_errors(current, previous)


def test_adjacent_acquisition_skip_must_match_native_delta():
    previous = frame(0).metadata
    current = frame(1).metadata
    current["source_sequence"] = 110
    current["frame_source_id"] = 10
    current["source_accounting"].update(selected_native_vsync_id=110, selected_sof_id=10,
        source_intentional_sampling_total=9, intentional_skips_since_previous=9)
    current["counters"]["source_skips"] = 9
    assert _accounting_errors(current, previous) == []
    current["source_accounting"]["intentional_skips_since_previous"] = 8
    assert _accounting_errors(current, previous)


def test_native_sequence_wrap_or_reset_is_not_accepted():
    previous = frame(0).metadata
    previous["source_sequence"] = 2**32-1
    previous["source_accounting"].update(selected_native_vsync_id=2**32-1,
        first_acquired_source_id=2**32-1)
    assert _accounting_errors(previous) == []
    current = frame(1).metadata
    current["source_sequence"] = 0
    current["source_accounting"].update(selected_native_vsync_id=0,
        first_acquired_source_id=2**32-1)
    assert _accounting_errors(current, previous)


def test_recorded_accounting_failure_stops_and_preserves_exact_frame(tmp_path):
    sample = frame(0)
    sample.metadata["source_accounting"]["identity_snapshot_coherent"] = False
    args, factory, clock = setup_run(tmp_path, [sample])
    report = run(args, client_factory=factory, clock=clock)
    assert report["metadata_failures"] == 1
    assert report["exact_frames"] == 1
    assert report["source_accounting_validated_frames"] == 0
    entry = json.loads(args.log.read_text())
    assert entry["verification"]["exact_match"]
    assert entry["metadata_errors"]


def test_frozen_native_and_sof_tuples_must_share_constant_offset():
    previous = frame(0).metadata
    current = frame(1).metadata
    current["frame_source_id"] = 2
    current["source_accounting"]["selected_sof_id"] = 2
    assert _accounting_errors(current, previous)


def test_summary_reconciles_received_window_and_keeps_startup_unknown(tmp_path):
    first, second, third = frame(0), frame(3), frame(4)
    for sample, native_id, total, skip in ((second, 112, 9, 2), (third, 122, 18, 9)):
        sample.metadata["source_sequence"] = native_id
        sample.metadata["frame_source_id"] = native_id-100
        sample.metadata["source_accounting"].update(selected_native_vsync_id=native_id,
            selected_sof_id=native_id-100, source_intentional_sampling_total=total,
            intentional_skips_since_previous=skip)
        sample.metadata["counters"]["source_skips"] = total
    args, factory, clock = setup_run(tmp_path, [first, second, third])
    report = run(args, client_factory=factory, clock=clock)
    assert report["passed"]
    assert report["source_accounting_received_window"] == dict(first_native_source_id=100,
        last_native_source_id=122, native_frame_intervals=22, acquired_frame_intervals=4,
        intentional_skips=18, acquired_frames_not_delivered=2, native_startup_skips=None)
    assert report["full_m1_qualification"] is False
    assert report["physical_source_sequence_verified"] is False


@pytest.mark.parametrize("key,value", [("source_skips", None), ("source_skips", 1),
    ("source_overruns", None), ("source_overruns", 1),
    ("source_invalid_frames", None), ("source_invalid_frames", 1),
    ("source_errors", None), ("source_errors", 1),
    ("source_cleanup_errors", None), ("source_cleanup_errors", 1)])
def test_public_source_counters_must_be_known_and_reconciled(key, value):
    sample = frame(0)
    sample.metadata["counters"][key] = value
    assert _accounting_errors(sample.metadata)


def test_native_sampling_not_combined_with_old_software_sampling_counter():
    previous, current = frame(0).metadata, frame(1).metadata
    current["source_sequence"] = 110
    current["frame_source_id"] = 10
    current["source_accounting"].update(selected_native_vsync_id=110, selected_sof_id=10,
        source_intentional_sampling_total=9, intentional_skips_since_previous=9)
    current["counters"].update(source_skips=9, intentional_sampling_drops=0)
    assert _accounting_errors(current, previous) == []


def test_real_credit_producer_wire_metadata_passes_formal_qualifier(tmp_path):
    """Exercise the reader/sender/parser boundary instead of hand-written metadata."""
    import asyncio
    import socket
    import threading

    from test_sources import credit_reader_fixture
    from hdmi_capture.protocol import encode_frame, read_frame
    from hdmi_capture.sender import Sender

    source, _ = credit_reader_fixture()
    source.manifest.update(frame(0).metadata['source_health_provenance'])
    baseline = dict(source.integrity_baseline,
        overflow_units='assertion_episodes_not_lost_frames',
        sample_point='before_first_credit_while_gate_disabled_dma_halted')
    source.integrity_baseline = source.integrity_previous = baseline
    source.control.snapshot = lambda: dict(baseline, enabled=True,
        native_vsync_edges=source.control.next_native + 1)
    sender = Sender(source, fps=2)

    async def acquire():
        received = []
        for i in range(3):
            source.control.next_native = 102 + 30*i
            source.control.next_sof = 22 + 30*i
            source.native.buffer[:] = pattern(i)[..., ::-1]
            sample = await source.read()
            sender.counters['acquired'] = i+1
            rgb = sample.copy_rgb()
            wire = encode_frame(rgb, sender._metadata(sample, i+1))
            sample.close()
            # This must fit the production protocol bound and decode actual bytes.
            left, right = socket.socketpair()
            try:
                thread = threading.Thread(target=right.sendall, args=(wire,))
                thread.start()
                received.append(read_frame(left))
                thread.join(2)
                assert not thread.is_alive()
            finally:
                left.close()
                right.close()
        return received

    samples = asyncio.run(acquire())
    args, factory, clock = setup_run(tmp_path, samples)
    report = run(args, client_factory=factory, clock=clock)
    assert report['passed'], report
    assert report['source_accounting_validated_frames'] == 3
    assert report['source_accounting_metadata_validated']
    assert report['last_metadata']['counters']['source_skips'] == 58
