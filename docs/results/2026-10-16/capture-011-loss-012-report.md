# Normal capture pass and HDMI loss failure

Run011 completed the normal received-frame criterion on the new SD card:
1,201/1,201 distinct exact RGB888 frames over600.368226seconds,
2.000439FPS /14.748836Mbps payload. All received metadata/accounting checks
passed. The received window spans36,001 native intervals:1,200 acquisition
intervals plus34,801 intentional skips, with zero acquired frames missing
from that window. Startup native skips remain unknown. All1,201 optical IDs
match unique logged KMS source IDs; no mixed, ambiguous or unmatched IDs.
The source uses direct DRM/KMS, XR24,640x480,25.2MHz; source exit0 and VT return
passed. This is real HDMI input through017 LiteX, DDR and Ethernet.

Sender exit0, dma_shutdown_safe=true, before/after ext4 error counts0 and the
16MiB persistence hash matched. Independent raw readback confirmed RS0/Halted1
and enable bit0 clear. The first post-halt probe wrongly required the whole
command to equal0; its failed log remains. Verified command0x2 retains the
request toggle, with capture disabled. It is not an active DMA command.
One final cancelled credit remained busy/done in global endpoint counters;
global selected/completed and acquired totals must not be conflated.

The120 in-window resource samples measured17.9733–20.4067% of one CPU core,
RSS78,610,432–80,461,824bytes. Host pattern generation to complete PC receipt
latency p50=0.239041s/p95=0.345837s; this is not wire-only latency. One DRM
metadata snapshot was taken, not periodic scanout monitoring. Raw evidence is
m1-017-newcard-attach-011*, with copied source logs capture-011-source-*.
Saved first/last NPY arrays remain private in ignored artifacts/captures/.

Run012 failed during physical HDMI-only removal/reconnection. The user
confirmed HDMI IN was unplugged for about5seconds, with Hub/Micro-B untouched.
The PC received88 exact healthy frames before timeout. The sender died with
SIGBUS(-7) at PYNQ dvi.py mode -> sources.py _healthy -> read/idle.
The kernel recorded a non-linefetch external abort at0xb6ed0030. Sender final
status and safe cleanup were absent. Source child exit1/DRM pageflip EINVAL;
VT restoration passed. The temporary outer worker incorrectly returned0.
The client also missed its narrow planned timing window; neither failure is
relabeled as a pass. Original012 raw evidence remains unchanged.

Storage before/after remained ext4errors_count0 and persistence hash correct.
A separate fixed-clock recovery helper attached without FPGA reload, observed
CR0x15010/SR0x11001, disabled the gate, and proved RS0/Halted1 again with command0.
No capture buffers were allocated by recovery; no forced DMA process kill or
reboot was used. See m1-017-hdmi-loss-012-emergency-stop.log.

## Diagnosis and changed behavior

017 HWH connects VTC core clk to recovered HDMI PixelClk, despite a separate
AXI clock. PYNQ3.0.1 HDMIInFrontend.mode calls native frame_width/frame_height;
both call VtcDetect and read VTC registers. AMD PG016 requires core clk to run
for register access and specifies SLVERR if stopped:
https://docs.amd.com/r/en-US/pg016_v_tc/clk-Pin
This explains the traceback/external abort much better than network-only or
SD failure. Physical retest after the fix is still pending.

The credit source previously read native VTC mode in every _healthy call,
including cleanup, so losing HDMI could kill the process before safe halt.
The fix keeps both startup mode checks before allocation but removes that
steady-state VTC read. Runtime still checks fixed-clock LiteX invalid geometry,
FIFO overflow/underflow, credit command/source faults, native pairing, identity
and exact VDMA completion. Missing input without a hardware fault still times
out; final accounting checks native edge progress. Wrong dimensions are
rejected by AXIS EOL/SOF geometry and selected-credit completion, rather than
by a continuously polled VTC mirror. Same-dimension timing-only changes were not checked by the old dimension-only
mode guard and remain unmeasured by this runtime check; automatic recovery is absent.
Legacy PynqSource/LiteXSource retain their existing native-mode paths.
Startup native configuration still requires input clock and is not fixed here.

## Impact and evidence

Reading order: sources.py start -> read/_wait/_healthy -> _release_credit ->
close/OneFrameDMA.stop_mmio, then sender.py _capture/close and gateware/capture.py.
Entry chain: sender.main -> Sender.run -> Sender.start -> _capture ->
LiteXCreditSource.read -> _wait -> idle/armed/complete -> _healthy.
Copy/release chain: _capture -> Sample.close -> release callback ->
_release_credit -> _healthy -> CreditControl snapshot/identity -> AXI GPIO.
Cleanup: Sender.run finally -> Sender.close -> source.close -> _healthy,
then disable gate -> raw DMA halt -> frontend.stop -> buffer.freebuffer.
The frontend stop is empty in pinned PYNQ3.0.1; native VideoStop is empty too,
and Py_Del_XVtc releases mappings, without a VTC register transaction.
Dynamic dispatch/callback edges were verified in source; the graph alone
misses nested predicate calls and cannot prove complete impact.

Graph generation2026-10-15T17:27:22Z reported no recorded gaps for sources,
sender, both test modules and gateware/capture. Vendor/operator files are
excluded and were read directly. No HDL or bitstream changed.

The regression replaces the native mode accessor with a trap only after
simulated clock loss, at idle, armed, completed, release and cleanup phases.
All5 cases failed on the unsafe native access before the source fix. Afterward
those paths raise SourceError, avoid delivery/ACK, halt before buffer free and
leave capture disabled. The armed-case fake MMIO needed explicit halt-on-stop
behavior; that fixture correction is not hardware evidence. The focused suite
then passed93 cases; full host suite passed312 with1 optional Migen/LiteX skip.
Final host suite with isolated geometry/FIFO guards and clock-loss timeout
without a fault flag passed316/1skip; separate
pinned Migen/LiteX environment passed45 gateware simulations in5.88seconds.
An initial attempt used a missing artifacts/gate-venv path and did not run;
the successful command used ../litex-network-router/.venv/bin/python.
Saved regression-red/green/full-host logs preserve actual outcomes.

Full M1 remains unqualified. Required next evidence includes fixed-runtime
physical loss with safe cleanup, explicit mode change/restart, normal capture
regression, and promotion of the warm-receiver attach procedure into a documented
clean-checkout production path. The previous011 normal pass used v11, not v12.

Changed comments were checked against PG016 and the actual runtime calls.
The first diagnostic-snapshot comment only removes the obsolete mode claim;
the new nearby comment explains the clock constraint. No unrelated comment
rewrites, new protocol, RTL, CAD build or hosted CI execution are claimed.

The final timeout regression also removes input without raising a gate fault:
acquisition times out, final accounting rejects missing native edges, and raw
halt precedes free. Real hardware halt with the clock gone remains pending.
A GPT-6.1 Sol medium review found no confirmed new defect in the bounded change;
it verified retained geometry rejection and comments. Its fresh focused command
PYTHONPATH=src python -m pytest tests/test_sources.py -q passed74 cases before
the extra timeout case; initial missing PYTHONPATH failed collection.

v12 archive SHA256837ca5b0b115f79bc66919a67a368a83477397061c5f0cb44dfd583a98bc1284
was staged to /tmp/hdmi-capture-newcard-017-v12 with source SHA256
babad497c165b84a5cbccc8a8112316752a3b46002a9023c5be6ec3b26726926.
017 bit/HWH readback hashes matched. No new overlay was loaded: board sudo
authentication expired before privileged preparation.013 is prepared as one
board-auth -> bounded root waiter -> PC-auth ->120second source workflow,
with native capture90second timer, hard waiter900seconds and no forced kill.
The root waiter will guard RS0/Halted1/gateoff before017 reload, set HPD without
native configuration, and wait for verified KMS readiness before capture.
It is syntax-checked and staged; privileged runtime and physical result pending.
The next checker allows20..105seconds for loss, correcting012's narrow window
without changing012 evidence. It also requires observed sender source failure,
safe cleanup, storage pass and no new kernel external abort; source-worker
nonzero child exit is now propagated. Manual action is still separately confirmed.
