# Real loop capture and component measurements

Build005 drove the physical J9→J10 changing1080p30 loop. The source geometry,
74.25MHz pixel clock and progressive format are controlled fixture settings;
fixed-clock GPIO observations independently showed approximately30VSYNC/s.
The runtime still reports source color format/range and actual pixel clock as
unknown rather than claiming that it measured them.

Both20-second client tests requested5FPS and checked every delivered RGB888
byte against the independent Python pattern. Neither run changes output timing,
uses compression or resizes the delivered image.

| Delivered-image measurement | Previous copy | Channel copy |
| --- | ---: | ---: |
| Runtime | df5410d | cfd30d3 |
| Distinct exact frames | 37 | 50 |
| Observation seconds | 20.084306 | 20.157482 |
| Average FPS | 1.842234 | 2.480469 |
| RGB payload Mbps | 91.681377 | 123.443989 |
| Longest delivery gap seconds | 0.571140 | 0.437833 |
| Pixel/metadata/transport errors | 0/0/0 | 0/0/0 |

The client-window rate increased34.64%. This is one sequential before/after
pair, not a statistical maximum-rate claim. The previous board run failed its
50ms final source proof after the client had passed; that original failure is
preserved in the [bring-up report](1080p30-loop-bringup-001.md). The new runtime
also fixes only that final proof interval outside the measured delivery window.
The new board sender exited0 with DMA safe, zero source/cleanup/network errors,
and three observed final VSYNC edges over its100ms proof.

The profiling harness measured the actual copy/encode calls over the complete
60-second sender run, including periods before/after the client connection.
Previous copy median was259.523ms across159calls; channel copy median95.583ms
across250calls,2.72× faster. Encoding medians were115.586ms across37calls and
118.791ms across51calls. Some encoded frames need not reach the host when it
disconnects. These phase counts must not be treated as delivered frame counts.
Source files, exact manifests, final counters and timing summaries are in the
[old client](1080p30-loop-baseline-001-summary.json),
[old board](1080p30-loop-baseline-001-board.json),
[new client](1080p30-loop-optimized-001-summary.json) and
[new board](1080p30-loop-optimized-001-board.json) records.

The [held-lease observation](1080p30-lease-001.jsonl) passed the tracked checker
using the same cfd30d3 runtime. While A remained leased, its raw/RGB hashes,
credit identity and parked halted DMA stayed stable as the input advanced188
VSYNC edges. A second leased read was rejected before another arm. After ACK,
B had a different exact optical ID. The configured dwell was1second; hashing
and verification extend actual hold time. It does not independently map an
optical ID to an absolute native edge.

An operator wrapper retained the checker lifecycle and added20more distinct,
exact full-image captures. Read-only timing around the real DMA methods gave:

| Operation | Samples | Median | Min–max |
| --- | ---: | ---: | ---: |
| DMA arm→observed auto-halt | 22 | 42.207ms | 34.375–66.182ms |
| Read including credit/cache/pacing | 20 | 57.604ms | 49.567–81.196ms |
| Native buffer→owned RGB | 20 | 99.009ms | 95.424–100.088ms |

DMA timing includes frame-boundary waiting and polling, not only AXI transfer
time. The22samples include A/B. Each extra frame was copied and fully verified
outside the read timer before ACK; that intentionally expensive board-side
verification dominates the55.262-second test and is not production throughput.
The wrapper delegates arm/completion methods and restores them before normal
close; it changes no lease, health or halt check. Result passed with DMA safe.
Harness: `artifacts/deploy/1080p30-003/lease-capture-profile.py`.

The separate [raw TCP test](1080p30-raw-transport-001.json) sent127complete
cached6,220,800-byte payloads in10.040799host seconds,629.465Mbps. The PC checked
the SHA256 of every payload and acknowledged the total. The payload was a
repeated synthetic RGB array; no DMA, image generation in the timed loop,
production frame protocol, compression or new-frame criterion was involved.
The board measured629.627Mbps,9.982CPU seconds and35,720KiB maximum RSS. The
host NIC reports a1000Mbps link. Raw socket scripts and logs are under
`artifacts/operator/raw-transport-host.py`,
`artifacts/deploy/1080p30-003/raw-transport-board.py` and
`artifacts/operator/1080p-raw-transport-*`.

The raw link has substantial headroom above the123.444Mbps real pipeline.
Measured RGB copying and encoding together cost roughly0.22CPU-heavy seconds
per image and run on the sender's single event loop. Their costs, DMA wait,
memory/kernel copies and event-loop scheduling explain why raw-link throughput
cannot predict delivered FPS. The copy change improves actual delivered rate;
remaining work is not assigned wholly to one unmeasured phase. Resource samples
showed roughly90–94% of one CPU core during observed active intervals and about
90–102MB process RSS, with roughly293,000–306,000KiB available board memory. The short
resource windows include time outside the client connection and are not a
leak/stability qualification.

These measurements are separate from the
[passed ten-minute production criterion](1080p30-completion.md):1,200exact
images over600.076875seconds at1.999744FPS, with safe shutdown.
[Real GUI/BMP](1080p30-gui-hdmi-001.md) also passed. The independent PC fixture
and prior qualified VGA evidence are retained; no new PC-source1080p hardware
result is claimed here.
