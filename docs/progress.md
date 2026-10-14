# Progress and handoff

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
counts remain unknown. Per-slot ownership metadata and a single-credit capture
alternative are being evaluated against the actual installed DMA driver before
implementation. This is required M1 work, not an optional later enhancement.

Board UART is `/dev/serial/by-id/usb-Xilinx_TUL_1234-tul-if01-port0`,115200.
`tools/board_console.py` uses the already-authenticated session; sudo was renewed
locally after reset. No passwords belong in chat. Board link-local address is
`fe80::200:5ff:fe6b:1a0%enx98fc84e0c4e8` on this host. Temporary dedicated NM profile
`codex-hdmi-m0` remains active; prior connection UUID
`864ebd1d-48cd-3cc5-bddd-93475bb4700e` is saved. Temporary display snapshots are in
ignored `artifacts/operator/`. Restore only after pending hardware testing and
verified safe sender cleanup. No SD repair/reimage or global package change.

## Reproduction and scope

[Quickstart](quickstart.md), [build](build.md), [sender](board-capture.md),
[protocol](protocol.md) and [qualification](qualification.md) document setup.
Build013 artifacts are `artifacts/m1-project-013/{capture.bit,capture.hwh,build-manifest.json}`.
Rebuild scripts pin vendor/RTL dependencies. A complete isolated clean-checkout replay is now running in
`artifacts/clean-replay-001`; fresh pinned RTL and both HLS packages have been
rebuilt, and implementation is in progress. Final CAD results remain pending.
Build013 itself reused HLS outputs generated locally in001. Real arrays remain in
ignored artifacts and were not uploaded. Web/bypass/LCD remain deferred.

User already confirmed640×480p≈60RGB888,>=1freshFPS for10minutes/>=600frames,
counted whole software drops, PS Linux TCP path, and temporary overlay/dedicated
network operations. Do not repeat first-round approval questions. The source is
this PC's verified USB-C→HDMI adapter and cable. See requirements for decisions.
