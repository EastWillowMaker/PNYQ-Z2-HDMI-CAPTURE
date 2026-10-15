# Progress and handoff

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
