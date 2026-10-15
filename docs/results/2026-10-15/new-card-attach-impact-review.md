# Attached-source diagnostic impact review

Goal: compare loading017 after KMS readiness with attaching the already-loaded
017 pair. Preserve the selected VGA mode, raw RGB bytes, mode/integrity checks,
single-credit ownership, TCP framing, and halt-before-free policy. This is an
operator experiment; production sender/adapter code is unchanged at c81e819.
Recommended reading order: dispatch and load ownership, startup checks, native
DMA/cleanup, then the local source worker. Hardware attach003 is NOT RUN.

## Call and state map

The experimental entry is `artifacts/deploy/attached-credit-sender.py:23`.
It assigns AttachedCreditSource to the sender module atline22, then calls
`sender.main` (`src/hdmi_capture/sender.py:286`). The factory atline324 selects
the substituted class. `main:339` calls asyncio.run(Sender.run), `run:192`
awaits Sender.start, `start:175` calls source.start, and
`LiteXCreditSource.start` (`src/hdmi_capture/sources.py:650`) calls load_overlay.
The runtime override is `attached-credit-sender.py:9`. This dispatch edge is
verified by source, not resolved by the graph. Asyncio scheduling/SDK internals
are not claimed fully traced. This reaches a verified script entry through
more than three caller edges; no public production callers changed.

The override calls the original load_overlay(download=False) at
`sources.py:382`: paired-file/manifest verification, ABI/PYNQ-version checks,
PYNQ attachment, is_loaded check, S2MM-only VDMA/resource lookup, then a
GPIO-only return atline408. It reads raw DMA RS/Halted and command reset0
before creating VideoIn athelperline17. VideoIn/PixelPacker initialization can
write registers even before capture, so the halt check precedes driver setup.
The later source.start creates CreditControl, configures video, checks measured
mode, native identity, zero selected completion, disabled startup baseline and
frontend loss counters before allocating the one capture buffer atline688.
Reads still use the original health/identity/VDMA completion checks.

Cleanup follows Sender.run:202 -> Sender.close:217 -> source.close:813 ->
OneFrameDMA.stop_mmio:543 -> buffer.freebuffer:850. A halt timeout leaves the
source unsafe; sender.main:341 enters _hold_unsafe_dma instead of freeing live
buffers. Final native-source accounting can fail while raw halt still succeeds;
that remains a failed run, not a clean qualification.

## Changed input class and limits

Before: the source always reprogrammed the FPGA on startup. After: this explicit
operator entry can reach configuration using a detected, already-loaded017
pair with stopped DMA/reset0 commands. Existing native clocks/counters therefore
persist. The current timing probe has invalid unselected frames; none are
silently discarded from evidence. Startup invalid counts stay disclosed, and
any increment after the disabled baseline still fails original health checks.
This experiment does not waive geometry, lock, or native pairing failures.

Unsupported manifest/ABI/mode and forbidden active-DMA/nonzero-command paths
remain rejected by the stated checks. Their actual hardware rejection paths
have not been exercised by unsafe mutations. is_loaded is PYNQ software
metadata, not hardware cryptographic readback; external programming outside
PYNQ or stale software state is outside this one-run attachment contract.
There is no production CLI option to attach after arbitrary prior capture.

A known pre-existing reporting gap is visible at sender.py:175 and192: source
startup occurs before the run's final status/cleanup-report try block. Source
startup failures can therefore omit the final dma_shutdown_safe JSON, even
when source-local cleanup or later MMIO establishes Halted. KMS001 reproduced
this. Preserve its null result and separate follow-up MMIO evidence. Blame attributes both startup-before-try sites to aa4e86ee. This
experiment leaves that reporting gap unchanged; fixing lifecycle reporting
requires separate source changes and regression coverage.

## Local worker and verification

`start-kms-source-session.sh` calls sudo -> Python script __main__:81 -> main:29
-> read_request:14 -> bounded JSON parsing. The execution route atline58 is a
fixed command for tools/run_kms_vt.py/VT3/known output, which calls openvt ->
child runner -> the C KMS fixture. Neither request values nor paths select an
arbitrary executable. Only integer duration1..720 and uint32 frame_id keys are
allowed; six runs and a thirty-minute session limit apply. The C source already
refuses frame-ID wrap attools/hdmi_pattern_kms.c:242. Unsupported dimensions,
connector/EDID, active VT and DRM-master failure remain the existing runner's
responsibility; no fallback output or geometry is introduced.

Executed locally: Python compilation, one supported request, rejected boolean
duration, duration721, negative ID, extra command key (five parser cases total),
and unprivileged worker execution rejection. These validate request routing,
not root runtime, display restoration or hardware capture. The20-second source
probe has separate real root/VT/read-only kernel snapshot and native-sync
results. Root worker normal/signal/error paths and attach003 remain unexecuted.
Existing host-only timeout SIGKILL in the VT runner is not board DMA cleanup.
No hosted CI, full software suite or physical unplug/mode-change test was run.

Graph coverage at2026-10-15T15:59:17Z reported no recorded gaps for sender.py,
sources.py and run_kms_vt.py. Operator/deploy files are excluded; full source was
read directly, and no graph completeness claim is made for their dynamic
assignment, subprocess or external SDK calls. This review does not establish
runtime correctness of unchanged code merely from unchanged call edges.
