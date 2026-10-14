# M1 build 013 v5: capture-window correlation

The completed capture summary reports 1,201 distinct exact RGB888 frames over
600.505782 seconds, approximately 1.999981 frames/s and 14.745458 Mbit/s of
payload, with zero pixel, mixed-frame, metadata, transport or storage errors.
All 1,201 coherent optical IDs match unique source events, and every matched
source event records a passing synthetic GL framebuffer self-check.

Evidence: [completed capture summary](m1-013-v5-sustained.json),
[capture frame log](m1-013-v5-sustained.jsonl), and
[full correlation report](m1-013-v5-correlation.json). The source and scanout
logs remain local under `artifacts/`; the report records their read-snapshot
hashes, sizes and coverage. No captured image was opened for this analysis.

## Host intervals, not HDMI wire latency

The following distributions match the image's per-row optical ID to the
source application's generation/pre-swap timestamps and the host's complete
frame receipt timestamp. Both timestamps use the host monotonic clock.
Intervals include source-image hold age, rendering/presentation, board
acquisition and delivery. They are **not HDMI wire latency**, and no board
timestamp was subtracted from the host clock.

| Host interval | Samples | p50 | p95 | Maximum |
| --- | ---: | ---: | ---: | ---: |
| Generation completion → complete frame receipt | 1,201 | 273.708 ms | 392.213 ms | 413.643 ms |
| Pre-swap event → complete frame receipt | 1,201 | 272.173 ms | 390.553 ms | 412.050 ms |
| Consecutive complete frame receipts | 1,200 | 500.470 ms | 504.843 ms | 526.743 ms |

Generation-to-receipt minimum was 139.499 ms and mean was 271.152 ms.
Percentiles use linear interpolation. No optical frame was unmatched,
ambiguous, repeated or regressing in this capture.

The source started at host monotonic 189621.302945600 seconds with optical
ID 40000, a 250 ms animation interval and self-check enabled. Launched
source SHA-256 was
`f3363c22b867055996e0302f9787a8d805a966e029f978f8ec170fe54fb162eb`.
The capture process started at 189673.559254982 seconds. First complete
receipt was 189674.077389776 seconds, matching ID 40196 generated at
189673.759905609 seconds. Last complete receipt was 190274.050491162
seconds, matching ID 42446 generated at 190273.787201534 seconds.
The completed process elapsed time includes startup/closing time around
that first-to-last receipt window.

## Scanout samples during the receipt window

All 2,399 metadata samples between first and last receipt reported XR24
(8-bit XRGB8888), active 640×480, 25.200 MHz pixel clock, 800×525 total
timing and mode flags 10. There were zero metadata read errors and zero
inactive/missing-state samples. Nine samples observed a changed framebuffer
ID between the initial and final CRTC read; those observations are retained
as inconsistent samples, even though their reported format was XR24.
Sample spacing had p50 250.147 ms, p95 250.212 ms and maximum 255.657 ms.

Within the individual generation-to-receipt intervals:

- 1,099 frames had only consistent XR24 samples.
- 97 intervals contained no sample because the interval was shorter than or
  fell between metadata sample times.
- 5 intervals included an inconsistent framebuffer-ID sample.

Periodic samples can miss a brief format/presentation change. These figures
do not prove continuous direct scanout or assign an actual HDMI presentation
time. Exact received pixels are established separately by the full analytic
comparison of each captured frame.

After operator closeout, the complete scanout log contains 3,033 samples:
243 XR30 and 2,790 XR24, with zero metadata read errors. Two XR30 samples
occurred before capture; later XR30 observations followed the post-window
switch to 59.940 Hz (25.175 MHz pixel clock). The capture-window statistics
above remain unchanged: all 2,399 samples there were XR24 at 25.200 MHz.
Do not describe the whole source/scanout log as XR24-only or include the
later mode-switch experiment in the 600-second capture qualification.

Both logging processes are now closed. The source log has 2,618 generated
IDs and a `source_stop` event at monotonic 190320.617697457 seconds; the
operator observed the source exit through its placement guard after the
mode switch reported a 2560×1440 drawable instead of 640×480. The stop
event records cleanup, not a normal successful renderer exit. The metadata
logger was interrupted with SIGINT after its final sample began at
190380.582559644 seconds, so its normal `scanout_summary` event is absent.
That interruption remains an incomplete normal-termination marker even
though all recorded metadata reads succeeded. The refreshed report hashes
cover the complete closed files, including these post-window observations.

## Gaps and remaining limits

Between the 1,201 delivered optical IDs there were 1,050 unobserved
intermediate IDs; maximum positive optical-ID step was 2, with no adjacent
repeats or regressions. Transport acquisition IDs had 31,159 unobserved
intermediate IDs and maximum step 28. These are observed sampling gaps,
not an attribution to network or hardware loss. The authorized stream
intentionally samples below the physical source/acquisition rate; retain
the capture summary's counters and their provenance when assessing drops.

The completed summary still marks physical source sequence verification
false and LiteX snapshots as sequential/non-atomic with no per-frame
association. This correlation does not upgrade those limitations, establish
a zero-drop contract, synchronize board/host clocks, or qualify 60-frame/s
delivery. It analyzes the completed M1 capture window and keeps the
source/scanout coverage gaps visible.
