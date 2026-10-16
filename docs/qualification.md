# Sustained HDMI qualification

The [fixed-mode M1 completion report](results/2026-10-16/m1-completion.md)
combines normal019's600s criterion with held-buffer015, clean-source023,
physical024, restart025 and timing021 evidence. Failed capture012 and observation attempts020/021
retain their original verdicts in dated reports. A pixel criterion alone
still does not establish all M1 obligations.

Run only after the external optical pattern and authorized board sender are
already running. This tool neither changes the source nor loads an overlay.
Its `passed` and CLI exit status describe the sustained delivered-image
criterion, with source-accounting checks required in the default LiteX mode.
`criterion_passed` is an explicit alias;
`full_m1_qualification=false` and `unmet_m1_requirements` are conservative
per-run fields; this tool does not discover external hardware evidence. Use
the aggregate report to reconcile the separate qualification obligations. A successful pixel run
alone must not be reported as full M1 completion.

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

Default `--require-litex` runs require the `single_credit_parked_v1` accounting
ABI; legacy 013 metadata with unknown source sequence is rejected even when
every pixel matches. To reproduce the historical delivered-image criterion,
add `--legacy-delivered-image-criterion`. That explicit mode omits accounting
validation, labels the scope as legacy, and leaves accounting and full M1
unverified. It does not reclassify old evidence as a formal accounting run.

For the new ABI, each frame must report a held, coherent completed-credit
identity matching both top-level `source_sequence` (native VSYNC counter) and
`frame_source_id` (accepted AXIS SOF counter). The parked DMA must have
auto-halted on slot zero, with raw status HALTED and frame IRQ set and all
`0xC9F0` error bits clear; frame IRQ by itself is insufficient. The buffer must
stay stable until release, credit busy/done must remain true, and failed,
command-error and source-sequence-fault indicators must remain clear. Native
pairing must be armed, with explicit 32-bit identities and a reject-wrap/reset
policy. Producer ownership, release/ACK and frozen-status bracketing establish
the association claim; the host validates the resulting metadata invariants.

The acquired total, completed-credit count and acquisition ID must agree.
From the first acquisition onward, native sequence advancement must equal
acquired frames plus cumulative intentional source sampling skips. Between
received endpoints the same equation holds, even when complete acquired
frames were omitted by the sender. The per-acquisition skip field is compared
directly only for adjacent acquisitions; it is not misread as a host delivery
gap. Native and accepted-SOF identities must retain a constant offset, as
required by the armed source-pairing fault check. First-acquisition native and
SOF identities stay constant throughout a session. Native startup skips remain
explicitly unknown at the phase boundary, without substituting accepted-SOF
counts. No wrap, reset, session change or inconsistent total is accepted.

Public `counters.source_skips` must equal the cumulative native intentional
sampling total after the first acquisition. It is distinct from the legacy
software `intentional_sampling_drops` counter. Public `source_invalid_frames`
must be zero relative to the disabled startup baseline; startup invalid input
is disclosed separately. Public `source_overruns` must be observed zero under
the single parked-buffer/no-next-credit-before-release contract and clean
frontend monitors. Null or conflicting public counters fail default formal
validation. These conditional zeros are not retroactively applied to legacy
013 metadata.

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
`before_first_credit_while_gate_disabled_dma_halted`, with integrity
policy `single_credit_parked_auto_halt_fail_closed_v1`. The explicit legacy
criterion instead uses startup sample point
`sequential_gpio_reads_after_dma_start_before_capture_enable` and also accepts
`disabled_zero_selected_baseline_then_stop_on_integrity_change`.

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
source counters. `source_accounting_metadata_validated` and
`source_accounting_received_window` report the checked single-credit metadata
and the reconciled received window. `physical_source_sequence_verified` and
`full_m1_qualification` remain false: arithmetic metadata checks are not
independent hardware proof. Native startup skips stay unknown. Global LiteX
counters remain sequential, non-atomic snapshots; the held credit identity
tuple uses its separate coherence/ownership contract. The runner does not
infer frame ownership from those global counters. Pattern
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

Credit frame records must also report zero source_errors and source_cleanup_errors.
A failed source session reports physical overruns as unknown and preserves the
actual last invalid geometry/orphan counter delta when readable. Final cleanup
errors are separate from acquisition failures; inspect the final sender report
and halt proof even after this receiver's frame-window criterion passes.

## Desktop source presentation is part of the experiment

The GLES fixture's exact8-bit readback precedes desktop presentation. It does
not prove the HDMI connector transmits those same values. On the tested GNOME50
AMD system, showing a notification on the primary monitor caused the fullscreen
secondary test output to switch from XR24 direct scanout to XR30 composition,
and real capture changed by up to1LSB. The same fixed source ID was exact before
and after the notification. Suppressing notification banners passed the short
controlled trigger test but did not prevent other long-run composition changes.

Keep full byte comparison strict. Do not mask a low bit, learn a golden capture,
or discard mismatches from the result. Record source events and DRM metadata
alongside every run; metadata sampling is not continuous physical-output proof.
`tools/check_hdmi_notification.py --help` describes the bounded real-board
regression. It intentionally does not change desktop settings and is not a
substitute for the health/accounting checks in this qualification tool.
See [evidence and limits](results/2026-10-15/frame-difference-diagnosis.md).
