# M1 physical bring-up

## Build 012 and first startup

The local 012 build passes setup 0.614 ns, hold 0.007 ns and pulse-width
0.264 ns, with zero critical CDC/DRC, bus-skew violations or internal
unconstrained endpoints. Remaining external TMDS/DDC/HPD timing assumptions
and vendor VTC multi-bit CDC warning are recorded in the build report.
This is a nominal build check, not electrical-margin or runtime qualification.

The archive and all three bit/HWH/manifest hashes match after transfer to the
board (`m1-012-transfer.log`). The first sender attempt failed importing
`VideoIn` from `pynq.lib.video` (`m1-012-status1.log`), before overlay loading
or DMA start. No M1 image or gate test was obtained. Exact installed PYNQ API
compatibility is being corrected before retry; the failed attempt is preserved.

## Corrected import and VDMA binding failure

Sender v4 imports VideoIn from its actual hierarchies module; 42 focused tests
pass. Its deployment archive hashes match. The second attempt successfully
loads build012, then fails constructing AxiVDMA because `s2mm_introut` is absent
from the parsed driver's interrupt attributes (`m1-012-v4-status1.log`). DMA
has not started and no capture buffer was allocated. This exposes an HWH/driver
interrupt integration gap that local stub tests did not cover. The board remains
available; no force termination or hardware reset was performed for this failure.

## Active metadata parser root cause

Read-only `Overlay(download=False)` inspection on the board confirms
`pynq.metadata.runtime_metadata_parser.RuntimeMetadataParser`, with empty
VDMA interrupt attributes, interrupt pins and interrupt controllers
(`m1-parser-inspect.log`). In contrast, the pinned legacy HWH parser discovers
the direct-PS VDMA interrupt at raw IRQ61. The active runtime metadata views
only traverse AXI interrupt controllers, and build012 has none. Thus the HWH
wire exists, but this deployed software does not route it to a driver interrupt.

The fix in progress adds a real AXI interrupt controller on PS GP0, with
capture interrupt inputs and its output connected to PS IRQ. No dummy interrupt,
polling bypass or synthetic metadata is used. Runtime parser validation must
precede the next hardware start. This newly reachable driver path also performs
controller initialization; it needs actual interrupt-delivery validation before
claiming functional capture.

## Build 013 first real frame, gate test and orderly shutdown

The real AXI interrupt controller restored native driver initialization. Input
locked to the PC's 640x480 / 25.2 MHz mode and the sender started. Optical frame
30078 matched every RGB byte (`m1-013-first-pixels.json`); contemporaneous scanout
metadata reports XR24, while the source performs its own framebuffer self-check.

The brief gate test recorded selected 4825 -> 4825 -> 4855 and dropped
66 -> 96 -> 96 across enabled/half-second-disabled/half-second-enabled snapshots.
Invalid stayed 1 and overflow/underflow stayed zero. `completed_frames` counts
observed complete geometry including discarded frames; it is not delivered-frame
count. Gate evidence: `m1-013-gate-and-stop.log`.

The first short qualification correctly rejected startup invalid=1 despite exact
pixels (`m1-013-short-initial.json`). Its baseline was sampled after enabling
capture; a non-atomic selected=0 read cannot prove the error preceded selection.
This run remains failed. The planned correction samples while gate is still held
disabled, retains startup errors explicitly, and rejects every later change.

SIGINT sent to the nohup/background process did not stop it. Cooperative SIGTERM
then completed native DMA halt: status 65536 -> 65537 (Halted asserted), followed
by freeing the five retained buffers exactly once and dma_shutdown_safe=true.
The process exited and the board remained responsive (`m1-013-stop-final.log`).
The existing PYNQ UioController destructor still reports an ignored event-loop
RuntimeError after cleanup; it is retained, not suppressed or claimed resolved.
No SIGKILL or forced timeout was used. The earlier M0 kernel-panic cause is still
unproven; this orderly shutdown is one successful execution, not a root-cause fix.

## Disabled startup baseline and sustained run

V5 verifies the reset-disabled setting in the manifest and paired HWH, starts
VDMA, then records counters while holding enable=0; only afterward does it enable
selection. New focused gate tests prove malformed unselected startup frames
produce no forwarded pixels. The runtime baseline reports enabled=false,
selected=0, invalid=1, overflow=underflow=0. That startup invalid remains visible;
every subsequent invalid/overflow/underflow change still fails. This is an
explicit attribution rule, not counter clearing or a new golden image.

The v5 short run passed 11/11 distinct exact optical frames in 5.184 seconds
(`m1-013-v5-short.json`). The separate 600-second run is in progress; its short
predecessor and a growing JSONL log are not final acceptance evidence. Source
self-check, contemporaneous DRM scanout metadata, and board resource sampling
are collected independently. No physical cable interruption occurs during this
window.

## Sustained result and follow-up

The separate v5 sustained run completed successfully:1,201 exact distinct frames
in600.505782seconds at1.999981FPS, with zero pixel/mixed/repeat/metadata/transport
errors. Client pause/reconnect also passed. A60→59.94Hz modeset triggered the
expected mode rejection and safe DMA halt-before-free; explicit restart then
passed10exactframes. See [consolidated qualification](m1-qualification.md) for
counters, resources, same-host timing and limitations. Physical cable removal
has been requested from the operator and remains pending; a working recovery
sender is available for that test. Do not treat the earlier in-progress notes
as the final sustained result.
