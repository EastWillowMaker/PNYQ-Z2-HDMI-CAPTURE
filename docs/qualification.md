# Sustained HDMI qualification

Run only after the external optical pattern and authorized board sender are
already running. This tool neither changes the source nor loads an overlay.
It compares every received pixel against `tools/hdmi_pattern.py` using the
independently encoded optical ID on every row. It never learns a golden image.

```sh
.venv/bin/python tools/qualify_capture.py BOARD_ADDRESS --port 9020 \
  --duration 600 --min-frames 600 --min-fps 1 --hard-deadline 660 \
  --require-litex --log docs/results/RUN/frames.jsonl \
  --summary docs/results/RUN/qualification.json \
  --save-endpoints captures/RUN
```

Create `docs/results/RUN` beforehand. JSONL and summary files must be new;
the optional endpoint directory must also be new. Endpoint saving is opt-in.
Use `--no-require-litex` solely for a labelled M0 baseline qualification.
Synthetic-origin metadata is rejected for both scopes.

M1 additionally requires `litex_counters` and `litex_startup_counters` snapshots:
observed uint32 `frontend_overflow_episodes`, `frontend_underflow_episodes`,
`native_vsync_edges` and `invalid_frames`, explicit overflow episode units,
and the sender's fail-stop integrity policy. Source-health provenance must
include its SHA256, FPGA-load counter lifetime, overflow-episode units and
shared per-clock receiver reset policy. Missing/null health values (including artifact 009) fail M1
even when all RGB pixels match. The sender must verify manifest and paired HWH
capture-enable reset defaults are zero, report `capture_enable_reset=0`, and
hold capture disabled throughout the complete startup snapshot. That snapshot
must report `enabled=false`, `selected_frames=0`, and sample point
`sequential_gpio_reads_after_dma_start_before_capture_enable`, with integrity
policy `disabled_zero_selected_baseline_then_stop_on_integrity_change`.

A nonzero startup invalid-frame count is accepted only with every one of those
proof conditions. It remains in metadata and the summary as
`startup_invalid_frames`; it counts unselected input before capture enable.
The RTL counts geometry errors on selected and unselected frames. The focused
[gate tests](../tests/test_gateware.py) demonstrate malformed input while held
disabled produces zero output pixels, followed by only the complete valid
frame after enabling. This is a conditional startup exception, not a waiver
for corrupted capture. The original after-enable, non-atomic 013 baseline
does not establish these conditions and its rejected report remains rejected.

Startup overflow and underflow counts must be zero and remain disclosed.
Any new invalid-frame, overflow or underflow episode after the disabled
baseline fails qualification. Native VSYNC counter rollback, including wrap,
also fails. Overflow/underflow episodes are not lost-frame counts and are not
associated with a delivered buffer. Artifact 009 was transferred only, never
loaded; it is not hardware evidence.

Default limits require **both** at least 600 seconds of observation and 600
distinct exact optical frames, at least one distinct exact frame/second, zero
pixel failures, zero mixed frames, zero optical repeats, zero metadata
rejections and zero transport errors. The 660-second hard deadline always
bounds reading; incomplete data at that deadline is reported separately.
Shorter parameters are available for tool tests and bring-up, and are recorded
in the report; they cannot establish the default ten-minute contract.

Every complete frame gets a flushed JSONL record containing original metadata
and full analytic verification. Pixel failures count and remain in the log;
the tool keeps reading until the bounded completion conditions. Parser/CRC,
EOF and timeout failures terminate the connection and become error records.
Synthetic or baseline-only metadata terminates M1 qualification after logging
the received frame. A successful result exits 0; failed qualification exits 1;
invalid arguments/output setup exits 2.

The summary distinguishes transport IDs, gaps, unique exact optical IDs,
repeats, mixed frames, bad pixels, payload goodput, delivered FPS and distinct
exact FPS. Original first/last metadata retains session IDs and all cumulative
source counters. Unknown physical DMA sequences stay unknown. LiteX counters
are sequential, non-atomic status snapshots without per-frame association;
the runner does not infer exact hardware frame ownership from them. Pattern
exactness and metadata alone do not replace bitstream provenance, board timing,
source-mode verification, CPU/memory measurement or interruption tests.

The summary records `host_start_monotonic_seconds` and `host_clock`; each
frame records `host_received_monotonic_seconds` before pixel verification.
Optical IDs can match these receipts to source generator events on the same
host clock, yielding generation-to-receipt intervals. Such intervals include
display scheduling and buffering; they are not HDMI wire latency. Board
timestamps use another clock and cannot be subtracted from these host times.

For a deliberate brief gate check on an already running board sender,
`tools/board_gate_smoke.py BITFILE MANIFEST` attaches only to GPIO, disables
capture for half a second, then restores enable in a `finally` block and records
sequential before/disabled/enabled counters. This changes hardware behavior;
run it only in the authorized test session and outside the sustained window.
It is not a physical source-disconnect test. A killed process cannot execute
`finally`, so do not force-terminate the probe while disabled.

`tools/board_resources.py PID --count 130 --interval 5` records read-only
process CPU/RSS and board memory/CMA samples on the board. CPU percentage uses
one core as 100%; observations are sampled rather than true peak measurements.
The sampler stops on process exit and rejects PID reuse.
