# Real 1080p30 loop bring-up and final-accounting failure

The user confirmed the requested J9 HDMI OUT→J10 HDMI IN cable change with
“Done”. The Hub/Micro-B remain connected under that requested configuration.
The guarded switch rechecked the old VGA receipt, same boot, RS0/Halted1,
capture disabled and no saved SDK shutdown IPs or competing capture process.
Build005 was then loaded with GPIO-only access, checked reset/empty, and
prepared normally from that established reset state. No native video driver
was constructed before observing a live input.

`1080p-overlay-switch-005.log` and `1080p-source-cadence-001.log` under
`artifacts/operator/` preserve the switch and six fixed-clock observations.
Across5.011851seconds, native VSYNC advanced150edges, approximately29.929Hz.
Invalid frames and FIFO overflow/underflow stayed0; selected frames stayed0
and DMA was halted. This is a cadence measurement, not a measurement of the
74.25MHz pixel clock. That clock and progressive timing come from the
controlled PL fixture and its verified CAD configuration.

The first capture used the original `df5410d` runtime's copy implementation
at `/tmp/hdmi-capture-1080p30-001/src`. The operator profiling wrapper measured
calls to the production copy/encode functions without changing lease or DMA
behavior. Target FPS was5, sender duration60seconds, port9042. The host
qualifier used `--mode 1080p30 --duration 20 --min-frames 20 --min-fps 1`.

The [client criterion](1080p30-loop-baseline-001-summary.json) passed37distinct
exact RGB888 images in20.084306seconds,1.842234FPS and91.681377Mbps payload.
Longest delivery gap was0.571140seconds. Pixel, mixed-frame, repeated optical
ID, metadata and transport errors were0. All1080optical marker rows and all
6,220,800RGB bytes of each delivered image matched the analytic source pattern.
Endpoint arrays remain local under `artifacts/operator/1080p-baseline-001-captures`.

The overall board run failed at shutdown, exit1. Its
[board records](1080p30-loop-baseline-001-board.json) show
`Native source stopped during final accounting interval`, one cleanup error,
and `dma_shutdown_safe=true` after raw halt and buffer release. This failure
is retained separately from the passed client image criterion. A premature
host request for the final result file also failed because the file did not
exist yet; the later bounded observer collected the completed result without
signaling the native process. No whole-run success is claimed.

The runtime waited a fixed50ms and required at least two new VSYNC edges.
At30Hz,50ms covers only1.5periods and can contain just one edge. A deterministic
fake-clock regression at three phases reproduced the invalid rejection on
healthy30Hz input. The red run had3failures and15passes; two failures were the
actual stopped-source exception and one exposed the too-short reported proof
interval. VGA60/59.94Hz and genuinely stopped sources were included.

After the board run, a second GPIO-only observation showed150more VSYNC edges
over5.011491seconds with unchanged clean integrity counters, RS0/Halted1 and
capture disabled. This supports the timing-window diagnosis rather than a
persistent stopped source. It does not independently exclude every brief
physical source interruption during the earlier shutdown.

The fix keeps the proof enabled for three periods of the selected profile:
100ms for1080p30 and the existing50ms for VGA. It retains the two-edge requirement,
health checks, missing-SOF watchdog, failure propagation and raw-halt-before-free
order. Only the necessary words in the existing source comment changed.
The focused source/sender/lease/preparation suite passed252tests; full host
validation passed592with one optional Migen/LiteX module skipped. Red/green
logs are `artifacts/operator/1080p-final-accounting-{red-002,green,full-host}.log`.

Caller review: CLI main→Sender.run→Sender.close→the source's dynamic close;
the held-lease main→run_session cleanup also calls that close. Source startup
failure can call close directly. The graph did not resolve every dynamic caller;
direct source reads covered those edges. Profile selection already rejects
unsupported modes. No new input mode is admitted by this fix. Board verification
of the fix, improved-copy capture, held lease, real GUI/BMP and the ten-minute
qualification are pending. The bit/HWH/manifest are unchanged by this host fix.
