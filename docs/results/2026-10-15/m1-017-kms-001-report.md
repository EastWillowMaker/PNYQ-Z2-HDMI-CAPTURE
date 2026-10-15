# Direct KMS real HDMI sustained capture

The strict delivered-image and single-credit accounting criteria passed:
1201 distinct complete640x480 RGB888 frames in600.155270seconds,
2.001149FPS and14.754070Mbps payload. Every byte matched the analytic source.
Pixel, mixed-ID, repeated-ID, metadata, transport and storage failures were zero.
This is **not full M1 completion**: safe sender/DMA shutdown was not established,
and new-path interruption/physical recovery tests remain outstanding.

## Path and evidence

PC direct DRM/KMS onVT3 -> USB-C/HDMI adapter/cable -> PYNQ-Z2 HDMI input ->
017 LiteX single-credit gate / HLS / VDMA -> PS Linux/v10 sender -> onboard PS
Ethernet -> PC Python. No GNOME composition, tolerance masking or golden-image
learning. Build017 SHA256 remains
`dbcfa96f370ade0655e08c610903e34af08535649b8d9363be4ac590b00cdf1b`.
The sender session was`6f83de87-3407-401d-b978-9bf07220c5a4`.

- `m1-017-kms-001.json`: completed strict qualifier summary, passed=true.
- `m1-017-kms-001.jsonl`: all1201 comparisons and per-frame source metadata.
- `m1-017-kms-001-smoke.json`: preceding real-pixel smoke passed.
- `m1-017-kms-001-evidence.json`: source-ID/resource/scanout crosschecks and hashes.
- `m1-017-kms-001-resources.jsonl`:130 rescued board-monotonic resource samples.
- `m1-017-kms-001-coordinator.json`: original orchestration result, including
  cleanup_error and shutdown_safe=null. It is preserved without rewriting success.
- `m1-017-kms-001-cleanup-failure.log`, `...-postcheck.log` and
  `...-board-rescue.log`: actual storage errors and sender crash evidence.

The720-second source run completed2700 page flips, reportedXR24,640x480,
25200kHz pixel clock (60Hz VGA), exited0 and verified return to originalVT2.
All1201 received optical IDs matched distinct logged KMS source IDs.
Host source-generation-to-complete-receipt latency:p50=0.253930s,
p95=0.363925s,maximum0.419247s. These include source sampling and capture time;
they are not pure Ethernet latency or precisely measured physical presentation.

Within the received-frame window,2397 DRM metadata samples were allXR24 with
zero read errors. One sample changed framebuffer IDs during its non-atomic
read.250ms sampling does not prove continuous physical scanout; exact pixels
are established for the actual1201 delivered frames.

Source accounting over the delivered interval:
36000 native intervals =1200 acquisition intervals +34800 intentional skips.
No acquisitions were missing between delivered frames. Native startup skips
remain unknown; global startup invalid_frames=1 was unchanged throughout the
qualified window under the existing disabled/zero-selected baseline contract.
The qualifier's physical_source_sequence_verified=false and
full_m1_qualification=false remain unchanged.

Resource samples filtered by **board** frame timestamps:115 samples in-window,
114 with CPU measurements (the initial CPU baseline isnull),17.97–20.58% of one
core, RSS79,372,288–81,219,584bytes, CMA free18,524–68,828KiB. These discrete
samples do not establish continuous peak usage or an error-free storage device.

## Known failure outside the pixel result

The coordinator's cooperative SIGTERM command could not execute`/usr/bin/sudo`:
Input/output error126, with EXT4 directory-read errors onmmcblk0p2. Later`ps`
and`tail` also failed withI/O errors. Bash builtins rescued the/tmp logs and
confirmed/proc/16610 absent. The sender recorded fatal SIGBUS in PYNQ
`pynq/lib/video/dvi.py:62` during source health checking, with no final
`dma_shutdown_safe` result. Process absence does not prove DMA is halted.

The SIGBUS timing and causal relationship to the SD I/O errors versus the
later end of the KMS source have not been established. Do not attribute it
solely to SD corruption or call it a normal shutdown. Earlier filesystem errors
were already documented, but these observations now prevent reliable normal
command execution. No fsck, SD reimage, forced DMA kill, or storage repair was
performed. Further board tests must wait for hardware/storage recovery; preserve
the SD contents before considering repairs. The original failed cleanup remains
part of this report even though the600-second pixel criterion passed.

## Before/after and scope

The desktop8-bit source produced1200frames with11 failures. Temporarily hiding
notification banners still produced53 failures among1201 frames. Replacing the
source presentation path with direct KMS, with unchanged017/v10 capture and
unchanged byte-exact acceptance, produced1201/1201 exact frames. This establishes
a working controlled source for this run; it does not certify arbitrary HDMI
sources, every desktop color conversion, or full runtime fault recovery.

This reporting change adds actual hardware evidence, not a new parser or DMA
implementation. No new software tests were needed for documentation/data only;
the prior9 compiled-source tests and298-pass/1-skip software run are separate
local evidence. No hosted CI was run and no real frame arrays were displayed or
uploaded. Endpoint arrays remain in ignored`artifacts/captures/m1-017-kms-001`.
