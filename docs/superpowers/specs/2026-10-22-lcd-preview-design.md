# Gateware HDMI preview on the Waveshare LCD C

Status: proposed full design. On 2026-10-22 the user authorized a quick demo
instead, with FPS and milliseconds explicitly not completion gates. The simpler
single-buffer demo is separate from this full design; the performance and optical
acceptance criteria below are retained as historical proposals, not demo gates.
Accepted requirements are recorded in [the interview](../../requirements.md#lcd-preview-design-interview-2026-10-21).
Architecture and numeric defaults identified below are implementer choices,
not additional user answers. This document describes a project requiring a
written implementation plan, gateware integration and physical qualification.

## Intent and accepted behavior

Show the live PYNQ-Z2 HDMI input on the attached Waveshare 3.5inch RPi LCD (C).
Gateware scales pixels and sends SPI commands/pixels. Software may initialize
and configure devices, allocate buffers and supervise mode changes; it must not
process pixels, submit each frame or feed each frame's SPI transactions.

LCD preview and PC capture operate simultaneously. PC RGB888 pixels, buffer
ownership, API and loss/error reporting retain their existing contract. The LCD
uses RGB565 and may independently skip complete source frames to stay current.
Each uploaded image must derive from one complete valid source frame. Occasional
panel scanout tearing is allowed; mixing source images within an upload is not.

Preserve the entire image and aspect ratio. At each input-resolution change,
compare 0-degree and 90-degree fits and select the larger occupied area. Retain
the previous orientation on ties; initially prefer landscape. A fixed mounting
may show a sideways image. Center the fitted image and make the remaining pixels
black, distributing any odd border pixel to the bottom/right. Integer dimensions
approximate the source ratio to the nearest feasible pixel without cropping.
For the accepted landscape inputs, VGA fits about 427x320 and 1080p fits 480x270.

Initial input profiles are progressive RGB 640x480 near 60Hz (25.175/25.2MHz)
and 1920x1080p30 (74.25MHz). Existing 1080p evidence is a controlled HDMI loop;
arbitrary external-source compatibility needs testing. 1080p60, other timings,
interlace, touch UI and new PC transport features are excluded.
See the existing [VGA qualification](../../results/2026-10-16/m1-completion.md)
and [1080p30 qualification](../../results/2026-10-17/1080p30-completion.md).

The initial target remains 30 new displayed images/s and at most 100ms
source-to-visible latency, subject to feasibility. Duplicate images cannot count
as new updates. A slower verified result must be reported as a target shortfall,
not silently accepted as completion.

## Proposed data path

Tap the unpacked 24-bit receiver stream before the single-credit capture gate.
Keep the existing capture arm intact. The preview arm must never add backpressure
to that arm: admit at a source-frame boundary only when resources are available;
otherwise consume/discard the entire preview frame. On preview FIFO overflow or
malformed geometry, invalidate that frame and resynchronize at a subsequent SOF.
Observe actual upstream transfers, not repeated valid samples during a stall.
Shared receiver stalls remain a system constraint to qualify under PC load.

Use a separable fixed-point bilinear scaler as the implementer's first choice.
It offers modest line storage and interpolated edges; it is not a full area
antialiasing filter, so fine 1080p textures may still shimmer. Keep intermediate
color precision through interpolation, then round/clamp and pack RGB565 on the
LCD arm only. Use deterministic coordinate mapping and a software reference for
verification, including first/last pixels and odd fit dimensions. Exact arithmetic
widths, pipelining and line-buffer organization belong to the implementation plan.

Use LCD address-mode rotation so gateware emits sequential rows in the selected
logical orientation. Change address mode/window only at an upload boundary;
clear borders whenever geometry changes. The physical SPI path uses the confirmed
header pins, 16-bit command/parameter words and 16-bit RGB565 pixel words.

## Frame ownership and memory

The implementer proposes three full-panel buffers in PS DDR (921,600 bytes total).
Two buffers can isolate upload/render ownership, but a third permits a completed
ready frame to coexist with both operations and makes freshness policy explicit.
BRAM holds line buffers and bounded burst FIFOs, not full-panel snapshots.

Gateware owns transitions between FREE, RENDERING, READY and UPLOADING. There is
at most one rendering buffer, one uploading buffer and one ready frame. Validate
source EOF, geometry and health, and wait for all DDR write responses before
publishing READY. At publication, discard an older READY frame if present. The
SPI reader claims the latest READY frame and keeps its storage immutable until
the final pixel transfer completes. If no buffer is free at source SOF, skip
that source frame. Never overwrite a buffer owned by the reader or writer.

Each buffer carries source-frame identity, source SOF timestamp, geometry and a
configuration generation. Mode changes invalidate old READY/RENDERING frames;
old transfers must be drained or canceled safely before reusing memory. Software
allocates DMA-accessible contiguous buffers once and programs bounds/addresses.
It neither copies nor schedules their per-frame contents. Shutdown must prove
all DMA stopped before freeing memory. Invalid addresses/lengths, AXI errors and
DMA timeouts disable the affected preview operation and report a fault.

Add PL DDR write/read masters and arbitration appropriate to the existing PS
configuration; the current VDMA only writes PC capture. Port choice, burst sizing,
CDC FIFOs and interconnect configuration are builder decisions supported by
bandwidth and timing evidence. Pixel payload at 30Hz is 9.216MB/s; writing and
reading that payload costs at least 18.432MB/s, excluding AXI overhead and any
rendered frames later skipped. Admission must be paced to the preview budget.

## SPI, clocks and recovery

Start physical qualification at a conservative clock and increase it only with
constraints, routed timing and display evidence. 100MHz is a candidate, not a
guarantee. Full-panel RGB565 payload requires 73.728Mbit/s at 30Hz; at 100MHz an
upload needs 24.576ms before commands/gaps. Waveshare's advertised 125MHz and its
driver setting do not qualify this board's electrical path. Maintain explicit
clock-domain crossings and external timing constraints; derive clocks with
FPGA clocking resources rather than an unconstrained fabric clock.

The SPI engine owns CS, D/C, reset and transaction serialization. Software init
commands and status requests use a control interface arbitrated against pixel
uploads. A small gateware pattern/text generator produces black status screens
with white "No signal", "Unsupported mode" or "Preview fault" text; no CPU
framebuffer rendering is needed. Keep the display/watchdog domain running when
the recovered HDMI clock stops.

Proposed recovery defaults: declare missing input after 100ms without valid frame
progress, finish or safely abort an in-flight upload, then replace stale video
with status within a further 150ms at the qualified SPI rate. A signaled
unsupported timing displays its corresponding status. Resume preview after three
consecutive valid frames in a supported profile and successful bounded receiver
configuration. Receiver reconfiguration is a software control-plane operation,
not per-frame processing. Set a 2s recovery objective after stable supported input;
measure it separately from normal frame latency.

Do not silently restart a failed PC capture session. Shared receiver changes must
first stop/quiesce its DMA under the existing ownership contract; notify the PC
of signal/mode failure and retain its explicit restart behavior. Preview may
recover automatically once shared hardware is safe. A slow or disconnected PC
must not prevent preview progress. HDCP/unsupported source formats remain outside
the accepted input contract and must not be mistaken for supported video.

## Qualification and known evidence

The [slow SPI probe](../../lcd-spi-smoke.md) completed 153,600 pixel writes and
the user confirmed the full pattern/colors. It took 58.806s to draw using
MicroBlaze GPIO. LCD readback is not exposed; idle touch ADC samples do not
verify display data or functional touch reads. No high-speed result follows
from that test. The base overlay remains loaded after the probe.

Use simulation to compare scaling/pixel order with the reference and exercise
frame skips, stalls, malformed lines, mode changes, buffer contention, memory
errors, CDC/reset and loss of input clock. Check RGB888 PC output remains exact
with preview enabled and disabled. Simulate SPI command/parameter framing,
window/rotation and full-frame upload identity. Then require synthesis, routing,
timing, CDC and relevant DRC checks before hardware deployment.

Proposed physical acceptance is a ten-minute run for each accepted input profile,
with independent source identities, simultaneous PC capture at its existing
qualified rate, and at least 30 new complete LCD uploads/s on average. Record
per-second rate and worst update gap; averages do not prove smooth cadence.
Use moving markers, fine text/checkerboards and colors to expose ordering,
scaling and signal-integrity problems, plus source loss/reconnect and unsupported
timing tests. Report all skips, invalid frames, overruns and failed attempts.

Preserve the 100ms optical requirement: measure source-frame start to the last
visible pixel belonging to that update with synchronized source markers and an
optical instrument/camera of sufficient time resolution. Record instrumentation
and uncertainty. Source SOF to final SPI bit is a useful separate digital latency
metric but cannot substitute for visible latency or panel response. Availability
of optical measurement equipment is currently unknown; absence leaves that
requirement unverified. Report the worst observed latency over tested samples,
not a universal guarantee.

Read in this order: accepted requirements, this architecture/ownership contract,
[existing capture integration](../../build.md), then the SPI probe evidence.
Existing source integration points are `hardware/capture.tcl`,
`gateware/capture.py` and `src/hdmi_capture/sources.py`. Full architecture remains
subject to resource, bandwidth and physical timing checks. If 30Hz or 100ms cannot
be met, present the measured constraint and alternatives to the user before
changing the target, display or image contract.
