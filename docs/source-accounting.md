# Single-credit capture accounting

Status: implementation authorized; hardware validation pending. Legacy build013
and the M0 PYNQ source remain separate evidence and retain unknown DMA-associated
source IDs. This design must not reinterpret their GPIO registers as the new ABI.

## Why the existing PYNQ reader cannot supply exact IDs

The exact installed PYNQ 3.0.1 `dma.py` SHA256 is
`94346a4ae6a7a7f9e4b78887179e2a55ff821c7ed3724b584a7bb4c228fea30f`.
Its `S2MMChannel.start()` (lines 272–291) starts a four-store circular channel and
sets interrupt threshold 4 to initialize all stores. `readframe_async()`
(189–199) waits for a frame interrupt then calls `_readframe_internal()`
(151–164), which returns store `(activeframe+2)%4`, replaces that store's address,
and invalidates the returned array. `activeframe` (202–209) also clears status
bits. The documented first read after a pause can be stale; the current sender
discards its initial acquisition. The
[pinned upstream source](https://github.com/Xilinx/PYNQ/blob/v3.0.1/pynq/lib/video/dma.py)
matches the inspected installed file.

A single credit added to that reader can leave its startup threshold unsatisfied,
and its selected store is not identified by the gate's latest completed ID. Four
dummy startup credits and a guessed ring offset do not prove association. Neither
ring-slot index nor completion time alone establishes which source frame the
returned bytes contain. The new path therefore uses a known parked store and a
custom completion reader, with no stock ring rotation or initial discard.

## Completion proof and register assumptions

The primary specification is AMD AXI VDMA v6.3 PG020, 2022-06-08. Importantly, its
interrupt-count text describes a count associated with frame transfer starts;
an IRQ alone is not the chosen DDR-completion proof. `FrameCntEn=1` makes the
channel halt after the configured frame count has completely transferred.
Software must first observe running, then require auto-HALTED and the selected
gate completion token. [S2MM control register](https://docs.amd.com/r/en-US/pg020_axi_vdma/S2MM_VDMACR-S2MM-VDMA-Control-Register-Offset-30h).

The required frame-counter feature is
`C_ENABLE_S2MM_FRM_COUNTER` (legacy generated name `C_ENABLE_DEBUG_INFO_15`),
not MM2S's debug 7. Build 013 HWH and generated synth wrapper set debug 15=1;
installed Vivado 2025.2 `axi_vdma_v6_3_rfs.vhd:18654` enables the corresponding
S2MM control path. The next artifact must declare and verify this feature, then
read back the control bits before any credit. [PG020 hidden parameters](https://docs.amd.com/r/en-US/pg020_axi_vdma/Additional-Design-Information).

Proposed programming values for a 640x480 RGB888 frame are:

| Register | Requirement |
| --- | --- |
| `0x28 PARK_PTR_REG` | S2MM parked reference 0, preserving unrelated fields |
| `0x30 S2MM_VDMACR` | `0x00015011`: count 1, frame/error IRQ enables, FrameCntEn, RS; circular/genlock disabled |
| `0x34 S2MM_VDMASR` | Read raw before any W1C; error mask `0xC9F0` must be zero; completion requires HALTED bit 0 plus recorded frame-IRQ bit 12 |
| `0xAC..0xB8` | Four valid addresses, all pointing at the one owned buffer; park0 is checked |
| `0xA8 STRIDE` | 1920 bytes |
| `0xA4 HSIZE` | 1920 active bytes |
| `0xA0 VSIZE` | 480; write last to commit/start programmed transfer |

The control write sequence explicitly reloads count before each arm. The address,
size, park and control readbacks are checked before granting a frame. Initial
HALTED is not completion: the reader requires a running transition for that
request. The error mask includes internal/slave/decode, early/late SOF/EOL, and
error-IRQ status; no use is made of PYNQ helpers that silently clear those errors.
[Status bit definitions](https://docs.amd.com/r/en-US/pg020_axi_vdma/S2MM_VDMASR-S2MM-VDMA-Status-Register-Offset-34h),
[programming order](https://docs.amd.com/r/en-US/pg020_axi_vdma/Programming-Sequence),
[parked store](https://docs.amd.com/r/en-US/pg020_axi_vdma/PARK_PTR_REG-Park-Pointer-Register-Offset-28h).

These register assumptions require IP simulation/readback and physical validation.
On a timeout or reset, the selected frame is rejected; cooperative stop must
establish HALTED before freeing native memory. A failed halt preserves native
references and invokes the CLI's indefinite safety hold, without forced kill.

## New hardware/software ABI

Manifest `capture_interface=single_credit_parked_v1`,
`vdma_completion_mode=parked_frame_count_halt_v1`,
`vdma_frame_counter_enabled=true`, and
`gate_completion_policy=next_sof_after_selected_output_drain_v1`. The control GPIO is 32-bit and resets to 0.
Software must reject missing/legacy ABI or mismatched artifact hashes.

| GPIO | Channel 1 / offset 0 | Channel 2 / offset 8 |
| --- | --- | --- |
| `capture_control` | bit 0enable,bit 1request-toggle,bit 2ACK-toggle | existing global completed count |
| `capture_credit` | bit 0busy,1done,2failed,3request-seen,4ACK-seen,5source-sequence-fault,6native-armed | latched accepted-SOF source ID |
| `capture_completion` | selected output-completed count | forbidden-command count |
| `capture_sequence` | selected native-VSYNC ID | sticky source-sequence fault count |

There is one outstanding credit. Request recognition in IDLE moves to WAIT; a
simultaneous SOF remains unselected. The next accepted SOF latches both IDs and
selects one complete frame. All other source frames continue through accounting
and are dropped whole. DONE is published at the next accepted unselected SOF after the selected
final pixel's output handshake, proving no trailing geometry violation; this is stream completion before color-conversion/packing and
does not itself imply DDR completion. IDs remain immutable until valid ACK.

Software waits for DONE, expected selected-completion count, error-free DMA
auto-HALTED, and healthy source accounting. It invalidates the known buffer,
copies RGB, rechecks faults, then releases the lease and sends ACK. It waits for
ACK-seen and IDLE before another arm/request. Request while busy, premature ACK,
malformed selected frames, source reset/fault, timeout, and ID wrap end the session.
One native allocation is reused as an object, without PYNQ pointer-cache reuse.
The network sends independent immutable RGB copies; slow TCP never owns the DMA
lease or pauses the native source.

Acquisition is paced before issuing credits, at the requested capture rate.
The native HDMI/frontend still runs continuously; PL intentional drops account
for unselected source frames. The existing software acquisition-level sampling
and startup discard are disabled specifically for this ABI to avoid duplicate
skip accounting and discarding the first exact buffer.

## Upstream source-loss proof

The gate latches the already synchronized native-VSYNC count at every accepted
AXI SOF. After startup pairing, consecutive SOFs require native delta 1; between
SOFs, an advance of 2 or more is a sticky fault detecting a missing trailing SOF.
Receiver reset while capture is enabled is also a sticky fault. Native clock
inactivity is handled by a bounded read/watchdog, not relabeled intentional
sampling. Sequential GPIO native/observed comparisons with lifetime ±1 tolerance
are insufficient because they can hide a permanently missing frame.

Startup baseline is taken while gate disabled, no selection, and DMA halted;
it must use a new truthful sample point, not legacy `after_dma_start`. Native
pairing/fault proof is checked before the first credit. The completed identity is
coherent because it is held through DONE and bracketed status reads, while global
free-running counter snapshots remain explicitly non-atomic. End-of-session
evidence must cover the trailing missing-SOF watchdog interval before disabling
the source proof. Native/SOF loss and selected-buffer association are distinct
checks, both required for full source accounting.

## Metadata and validation

`source_sequence` is the selected native-VSYNC ID; `frame_source_id` is the
selected accepted-SOF ID. Both are 32-bit and wraps/resets terminate the UUID
session. `source_sequence_domain=native_vsync_edge_counter`;
`source_sequence_policy=reject_wrap_or_reset`.

`source_accounting` records ABI, parked auto-halt mode, slot 0, raw DMA status,
coherent held identity, credit busy/DONE/failure flags, source fault/arming flags,
command errors, selected-completion total, acquired-frame total, first acquired
native ID, and the cumulative intentional native-ID gaps after that first frame.
`intentional_skips_since_previous` refers to the previous acquired frame, not
the previous delivered frame. It is null for the first acquisition. The first
selected accepted-SOF ID supplies a separate startup unselected-SOF count;
startup native-frame skips remain explicitly unknown because the baseline can
be inside the VSYNC→SOF interval. Startup errors/counts are preserved.

Across delivered frames, exact reconciliation is
`native_id_delta = acquired_total_delta + intentional_sampling_total_delta`.
Network-ready drops appear as an acquired-total gap and remain separate from
intentional unselected source frames. A new counter snapshot cannot replace this
latched identity relation. Qualification must require the new provenance and
completion/fault proofs; legacy records remain incomplete source accounting.

## Implemented dispatch and local evidence

Use `--source litex-credit` for the new ABI. `--source litex` rejects credit
artifacts before loading; the credit adapter rejects legacy or incomplete
manifests before programming. M0 remains `--source pynq`. The new source reuses
one allocation with no pointer cache, circular reader, initial discard, or
acquisition-level software sampling. CPU RGB copies and TCP remain independent.

Each delivered credit records `source_skips` as the cumulative intentional native
sampling gaps after the first acquired identity. Startup native skips are unknown.
`source_invalid_frames=0` means no new invalid episode after the retained disabled
baseline. `source_overruns=0` requires the no-overwrite single-credit ownership
invariant and zero frontend overflow/underflow deltas; it is not a generic
unsupported-driver zero. Global register counts remain non-atomic.

The new shutdown checks source health for 50 ms and at least two native edges
before disabling capture, then clears RS and polls raw HALTED with a deadline.
It bypasses the stock driver's unbounded stop loop. Failure retains the native
allocation and source handles and enters the CLI process-lifetime safety hold;
there is no forced kill. The final source-proof record is emitted separately
from DMA halt diagnostics.

Focused fake-MMIO tests exercise start IRQ before completion, stale HALTED, all
raw error-mask bits before clear, HALTED before delayed gate closure, immutable
leases/ACK, exact native/SOF gaps, reset/repeat/wrap rejection, integrity faults,
startup ordering, halt timeout/MMIO failure retention, and release after halt.
These local tests establish software dispatch/control flow, not actual VDMA
auto-halt behavior, receiver CDC correctness, or hardware qualification. The
running transition before source SOF remains a physical readback requirement;
it must not be weakened to accept initial stale HALTED if the IP behaves
differently.

## Free-run DMA candidate after build014 failure

The first build014 board run selected and SOF-closed one frame, but VDMA remained
running with status0x10000, no frame IRQ, and zero acquisitions. It halted safely
only during explicit abort/cleanup; that abort is not completion evidence.
Build015 changes only the per-channel S2MM synchronization option to free-run,
while the LiteX gate, fixed parked buffer and strict auto-halt proof remain.
Fresh HLS and CAD are being rebuilt; board behavior is unverified.

Manifest and producer now require `vdma_fsync_mode=free_run` and paired HWH
`C_USE_S2MM_FSYNC=0`, checked before programming. The generated legacy combined
`C_USE_FSYNC` field stays1 even with the actual per-channel mode0. Vendor6.3_24
RTL69143 derives S2MM selection directly from the per-channel parameter; it does
not derive it from that legacy field. Requiring combined0 would reject the real
supported candidate, so this incorrect packaging-only check was removed. The
initial snapshot validator was preserved, and its correction was recorded while
CAD continued; generated IP/RTL and constraints were unchanged by that correction.

The supported and rejected synchronization classes are covered by source and
manifest tests. Metadata must also identify free-run mode. The qualifier still
requires error-free automatic HALTED, frame IRQ, held source identity and strict
next-SOF closure; it never substitutes manual stop. Existing legacy paths retain
their original semantics. The latest broad test run was300passed/1optional skip
before this legacy-field guard correction; the corrected19manifest and5source
mode tests pass. New bitstream and physical correctness remain pending.

## Isolated-frame HLS drain requirement

Build016/v10 reached real HDMI but again timed out with one completed gate
credit and no DMA completion. The generated color_convert RTL retained five
pixels after the final input, as reproduced independently of the VDMA with the
actual HLS pair. Continuous legacy input masks that defect by advancing the
pipeline with the next source frame. A gate DONE only establishes transfer to
the converter and therefore cannot substitute for native DMA completion.

The build now changes only the isolated pinned color_convert C++ copy from
`pipeline II=1` to `pipeline II=1 style=flp`. The converter keeps its matrix,
register map and AXIS interfaces; pixel_pack and source acceptance stay intact.
The new `scripts/check_hls_drain.py` requires Icarus (`iverilog` and `vvp`) and
simulates both actual generated HLS modules before Vivado project generation.
It writes the identity matrix over AXI-Lite, checks every color pixel and packed
byte plus SOF/EOL, and requires full drain without any following input. Small
and640x480 isolated frames run with and without input bubbles/output backpressure;
output must remain stable while stalled. Missing modules, simulation failures
and timeouts reject the build. Other packing modes, nonidentity coefficient
matrices and malformed HLS input are unverified by this particular test; the
separate gate tests cover malformed geometry before these HLS blocks.

Before the change the32-pixel regression fails at27 converter pixels; source
pixels and boundaries already transferred by the gate stay stranded downstream.
After the change, only generated-RTL test results may establish drain behavior;
physical exactRGB and automatic DMA halt still require board execution. No
manual-stop completion, weakened DMA proof or new data dummy frame is allowed.
See [before/after evidence](results/2026-10-15/credit-016-hls-drain.md).
