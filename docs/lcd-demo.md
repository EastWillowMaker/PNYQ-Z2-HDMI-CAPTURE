# Quick gateware LCD demo

The user authorized a quick demonstration on 2026-10-22, with FPS and latency
explicitly not completion gates. This prototype keeps scaling and SPI in PL.
It is separate from the proposed DDR-buffered full design.

The confirmed physical fixture is PYNQ-Z2 HDMI OUT (J9) cabled to HDMI IN (J10).
The existing changing 1080p30 HDMI pattern passes through that cable and the HDMI
receiver before the new preview tap. The camera alignment preview is separately
available at [localhost](http://127.0.0.1:8767/); the user confirmed it works with
the Brio 100 and can frame the LCD. It does not record or measure optical latency.

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
    --output artifacts/lcd-demo-build-004 \
    --reuse-hls artifacts/1080p30-loop-005/hls \
    --reuse-ip-cache artifacts/lcd-demo-build-003/vivado/capture.cache/ip \
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

The runner checks the bit/HWH hashes, loads the generic overlay, asserts HPD,
detects the source and observes LCD counters without starting VDMA. It leaves
the demo running after its observation period. `--attach` observes the same
already-loaded image without reprogramming; `--prepare-only` asserts HPD without
native source detection. Do not run this observer concurrently with PC capture.

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
`artifacts/lcd-demo-session/sim-integer-004.log` and `sim-fractional-004.log`.

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
Build004 is running with this revision. The final RTL passed static review and both pixel simulations pass;
routed timing and the on-board image remain unverified. The copied
IP cache did not avoid the IP synthesis jobs in this run.
AMD documents the explicit block-memory inference setting in
[RAM_STYLE](https://docs.amd.com/r/2023.2-English/ug912-vivado-properties/RAM_STYLE).
On-board results are pending. The earlier
[slow wiring probe](lcd-spi-smoke.md) and its user-confirmed colors are evidence
for that probe only, not this new bitstream.

## Review scope

Read the LCD RTL first, then `hardware/lcd_demo_attach.tcl` and
`hardware/lcd_demo.xdc`, followed by `scripts/build_lcd_demo.py` and
`tools/run_lcd_demo.py`. The existing `hardware/capture.tcl` changes only by
sourcing the optional demo attachment before address assignment.

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
It found no material defect in that scope. Physical SPI timing, the displayed
image and simultaneous PC capture require their own evidence; static review
and reduced-size simulation do not establish them.
