# LiteX frame capture boundary

Date: 2026-10-15. Builds014 and016 synthesized, timed and loaded this credit
interface on PYNQ-Z2. Both selected and closed a real HDMI frame, but neither
completed downstream DMA or delivered RGB. Generated-HLS simulation now exposes
a five-pixel color-conversion tail stall; build017 tests a flushable repair.
See [physical evidence](results/2026-10-15/credit-016-hls-drain.md).
M1's ten-minute/600-frame criterion remains incomplete for this interface.

## Current single-credit interface

Generation now emits `single_credit_parked_v1`. `VideoCapture` wraps the retained
`LegacyVideoCapture` geometry/elastic-transfer implementation. Historical build
013 uses the earlier continuous-enable interface and remains a separate artifact;
its GPIO layout must never be interpreted as this credit interface.

The module defaults disabled and accepts one request toggle while idle and
enabled. It selects the next accepted SOF, latches both its accepted-SOF ID and
the synchronized native-VSYNC counter, and consumes all other source frames as
whole-frame sampling drops. One outstanding credit remains busy until software
acknowledges ownership release. The selected IDs remain immutable while busy,
including during later dropped frames. Enable alone never selects a frame.

| GPIO | Channel 1, offset 0 | Channel 2, offset 8 |
| --- | --- | --- |
| `capture_control` | Output bits 0 enable, 1 request toggle, 2 acknowledgement toggle; all 32 bits reset zero | Global observed-geometry `completed_frames` |
| `capture_counts` | Global `observed_frames` | Global `selected_frames` |
| `capture_errors` | Global `dropped_frames` | Global `invalid_frames` |
| `capture_credit` | Status bits 0 busy, 1 done, 2 failed, 3 request seen, 4 acknowledgement seen, 5 source sequence fault, 6 native pairing armed | Frozen `selected_source_id` (accepted AXIS SOF ID) |
| `capture_completion` | `selected_completed` (valid selected tail transfer plus following unselected SOF closure) | `command_errors` |
| `capture_sequence` | Frozen `selected_native_vsync_id` | `source_sequence_faults` (first sticky source-fault episode) |

DONE is asserted only after the selected frame's final output beat is accepted
**and the following unselected SOF confirms the prior frame has no extra pixels**.
The completion-policy manifest field is
`next_sof_after_selected_output_drain_v1`. A delayed orphan after the expected tail
sets a sticky fault before any successful DONE; the implementation does not rely
on the CPU being slower than malformed trailing pixels. Closure may coincide
with the final output transfer, but ACK on that edge is premature and fails.
It is **not DDR completion**: color conversion, pixel packing, VDMA and AXI write
responses remain downstream. The reader must park VDMA on its known buffer,
enable one-frame auto-halt, observe running for that transaction and subsequently
observe an error-free automatic HALTED state before invalidating/copying that
buffer. IRQFrameCount alone indicates a transfer start according to
[PG020 S2MM control](https://docs.amd.com/r/en-US/pg020_axi_vdma/S2MM_VDMACR-S2MM-VDMA-Control-Register-Offset-30h);
clearing RS can terminate an in-progress stream early. The stock PYNQ circular
reader is unsuitable: it initially requests four frames before interrupting,
selects `(activeframe + 2) % 4`, and clears certain errors before inspection.
There is no forced stale-frame discard in the new one-buffer reader contract.

After software copies the acquired sample into its independent RGB array and
releases that sample, it toggles ACK, waits for idle/acknowledgement confirmation,
then may issue another request. Sending the independent CPU copy may overlap
later capture. A request while busy or disabled, a premature ACK, or simultaneous
ACK/new-request fails closed and increments `command_errors`. A request accepted
on the same clock edge as SOF applies to a later SOF; that current frame is dropped.
Selected malformed geometry sets failed and never reports successful DONE. Orphan
pixels while enabled or busy also fail, including after ACK, and increment the
global invalid counter once per orphan episode until a new SOF. A protocol error
in a later unselected frame is reported as a later session failure; it does not
retroactively make an already SOF-closed selected frame incomplete. Partial
pixels already emitted still require DMA error/timeout recovery.

Every SOF while capture is enabled must see native-VSYNC advance by exactly one
modulo 32 bits since its predecessor. Between SOFs, native progress of zero or
one is permitted; progress of two sets a sticky missing-SOF fault. A repeated
native count at SOF is also a fault. Thus an omitted last SOF is detected by the
following native VSYNC. A completely stopped source clock requires the reader's
bounded acquisition timeout; no clock progress is invented. At shutdown, keep
the checker enabled long enough for at least two source periods to observe a
trailing omission before freezing the final evidence.

The raw native counter reaches this module through the existing four-stage Gray
CDC. In supported VGA timing VSYNC precedes active video by vertical blanking,
and the frontend FIFO is 4096 pixels, much smaller than a 307,200-pixel frame.
The native count at SOF must therefore represent that source frame; this timing
and phase assumption still requires integration/on-board evidence. Overflow,
underflow or new invalid geometry is a session failure, not a sampling-drop label.

Receiver reset while enabled **or while a credit remains busy** sets the sticky
source fault even when no frame is being selected. `receiver_reset_sync.v` captures
and stretches reset asynchronously with a four-stage XPM reset synchronizer, then
passes that level through a separate two-stage XPM data synchronizer. The gate
observes ordinary synchronized data. The chains retain vendor ASYNC_REG handling;
their recognized CDC/timing paths must be checked in the new build without broad
waivers. Disabled startup resets disarm native pairing. System reset clears the
gate and pending output; software must reject the old transaction and start a new
session rather than reuse a pre-reset ID or DMA buffer.

Hardware IDs wrap modulo 32 bits, including native pairing's delta comparison.
The reader/qualifier currently rejects wrap within a session instead of silently
reusing an ID. With no faults, resets or disabled rebaselining between selected
credits, native-ID deltas equal accepted-SOF-ID deltas. This gives exact intervening
whole-frame sampling counts; immutable identities prevent a latest-counter/DDR
slot race. It still requires the reader's actual parked-buffer completion and
ownership checks. Network ready-slot replacements remain a separate drop class.

The manifest binds the interface, parked auto-halt mode, 32-bit default-zero
control GPIO, S2MM frame-counter feature (`C_ENABLE_DEBUG_INFO_15=1` in the
integrated IP), exact gateware and reset-bridge source hashes. Missing, duplicate,
legacy-width or enabled-default HWH configurations are rejected before labeling
an artifact with this interface.

## Placement and format

`gateware/capture.py` implements a real `LiteXModule` with LiteX stream endpoints.
The implemented PYNQ seam is `frontend/video_out -> litex_capture ->
color_convert/stream_in_24`, all on the existing video AXIS clock. The frontend
provides one 24-bit pixel per transfer; these bytes are passed unchanged.
The existing PYNQ path uses BGR channel order. This block does not establish RGB
order or range: downstream color conversion must be explicit, and the PS sender
must reorder BGR to the API's RGB888 representation without gamma/range changes.

The initial suggestion to place this 24-bit block after `pixel_pack` cannot be
used if packing changes the stream width or pixel-per-transfer relationship.
The approved seam precedes that packing and conversion. Exact installed-overlay
IP versions, interface widths and clock connections are retained in each build's
paired HWH and source snapshot; runtime correctness needs separate qualification.

`s_axis_tuser`/`m_axis_tuser` are one-bit **start-of-frame** signals;
`s_axis_tlast`/`m_axis_tlast` are **end-of-line**, never end-of-frame. The fixed
640x480 default checker completes a frame after 307,200 accepted pixels, expecting
480 line endings at each 640th pixel. Constructor/generator width/height options
allow other fixed progressive geometries in 1..65535; automatic mode changes and
interlace are unsupported. Pixels before the first SOF or after the configured
frame length are orphaned and discarded. All counters wrap modulo 2^32.

## Retained geometry observer and AXI flow control

The legacy observer's internal `enable` is sampled only at an **accepted** SOF
(`tvalid && tready`), then held
for that whole source frame. Enabled frames are forwarded with a one-beat elastic
register. Disabled frames are consumed and discarded, including their SOF/EOL;
each source SOF still advances its ID and statistics. A control update during a
frame therefore takes effect at the next accepted SOF. A Verilog input has no
hardware default. In the current credit wrapper the observer's enable is driven
only by an outstanding eligible credit. The GPIO initializes to zero, records
its disabled startup baseline, then enables explicit requests.

All output data, SOF, EOL and `output_frame_id` remain stable while output VALID
is asserted and READY is low. The upstream source must likewise hold its input
signals until accepted. One register tolerates one outstanding pixel only; sustained
VDMA backpressure propagates to the video frontend. This block is **not** a frame
buffer and cannot prevent HDMI receive FIFO overrun when VDMA stalls. PYNQ frontend
overflow and DMA errors must be checked separately. Whole-frame network dropping
belongs to the bounded PS completed-frame queue; the stream gate does not convert
arbitrary mid-frame stalls into whole-frame drops.

`sys_clk` must be the same stable AXIS clock used by both adjacent endpoints,
initially the PYNQ video domain (reference 142.857 MHz). `sys_rst` is active-high
and synchronous. It clears pending output, partial geometry state, IDs, errors and
counters; pixels after reset are discarded until SOF. Use the existing domain's
synchronized reset, inverting active-low polarity if needed. Do not connect a raw
asynchronous reset or a GPIO in another clock domain directly. There is no invented
CDC: AXI GPIO control/stats must use the same video clock or gain a separately
verified request/snapshot bridge. Multiword software snapshots during active video
are not coherent automatically. Reset during a selected frame aborts DMA-visible
content; stop/reset/rearm VDMA and discard its incomplete buffer before resuming.

Generated clock/reset interface attributes associate both AXIS interfaces with
`sys_clk`/`sys_rst`. `--clock-hz` defaults to the reference design's 142857132 Hz
metadata; this is a declared clock frequency, not a timing result. Set it to the
actual integrated clock frequency and verify the Vivado block design's connections.

## Ports and statistics

Generated module: `litex_capture`; no AXI-Lite CSR bus is embedded. Control/status
are explicit wires for an integration GPIO/register layer. Stream pin prefixes are
`s_axis_` and `m_axis_`, with `tdata[23:0]`, `tvalid`, `tready`, `tuser`, `tlast`.

| Output | Semantics |
| --- | --- |
| `active` | A source frame is being observed; it may be selected or dropped |
| `frame_id[31:0]` | ID of most recently accepted SOF, first ID zero |
| `output_frame_id[31:0]` | Registered ID belonging to the current output pixel; meaningful with VALID |
| `observed_frames` | Accepted SOFs, including malformed and dropped frames |
| `selected_frames` | SOFs accepted with enable high; selection, not DMA completion |
| `dropped_frames` | SOFs accepted with enable low; intentional source selections skipped |
| `completed_frames` | Source frames reaching configured final pixel, including malformed frames |
| `valid_frames` | Configured-length pixel prefixes with expected EOL geometry, including intentionally dropped frames; this early observation does not prove absence of extra pixels before the next SOF |
| `invalid_frames` | Frames with an EOL error/early SOF, plus consecutive orphan episodes, counted once per such episode until a new SOF |
| `orphan_pixels` | Accepted pixels outside an active frame without SOF |
| `stall_cycles` | Cycles with output VALID and downstream READY low |
| `errors[2:0]` | Sticky bits: bit0 orphan, bit1 unexpected SOF during active frame, bit2 incorrect EOL |

Global counters are source observations before conversion/VDMA, not network
delivery counts. Reading the latest `frame_id` after a stock `readframe()` remains
insufficient. The credit wrapper supplies a separate frozen identity as described
above. There is no PL timestamp port; acquisition timestamps still refer to the
board monotonic clock after verified DMA completion.

### Disabled startup errors and qualification

`completed_frames` and `invalid_frames` observe both selected and dropped source
frames. A malformed frame while enable is low therefore increments the invalid
counter and sticky errors even though none of its pixels are forwarded. If an
atomic, reset-consistent counter observation has `selected_frames == 0` and no
32-bit wrap, no accepted SOF has selected a frame: the internal selected latch
starts zero and is set only by enable at SOF, and the output VALID register is
fed only by that selection. Such a disabled startup error cannot itself have
sent malformed pixels from this gate into downstream DMA. This is a routing
proof, not evidence that all other downstream state or DMA buffers are healthy.

The baseline must be captured with enable held low throughout, before enabling
selection, and counters must remain visible rather than be cleared. A later
invalid-counter increase or frontend overflow/underflow episode increase rejects
the qualification run. An unchanged invalid counter can coexist with new valid
selected frames; it does not by itself establish DMA-buffer metadata association
or full-frame ownership correctness.

The actual `m1-013-first.json` records startup invalid=1, selected=0, observed=66,
dropped=66, completed=64, then invalid=1 and selected=1387. Its startup GPIO
snapshot is explicitly non-atomic and records enable=true. Those recorded values
alone do **not** establish the required disabled-baseline ordering: the selected
read could precede a selected SOF and the invalid read follow it. If implementation
ordering proves that invalid=1 was read before any possible selected SOF, or a
separate disabled snapshot establishes it, attribution can be made with that
additional evidence. Do not infer it solely from the mixed sequential snapshot
or from exact pixels in the first delivered frame. Also, observed-minus-completed
is not a precise lost-frame count: it can include an active frame, aborts and the
time difference between separate reads.

Two focused Migen cases exercise an incorrect EOL in a completed dropped startup
frame and an early SOF abort of a dropped frame. Both increment invalid once,
forward zero startup pixels with selection disabled, then forward exactly a
subsequent valid selected frame with the persistent invalid baseline unchanged.
These tests qualify that gate behavior, not the actual GPIO snapshot chronology.

## Acceptance changes and downstream risks

Before insertion the existing frontend feeds color conversion directly. For a
well-formed stream with enable high, this block preserves every pixel and both
markers, adding one registered transfer stage and normal AXI backpressure. For
enable low it discards the complete selected source frame while continuing to
observe geometry. Enable changes cannot join portions of selected/drop frames.

Malformed input is diagnosed rather than repaired. Missing/extra EOL keeps a fixed
pixel count (an EOL never substitutes for a frame boundary); a premature SOF aborts
the earlier frame and starts a new observation. Already forwarded malformed pixels
cannot be retracted. The VDMA may see a truncated frame, bad line length or early
SOF, raise its own errors, or leave an invalid DDR buffer. Those downstream paths
have not been executed here. The sender must not expose that buffer as a valid
complete frame; VDMA error/ownership recovery and metadata association are required
before board qualification. Silent validation based only on the gate's acceptance
would be incorrect. Orphan rejection also changes the prior downstream observable
stream; the first valid SOF resumes forwarding.

No historical predecessor exists for this new module. The PYNQ frontend FIFO,
color-converter, pixel-pack and VDMA behavior are reused downstream dependencies,
not evidence that observable behavior under frame gating or malformed streams is
unchanged. Source mode change, clock loss, frontend overflow, VDMA error recovery,
forbidden HDCP/interlaced/deep-color input, GPIO CDC and board reset behavior remain
unverified in this standalone simulation.

## Reproduce

The existing sibling virtual environment was used without global installation:

```sh
../litex-network-router/.venv/bin/python -m pytest -q tests/test_gateware.py
../litex-network-router/.venv/bin/python -m gateware.generate --output artifacts/litex_capture.v
```

`gateware/dependencies.json` pins upstream Git revisions, package versions and a
SHA256 over sorted installed Python sources (relative path, NUL, bytes, NUL).
Both source checkouts were clean when recorded. Generation rejects installed
package version/hash drift and emits RTL/source hashes plus dependency provenance
to `artifacts/litex_capture.json`; generated artifacts are ignored by Git. To
recreate a separate environment, install Migen and LiteX from those exact Git
revisions and pytest, then run these commands; do not substitute unpinned latest
packages. Python 3.12 was used. Icarus Verilog is needed for the compiled test;
its absence causes an explicit pytest skip, not a passing compiled result.
Host-only environments without Migen/LiteX explicitly skip this test file; run the
separate pinned gateware environment to obtain the simulation evidence above.

Latest result: **62 passed in 5.85 seconds**, zero skips, for
`tests/test_gateware.py hardware/test_build_manifest.py`: 45 gate cases (44 Migen
and one compiled RTL) plus 17 manifest/HWH cases. The retained legacy cases
check exact pixels/SOF/EOL/IDs, stalled-output stability, stop/restart selection,
all six early/missing EOL positions in a 3x2 frame, orphan/early-SOF recovery,
invalid counting, 1x1 frames and forbidden dimensions. The compiled generated
default RTL case checks four actual 640x480 frames (1,228,800 input pixels), two
selected complete outputs, two complete drops/closure frames, deterministic VDMA-side stalls and
synchronous reset during a partial frame. Credit tests additionally exercise
default disabled selection, immutable identity through dropped frames, command
collisions/premature acknowledgement, all selected EOL failures, early SOF abort,
native mismatches, trailing missing-SOF detection, enabled/busy receiver reset,
final-output stall/next-SOF closure, delayed overlong-frame faults, same-edge
closure/ACK priority and modulo-32 identity wrap. This establishes the
module's simulated handshake and geometry behavior, not runtime correctness of
its PYNQ integration.

The vendor XSIM reset-bridge test uses the actual XPM models and generated gate:
it passes stopped-clock 40 ns pulse retention, two-stage data observation,
six-edge release and sticky gate fault. Assertions remain enabled. The source
pulse width in that simulation is explicit; it is not analog minimum-pulse timing
qualification. XSIM elaboration retains its environment `LIBRARY_PATH` warning
and a testbench unconnected stream-output warning; neither was suppressed. New
CAD CDC/timing and board tests remain required before qualifying this credit ABI.
