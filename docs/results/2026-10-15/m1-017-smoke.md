# First exactRGB single-credit board capture

Build017 plus unchanged sender v10 received real640x480p59.94 HDMI from the PC
through the generated LiteX gate, color conversion, pixel packing, one parked
VDMA buffer, PS DDR and onboard PS Ethernet. The five-second default formal
metadata smoke passed:11 distinct byte-exact RGB888 frames in5.399744seconds,
zero pixel/mixed/repeat/metadata/transport errors. First/last NPY and metadata
remain in ignored artifacts/captures/m1-017-v10-smoke; no image was viewed/uploaded.

Each delivered sample reported automatic HALTED and IRQ (raw0x11001), slot0,
held coherent identity, next-SOF closure, stable ownership until release, no
command/source-sequence fault, and zero new invalid/overflow/underflow. Startup
invalid1 is retained from the proven disabled, zero-selected baseline.
Public source_errors/source_cleanup_errors/source_overruns/source_invalid_frames
were all0. Native IDs936→1236, acquisitions30→40 and intentional skips840→1130
reconcile300=10+290. Accepted SOF stayed native−1. These are observed short-run
metadata and exact image checks, not a full ten-minute qualification.

The sender had already acquired29 frames before the first delivered endpoint;
its network ready-slot losses are separately counted. No startup native skip
count is invented. Source format/range remain unknown metadata; controlled test
pixels establish exactRGB for this source only.

Raw receiver evidence: m1-017-v10-smoke.{json,jsonl}; bit/HWH/provenance and CAD
limits: [build017](credit-017-build.md). The next authorized test is a new
600-second/600-distinct-frame session with resource/scanout/source records, then
client reconnect and source interruption/recovery. M1 remains incomplete.

Cooperative SIGTERM cleanup left DMA already auto-halted0x11001/control0x15010,
with zero source/cleanup errors and dma_shutdown_safe=true. The50ms trailing
monitor saw four native edges without fault. Final totals were100 acquired,
101 selected-completed: one selected DMA frame was cancelled before acquisition
commit at the shutdown boundary. It is outside the delivered accounting window;
the reported2868 source sampling skips cover acquisitions1–100, not all native
edges through shutdown. Network_errors1 follows normal client close; ready-slot
replacements86 and client-discarded1 are separately reported, not pixel failures.
The retained PYNQ UIO-destructor/no-current-loop warning still occurs. Inspect
m1-017-v10-smoke-board.log for final status and the boundary distinction.
