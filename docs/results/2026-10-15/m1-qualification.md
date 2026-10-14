# M1 real HDMI capture qualification

## Result

The sustained capture criterion passes on build013 and sender v5:
PC USB-C/HDMI adapter → PYNQ-Z2 HDMI IN → LiteX frame gate → VDMA/PS DDR →
PS Ethernet → Python RGB888. This is real HDMI, not synthetic network delivery
or the M0 base overlay. Full M1 completion remains pending: accepted P4 source
sequence/drop accounting is not yet satisfied, and physical cable removal has
not been tested. Passing delivered-image checks does not close either gap.

| Measurement | Observed result |
|---|---:|
| Input scanout | 640×480 progressive, 25.2 MHz / 800 / 525 = 60 Hz |
| RGB payload | 921,600 bytes/frame; uint8 H×W×3 R/G/B |
| Observation duration | 600.505782 s |
| Distinct exact optical frames | 1,201 |
| Delivered / distinct exact rate | 1.999981 FPS |
| RGB payload goodput | 14.745458 Mbps |
| Pixel / mixed / repeated frames | 0 / 0 / 0 |
| Metadata / transport / storage errors | 0 / 0 / 0 |
| New gate invalid / FIFO overflow / underflow episodes | 0 / 0 / 0 |
| Startup invalid input | 1, while capture held disabled and selected=0 |
| Sender CPU samples | mean 39.30%, range 36.42–41.46% of one core |
| Sender RSS samples | 78,475,264–81,240,064 bytes |
| Source generation→host receipt | p50 273.708 ms; p95 392.213 ms; max 413.643 ms |

The startup invalid count is retained, not reset or excluded secretly. The
verified reset-disabled gate and before-enable snapshot establish that startup
input was unselected. Source FIFO startup overflow/underflow are zero. Every
new integrity error would fail the run. Counter snapshots are non-atomic and
have no per-buffer association; optical row IDs and all-byte comparisons provide
independent delivered-image checks. The older after-enable baseline was rejected
and remains in the failed evidence.

Timing intervals use the source generator and receiver on the same host monotonic
clock, matched by optical ID. They include display scheduling and buffering;
they are not HDMI-wire latency. 2,399 scanout samples in the receipt window show
XR24 at 25.2 MHz, with no read/inactive errors. Nine samples straddle framebuffer
changes; sampling cannot prove every instant or every frame's display format.
The correlation report retains unsampled and inconsistent interval coverage.
CPU values average five-second sampling intervals; they are not instantaneous
peaks. Resource windows use board monotonic metadata, never subtract host and
board clocks.

## Counters and limits

Between first/last received metadata, native VSYNC, observed, selected and
completed geometry each advance 36,000. Acquisitions advance 32,359, software
intentional sampling drops 31,159, and TCP enqueues 1,200. These are endpoint
deltas, not the inclusive host total of 1,201. Network-backpressure drops and
source/network error deltas are zero during this sustained connection.

The PL continues accepting approximately 60 frames/s; software samples about
2 frames/s. Completed geometry includes unselected frames. VDMA read IDs do not
identify physical frames: the difference between PL counts and acquisitions is
not silently labelled zero overrun or precisely attributed loss. Source skips
and DDR-ring overwrite counts remain unknown. Whole software drops are counted;
physical per-buffer sequence/drop attribution remains an unmet M1 requirement.

HDMI format/range metadata remains unknown. No gamma/range correction, reference
recapture, lossy compression, or tolerant pixel comparison was used. The controlled
source's RGB ramps and single-pixel/row markers match exactly in received frames.
This does not qualify arbitrary sources, protected content, interlace or 720/1080p.

## Follow-up executions

- Gate off/on: half-second disable leaves selected unchanged and adds 30 dropped
  frames; re-enable adds 30 selected frames. No new integrity errors.
- Client pause/reconnect: eight-second pause, six exact distinct frames across
  connections, same sender session, no retry failures. Acquisitions advance 596,
  backpressure drops 13, one network error denotes timeout/close, not corruption.
- 60→59.94 Hz change: source relock caused a mode rejection; sender stopped
  delivery, verified DMA Halted, then freed five buffers. Explicit sender/source
  restart recovered ten exact frames at 25.175 MHz / 800 / 525 ≈59.94 Hz.
  Automatic mode recovery is not implemented. The source renderer also exited
  when the modeset changed its drawable placement, rather than drawing on the
  wrong-sized output.
- Physical HDMI removal/reinsertion: pending operator action.
- Host software: 195 passed, one optional-dependency skip. Dedicated gateware
  environment: 17 passed, zero skips. No hosted CI run.

The existing PYNQ UIO destructor still logs an ignored event-loop RuntimeError
after cleanup. Actual recorded cleanup orders DMA halt before five frees. Earlier
M0 kernel panic remains unexplained; these successful executions do not establish
its root cause. Existing SD filesystem warnings were not repaired or hidden.

## Reproduction and evidence

Use [quickstart](../../quickstart.md), [build](../../build.md),
[qualification tool](../../qualification.md) and [performance budget](../../performance.md).
Build013 bit SHA256: `33f6a640cf2a6e068515f8a4e8e85ff60d4015d323a6ce67b5332479cd0e7a73`.
HWH SHA256: `9d2dfef03a329807471635e3f8804e9981f7a41ee7aa905d6eb10024310c6aeb`.
Sender v5 archive SHA256: `5b54cb9cb20a96f3491363afaca9557e882ed6b43346d11e2e94a187dead735d`.

The local routed design passes setup/hold 0.516/0.020 ns, all 41 bus-skew checks,
and has no critical CDC/DRC or internal unconstrained endpoints. Retained vendor
VTC warning, external I/O timing gaps, vendor Gray CDC scoped waivers, and two
XPM startup simulation diagnostics remain disclosed in the build guide.
The complete clean-checkout build was not rerun: 013 reused HLS IP generated
locally in 001. The user subsequently requested incremental local commits. No push, web, bypass
or LCD implementation was performed.

Primary evidence:

- [Sustained result](m1-013-v5-sustained.json) and [every-frame log](m1-013-v5-sustained.jsonl)
- [Correlation and scanout analysis](m1-013-v5-correlation.md)
- [Resource summary](m1-013-v5-resource-summary.json) and [samples](m1-013-v5-resources.jsonl)
- [Client reconnect](m1-013-v5-reconnect.json)
- [Mode rejection and safe cleanup](m1-013-v5-mode-cleanup.log), [recovery](m1-013-v5-recovery.json)
- [Gate control](m1-013-gate-and-stop.log), [initial orderly shutdown](m1-013-stop-final.log)
- [Bring-up history and failures](m1-bringup.md), [software tests](software-tests-final.txt)

Actual frame arrays remain local under ignored `artifacts/`; they were not viewed
through external image tools or uploaded.

## Qualification report scope correction

The qualifier now labels its `passed` result as the sustained delivered-image
criterion and separately reports `criterion_passed`, `full_m1_qualification=false`
and the unverified M1 evidence. Existing saved reports remain unchanged historical
evidence. Accepted inputs, image/health rejection paths and CLI exit behavior are
unchanged; no new metadata class is accepted by this reporting-only change.
The legacy build013 null-source-sequence fixture passes the image criterion while
explicitly remaining incomplete for M1. All 24 qualification tests pass locally;
this scope correction has not been rerun against board hardware or hosted CI.
