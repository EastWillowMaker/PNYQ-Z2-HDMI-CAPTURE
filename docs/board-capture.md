# Board capture and sender

`pynq` selects the M0 base-overlay baseline; `litex` selects the paired custom
overlay and capture gate used in the [M1 physical qualification](results/2026-10-15/m1-qualification.md).
The explicit `synthetic` source tests transport; it never substitutes for HDMI.
Unit tests alone do not establish a physical capture result.

## Run

Install the repository in a local environment using the main README. On the
board, use the existing PYNQ Python environment; do not install or replace its
global packages. After overlay replacement and temporary network setup have
been authorized, run from a checkout with the package available:

```bash
PYTHONPATH=src /usr/local/share/pynq-venv/bin/python -m hdmi_capture.sender \
  --source pynq --host :: --port 9020 --fps 1 --duration 30 --startup-diagnostics
```

The installed board environment also requires `XILINX_XRT=/usr`, established by
`/etc/profile.d/xrt_setup.sh`. If `sudo` resets that environment, the Python device
discovery reports `NoDevices`. Preserve only the required value explicitly:

```bash
sudo -n env XILINX_XRT=/usr PYTHONPATH=src \
  /usr/local/share/pynq-venv/bin/python -u -X faulthandler \
  -m hdmi_capture.sender --source pynq --host :: --port 9020 \
  --fps 1 --duration 30 --startup-diagnostics
```

Optional startup diagnostics emit flushed JSON stages to stderr before PYNQ
import, overlay load, HDMI configuration/input-lock wait, mode checks, DMA start,
and source ready. The library is silent unless its optional progress callback is
supplied. `--duration` starts after source initialization and server startup; it
is not a bound on hardware startup. Enable Python faulthandler for native hangs.
An external `timeout --signal=INT 90s` requests cooperative cancellation but does
not guarantee exit; never add a forced-kill deadline once DMA can be active.
SIGKILL or repeated interruption during native stop can release XRT buffers while
the hardware still writes to their physical addresses. If DMA cannot be confirmed
halted, reset the PL/DMA through a verified safe procedure or physically reset the
board before releasing those buffers. Parent-owned staged hardware
probes can call `faulthandler.dump_traceback_later(15, repeat=True)` before loading
the overlay to record the Python call active during a native wait.

With diagnostics enabled, normal shutdown also emits `source_cleanup` events:
DMA stop begin, S2MM control/status registers0x30/0x34 before stop, successful
status after stop, DMA stop complete, pool free begin, and pool free complete.
The adapter checks that the S2MM channel reports halted before freeing its pool.
If native stop raises or is interrupted, the pool references remain retained and
no free stage is emitted. Retained Python references alone do not protect memory
after process exit. The standalone hardware CLI now marks DMA safety unverified
before attempting native start and confirms safe shutdown only after halt and
buffer cleanup. If an exception escapes while safety is unverified, it emits
`fatal_dma_shutdown_unverified` and enters an indefinite hold with strong source
and BO references. During that hold it ignores INT/TERM/HUP/QUIT termination
requests, performs no hardware writes, and applies no automatic deadline or kill.
Hardware-source TERM/HUP/QUIT requests during normal operation first request
cooperative cleanup. A failed stop therefore does not return normally from the
CLI and silently release live DMA allocations at process teardown.

Use an authorized physical board reset, or verify an authorized PL/DMA reset
before terminating a held process. The software does not infer a hardware reset
from elapsed time or a changed flag. SIGKILL/native crashes cannot be prevented
by Python handlers and remain unsafe while DMA may be active. Library `close()`
continues to raise on failure: its caller must retain the source, its BOs, and
the process until hardware halt/reset is established. Catching the exception and
exiting, or merely retaining a source in a soon-to-exit process, is insufficient.
These events locate a later hang; they do not impose a
native-stop deadline or prove the underlying hardware completed every write.

Loading `base.bit` replaces the current FPGA design. It requires board-local
privileges and can interrupt existing PL services. The first `configure()` may
block in the PYNQ frontend's native detection, with its default 60-second init
timeout. The sender's three-second `--read-timeout` applies to each subsequent
asynchronous acquisition, not overlay loading or initial configuration.

For a hardware-independent transport test:

```bash
python -m hdmi_capture.sender --source synthetic --host 127.0.0.1 \
  --port 9020 --fps 10 --width 640 --height 480 --input-fps 60
```

The synthetic image contains independent column/row ramps, changing frame
markers, and adjacent red/green/blue single-pixel markers. It is marked
`source_origin=synthetic`, `baseline_only=false`; this flag never means M1 passed.
Only `--source pynq` creates a PYNQ source. Missing PYNQ, wrong version, unsupported
mode, missing signal, and source errors terminate the sender with an error.

## Ownership and backpressure

The main asyncio event loop reads `hdmi_in.readframe_async()` continuously,
independently of the TCP client. The PYNQ driver transfers ownership of a complete
DMA buffer and invalidates its cache before returning. The adapter configures
`PIXEL_BGR`, the identity conversion, then copies selected frames with a channel
reversal into tightly packed RGB888. The copy is immutable and the DMA buffer is
returned to an adapter-owned object pool in a `finally` block. Skipped frames are
returned without copying. No scaling, gamma, or quantization conversion is applied.

The installed PYNQ3.0.1 `PynqBuffer.freebuffer()` returns a pointer to its cache
on the first call, then its destructor calls `freebuffer()` again and can release
the now-cached native buffer. Also, `_xrt_allocate(pointer=...)` attaches another
native finalizer on each pointer reuse. The adapter avoids both paths by retaining
the original four DMA buffer objects and at most one additional object, reusing
those objects through its own pool. It replaces only this channel's
`_cache.getframe` instance method; it does not modify the installed package. After
stopping DMA, it frees each retained allocation once, bypassing the pointer cache.
For 640x480 this retains at most 5×921600 bytes of native pixel storage, plus RGB,
wire, and transport copies. The initial explicit-free sender path exposed a DMA
invalidate failure on board; the pinned-class regression reproduces the cached
allocation release before the fix. Native release calls are stubbed in that unit
test. Subsequent physical execution is recorded below; it does not establish
unobserved hardware skip/overrun counts or arbitrary source recovery.

There is one replaceable ready frame and one immutable frame being transmitted.
If a new sample arrives while the ready slot is occupied, the previous unsent
frame is dropped whole. TCP drain has a five-second deadline by default. A slow
or disconnected client cannot suspend acquisition. Failed or timed-out writers
abort their transports to discard buffered bytes immediately. Shutdown closes
and cancels clients before awaiting server closure, including Python3.14's
active-client server-close behavior. A second simultaneous client
is closed. Reconnecting discards the previous ready slot and waits for a new
sample. Sender shutdown cancels acquisition/client tasks and closes the HDMI
pipeline; source exceptions propagate after cleanup.

## Custom LiteX source and capture control

The distinct `--source litex` requires an explicit custom bitstream and generated
build manifest. It verifies matching bitstream/HWH SHA256, schema, pinned PYNQ
receiver commit, 640x480 geometry, and 142857132Hz clock before loading. It uses
the manifest's 25.2MHz preferred/25.175MHz supported pixel clocks and
`receiver_k_clk_range=5`; it also verifies the HWH receiver module's `kClkRange=5`
before loading, because this receiver has no AXI control registers and may not
appear in `ip_dict`. Older range1 or incomplete manifests are rejected. The EDID
hash records build provenance; it is not an independent runtime readback of the
source's EDID or measured pixel clock. It uses
generic `pynq.Overlay`, never the stock base fallback. After loading it checks
the expected S2MM-only VDMA6.3 and three AXI GPIO2.0 resources from the HWH's
`ip_dict`, then binds `VideoIn(description, overlay.video.axi_vdma)` explicitly.
This matters because the generic HDMI hierarchy otherwise has no attached VDMA.
Installed PYNQ3.0.1 exports pixel formats from `pynq.lib.video`, but exports the
`hierarchies` module rather than its `VideoIn` class. The adapter imports
`VideoIn` from `pynq.lib.video.hierarchies` explicitly. An earlier build012 launch
failed on the incorrect package-root import before overlay programming
([retained log](results/2026-10-15/m1-012-status1.log)); the fake-module constructor
test now reproduces the installed export layout so that mismatch cannot pass.
`PIXEL_BGR` was checked in the copied installed `common.py` and package wildcard
export, and `VideoIn` and its constructor in copied installed `hierarchies.py`.
Generic `pynq.Overlay` and `pynq.MMIO` exports were checked against pinned upstream
PYNQ3.0.1 package initialization; the full installed package-root file was not
copied for an independent hash comparison.
During startup the software disables selection while waiting for input lock and
configuring/starting VDMA. It enables selection only after VDMA is running and
the owned buffer pool is installed AND the full startup counter baseline has
been recorded while selection remains disabled. The baseline must report
`enabled=false` and integer `selected_frames=0`; otherwise startup stops and DMA
is closed without enabling selection. The manifest's integer
`capture_enable_reset=0` and matching HWH `capture_control.C_DOUT_DEFAULT=0` are
verified before programming. Input frames during that interval are consumed and dropped whole;
startup dropped/error totals are retained, not reset or hidden. This avoids
unnecessary frontend backpressure while DMA is halted.

```bash
sudo -n env XILINX_XRT=/usr PYTHONPATH=src \
  /usr/local/share/pynq-venv/bin/python -u -m hdmi_capture.sender \
  --source litex --bitfile /path/to/capture.bit \
  --manifest /path/to/build-manifest.json --host :: --port 9020 \
  --fps 1 --duration 30 --startup-diagnostics
```

Only after the expected custom resources are verified can frames carry
`baseline_only=false` and `capture_implementation=litex_video_gate`. This describes
the selected implementation, not qualification: `hardware_qualification` remains
`unverified`. The protocol carries `frame_source_id=null` and
`source_sequence=null`; GPIO totals cannot associate a source frame ID with a
specific returned DMA buffer.

`litex_counters` contains observed, selected, completed, dropped, and invalid
frame counters plus capture enable. These are sequential 32-bit GPIO reads after
DMA read completion, with snapshot begin/end board-monotonic timestamps and
`snapshot_atomic=false`. They are not an atomic per-frame sample. Counter deltas
wrap modulo2**32; overlay reload/reset invalidates comparisons across that reset.
Gate drop/invalid counts do not establish DMA overrun counts; the separate M0
`source_overruns` and buffer source association remain unknown.

Build010 additionally maps `video/source_health` GPIO channel1 to
`frontend_overflow_episodes` and channel2 to `native_vsync_edges`, and
`video/source_faults` channel1 to `frontend_underflow_episodes`. Overflow and
underflow counts describe assertion episodes, not numbers of lost frames.
`source_health_provenance` carries the manifest's monitor SHA256,
`source_health_counters_lifetime=fpga_load`,
`source_health_overruns_unit=overflow_episodes`, and
`receiver_source_reset_policy=shared_per_clock`. The corrected native monitor
counters persist across receiver lock/reset; edge history is disarmed while its
pixel reset is asserted. They remain observational counters without DMA-buffer
association. Older build009 smoke runs lack these resources and expose null
monitor counters/provenance; they cannot establish final M1 integrity acceptance.

Before any acquired sample becomes a ready RGB frame, the LiteX source reads its
counters and compares them with its prior sample/baseline. Any change in invalid,
overflow, or underflow counts, or any decrease in native VSYNC edges, releases
that acquired buffer and stops the entire session with an explicit source error.
Counter rollback and VSYNC wrap also require a new session in these bounded runs.
This conservatively detects errors/reset evidence without inventing an association
between a hardware count and the returned buffer. It cannot retract bytes already
delivered or prove every unseen invalid frame was detected. On source failure the
sender discards its ready slot and aborts pending client transport.

`litex_startup_counters` preserves the baseline, including pre-existing nonzero
error/overflow/underflow counts. Baseline errors are not zeroed or silently removed
from evidence. Final sender reports also retain startup, last, and failure
snapshots even when the capture fails. A qualification run must evaluate those
startup totals and require the complete010 monitor contract, not infer clean input
from an unchanged runtime counter or from a legacy null field.

The v5 baseline sample point is
`sequential_gpio_reads_after_dma_start_before_capture_enable`; metadata policy is
`disabled_zero_selected_baseline_then_stop_on_integrity_change`, with
`capture_enable_reset=0`. Selection is held disabled through the entire sequential
snapshot and its validation, then enabled. This ordering supplies evidence that
nonzero startup gate-invalid counts arose before any selected frame. It does not
erase those counts or establish pixel integrity itself. A qualifier may make a
narrow exception for startup gate-invalid events only with that complete ordering
and reset proof; startup overflow/underflow events still remain disqualifying.
Older after-enable baselines have no such proof, even if one sequential read
reported zero selected frames; those retained runs must not be reclassified as
qualified by the new policy. Any newly detected integrity event after the v5
baseline stops acquisition, including events in a still-unselected partial frame.

Control commands attach to the already loaded verified overlay without loading
or replacing it. They return after GPIO-only setup and never access the lazy
`overlay.video` hierarchy or instantiate PixelPacker/VideoIn/VDMA drivers. This
avoids the PixelPacker constructor's write to its mode register and avoids opening
video interrupt handles merely to inspect gate counters. Overlay construction
with `download=false` parses descriptions and creates its lazy map; video driver
creation is deferred until attribute access in inspected PYNQ3.0.1 upstream code.
Resolve AXI GPIO addresses through `ip_dict`; no addresses are
hardcoded. Use a short pause below `--read-timeout` while a sender is active:

```bash
sudo -n env XILINX_XRT=/usr PYTHONPATH=src \
  /usr/local/share/pynq-venv/bin/python -m hdmi_capture.sender control \
  --bitfile /path/to/capture.bit --manifest /path/to/build-manifest.json --enable 0
sudo -n env XILINX_XRT=/usr PYTHONPATH=src \
  /usr/local/share/pynq-venv/bin/python -m hdmi_capture.sender control \
  --bitfile /path/to/capture.bit --manifest /path/to/build-manifest.json --enable 1
```

Omit `--enable` to inspect counters. Disabling gates complete frames selected at
SOF; re-enabling allows subsequent SOFs. A long pause makes the sender's acquisition
deadline expire, requiring restart. Control samples use the same sequential GPIO
snapshot routine but, because there is no acquisition, interpret their sample
point as standalone register reads rather than association with a DMA frame.
Control correctness, reset behavior, and real LiteX capture require separate
simulation/build/on-board evidence; manifest identity alone does not establish
timing, pixel integrity, or the ten-minute acceptance target.

PYNQ explicitly warns that the first read after a pause may be stale. The adapter
discards its first acquisition before sending, then keeps reading regardless of
network state. This removes that documented startup case; it does not establish
full pixel integrity, source identity, or arbitrary disconnect recovery on board.
Mode changes and signal loss terminate the current service; restart after the
source has stabilized. Mode checks compare detected dimensions before and after
each read. M0 accepts only 640x480 with 24-bit DMA pixels. PYNQ's native detector
does not expose actual frame rate or progressive/interlaced status, so metadata
leaves these unknown; a controlled RGB 640x480p60 source is a fixture requirement.

The stock PYNQ-Z2 base design advertises its synthesized `720p_edid.data`, selected
in upstream `boards/Pynq-Z2/base/base.tcl:439`. Its `dvi2rgb.vhd` DDC EEPROM is
instantiated with `kWritable=false` and has no AXI control port. The PYNQ Python
adapter cannot rewrite that ROM to advertise 640x480. A source that permits
forcing the agreed mode, or a rebuilt overlay with matching EDID, is required
when the source only offers the EDID's 1280x720 mode. The source adapter rejects
1280x720 explicitly; it does not silently scale it to 640x480.

## Metadata and counters

Each sender has a UUID `session_id`; acquisition IDs increase for every returned
sample, including samples subsequently discarded. They are not hardware source
sequence numbers. `source_sequence=null` for PYNQ. The timestamp is board
monotonic nanoseconds sampled immediately after DMA read returns; it is not SOF,
exposure time, or a clock synchronized to the host. Do not subtract it from a host
clock to claim one-way latency. Synthetic timestamps use the sender monotonic
clock after pattern generation.

Counters distinguish `startup_discarded`, `intentional_sampling_drops`,
`network_backpressure_drops` (ready-slot replacements), `client_discarded`,
`source_errors`, and `network_errors`. `transport_enqueued` records complete
`writer.drain()` calls, not host receipt or durable storage. Host capture counts
provide delivered-frame evidence. A counter snapshot attached to a frame can
precede that frame's enqueue and subsequent ready-slot drops.

`source_skips`, `source_overruns`, and `source_invalid_frames` remain `null`:
PYNQ M0 cannot observe them reliably. `source_color_format` and
`source_quantization_range` are `unknown` for HDMI because the adapter has no
AVI InfoFrame reporting. BGR DMA layout does not establish HDMI RGB or its range.
The controlled fixture must establish the source emits RGB; the adapter does not
decode or reject YCbCr, HDCP, deep color, or interlaced signaling directly.

## Evidence and limitations

The adapter was inspected against exact board-installed PYNQ 3.0.1 files fetched
read-only on 2026-10-15 and matching
[upstream v3.0.1](https://github.com/Xilinx/PYNQ/tree/v3.0.1/pynq/lib/video).
SHA256 values for installed and upstream files are identical:

| File | SHA256 |
| --- | --- |
| `dma.py` | `94346a4ae6a7a7f9e4b78887179e2a55ff821c7ed3724b584a7bb4c228fea30f` |
| `hierarchies.py` | `528106d7ea2c95cfd64ec27f2696f9daab76fb2c96341f1a48cd04b211f85950` |
| `common.py` | `2c4d6c2cb3ede0aca97aa2980dec7d5147ce6f4d446635ddd7dd1e894282cbf7` |

Relevant upstream source locations: `dma.py` S2MM `_readframe_internal`,
`readframe`, `readframe_async`, and `stop`; `hierarchies.py` `VideoIn.configure`,
`readframe_async`, and `close`; `common.py` `PIXEL_BGR` and `COLOR_IN_BGR`;
`dvi.py` `HDMIInFrontend.mode`. Local copies reside in ignored
`artifacts/board-source/` and `artifacts/pynq-3.0.1/`.

The existing PYNQ driver clears some DMA error bits in `_readframe_internal()` and
`activeframe`. That pre-existing behavior prevents an adapter read count from
proving zero hardware invalid frames or overruns. M0 neither measures real input
FPS nor detects every forbidden signaling class. A native DMA start/stop can also
busy-wait; the asyncio read timeout cannot bound native blocking code. These paths
are unverified on board. M1 must provide hardware source sequence/counters and
validate frame integrity, source recovery, clocks, and forbidden inputs directly.

Native startup inspection also exposes an unverified failure path in upstream
`pynq/lib/_pynq/_video/_capture.c`: its deallocator unconditionally frees VTC
state even when GPIO-lock timeout occurred before VTC initialization, while the
capture struct was allocated with `malloc`. `video_capture.c` normally returns a
failure after the default 60-second timeout and the wrapper raises `LookupError`,
but that destructor may access uninitialized VTC state. This is a pre-existing
upstream defect candidate, not a proven explanation of the physical sender's
SIGBUS recorded in `docs/results/2026-10-15/hdmi-process.log`. Native GPIO/MMIO
mapping failures are also insufficiently checked downstream. A staged
faulthandler run is required to distinguish overlay loading, input lock, and
failure cleanup; missing input must not be claimed to fail safely on this board.
The VTC destructor only accesses the value if its global native VTC registry
contains entries; this candidate alone does not explain a fresh-process failure
before any VTC was initialized. Physical staged-probe results take precedence
over this static candidate.

Before this patch there was no source adapter or board sender. New routing is
explicit synthetic generation or a PYNQ 3.0.1 base overlay: supported dimensions
enter the asynchronous ownership path; unsupported dimensions abort and close;
mode changes during a returned acquisition free the frame before aborting. Unit
tests verify BGR conversion, immutable copies, exactly-once release, mode-change
cleanup, bounded ready slots, slow sending with independent acquisition, TCP
single-client/reconnect behavior, source timeout cleanup, and input bounds. These
are local unit/socket checks, not hosted CI, hardware qualification, or the
ten-minute/600-frame M1 acceptance run.

Verification command:

```bash
PYTHONPATH=src python -m pytest tests/test_sources.py tests/test_sender.py -q
```

On-board capture, controlled color/channel verification, source unplug/replug,
mode changes, actual FPS, CPU/memory, and long-duration acceptance require
separate evidence in the dated results directory.

## Physical M0 evidence and remaining cleanup warning

On 2026-10-15 the repaired pool deployment completed a 180-second board run with
10352 returned DMA acquisitions, zero reported source errors, and 31 complete TCP
enqueues across snapshot/capture clients. See the
[final board log](results/2026-10-15/m0-pool-final-status.log). No invalidate or
double-free failure recurred in that run. The board acquisition count is not an
observed HDMI source sequence count. Native hardware skips/overruns remain unknown.

The subsequent native GLES/Wayland RGB8/XR24 fixture test delivered 30 frames in
14.59524 seconds, 2.05546FPS, 15.15453Mbps payload, with zero protocol errors
([host capture](results/2026-10-15/m0-gl-capture.json)). Its
[pixel report](results/2026-10-15/m0-gl-pixels-30.json) shows 30/30 byte-exact
matches, 30 distinct optical IDs, zero mixed frames, and zero maximum error. This
is short M0 HDMI→DDR→Ethernet→PC evidence for that controlled fixture. The earlier
GTK source experiment had a maximum one-unit pixel mismatch; that retained result
is disclosed in the [bring-up report](results/2026-10-15/m0-bringup.md). It was not
removed by adding tolerance or changing the receiver's color conversion.
Restarting the GLES fixture later again produced a transient one-unit first-frame
mismatch, under investigation. The 30 exact frames qualify that recorded run;
they do not establish permanent fixture fidelity across every restart.

Normal process exit still prints an ignored `UioController.__del__` exception:
`RuntimeError: There is no current event loop in thread 'MainThread'`. Exact board
log names installed PYNQ3.0.1 `uio.py:79`. Inspected upstream v3.0.1 `uio.py`
registers a reader on construction, then its destructor calls
`asyncio.get_event_loop().remove_reader(self.uio)` before closing the UIO file.
`interrupt.py` retains UIO controllers in its global `_uio_devices` registry,
allowing destruction to occur after `asyncio.run()` closed the loop. This explains
the observed exception's mechanism; those two complete installed files were not
yet copied/hash-compared. The warning occurred after capture statistics were
emitted, and no capture corruption is demonstrated by the warning itself. Clean
native interrupt-resource shutdown is not claimed.

The adapter does not patch installed PYNQ, alter controller instance classes, or
clear shared global interrupt registries merely to suppress this warning. Such
changes could invalidate another consumer's interrupt ownership. A future
standalone CLI can own an explicit event-loop lifetime and release only the
interrupt controllers it created before closing that loop, after exact installed
implementation verification and a resource-lifetime regression. That is an
unimplemented follow-up, not a completed cleanup fix. Source unplug/replug,
mode changes, stable missing-source startup, and the ten-minute/600-frame custom
LiteX acceptance run still need independent physical evidence.

## Subsequent board panic: ownership assessment

A later M0 GLES capture process stopped responding to ordinary UART/SSH commands,
and the board recorded `Kernel panic - not syncing: Attempted to kill init!
exitcode=0x0000008b` ([panic log](results/2026-10-15/uart-recover-2.log)). The
[last sender status](results/2026-10-15/hdmi-gl-final-status.log) shows the process
still present under an external timeout with forced-kill escalation; it does not
record completed DMA stop or buffer release. The exact causal path is unresolved.
This is a system stability failure, distinct from the previously observed ignored
UIO destructor warning. Earlier exact pixels and successful capture statistics
do not establish safe shutdown or sustained board stability.

The board also had pre-existing storage/service problems: the retained
[2026-10-14 boot log](results/2026-10-14/uart-boot.log) records ext4 recovery/errors
and a failed haveged service before this sender/pool existed. No SD repair or
reimage was performed. That is a competing environment risk, not proof that
storage caused this panic. A fresh boot log after the authorized physical reset
must preserve storage/kernel errors alongside DMA/XRT evidence; the init panic
must not be attributed solely to buffer ownership without discriminating evidence.

Independent static inspection traced the repaired ownership path through exact
installed PYNQ `dma.py` and `buffer.py` and installed `xrt_device.py` (matching
upstream SHA256 `b79765ec53d92ac97657e95a7c990e8d1bdacb133161b278e1a8c3e4159fcd5e`).
S2MM `_readframe_internal()` allocates the replacement first, removes ownership
of the returned frame from `_frames`, inserts the replacement, invalidates the
captured frame, then returns it. The pool retains all four initial objects plus
one replacement; normal release adds the original object to its available pool,
never invokes PYNQ `freebuffer()` or rewraps a pointer. Thus its normal repeated
acquisition path avoids the previously demonstrated double-free/finalizer paths.
Source close calls `VideoIn.close()`→S2MM `stop()`, whose pinned implementation
clears run/stop and polls HALTED before dropping `_frames` and clearing the DMA
pointer cache. Only after successful halt does the adapter free each retained
object once. No newly proved normal-path double-free was found in this review.

The pinned-buffer test confirms five retained allocations and one release each
after its simulated DMA ownership is relinquished. Additional tests confirm that
stop interruption or an unexpected non-halted return prevents pool release, and
successful cleanup events precede release. These are native-call-stub/ownership
tests; they cannot reproduce init death, verify actual AXI completion, or rule out
XRT/kernel/MMIO/clock defects. Native allocator release and actual shutdown remain
unverified for the failed run. An external SIGKILL after a stuck stop is a concrete
unsafe path: process teardown can release BOs while DMA still targets their physical
addresses. The recorded timeout permits that path, but the logs do not prove it
occurred or caused this panic. Forced-kill escalation has therefore been removed
from recommended launch commands; this does not constitute a root-cause fix.

The next physical run must retain cleanup status evidence, avoid automatic forced
kill, and establish DMA halt before native release. If halt cannot be established,
the board/PL must be reset through an authorized safe procedure before releasing
DMA buffers. Reproduction and kernel/XRT evidence are required before declaring
this stability issue fixed.

The previous CLI exception path could still exit after a failed native stop,
even though `PynqSource.close()` retained object references. The current CLI hold
closes that process-lifetime gap; local tests exercise actual `Sender.run()` and
`asyncio.run()` exception propagation with a simulated native stop failure, then
assert entry into the hold callback while BO references remain owned. Separate
tests cover partial native-start failure and safe failures that should propagate
normally. This is a tested control-flow safeguard, not proof that the unresolved
kernel panic is fixed or that actual hardware shutdown now succeeds.
