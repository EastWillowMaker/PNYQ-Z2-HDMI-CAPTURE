# External 1080p30 default: PC desktop and GUI check

The external scenario now defaults to 1920×1080 at 30 Hz in commit
`f3b4e2066c5b8d062e5570f13866f69cd8b04755`. The actual PC HDMI input reached **Capture is ready**, and the
host launcher displayed three complete RGB888 frames at 1920×1080 with
`source_origin=hdmi`, `capture_mode=1080p30` and no viewer error. The bounded
sender exited with status 0 and confirmed halted DMA. Both test applications
were closed after verification.

The PC launchers were run with `--scenario external` and no external-mode
override. The test reused the authenticated UART shell, automated the source
readiness pause for ten seconds, and bounded production capture to thirty
seconds after initialization. The actual GUI was instrumented only to observe
three frames and close. No screenshot or frame image was saved by this test.

Read-only DRM metadata on `card2-DP-2` reported an active 1920×1080 mode with a
74.25 MHz pixel clock and totals 2200×1125, corresponding to 30 Hz. The new EDID
was detected without manually changing PC display settings. This is source
configuration metadata, not an independent electrical pixel-clock measurement.
Five fixed-clock board observations measured approximately 30 VSYNC edges per
second with invalid-frame, overflow and underflow counters all zero.

The existing [build005 image](1080p30-build-005.md) was reused with its paired
HWH and manifest. It already passed routed timing and CDC checks. Its output
fixture remained enabled in the image, but J9 was unused: the PC supplied J10.
The input profile uses receiver `kClkRange=2`; no new FPGA build was required.
The board runtime remained the verified source in
`/tmp/hdmi-capture-1080p30-003/src`.

Post-capture GPIO checks found VDMA control 86032, status 69633 and capture
command 0: DMA halted, capture disabled and source counters still clean.
The source selected 60 frames during the bounded run; the GUI received three
before it closed. Selected frames are not a count of delivered GUI frames.
The current same-boot preparation receipt is
`/home/xilinx/.local/state/hdmi-capture/1080p30-prepared.json`, for the artifacts
under `/tmp/hdmi-capture-1080p30-002/overlay`. Recheck these temporary paths and
board state after a reboot.

Host validation passed **623 tests**, with one optional Migen-dependent test
module skipped. The updated default-selection and startup tests first failed
with the previous 1080p60 default, then passed with 1080p30. Input integrity,
DMA shutdown and explicit restart requirements were retained. Frame delivery
still targets 2 FPS; the HDMI input refresh rate is 30 Hz.

This is a short external-desktop check, not a new ten-minute qualification.
No independent comparison against the PC framebuffer's original pixel values
was performed. The earlier local-loop qualification and BMP byte-preservation
evidence remain separately scoped. The failed 1080p60 attempt is preserved in
[its report](1080p60-default.md).

The [machine-readable result](1080p30-external-default.json) records exact
image hashes, observations, scanout metadata, GUI result and local log paths.
