# Progress and handoff

2026-10-15 21:29 Asia/Taipei — direct KMS source probe002 passed: VT3,
XR24/640x480p60 (25200kHz),37 completed page flips, exit0, returnVT2 verified.
Omitted --vt is correct because default is3. This is source-only proof, not
board RGB qualification. Board has no sender and sudo authentication expired
(actual sudo -n requires password). Preparing source/overlay/receiver coordination
for real KMS-input capture. Evidence:[probe002](results/2026-10-15/kms-vt-probe-002.json).

2026-10-15 21:16 Asia/Taipei — first operator direct-VT probe returned toVT2
but source failed DRM-master acquisition. openvt pickedVT1, starting a GDM
greeter compositor (sessionc2/tty1). Runner now explicitly targets unusedVT3,
rejects occupied session VTs, and logs actual VT/session state. Revised local
sudo probe pending; source never produced a frame in the first VT test.

2026-10-15 21:09 Asia/Taipei — user requested HDMI source outside GNOME.
Notification suppression failed600s (1148/1201 exact); settings restored.
10-bit analytic GLES prototype passed15/15 with notifications but remains only
an isolated experiment. A DRM-lease prototype produced18 page flips then crashed
GNOME50.1 during revoke; main desktop restarted. No further lease retries.
DP-2 restored59.940, main monitor unchanged, banners=true. Board bounded sender
exited safely. Direct KMS C source and temporary-VT runner are built;9 source
tests pass, active-desktop master acquisition refuses safely. Direct-VT live
output/return remains unverified and needs local sudo. See[kms-source](kms-source.md).

2026-10-15 20:44 Asia/Taipei — frame difference reproduced and isolated to a
notification-triggered source-presentation failure mode. The first017 ten-minute
run failed (1189/1200 exact;7 one-LSB cases and4 damaged-marker cases). Fixed-ID
real-board notification regression: banners suppressed15/15 exact; enabled10/15
fail. No FPGA/capture tolerance changed. User authorized temporary suppression;
15-minute restore timer armed. Animated600s rerun `m1-017-v10-dnd` is active;
board PID11749, resource sampler11880. Diagnosis and limitations:
[frame difference](results/2026-10-15/frame-difference-diagnosis.md).

2026-10-15 20:27 Asia/Taipei — build017/v10 first real RGB capture passed:
11 distinct exact640x480 frames in5.399744s, zero pixel/mixed/repeat/metadata/
transport errors. Raw DMA0x11001 auto-halted, held IDs and sampling arithmetic
validated300native intervals=10acquisitions+290skips. Short-run evidence only;
ten-minute and interruption tests still required. Local source fix34e35dd.

017 CAD exit0: setup/hold0.401/0.014ns,56skewMET,0criticalCDC/DRC;256Gray+6reset
ASYNC_REG confirmed. Fresh HLS and actual exported RTL pass exact drain/stall
checks. Paired artifact hashes matched on board at
`/tmp/hdmi-capture-credit-017-v10/overlay-017`. Source PYTHONPATH is its parent.
Cooperative smoke shutdown halted safely before free; one selected-completed
frame was cancelled before acquisition commit at the boundary (101vs100),
outside the explicitly reconciled delivered window. UIO destructor warning retained.

New900-second sender launched for sustained qualification; startup PID10326 is
sudo, find the actual Python child before resource sampling or signaling. No
other sender remained at launch. Source/DRM fixture from20:17 stays active.
Next: wait listening, start600-second/600frame qualifier with resource samples,
then client pause/reconnect, mode and physical unplug/recovery. See
[smoke](results/2026-10-15/m1-017-smoke.md) and
[CAD](results/2026-10-15/credit-017-build.md).

2026-10-15 20:22 Asia/Taipei — current candidate017 is building from frozen
`artifacts/m1-project-017-source`; shell handle30743, console
`artifacts/m1-project-017-console.log`. Fresh HLS and four exact generated-RTL
drain cases passed; Vivado IP synthesis is running. No017 board capture yet.
Implementation commit34e35dd fixes the isolated copied color pipeline with
style=flp; original016 reproduces the five-pixel stall. Ordinary308tests pass
with one optional skip. Strict DMA/timing/CDC/DRC checks remain enabled.

The PC is unlocked with active640x480p59.94 animated GLES output. Bounded source
and read-only DRM logs use `artifacts/operator/m1-017-*` (2400seconds from20:17).
V10 source and resource sampler are hash-verified at
`/tmp/hdmi-capture-credit-017-v10`;017 overlay transfer waits for accepted CAD.
No board sender is running. Sudo refreshed noninteractively at20:20 while valid.
After strict build success, pair017 with this unchanged v10 source, run a short
exactRGB/accounting smoke, then600seconds/600newframes and interruption tests.

2026-10-15 20:12 Asia/Taipei — operator resumed with active HDMI and sudo renewed.
016/v10 now configured real input, selected SOF66/native67 and closed one credit,
but VDMA did not complete: zero acquisitions. Safe abort halted before free.
Actual generated-HLS simulation reproduces the cause: color_convert holds five
tail pixels when an isolated selected frame ends; pack-only drains completely.
Candidate repair is a flushable color pipeline with a generated-RTL regression
before fresh CAD. Additional DMA issues remain possible; M1 is incomplete.
See [drain evidence](results/2026-10-15/credit-016-hls-drain.md).

2026-10-15 09:22 Asia/Taipei — current candidate is build016 plus sender v10.
M1 remains incomplete. Build016 passed CAD with setup/hold0.399/0.033ns,
56 bus-skew checks MET, zero criticalCDC/DRC and verified synchronizer attributes.
Latest software tests:308 passed,1optional-dependency skip; dedicated gate/manifest:
64 passed. These local checks do not establish successful new physical capture.

The board-loaded016/v9 attempt acquired zero frames: PC ScreenSaver=true,
PowerSaveMode3 and inactive DRM DP-2 caused no incoming HDMI signal. Latest
read-only recheck still shows the desktop locked/output off, board alive and
no capture process. All CAD, shader and scanout processes have terminated.
User wake/unlock and replyDone are pending; HDMI should remain connected.
Do not restart capture until actual scanout is active. Existing overlay/network
permission persists; credential availability must be rechecked separately.

Use source PYTHONPATH `/tmp/hdmi-capture-credit-016-v10` with paired files at
`/tmp/hdmi-capture-credit-016/overlay-016/{capture.bit,capture.hwh,build-manifest.json}`.
Both package transfers matched SHA256. Current local commits include359ba31,
0390bb9 and53e23a9. Source/counter diagnostics and cleanup preserve known errors;
formal qualification requires clean source and cleanup counters. No images uploaded.

Next authorized actions: confirm active640x480p59.94/60 source, restart animated
GLES fixture with contemporaneous scanout logs, recheck sudo, run short smoke
requiring DMA autoHALT+IRQ and next-SOF-closed held identity with exactRGB. Only
then run600-second/600-new-frame qualification, client reconnect, source unplug
and mode-change recovery tests. No web/bypass/LCD work is started.

Evidence: [016build](results/2026-10-15/credit-016-build.md),
[diagnostic tests](results/2026-10-15/credit-fault-reporting.md),
[failed015timing](results/2026-10-15/credit-015-timing.md).

## Credit bring-up history

2026-10-15 — Build014 single-credit implementation and local checks completed;
first physical smoke failed automatic DMA halt; continued investigation required. Do not mark M1 complete. See
[the new checkpoint](results/2026-10-15/credit-014-build.md) for artifacts,
behavioral impact, 291 software tests and 62 gate/manifest tests. The new producer
is `--source litex-credit`; legacy013 requires `--source litex` and the qualifier's
explicit `--legacy-delivered-image-criterion`. Source accounting cannot be inferred
from old continuous-ring counts.

Build014 bit/HWH/manifest and v6 deployment packages are ready. Latest UART
preflight is `artifacts/operator/credit-ready-preflight.log`; sudo authentication
must be rechecked/renewed locally before board load. The first sender exited safely after a read timeout; no active DMA remains.
The optical fixture has a bounded duration and must be rechecked before use. User physical-unplug availability remains pending; never ask
them to unplug until a new capture is running. Subagents hit usage limits;
parent resumed direct checks and finished the local checkpoint.

[First build014 board attempt](results/2026-10-15/m1-014-bringup.md) records
zero delivered frames, safe halt-before-free, and the qualifier integration fix.

Build015 failed strict timing and was rejected. Build016 then passed CAD
(setup/hold0.399/0.033ns,56skewMET, no criticalCDC/DRC) and was board-loaded with
v9. Its first configuration found no HDMI signal because the PC screen was
locked/powered off (ScreenSaver=true, PowerSaveMode3; DRM DP-2 inactive). Sender
exited before DMA allocation/start; no hardware sender or fixture is active.
The user has been asked to wake/unlock the PC and replyDone, leaving HDMI connected.
This real source prerequisite is pending; don't reask overlay permission.
See [016checkpoint](results/2026-10-15/credit-016-build.md) and
[timing investigation](results/2026-10-15/credit-015-timing.md).
The paired016 artifacts and v9 package are transferred, with matching hashes.
V10 is the current source package, including truthful failure/cleanup counts;
it is transferred with matching SHA256 to `/tmp/hdmi-capture-credit-016-v10`.
Use that PYTHONPATH with the paired bit/HWH in
`/tmp/hdmi-capture-credit-016/overlay-016` for the next run. [Diagnostic evidence](results/2026-10-15/credit-fault-reporting.md)
records308 passing tests and1optional skip.
Next: verify source output active after operator reply, restart animated fixture,
run bounded smoke requiring autoHALT/IRQ plus held frame identity and exactRGB,
then renewed600-second run and physical/interruption tests. Sudo was noninteractively
refreshed at08:38 while valid, but may have expired during the operator wait;
recheck before restart. No images were uploaded.

## Preserved previous checkpoint


2026-10-15 Asia/Taipei — real LiteX HDMI capture sustained criterion passed;
source accounting and physical cable-removal qualification remain incomplete. User explicitly requests incremental
local commits as progress is verified; no push is authorized.

## Working path and evidence

PC USB-C/HDMI adapter → PYNQ-Z2 HDMI IN → LiteX gate → VDMA/PS DDR → PS Ethernet
→ Python uint8 RGB888 works at 640×480p60. Build013 and sender v5 delivered
1,201 distinct exact optical frames in 600.505782 seconds, 1.999981 FPS and
14.745458 Mbps. Zero bad/mixed/repeated frames, metadata/transport errors or new
invalid/FIFO events. Startup invalid=1 is explicitly attributed to unselected
input using a held-disabled baseline, not erased. Physical source sequence and
DDR-ring overwrite attribution remain unknown.

[Qualification report](results/2026-10-15/m1-qualification.md) contains evidence,
limits, counters, resource use and timing. [Bring-up](results/2026-10-15/m1-bringup.md)
preserves rejected attempts; [M0 history](results/2026-10-15/m0-bringup.md) retains
the unresolved earlier kernel panic and +1LSB source failures.

Gate half-second off/on counted30 dropped frames and resumed selection. Client
pause8seconds/reconnect passed6 exact distinct frames with13 backpressure drops.
Changing60→59.94Hz correctly stopped the sender during relock; DMA halted before
five buffer frees. Explicit restart recovered10 exact frames at59.94Hz. Automatic
mode recovery is not implemented. Existing UIO destructor warning remains.

Local integrated tests:195 passed,1 optional-dependency skip. Dedicated gateware:
17 passed,0skips. Build013 setup/hold0.516/0.020ns, all41bus-skewchecks MET, no
critical CDC/DRC or internal unconstrained endpoints; remaining warnings, external
I/O gaps, vendor waivers and startup simulation diagnostics are documented.

## Current operator step and runtime

The bounded recovery sender PID13150 exited normally after 600 seconds. Its
log confirms VDMA Halted before all five buffers were released, with
`dma_shutdown_safe=true`; the board remained alive. The source renderer and
scanout logger also exited with status zero. Evidence:
`results/2026-10-15/m1-recovery-duration-check.log`. The existing UIO destructor
warning occurred after safe cleanup. No current sender or pattern is armed.

The user was subsequently asked to reply when available, and to leave the cable
connected until a new test is armed. Physical removal has not been confirmed.
Do not reload an overlay or kill a process while DMA may be active. Cooperative
SIGTERM is handled; background nohup SIGINT was ignored. Confirm Halted before
buffer release. If native stop cannot complete, retain process/BOs and recover
physical hardware; never add forced SIGKILL. Recheck actual runtime before use.

Completion audit found an unmet P4 requirement: global PL counters and software
read IDs do not associate source frames with individual DMA buffers. The
36,000 selected / 32,359 acquired endpoint deltas cannot establish 3,641 overruns.
The delivered pixel test passed, but physical source skips and ring overwrite
counts remain unknown. A single-credit gate and fixed-slot one-frame VDMA reader are now being
implemented. Completion requires gate end-of-frame plus VDMA auto-Halted;
frame-count IRQ alone occurs at transfer start and is insufficient. Source ID
remains stable through the software copy/lease. Native VSYNC versus AXI SOF
tracking must distinguish lost input from intentional unselected frames. This is required M1 work, not an optional later enhancement.

Board UART is `/dev/serial/by-id/usb-Xilinx_TUL_1234-tul-if01-port0`,115200.
`tools/board_console.py` uses the already-authenticated session; sudo was renewed
locally after reset, but the latest read-only preflight now reports its
credential cache expired (`artifacts/operator/credit-preflight.log`). Board is
alive and no sender was found. Renew authentication only when the next board
experiment is ready, to avoid another idle expiry. No passwords belong in chat. Board link-local address is
`fe80::200:5ff:fe6b:1a0%enx98fc84e0c4e8` on this host. Temporary dedicated NM profile
`codex-hdmi-m0` remains active; prior connection UUID
`864ebd1d-48cd-3cc5-bddd-93475bb4700e` is saved. Temporary display snapshots are in
ignored `artifacts/operator/`. Restore only after pending hardware testing and
verified safe sender cleanup. No SD repair/reimage or global package change.

## Reproduction and scope

[Quickstart](quickstart.md), [build](build.md), [sender](board-capture.md),
[protocol](protocol.md) and [qualification](qualification.md) document setup.
Build013 artifacts are `artifacts/m1-project-013/{capture.bit,capture.hwh,build-manifest.json}`.
Rebuild scripts pin vendor/RTL dependencies. An isolated clean-checkout replay of `aa4e86e` completed with fresh pinned RTL,
both HLS packages and bitstream in `artifacts/clean-replay-001`. Setup/hold margins
are 0.568/0.017 ns; all 41 bus-skew checks pass, with no critical CDC/DRC or
internal unconstrained endpoints. Retained warnings and source hashes are in
[the clean-build report](results/2026-10-15/clean-build-report.md). This proves
legacy-path reproducibility, not on-board qualification of the newly built
artifact or the pending source-accounting changes. Build013 itself reused HLS
outputs generated locally in001. Real arrays remain in
ignored artifacts and were not uploaded. Web/bypass/LCD remain deferred.

User already confirmed640×480p≈60RGB888,>=1freshFPS for10minutes/>=600frames,
counted whole software drops, PS Linux TCP path, and temporary overlay/dedicated
network operations. Do not repeat first-round approval questions. The source is
this PC's verified USB-C→HDMI adapter and cable. See requirements for decisions.
