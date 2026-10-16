#!/usr/bin/env python3
"""Bounded board observation of a held single-credit DMA lease."""

import argparse
import asyncio
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import sys
import time

import numpy as np

from hdmi_capture.sources import DMA_ERRORS, SourceError
from hdmi_capture.modes import CAPTURE_MODES, get_mode

try:
    from tools.hdmi_pattern import verify
except ModuleNotFoundError:
    from hdmi_pattern import verify


class LeaseCheckError(RuntimeError):
    """The observed lease does not satisfy the ownership contract."""


def require(condition, message):
    if not condition:
        raise LeaseCheckError(message)


def digest(pixels):
    return hashlib.sha256(np.asarray(pixels).tobytes(order="C")).hexdigest()


def observe(source, sample):
    """Read only fixed-clock registers, then invalidate the halted buffer."""
    native = source.native
    require(native is not None and sample.pixels is native.buffer,
            "Sample is not the owned native buffer")
    begin = time.monotonic_ns()
    identity_before = source.control.identity()
    counters = source.control.snapshot("credit_lease_check_fixed_clock_reads")
    raw = {hex(offset): native.mmio.read(offset) for offset in
           (0x28, 0x30, 0x34, 0xA0, 0xA4, 0xA8, 0xAC, 0xB0, 0xB4, 0xB8)}
    identity_after = source.control.identity()
    proof = dict(begin_ns=begin, registers_end_ns=time.monotonic_ns(), clock="board_monotonic",
                 identity_before=identity_before, identity_after=identity_after,
                 counters=counters, vdma=raw,
                 buffer_physical_address=int(native.buffer.physical_address))
    # Avoid invalidating a buffer unless raw readback first proves DMA halted.
    if not raw["0x30"] & 1 and raw["0x34"] & 1:
        native.buffer.invalidate()
        proof.update(raw_buffer_sha256=digest(sample.pixels),
                     rgb_sha256=digest(sample.copy_rgb()))
    proof["end_ns"] = time.monotonic_ns()
    return proof


def validate(proof, sample, previous=None, *, mode="vga"):
    profile = get_mode(mode)
    raw, identity = proof["vdma"], proof["identity_after"]
    require(raw["0x30"] & 0xFFFFFF7F == 0x15010
            and raw["0x34"] & 0x1001 == 0x1001 and not raw["0x34"] & DMA_ERRORS,
            "VDMA is not error-free single-frame auto-HALTED with RS0 and frame IRQ")
    require(raw["0x28"] & ((0x1F << 24) | (0x1F << 8)) == 0,
            "VDMA did not remain parked on store zero")
    require((raw["0xa0"], raw["0xa4"], raw["0xa8"]) ==
            (profile.height, profile.width * 3, profile.width * 3),
            "VDMA geometry changed")
    require(sample.pixels.dtype == np.uint8 and
            sample.pixels.shape == (profile.height, profile.width, 3),
            "Owned buffer does not match the selected capture mode")
    require(all(raw[hex(offset)] == proof["buffer_physical_address"]
                for offset in (0xAC, 0xB0, 0xB4, 0xB8)),
            "VDMA store address differs from the owned buffer")
    require(identity is not None and proof["identity_before"] == identity
            and identity["identity_snapshot_coherent"]
            and identity["credit_busy"] and identity["credit_done"]
            and identity["native_armed"], "Held identity is not coherent busy/DONE")
    require(not any(identity[name] for name in
                    ("credit_failed", "source_sequence_fault", "command_errors",
                     "source_sequence_faults")), "Credit/source fault is present")
    metadata = sample.extra_metadata
    require(metadata.get("capture_mode", "vga") == profile.name,
            "Sample capture mode does not match the selected profile")
    accounting = metadata["source_accounting"]
    require(identity["selected_native_vsync_id"] == sample.sequence
            and identity["selected_sof_id"] == metadata["frame_source_id"]
            and identity["selected_completed"] == accounting["selected_completed"],
            "Held identity does not match sample metadata")
    require(all(identity[name] == accounting[name] for name in identity),
            "Held identity differs from acquired credit")
    counters, baseline = proof["counters"], metadata["litex_startup_counters"]
    require(counters["enabled"], "Capture gate is no longer enabled")
    for name in ("invalid_frames", "frontend_overflow_episodes", "frontend_underflow_episodes"):
        require(type(counters[name]) is int and counters[name] == baseline[name],
                f"Integrity counter changed: {name}")
    require(type(counters["native_vsync_edges"]) is int,
            "Native edge counter is unavailable")
    require("raw_buffer_sha256" in proof and "rgb_sha256" in proof,
            "Halted buffer was not hashed")
    if previous is not None:
        require(raw == previous["vdma"], "VDMA registers changed while leased")
        require(identity == previous["identity_after"], "Identity moved while leased")
        require(counters["selected_frames"] == previous["counters"]["selected_frames"],
                "Another frame was selected while leased")
        require(counters["native_vsync_edges"] >= previous["counters"]["native_vsync_edges"],
                "Native counter wrapped or reset")
        require(proof["raw_buffer_sha256"] == previous["raw_buffer_sha256"]
                and proof["rgb_sha256"] == previous["rgb_sha256"],
                "Native buffer changed while leased")


async def reject_second_read(source):
    """Guard arm before exercising the public leased-read rejection."""
    require(source.leased, "Source does not report an active lease")
    native, attempted = source.native, []
    original_arm = native.arm

    def forbid_arm():
        attempted.append(True)
        raise LeaseCheckError("Leased read attempted to arm DMA; write prevented")

    native.arm = forbid_arm
    try:
        try:
            await asyncio.wait_for(source.read(), timeout=0.2)
        except SourceError as error:
            require(str(error) == "Previous DMA lease must be released before requesting another frame",
                    f"Leased read rejected for an unexpected reason: {error}")
        else:
            raise LeaseCheckError("A second read returned while the first lease was held")
        require(not attempted, "Leased read reached DMA arm")
    finally:
        native.arm = original_arm


async def check_lease(source, emit, *, mode="vga", hold_seconds=1, sleep=asyncio.sleep):
    profile = get_mode(mode)
    require(math.isfinite(hold_seconds) and 0.1 <= hold_seconds <= 3,
            "Hold duration must be finite and in [0.1,3] seconds")
    sample_a = await source.read()
    a = observe(source, sample_a)
    emit(dict(event="lease_a", sample_sequence=sample_a.sequence,
              metadata=sample_a.extra_metadata, proof=a))
    validate(a, sample_a, mode=profile.name)
    verification_a = verify(sample_a.copy_rgb(), mode=profile.name)
    emit(dict(event="pattern_a", verification=verification_a))
    require(verification_a["exact_match"], "Sample A is not an exact analytic RGB pattern")
    await reject_second_read(source)
    after_rejection = observe(source, sample_a)
    emit(dict(event="leased_read_rejected", proof=after_rejection))
    validate(after_rejection, sample_a, a, mode=profile.name)
    previous = after_rejection
    hold_begin = time.monotonic_ns()
    for index in range(4):
        await sleep(hold_seconds / 4)
        current = observe(source, sample_a)
        emit(dict(event="lease_hold", index=index, proof=current))
        validate(current, sample_a, previous, mode=profile.name)
        previous = current
    native_delta = previous["counters"]["native_vsync_edges"] - a["counters"]["native_vsync_edges"]
    require(native_delta >= 2, "Native source did not advance by at least two edges during lease")
    sample_a.close()
    emit(dict(event="lease_a_released", monotonic_ns=time.monotonic_ns(),
              hold_begin_ns=hold_begin, configured_hold_seconds=hold_seconds,
              native_edges_during_lease=native_delta,
              identity_after_ack=source.control.identity(),
              command_after_ack=source.control.command))
    require(not source.leased, "Source did not release sample A")
    sample_b = await source.read()
    b = observe(source, sample_b)
    emit(dict(event="lease_b", sample_sequence=sample_b.sequence,
              metadata=sample_b.extra_metadata, proof=b))
    validate(b, sample_b, mode=profile.name)
    verification_b = verify(sample_b.copy_rgb(), mode=profile.name)
    emit(dict(event="pattern_b", verification=verification_b))
    require(verification_b["exact_match"], "Sample B is not an exact analytic RGB pattern")
    old, new = a["identity_after"], b["identity_after"]
    require(new["selected_native_vsync_id"] > old["selected_native_vsync_id"]
            and new["selected_sof_id"] > old["selected_sof_id"]
            and new["selected_native_vsync_id"] - old["selected_native_vsync_id"]
            == new["selected_sof_id"] - old["selected_sof_id"]
            and new["selected_completed"] == old["selected_completed"] + 1,
            "Next credit did not advance native/SOF IDs and completion consistently")
    require(verification_b["expected_id"] != verification_a["expected_id"]
            and b["rgb_sha256"] != a["rgb_sha256"],
            "Next credit did not contain a different exact optical pattern")
    sample_b.close()
    require(not source.leased, "Source did not release sample B")
    emit(dict(event="lease_b_released", monotonic_ns=time.monotonic_ns(),
              identity_after_ack=source.control.identity(),
              command_after_ack=source.control.command))


async def run_session(source, emit, *, mode="vga", hold_seconds=1, sleep=asyncio.sleep):
    result = dict(event="result", passed=False, dma_shutdown_safe=False,
                  physical_source_sequence_verified=False,
                  scope="held_single_credit_buffer_ownership_observation", capture_mode=mode)
    try:
        get_mode(mode)
        source.start()
        await check_lease(source, emit, mode=mode, hold_seconds=hold_seconds, sleep=sleep)
        result["passed"] = True
    except BaseException as error:
        result.update(error_type=type(error).__name__, error=str(error))
    finally:
        try:
            source.close()
        except BaseException as error:
            result.update(passed=False, cleanup_error_type=type(error).__name__,
                          cleanup_error=str(error))
        result["dma_shutdown_safe"] = source.dma_shutdown_safe is True
        if not result["dma_shutdown_safe"]:
            result["passed"] = False
        result["final_source_accounting"] = source.final_accounting
        emit(result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bitfile", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--prepared-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New JSONL evidence file")
    parser.add_argument("--hold-seconds", type=float, default=1)
    parser.add_argument("--mode", choices=tuple(CAPTURE_MODES), default="vga")
    args = parser.parse_args(argv)
    if not math.isfinite(args.hold_seconds) or not 0.1 <= args.hold_seconds <= 3:
        parser.error("--hold-seconds must be finite and in [0.1,3]")
    # Open before source construction so an existing output cannot start hardware.
    with args.output.open("x") as output:
        def emit(record):
            output.write(json.dumps(record) + "\n")
            output.flush()

        from hdmi_capture import sources as sources_module
        from hdmi_capture.sender import _hold_unsafe_dma

        def progress(stage):
            try:
                emit(dict(event="source_stage", detail=stage))
            except OSError:
                # Evidence storage failure must not prevent cooperative DMA halt.
                pass

        source = sources_module.LiteXCreditSource(
            args.bitfile, args.manifest, capture_mode=args.mode, capture_fps=2,
            prepared_receipt=args.prepared_receipt, progress=progress)
        files = dict(bitfile=args.bitfile, hwh=args.bitfile.with_suffix(".hwh"),
                     manifest=args.manifest, prepared_receipt=args.prepared_receipt,
                     checker=Path(__file__), runtime_sources=Path(sources_module.__file__))
        emit(dict(event="configuration", capture_mode=args.mode, hold_seconds=args.hold_seconds,
                  provenance={name: dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
                              for name, path in files.items()},
                  pid=os.getpid(), boot_id=Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
                  clock="board_monotonic"))

        async def execute():
            loop = asyncio.get_running_loop()
            task = asyncio.current_task()
            for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT):
                loop.add_signal_handler(signum, task.cancel)
            try:
                return await run_session(source, emit, mode=args.mode, hold_seconds=args.hold_seconds)
            finally:
                for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT):
                    loop.remove_signal_handler(signum)

        try:
            result = asyncio.run(execute())
        except BaseException as error:
            # Output or event-loop failure must not bypass native-buffer retention.
            if source.dma_shutdown_safe is not True:
                _hold_unsafe_dma(source, error)
            raise
        if not result["dma_shutdown_safe"]:
            _hold_unsafe_dma(source, LeaseCheckError(result.get("cleanup_error", result.get("error", "Unsafe DMA"))))
        return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
