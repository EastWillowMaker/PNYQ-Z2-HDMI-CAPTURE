# Build016 real input and downstream drain failure

The operator woke/unlocked the source PC and renewed board sudo. At20:06
ScreenSaver=false and PowerSaveMode0; DRM DP-2 was active640x480p59.94.
The animated GLES source passed its synthetic framebuffer self-check. Scanout
sampling observed XR30 initially and XR24 subsequently; this is metadata
sampling, not continuous physical pixel proof.

Build016/v10 loaded and configured real HDMI. Disabled startup baseline had
64 native edges, zero selected frames, one unselected invalid episode and
zero FIFO overflow/underflow. The gate subsequently selected SOF66/native67,
completed one credit with next-SOF closure and no sequence/command fault.
VDMA remained running0x10000/control0x15011 and acquisition timed out: zero
frames acquired or delivered. Cleanup changed control to0x15010 and status
to0x10001 before freeing the allocation; dma_shutdown_safe=true. The process
exited normally through its error path; board remains responsive. The existing
UIO destructor warning remains. Raw evidence: m1-016-v10-smoke-board.log.

The first receiver connection raced startup and was refused; its separate
m1-016-v10-smoke.json records zero frames. This is not pixel validation.

## Reproduced downstream defect

Icarus simulated the actual build016 synthesized color_convert and pixel_pack
Verilog. Feeding an isolated8x4 frame and waiting200 cycles produced only27
color pixels, three EOL and18 packed words. The expected counts are32 pixels,
four EOL and24 words. The test fatally rejects this incomplete drain.
Adding16 further input pixels advances the color total to43, retaining the
same five-pixel tail. Bypassing only color_convert produces all32 pixels and
24 packed words with four EOL. No real image was inspected or uploaded.

This distinguishes the third ranked hypothesis (an upstream boundary/data
pipeline problem) from the initial Fsync-only hypothesis. It establishes a
real downstream defect exposed by isolated frame selection, even though that
HLS C++ was unchanged from the continuously fed legacy capture. It does not
exclude an additional VDMA completion issue after drain is repaired.

The [AMD pipeline documentation](https://docs.amd.com/r/2025.1-English/ug1399-vitis-hls/Flushing-Pipelines-and-Pipeline-Types)
describes default stalling and flushable pipelines. The candidate will change
only the isolated color_convert copy to pipeline style=flp, retain vendor
coefficients/interfaces and pixel packing, and require the generated RTL drain
test before CAD. Original vendor checkout and prior evidence stay preserved.
Physical behavior of that change remains unverified.

The durable generated-RTL regression now rejects original016 with exit1 at
27/32 color pixels. Fresh build017 changes only the copied color pipeline
pragma to style=flp; its four pre-CAD cases all pass:8x4 and640x480, each with
and without input bubbles/output backpressure. Identity coefficients are written
through the actual AXI-Lite interface; every color pixel, packed byte, SOF/EOL
and stalled-output stability is checked. VGA drains307200 pixels/230400 words/
480EOL with no following input. Missing synthesized modules also reject.
See hls-drain-regression.txt and hls-drain-source-hashes.json. The ordinary
software suite remains308passed/1optional skip in3.24s; no hosted CI was run.
CAD and physical tests for017 remain pending at this checkpoint.

Probe: artifacts/build-probe/hls-drain-016/{tb.v,isolated.log,extra.log,pack-only.log}.
The isolated test exits1; pack-only exits0. Source artifacts are from016,
not a hand-written model of the HLS implementation.
