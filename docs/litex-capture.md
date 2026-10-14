# LiteX frame capture boundary

Date: 2026-10-15. Evidence: Migen handshake simulation and compiled generated
Verilog simulation. This component has not been synthesized, timed, programmed,
or measured on PYNQ-Z2. It does not satisfy the M1 ten-minute/600-frame criterion.

## Placement and format

`gateware/capture.py` implements a real `LiteXModule` with LiteX stream endpoints.
The proposed PYNQ seam is `frontend/video_out -> litex_capture ->
color_convert/stream_in_24`, all on the existing video AXIS clock. The frontend
provides one 24-bit pixel per transfer; these bytes are passed unchanged.
The existing PYNQ path uses BGR channel order. This block does not establish RGB
order or range: downstream color conversion must be explicit, and the PS sender
must reorder BGR to the API's RGB888 representation without gamma/range changes.

The initial suggestion to place this 24-bit block after `pixel_pack` cannot be
used if packing changes the stream width or pixel-per-transfer relationship.
The approved seam precedes that packing and conversion. Exact installed-overlay
IP versions, interface widths and clock connections still require build validation.

`s_axis_tuser`/`m_axis_tuser` are one-bit **start-of-frame** signals;
`s_axis_tlast`/`m_axis_tlast` are **end-of-line**, never end-of-frame. The fixed
640x480 default checker completes a frame after 307,200 accepted pixels, expecting
480 line endings at each 640th pixel. Constructor/generator width/height options
allow other fixed progressive geometries in 1..65535; automatic mode changes and
interlace are unsupported. Pixels before the first SOF or after the configured
frame length are orphaned and discarded. All counters wrap modulo 2^32.

## Selection, AXI flow control and reset

`enable` is sampled only at an **accepted** SOF (`tvalid && tready`), then held
for that whole source frame. Enabled frames are forwarded with a one-beat elastic
register. Disabled frames are consumed and discarded, including their SOF/EOL;
each source SOF still advances its ID and statistics. A control update during a
frame therefore takes effect at the next accepted SOF. A Verilog input has no
hardware default: standalone transparent operation requires enable high. The
qualified integration instead initializes the control GPIO to zero, records its
disabled startup baseline, then explicitly sets enable high for capture.

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
| `valid_frames` | Completed source frames with expected EOL geometry, including intentionally dropped frames |
| `invalid_frames` | Started frames with at least one EOL error or aborted by another SOF, counted once per frame |
| `orphan_pixels` | Accepted pixels outside an active frame without SOF |
| `stall_cycles` | Cycles with output VALID and downstream READY low |
| `errors[2:0]` | Sticky bits: bit0 orphan, bit1 unexpected SOF during active frame, bit2 incorrect EOL |

Counters are source observations before conversion/VDMA, not network delivery
counts. `frame_id` does not yet prove which frame occupies which DDR buffer.
The integration must associate a DMA completion/buffer with an atomic SOF metadata
record; reading the latest counter after `readframe()` is insufficient. There is
no timestamp port yet. Consequently source skip counts, source timestamps and
DDR frame ID assignment remain unqualified end to end.

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

Observed result: **17 passed in 2.98 seconds**, zero skips, using Icarus Verilog
12.0 for the compiled case. Sixteen Migen cases
check exact pixels/SOF/EOL/IDs, stalled-output stability, stop/restart selection,
all six early/missing EOL positions in a 3x2 frame, orphan/early-SOF recovery,
invalid counting, 1x1 frames and forbidden dimensions. The compiled generated
default RTL case checks three actual 640x480 frames (921,600 input pixels), two
selected complete outputs, one complete drop, deterministic VDMA-side stalls and
synchronous reset during a partial frame. This establishes the module's simulated
handshake and geometry behavior, not runtime correctness of its PYNQ integration.
