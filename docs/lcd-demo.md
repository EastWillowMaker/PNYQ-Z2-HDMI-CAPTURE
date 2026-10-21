# Quick gateware LCD demo

The user authorized a quick demonstration on 2026-10-22, with FPS and latency
explicitly not completion gates. This prototype keeps scaling and SPI in PL.
It is separate from the proposed DDR-buffered full design.

The confirmed physical fixture is PYNQ-Z2 HDMI OUT (J9) cabled to HDMI IN (J10).
The existing changing 1080p30 HDMI pattern passes through that cable and the HDMI
receiver before the new preview tap. The camera alignment preview is separately
available at [localhost](http://127.0.0.1:8767/); the user confirmed it works with
the Brio 100 and can frame the LCD. It does not record or measure optical latency.
Build006 now runs this loopback on the board. A fresh load detected 1920x1080
and counted 75 live uploads in 15.022 seconds. Local Brio snapshots show the
captured pattern on the panel and changes between observations.

## Data path and limits

The preview observes accepted RGB888 AXI stream transfers before the existing
single-credit PC capture gate. It never adds backpressure. Nearest-neighbor
scaling fits 1920x1080 into 480x270, centered in 480x320 with 25 black rows above
and below, then packs RGB565. The build also supports a separate VGA profile;
profile changes require a matching bitstream, not automatic mode switching.

One BRAM frame buffer is written while the SPI reader is idle. A candidate is
published only after the next source SOF confirms the expected complete frame;
wrong line length, extra pixels and FIFO faults reject it. The writer is frozen
throughout upload. Input frames arriving during upload are skipped. The SPI
clock is approximately 17.86 MHz (142.857 MHz divided by 8), before per-word gaps.
This deliberately trades refresh rate for a small, independently testable demo.

At startup, the LCD displays generated color bars until the first valid capture.
The prototype retains the last displayed image on missing input; text status
screens, automatic input-profile changes and advanced filtering belong to the
full design. Recovery at the next clean source frame is exercised in simulation;
physical reconnect behavior requires separate verification. No CPU pixel scaling,
pixel transfer loop, touch feature or external DDR preview DMA is used.

The PC capture route is retained in the block design. This demo observer leaves
its VDMA halted; simultaneous PC capture is not established by the demo run.
The new pin timing budget is a conservative demo assumption, not a manufacturer
electrical qualification. High-speed SPI and the earlier 30 fps / 100 ms targets are
not claimed.

## Build and run

The build reuses explicitly selected, copied HLS IP and reruns its isolated-frame
drain checks. Optional `--reuse-ip-cache` copies a Vivado IP synthesis cache;
Vivado selects matching entries by configuration and tool version, as documented
in [config_ip_cache](https://docs.amd.com/r/2024.1-English/ug835-vivado-tcl-commands/config_ip_cache).
The imported cache file hashes are recorded before use; the original cache is
not modified. It stages new receiver IP and preserves existing artifacts.

```sh
python3 scripts/build_lcd_demo.py \
    --mode 1080p30 --with-hdmi-output \
    --output artifacts/lcd-demo-build-006 \
    --reuse-hls artifacts/1080p30-loop-005/hls \
    --reuse-ip-cache artifacts/lcd-demo-build-005/ip-cache \
    --gateware artifacts/1080p30-gate-001/litex_capture.v \
    --vivado /home/eastwillow/Xilinx/2025.2/Vivado/bin/vivado
```

Choose a fresh output directory for each build. It must pass the existing
implementation, setup/hold, CDC and DRC checks before export. The new
`HDMI_LCD_DEMO_TCL` build hook is absent in ordinary capture builds. Demo source
hashes and reused HLS hashes are saved in its source manifest; the exported
manifest identifies the prototype explicitly.

Copy the matching `capture.bit`, `capture.hwh`, `build-manifest.json` and
`tools/run_lcd_demo.py` to the board. Stop other FPGA owners before loading:

```sh
sudo -n env XILINX_XRT=/usr /usr/local/share/pynq-venv/bin/python -u \
    run_lcd_demo.py /path/to/demo-build --seconds 30
```

The runner checks the bit/HWH hashes, loads the overlay, asserts HPD,
detects the source and observes LCD counters without starting VDMA. It leaves
the demo running after its observation period. `--attach` observes the same
already-loaded image without reprogramming; `--prepare-only` asserts HPD without
native source detection. Do not run this observer concurrently with PC capture.
Input detection uses PYNQ's 60-second default; the tested loopback takes about
14 seconds to produce valid video after programming. A missing input can take
up to that timeout to report failure. `--seconds` controls observation time
after successful detection.

On the tested PYNQ 3.0.1 image, the default graph metadata parser rejects the
scalar AXIS tap in the generated HWH. The runner selects PYNQ's legacy HWH
parser for this bitfile and restores the device method after construction.
Programming still uses the normal full-overlay download. It clears the previous
graph metadata pickle before download because the legacy parser does not replace
it; the bitstream and HWH files are not edited. Other PYNQ versions are unverified.

`uploaded_frames` counts live uploads only, excluding initial color bars. Status
bits 4:0 are the controller state; 5 memory initialized; 6 panel ready; 7 capturing;
8 bad candidate; 9 live frame pending; 10 receiver reset; 11 SPI busy; 12 LCD reset
level; 13 awaiting next-SOF closure; 23:16 rejected-frame count; 31:24 FIFO-fault
edge count. These counters support digital execution evidence, not optical latency.

## Verification record

The pin-level simulation checks SPI initialization, address windows, RGB565
pixels, black borders, immutable uploads, frame-boundary publication and rejection
of malformed/faulted frames with subsequent recovery. Run it with:

```sh
iverilog -g2012 -Wall -s lcd_demo_tb -o /tmp/lcd-demo.vvp \
    hardware/lcd_demo.v hardware/lcd_demo_tb.sv
vvp /tmp/lcd-demo.vvp
```

The default 32x16 to 8x4 and fractional 16x16 to 11x11 simulations pass,
including every diagnostic and live panel pixel. The fractional case exercises
non-integer scaling; it is not a full-size VGA simulation. The checker also
covers malformed and overlong input, faults and recovery. Logs are retained in
`artifacts/lcd-demo-session/sim-integer-006.log` and `sim-fractional-006.log`.

Build001 failed block-design validation before synthesis: the scalar tap replaced
inferred AXIS connections without explicitly including the frontend driver.
The attachment now connects the frontend, existing gate and LCD tap together.
The failed logs remain in `artifacts/lcd-demo-build-001/`. Build002 passed block
design validation and its generated Verilog confirmed all five stream signals
connected to the receiver, gate and LCD. Synthesis then mapped the framebuffer
to 28,800 distributed RAM primitives, which exceeds the device; the owned build
was stopped. Its logs remain in `artifacts/lcd-demo-build-002/`. The corrected
RAM uses a muxed single write port, a separate synchronous read
and explicit block-memory inference. Isolated synthesis passed with 80 RAMB36E1
blocks, no distributed RAM and zero critical warnings/errors; see
`artifacts/lcd-bram-check-001/`. Both pixel simulations pass after that correction.
Build003 completed routing but failed the existing export gates: setup slack
was -2.830 ns, while hold slack was +0.050 ns. The worst path ran from the
receiver's SOF bit through the scaler's oversized error arithmetic to the row
selector. Three SPI outputs also failed the assumed setup budget because of
long routes from fabric registers to pins. The generated `lcd_spi_clock` did
resolve correctly at 56 ns (17.857 MHz). This bitstream was not exported or
loaded. The next revision shortens scaler logic and places the three SPI data
and control output registers in I/O blocks; timing budgets remain unchanged.
Build004 also failed export: setup slack was -1.320 ns, with the worst path
from the source underflow counter through fault detection to the framebuffer
write enable. The three requested IOB registers could not be packed because
their outputs required fabric routing (Place 30-722). The copied IP cache did
not avoid the synthesis jobs. Neither failed bitstream was loaded.

The next revision adds a register stage for accepted pixels together with fault
and reset signals, and a dedicated output stage for all four SPI signals. The
SPI stage delays SCK, MOSI, CS and DC together by one system-clock cycle. The
build selects a copied IP cache before creating IP. Both pixel simulations pass after these changes, including stalled-SOF and
partial-frame reset cases. Build005 reused 37 cached IP synthesis results. Its routed report confirms all
four SPI output registers in OLOGIC sites: CS X1Y120, SCK X0Y18, MOSI X0Y20,
and DC X0Y24. Static review found no material input/output alignment defect.
Overall setup still failed at -0.968 ns (162 endpoints); the reported worst
paths drive framebuffer write enables and startup-pattern data. This image was
not loaded. The next revision registers the complete RAM write command together
before the memory port, with a drain state before declaring initialization
complete. Both simulations pass, including checks that the last startup pixel
is stored before initialization completes and no write command overlaps an LCD
upload. Build006 passed the unchanged export checks: setup slack +0.291 ns,
hold slack +0.015 ns, and zero failing setup/hold endpoints. It reused 38 cached
IP synthesis results. The Luna watcher confirmed successful completion and all
four SPI output registers in OLOGIC. The changes do not relax timing requirements.
AMD documents the explicit block-memory inference setting in
[RAM_STYLE](https://docs.amd.com/r/2023.2-English/ug912-vivado-properties/RAM_STYLE).

On-board loading first failed in PYNQ's graph metadata parser before programming.
The legacy-parser adapter passed metadata parsing and full programming, but the
native input detector timed out on two fresh loads with its 10-second budget.
A subsequent attach detected 1920x1080 and counted 75 live uploads in 15.022
seconds, approximately 4.993 uploads/s. A concurrent register probe then showed
pixel-clock lock throughout startup and detector enable remaining set. VTC
dimensions and lock arrived between 14.072 and 14.323 seconds; the first live
LCD upload followed by 14.573 seconds. This disproved the suspected lost-enable
reset for that run and showed that the 10-second limit was too short. VTC
register interpretation follows AMD's
[driver definitions](https://github.com/Xilinx/embeddedsw/blob/xilinx_v2022.1/XilinxProcessorIPLib/drivers/vtc/src/xvtc_hw.h).

With the timeout restored to PYNQ's 60-second default, a fresh full load passed
input detection and all 15 observation samples. The live counter advanced from
5 to 80 in 15.021992 seconds (4.992680 uploads/s), with no rejected-frame or
FIFO-fault count in the sampled LCD status. The runner's halted-VDMA and disabled
PC-gate checks passed. This is a measured demo rate, not a performance guarantee.

The Brio was idle, so GStreamer captured two local 1920x1080 JPEG snapshots
about 35.66 seconds apart. The assistant inspected both: the LCD shows the
analytic loopback pattern rather than the startup bars. The patterned LCD
region changes primarily in red, consistent with the source's changing frame
term; sampled tabletop and board regions provide a static comparison. The
camera view is rotated relative to logical landscape and is soft and reflective.
These images establish visible output and change, not pixel-exact color,
electrical margin, or optical latency. The panel fit and exact RGB565 pixels
are checked by the pin-level simulation. The earlier
[slow wiring probe](lcd-spi-smoke.md) and its user-confirmed colors are evidence
for that probe only, not this new bitstream.

The exported bitstream SHA-256 is
`7309bffd254a46ab0da1020760fafc974f118341934d740b4f9a204aa9b6ed80`.
The [build manifest](results/2026-10-22/lcd-build-006-manifest.json),
[initial parser failure](results/2026-10-22/lcd-run-006-parser-failure.log),
[fresh-load detector timeout](results/2026-10-22/lcd-run-006-detector-timeout.log),
and [successful attach](results/2026-10-22/lcd-attach-006.log) preserve these results.
The final evidence is the [startup trace](results/2026-10-22/lcd-startup-probe-006.log),
[fresh-load run](results/2026-10-22/lcd-run-006-startup.log), and
[first](results/2026-10-22/lcd-webcam-006-a.jpg) and
[second](results/2026-10-22/lcd-webcam-006-b.jpg) camera images.

The final runner SHA-256 is
`0ddea17a8fb8269958c54fd93350681f6fa3b3f3ddb3487f00fad0f865dab2a6`.
It is installed on the board as `/tmp/lcd-demo-006/run_lcd_demo.py`.
The [postflight check](results/2026-10-22/lcd-postflight-006.log) verified that
hash, method restoration, absence of the stale metadata pickle, halted VDMA,
disabled PC capture, and a live upload counter that had reached 971.
The matching host package is
`artifacts/lcd-demo-session/lcd-demo-006-verified.tar.gz` (SHA-256
`a2b7170323e1daf7da4b719370b0ae00f9c81193a6f0bf953ae627bf458a805e`).
The FPGA remains running after the observer exits; the files under `/tmp` do
not provide automatic boot persistence.

## Review scope

Read the LCD RTL first, then `hardware/lcd_demo_attach.tcl` and
`hardware/lcd_demo.xdc`, followed by `scripts/build_lcd_demo.py` and
`tools/run_lcd_demo.py`. The existing `hardware/capture.tcl` adds optional demo cache selection before
IP creation and sources the demo attachment before address assignment.

The build entry point stages the demo sources and calls `capture.tcl`, which
sources `lcd_demo_attach.tcl`. The generated block design connects the receiver
`v_vid_in_axi4s_0/m_axis_video_*` signals to both the existing capture gate and
the LCD inputs. The existing gate alone drives ready. Within the LCD engine,
accepted transfers feed the scaler and frame validator; complete candidates
freeze the BRAM writer while the SPI engine sends the window and RGB565 pixels.
The runner loads the exported overlay, enables HDMI detection and reads status;
it neither scales nor transfers pixels. Its post-load DMA checks do not protect
a previously loaded design: stopping other FPGA users before loading remains
a required precondition.

An independent static review covered these connections, endpoint scaling,
frame closure, fault handling, SPI initialization and the corrected RAM ports.
It found no material defect in that scope. A further independent review checked
the legacy metadata adapter, cache invalidation, method restoration, and the
startup timeout against the pinned PYNQ 3.0.1 sources and board trace. The routed
timing report and camera observations add implementation and visible-output
evidence. Electrical margin, physical reconnect recovery, other PYNQ versions,
VGA on the board and simultaneous PC capture remain unverified.
