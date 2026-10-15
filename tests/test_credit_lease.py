import asyncio
import copy
from types import SimpleNamespace

import numpy as np
import pytest

from hdmi_capture.sources import Sample, SourceError
from tools import check_credit_lease as checker
from tools.check_credit_lease import check_lease, run_session
from tools.hdmi_pattern import pattern


class Buffer(np.ndarray):
    physical_address = 0x100000

    def invalidate(self):
        self.invalidations += 1


class FakeSource:
    def __init__(self, fault=None):
        self.fault = fault
        self.leased = False
        self.acquired = 0
        self.edges = 100
        self.dma_shutdown_safe = True
        self.final_accounting = None
        self.started = self.closed = False
        self.acknowledgements = 0
        self.arm_calls = 0
        self.native = SimpleNamespace(buffer=np.empty((480, 640, 3), dtype=np.uint8).view(Buffer),
                                      mmio=SimpleNamespace(read=self.read_mmio), arm=self.arm)
        self.native.buffer.invalidations = 0
        self.control = SimpleNamespace(identity=self.identity, snapshot=self.snapshot, command=1)

    def start(self):
        self.started = True

    def arm(self):
        self.arm_calls += 1

    def read_mmio(self, offset):
        registers = {0x28: 0, 0x30: 0x15010, 0x34: 0x11001,
                     0xA0: 480, 0xA4: 1920, 0xA8: 1920}
        if self.fault == "running":
            registers[0x30], registers[0x34] = 0x15011, 0x11000
        if self.fault == "dma_error":
            registers[0x34] |= 0x10
        if offset in (0xAC, 0xB0, 0xB4, 0xB8):
            return self.native.buffer.physical_address
        return registers[offset]

    def identity(self):
        return dict(credit_busy=self.leased, credit_done=self.leased, credit_failed=False,
                    request_seen=self.acquired % 2, ack_seen=self.acknowledgements % 2,
                    native_armed=True, source_sequence_fault=False, command_errors=0,
                    source_sequence_faults=0, selected_native_vsync_id=self.selected_native,
                    selected_sof_id=self.selected_native - 1, selected_completed=self.acquired,
                    identity_snapshot_coherent=self.leased)

    def snapshot(self, sample_point="test"):
        return dict(enabled=True, selected_frames=self.acquired, invalid_frames=3,
                    frontend_overflow_episodes=0, frontend_underflow_episodes=0,
                    native_vsync_edges=self.edges, sample_point=sample_point)

    async def read(self):
        if self.leased:
            if self.fault == "missing_lease_guard":
                self.native.arm()
            raise SourceError("Previous DMA lease must be released before requesting another frame")
        self.native.arm()
        self.acquired += 1
        self.selected_native = self.edges
        self.leased = True
        self.dma_shutdown_safe = False
        optical_id = 1000 if self.fault == "repeat_pattern" else 1000 + self.acquired
        self.native.buffer[:] = pattern(optical_id)[..., ::-1]
        return Sample(self.native.buffer, 1, sequence=self.selected_native, bgr=True,
                      release=self.release, extra_metadata=dict(frame_source_id=self.selected_native - 1,
                          source_accounting=copy.deepcopy(self.identity()),
                          litex_startup_counters=self.snapshot()))

    def release(self):
        self.acknowledgements += 1
        self.control.command ^= 4
        self.leased = False

    async def sleep(self, duration):
        if self.fault != "no_progress":
            self.edges += 15
        if self.fault == "moving_id":
            self.selected_native += 1
        if self.fault == "mutated_buffer":
            self.native.buffer[50, 200, 0] ^= 1

    def close(self):
        self.closed = True
        if self.fault == "unsafe_close":
            raise SourceError("DMA halt timed out")
        self.dma_shutdown_safe = True


def run(source, records):
    return asyncio.run(run_session(source, records.append, hold_seconds=1, sleep=source.sleep))


def test_holds_native_buffer_until_ack_and_observes_new_exact_pattern():
    source, records = FakeSource(), []
    result = run(source, records)
    assert result["passed"] and result["dma_shutdown_safe"]
    assert source.started and source.closed
    assert source.acknowledgements == 2 and source.arm_calls == 2
    assert source.native.buffer.invalidations == 7
    assert len([r for r in records if r["event"] == "lease_hold"]) == 4
    assert [r["verification"]["expected_id"] for r in records
            if r["event"] in ("pattern_a", "pattern_b")] == [1001, 1002]
    assert not result["physical_source_sequence_verified"]


@pytest.mark.parametrize("fault, message", [
    ("moving_id", "does not match sample metadata"),
    ("mutated_buffer", "Native buffer changed"),
    ("running", "VDMA is not error-free"),
    ("dma_error", "VDMA is not error-free"),
    ("no_progress", "did not advance"),
    ("missing_lease_guard", "write prevented"),
    ("repeat_pattern", "different exact optical pattern"),
])
def test_rejects_invalid_ownership_observations_and_closes(fault, message):
    source, records = FakeSource(fault), []
    result = run(source, records)
    assert not result["passed"] and message in result["error"]
    assert result["dma_shutdown_safe"] and source.closed
    if fault in ("moving_id", "mutated_buffer", "running", "dma_error", "no_progress", "missing_lease_guard"):
        assert source.acknowledgements == 0
    if fault == "missing_lease_guard":
        assert source.arm_calls == 1
    if fault == "running":
        assert source.native.buffer.invalidations == 0


def test_cleanup_failure_remains_unsafe_and_emits_final_record():
    source, records = FakeSource("unsafe_close"), []
    result = run(source, records)
    assert not result["passed"] and not result["dma_shutdown_safe"]
    assert "DMA halt timed out" in result["cleanup_error"]
    assert records[-1] == result


@pytest.mark.parametrize("duration", [0, -1, 3.1, float("inf"), float("nan")])
def test_invalid_duration_cannot_read_or_arm(duration):
    source = FakeSource()
    with pytest.raises(RuntimeError, match="Hold duration"):
        asyncio.run(check_lease(source, lambda record: None, hold_seconds=duration))
    assert source.arm_calls == 0


class HoldEntered(BaseException):
    pass


@pytest.mark.parametrize("failure", ["start", "hash", "output"])
def test_cli_holds_source_after_unsafe_cleanup_even_when_work_raises(tmp_path, monkeypatch, failure):
    from hdmi_capture import sender, sources

    source = FakeSource("unsafe_close")
    source.dma_shutdown_safe = False
    held = []

    def hold(owned_source, error):
        held.append((owned_source, error))
        raise HoldEntered()

    async def fail_work(owned_source, emit, **kwargs):
        if failure == "output":
            raise OSError("Evidence write failed")
        return await run_session(owned_source, emit, sleep=owned_source.sleep)

    def fail_start():
        raise SourceError("Startup failed with unsafe DMA")

    if failure == "start":
        source.start = fail_start
    if failure == "hash":
        def fail_hash(pixels):
            raise ValueError("Hash/copy failed")
        monkeypatch.setattr(checker, "digest", fail_hash)
    monkeypatch.setattr(sources, "LiteXCreditSource", lambda *args, **kwargs: source)
    monkeypatch.setattr(sender, "_hold_unsafe_dma", hold)
    monkeypatch.setattr(checker, "run_session", run_session)
    if failure == "output":
        monkeypatch.setattr(checker, "run_session", fail_work)
    paths = [tmp_path / name for name in ("capture.bit", "capture.hwh", "manifest.json", "receipt.json")]
    for path in paths:
        path.write_text("{}")
    with pytest.raises(HoldEntered):
        checker.main([str(paths[0]), str(paths[2]), "--prepared-receipt", str(paths[3]),
                      "--output", str(tmp_path / "result.jsonl")])
    assert len(held) == 1 and held[0][0] is source
    assert source.native.buffer is not None and not source.dma_shutdown_safe


def test_existing_output_cannot_construct_source(tmp_path, monkeypatch):
    from hdmi_capture import sources

    constructed = []
    monkeypatch.setattr(sources, "LiteXCreditSource", lambda *args, **kwargs: constructed.append(True))
    output = tmp_path / "existing.jsonl"
    output.write_text("retained evidence\n")
    with pytest.raises(FileExistsError):
        checker.main(["missing.bit", "missing.json", "--prepared-receipt", "missing-receipt.json",
                      "--output", str(output)])
    assert not constructed
    assert output.read_text() == "retained evidence\n"
