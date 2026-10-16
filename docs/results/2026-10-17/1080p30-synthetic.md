# 1080p synthetic network and GUI measurements

The board ran the `df5410d` host/sender package from
`/tmp/hdmi-capture-1080p30-001/src`; its runtime source is unchanged by the
later clock-metadata commits. The archive SHA256 was
`c6018008648921a2e99e0d5d603f6eb69b996ee13ea20a020f2c8bfa757c8ef5`.
Compilation and profile import passed in the existing board PYNQ environment.
No new overlay was loaded and no native DMA was used for these measurements.

For the network run, the board sender used `--source synthetic --width 1920
--height 1080 --input-fps 30 --fps 5 --duration 25 --host :: --port 9040`.
The PC ran `hdmi-capture benchmark` against its scoped link-local address with
`--port 9040 --duration 15 --timeout 5`.

The client received 47 complete RGB888 frames in 15.008010 seconds: 3.131661 FPS
and 155.851493 Mbps of RGB payload. It reported zero protocol errors and one
observed frame-ID gap. The duration cutoff interrupted the next incomplete
frame, which was reported and excluded from totals. The board ended normally
after its bounded run; final counters included deliberate sampling and network
backpressure drops. See the [client report](1080p30-synthetic-network-001.json)
and [board log](1080p30-synthetic-board-001.log). This is combined synthetic
generation/serialization/TCP/parser throughput, not isolated Ethernet capacity
or an HDMI capture result. CPU, copy and memory costs are not separately
measured by this run.

A second bounded synthetic sender used port 9041 and a target of 2 FPS. The
actual Tk viewer connected through `CaptureClient`. A local harness invoked
the real save button and automated only the file dialog. It retained the exact
frame returned by the click-time freeze method, then decoded the saved BMP
with Pillow and compared every RGB byte. The result was 1920×1080×3 bytes,
24 bits per pixel and BMP compression code 0. Both RGB hashes were
`d33c482541882fb0af30fb3d2bee53f519b77d64d6981ae4a57dcaab8bc9ddbc`.
See the [GUI result](1080p30-synthetic-gui-001.json); the harness and image are
local at `artifacts/operator/check-board-gui-001.py` and
`artifacts/operator/board-gui-synthetic-001/`. The image is not committed.
The window closed normally after saving. Real HDMI GUI/BMP validation remains
pending.

The [one-FPS budget](1080p30-one-fps-budget.json) is a calculation, not a
measurement. It assumes one complete DMA frame and one sampled/delivered frame
per second for the single-credit path, while the HDMI source runs at 30 Hz.
It requires 6,220,800 RGB bytes per frame and 49.7664 Mbps of RGB payload before
protocol/network overhead. Actual capture, copies and resource use still need
measurement on the real path.
