# PYNQ-Z2 M1 build

## 1080p30 build

The qualified VGA build below remains the default. The new explicit
`1080p30` profile targets 1920×1080 progressive at 74.25 MHz, with totals
2200×1125 and receiver `kClkRange=2`. Its pixel timing is separate from the
142.857132 MHz capture AXI clock. The [fresh build005](results/2026-10-17/1080p30-build-005.md)
passed CAD and strict timing/CDC/DRC checks. Real J9→J10 short captures,
held-buffer ownership and GUI BMP saving also passed; see
[loop measurements](results/2026-10-17/1080p30-loop-performance.md).
The [ten-minute production criterion](results/2026-10-17/1080p30-completion.md)
also passed1,200distinct exact frames over600.076875seconds at1.999744FPS,
followed by safe shutdown and storage/kernel checks.

Generate matching gateware with the pinned environment, then build into a new
directory. For the optional same-board output-loop fixture:

```sh
python -m gateware.generate --width 1920 --height 1080 \
  --output artifacts/1080p30-gate-001/litex_capture.v
python scripts/build_capture.py --mode 1080p30 --with-hdmi-output \
  --output artifacts/1080p30-loop-001 \
  --gateware artifacts/1080p30-gate-001/litex_capture.v \
  --stage bitstream
```

Use the pinned generator environment and executable paths described below.
Omit `--with-hdmi-output` for an RX-only build. The optional output uses a PL
analytic pattern and independent PS FCLK0-derived clocks, with the pinned
`rgb2dvi` serializer. It adds no output DMA or frame-buffer owner. It runs a
fixed timing while locked, ignores output HPD/EDID, and is not active bypass.
The generated pattern includes a changing optical frame ID and must match
`tools/hdmi_pattern.py --mode 1080p30` byte for byte after RGB decoding.

Build preparation writes a profile-specific EDID, RX clock constraints and
`capture-mode.json`. The final manifest binds geometry, clock configuration,
timing and paired bit/HWH hashes. Optional output source identities are also
recorded. Keep each profile's artifacts separate; the runtime rejects a
manifest that does not match the explicitly selected profile. Use `--mode
1080p30` on both `hdmi_capture.sender prepare` and `hdmi_capture.sender
--source litex-credit`, and on `tools/qualify_capture.py`. The baseline
`--source pynq` adapter remains VGA-only.

Runtime observations verify dimensions and 24-bit pixels, not the input pixel
clock or refresh rate. Measure actual source cadence and disclose that limit
in board results. Neither a mode declaration nor protocol acceptance proves
1080p HDMI operation. See [primary-source research](research.md) for board
electrical limits and [output-loop operation](output-loop.md) for the verified
fixture's preparation and clock-readiness ordering.

For fast clock/reset metadata diagnosis, prepare a fresh staged output and run
the reduced TX block-design check. It creates no bitstream and does not access
the board:

```sh
python scripts/build_capture.py --mode 1080p30 --with-hdmi-output \
  --output artifacts/tx-check-inputs-001 --stage prepare
vivado -mode batch -source hardware/check_hdmi_output_bd.tcl \
  -log artifacts/tx-check-001.log -journal artifacts/tx-check-001.jou \
  -tclargs artifacts/tx-check-inputs-001 artifacts/tx-check-project-001
```

It requires `HDMI_OUTPUT_BD_CRITICAL_COUNT 0` and `HDMI_OUTPUT_BD_PASS`. The
check exercises actual Vivado inference with the staged serializer IP. It does
not replace combined block-design, synthesis, routing or on-board validation.

The build preserves Linux and Ethernet on the hard Zynq PS. It creates a
video-only overlay: J10 HDMI RX → upstream 24-bit video frontend → generated
LiteX capture gate → color converter → pixel packer → write-only AXI VDMA →
PS HP0 DDR. There is no soft CPU. The PYNQ base image and sibling project are
not overwritten or used as build output.

Source is pinned to [PYNQ v3.0.1, commit
93ddd21ab623883590a8c8b07f0b157b2855da4b](https://github.com/Xilinx/PYNQ/tree/93ddd21ab623883590a8c8b07f0b157b2855da4b).
The upstream Z2 base Tcl requires Vivado 2022.1. This integration extracts its
receiver procedures and complete PS7 configuration into an isolated project;
it does not change or bypass that upstream version check. This is a separate
integration port to the locally installed Vivado/Vitis 2025.2, requiring its own
validation.

## Reproduce

Run from the repository root with CPython 3.12 (tested: 3.12.13), Git, Icarus
(`iverilog` and `vvp`), and licensed Vivado/Vitis2025.2 already installed.
Create the gateware environment inside
ignored `artifacts/`; no sibling checkout or global Python installation is needed:

```bash
export PYTHON_BIN=python3.12 # Or the path to your installed CPython 3.12.
"$PYTHON_BIN" --version
mkdir -p artifacts/vendor
"$PYTHON_BIN" -m venv artifacts/gate-venv
artifacts/gate-venv/bin/python -m pip install --index-url https://pypi.org/simple \
  'migen @ git+https://github.com/m-labs/migen.git@e19524c963a8342952840983047557707fbe0b6a' \
  'litex @ git+https://github.com/enjoy-digital/litex.git@b2759f69bcae8be0357fb2ee5eebe216365d1f00'
git clone --branch v3.0.1 https://github.com/Xilinx/PYNQ.git artifacts/vendor/PYNQ-v3.0.1
test "$(git -C artifacts/vendor/PYNQ-v3.0.1 rev-parse HEAD)" = \
  93ddd21ab623883590a8c8b07f0b157b2855da4b
artifacts/gate-venv/bin/python -m gateware.generate --output artifacts/litex_capture.v

# Set these to your installed executable paths; no installation is performed.
export VIVADO_BIN=/opt/Xilinx/2025.2/Vivado/bin/vivado
export VITIS_RUN_BIN=/opt/Xilinx/2025.2/Vitis/bin/vitis-run
"$VIVADO_BIN" -version
"$VITIS_RUN_BIN" --version
"$PYTHON_BIN" scripts/build_capture.py \
  --output artifacts/m1-build-001 \
  --gateware artifacts/litex_capture.v \
  --vivado "$VIVADO_BIN" --vitis-run "$VITIS_RUN_BIN" \
  --stage bitstream
```

Use a new output directory on every attempt. The tested Migen/LiteX revisions
and installed Python-source hashes are recorded in `gateware/dependencies.json`;
generation rejects differing source content or versions. Source checkouts used
for qualification were clean at those exact commits. A separate clean checkout
at `aa4e86e` executed this bootstrap with an explicit
public PyPI index, both fresh HLS builds, and complete implementation/export;
see [the replay report](results/2026-10-15/clean-build-report.md). The explicit
index avoids inheriting a stalled host-specific package mirror. The source
hash checks passed in the fresh environment. `013` itself reused HLS001; the
separate replay confirms the recipe's fresh-HLS path and is a different paired
artifact, not an additional physical qualification.

`--stage prepare` verifies the source commit and writes extracted RX Tcl and
constraints without vendor tools. `hls` rebuilds just `color_convert` and
`pixel_pack`. `project` creates/validates the block design and generates IP and
the wrapper. `bitstream` additionally implements and exports matching
`capture.bit`/`capture.hwh`, with setup/hold slack checks. No stage programs
hardware, changes Linux, or edits the SD image. Existing output directories
cause failure rather than replacement. Source download and output are ignored
under `artifacts/`; the source license headers remain in the checkout.

Every HLS/project/bitstream build first checks the actual synthesized HLS pair
with `scripts/check_hls_drain.py OUTPUT/hls`. It must drain an isolated frame
without subsequent input and preserve exact data/boundaries under backpressure.
The isolated color_convert copy uses pipeline style=flp; the original default
stalling pipeline retained five final pixels in build016. Small/VGA regression
cases, missing modules and timeouts gate CAD. See the
[before/after evidence](results/2026-10-15/credit-016-hls-drain.md).

The extraction retains board-specific PS DDR configuration, including training
and board delays; it disables unused GP1, S_AXI_GP0, HP2, and FCLK3 ports.
FCLK0=100 MHz drives PS AXI control, FCLK1=142.857 MHz drives streams/HP0, and
FCLK2=200 MHz drives the receiver reference. Video pixel-domain resets follow
the recovered PixelClk lock. The exact v3.0.1 HDMI input pins are retained. The input clock is
constrained to 39.682540 ns (25.2 MHz), matching the VGA-only preferred EDID
timing, and receiver `kClkRange` is set to 5. Do not disable IP clock constraints, critical
warnings, DRCs, or timing checks to obtain a bitstream.

## Software seam

Hierarchy names preserve `video/hdmi_in/frontend`, `color_convert`,
`pixel_pack`, and `video/axi_vdma` for the PYNQ 3.0.1 drivers. A write-only VDMA
has no HDMI-output `writechannel`; code must construct
`VideoIn(overlay.video.hdmi_in.description, overlay.video.axi_vdma)` explicitly
if the hierarchy auto-binding does not supply the DMA. The existing full-base
`BaseOverlay` class is unsuitable for this reduced peripheral design.

The real `system_interrupts` AXI INTC receives VDMA, frontend GPIO, and VTC
interrupts at indices 0, 1, and 2, then drives PS IRQ 61. It is mapped on GP0
and uses the 100 MHz control clock/reset. This topology matters to the installed
PYNQ metadata parser: direct concat-to-PS wiring in `012` was understood by the
legacy HWH parser, but the active `RuntimeMetadataParser` found no interrupt
controllers or pins. Overlay construction consequently failed before DMA start
with a missing `s2mm_introut` attribute. `013` restores the base design's real
controller topology; an offline execution of the exact installed metadata
parser confirms the VDMA interrupt mapping. This establishes metadata routing,
not physical IRQ delivery or Linux UIO correctness.

The additional AXI GPIOs are in the stream clock domain. Find addresses using
the generated HWH/`Overlay.ip_dict`, rather than copying a base-overlay address:

| IP | channel 1 (`+0x00`) | channel 2 (`+0x08`) |
|---|---|---|
| `video/capture_control` | enable output, reset 0 | completed frames input |
| `video/capture_counts` | observed frames input | selected frames input |
| `video/capture_errors` | dropped frames input | invalid frames input |
| `video/source_health` | native FIFO overflow episodes | native VSYNC rising edges |
| `video/source_faults` | AXI FIFO underflow episodes | not present |

Capture defaults disabled. Configure the frontend, start VDMA, and install the
frame pool before enabling the gate; disabled frames are drained and counted as
intentional drops. GPIO direction must remain output for enable and input for every counter.
Reading a counter is atomic within a 32-bit access; multiple counters are not a
coherent snapshot. Enable is sampled at the accepted SOF, and disabling capture
waits for that boundary. The gate does not retract malformed pixels already
written by DMA. The sender must verify the captured geometry and discard
frames associated with errors; counters alone are not a DDR ownership scheme.
The gate works before color conversion, so its data seam does not establish the
final RGB888 channel order.

## Local evidence and limits

On 2026-10-15, local Vitis 2025.2 successfully synthesized and packaged the
unmodified v3.0.1 `color_convert` and `pixel_pack` sources. Pixel-packer HLS
reported all loop constraints satisfied and estimated Fmax 218.26 MHz. These
are HLS estimates, not physical timing closure. Local Vivado 2025.2 catalog
resolved dvi2rgb 1.7, v_vid_in_axi4s 5.0, v_tc 6.2, axi_vdma 6.3, PS7 5.5,
and both HLS IPs; the complete PS7 property list instantiated successfully.
Evidence is under `artifacts/build-probe/` and `artifacts/m1-project-001/`.

Build validation and implementation results are recorded below as they become
available. Instantiation and catalog presence do not prove successful checkout of every implementation/IP feature,
physical timing, image loading, PYNQ driver compatibility, captured pixel
correctness, or sustained HDMI operation. Physical M1 and hosted CI remain
unverified until matching bit/HWH are loaded and gate counters correlate with
received real-source frames. Interlaced/non-640x480 input, malformed geometry,
HDMI overflow during prolonged DMA stalls, unsupported clocks, and reconnect
recovery need separate qualification. Full-frame rejection and DDR ring-buffer
ownership are not implemented by the one-beat gate.

### Block-design validation

`artifacts/m1-project-003/console.log` records successful `validate_bd_design`,
IP target generation, wrapper creation, and clean process exit. This final
validation had no ERROR or CRITICAL WARNING. IP status reports the vendor
VDMA, VideoIn, VTC, PS7, and interconnect licenses as `Included`. Ordinary
warnings remain visible, including upstream GPIO interface pin overrides and
module video datatype metadata propagation. Earlier failed attempts are retained
in `m1-project-001` and `002`: empty return value from external-port creation,
read-only parameter writes, and missing module clock association were corrected
in the integration/generator. They are not evidence of final success.

The first routed `m1-project-003` attempt failed the export timing guard:
WNS -2.502 ns, WHS 0.012 ns. It also reported critical DRC AVAL-46 because
the inherited 8.334 ns input constraint with multiplier 5 gave a 599.952 MHz
MMCM VCO, below its 600 MHz minimum. No qualified bit/HWH package was exported.

During the implementation attempt, `runme.log` for the LiteX gate, pixel packer,
VTC, and control GPIO records successful `Synthesis`/`xc7z020` license checkout.
The generated HWH confirms active-low external reset inputs on all three reset
controllers and 32-bit VDMA S2MM with MM2S disabled. These checks cover the
actual inferred configuration, rather than attempted writes to read-only IP
parameters. They do not establish final routing/timing or board operation.

### Corrected VGA clock and EDID contract

The pinned `boards/ip/dvi2rgb_v1_7/src/TMDS_Clocking.vhd:64` documents the
range-specific multiplier. Lines 180–187 instantiate `CLKFBOUT_MULT_F =
kClkRange*5`, output divider `kClkRange`, and fixed MMCM parameters. DRP inputs
are tied off at lines 209–216. The upstream base's `kClkRange=1` cannot be
assumed to adapt automatically to a VGA pixel clock. For the target mode, range
5 gives VCO 630 MHz at 25.2 MHz (629.375 MHz at 25.175 MHz), serial clock 5x,
and pixel clock 1x. Its theoretical VCO input range is 24–48 MHz; this project
supports only progressive 640x480 near 60 Hz. 720p/1080p inputs are forbidden
for this overlay because their pixel clocks exceed that range.

The original IP package enum exposes only 1/2, despite the RTL generic already
supporting 5. Attempt `004` demonstrated that Vivado rejects the unmodified
package's value 5. Preparation now copies just the pinned RX IP into
`output/rx_ip`, adds enum value 5 in its local `component.xml`, and preserves its
TMDS clock arithmetic. The reset source changes described below are applied
separately. It preserves all license/source headers. Attempt `005` was
stopped before completion to replace its unsuitable 720p EDID.

`scripts/build_edid.py` derives a VGA-only EDID from the pinned first-party
PYNQ/Digilent `720p_edid.data`. It retains manufacturer/product/chromaticity
metadata, updates the block to EDID 1.4 with an 8-bit DVI/RGB-only input and
range-limits-only descriptor, replaces all timing advertisements, and
recalculates the checksum. The isolated package retains the
ROM filename `720p_edid.data` to preserve IP-XACT file references, but its
content now advertises only 640x480: preferred detailed timing 25.2 MHz, totals
800x525, 60.0 Hz, negative H/V sync, plus the established VGA 59.94 Hz variant.
No standard timing or extension block advertises a higher resolution.
The input constraint covers the faster preferred timing. The EDID verifier
passes this supported input and rejects checksum corruption, wrong geometry,
extra extension blocks, higher-resolution established timings, and interlace.
Its preferred timing fields match the VGA timing family in the
[Linux DRM EDID implementation](https://github.com/torvalds/linux/blob/v6.1/drivers/gpu/drm/drm_edid.c).

EDID is an advertisement, not an electrical firewall: a source can ignore it
or retain a forced higher-resolution configuration. Confirm the source's VGA
mode before enabling HDMI or loading this overlay. An out-of-range source must
not be used to qualify receiver operation. Even accepted VGA pixels can reach
VDMA before the gate has detected a geometry error; runtime checks and counter
errors must invalidate those captured frames. No unsupported-clock or malformed
physical-input execution test is claimed.

`m1-project-012` is the build with VGA clock/EDID, shared-domain resets,
source health counters, and disabled-by-default capture. Its local implementation
and review completed successfully; physical qualification is a separate step.
It runs with a 20-minute bound and two parallel jobs. Final output includes
`capture.bit`, `capture.hwh`, and `build-manifest.json` containing their SHA256
identities, the gateware hash, source commit, geometry, stream/pixel clocks,
receiver range, EDID hash, tool version, and measured setup/hold slack. The
manifest helper also verifies that the generated HWH receiver range is 5.

Independent validation uses upstream `utils/edid-decode` from v4l-utils commit
`95ad25f6a77a0a6650f5f657ac2c5046efcd04a0`, compiled into the ignored artifact
folder without installing packages. `artifacts/build-probe/vga-edid-decode.log`
reports **EDID conformity: PASS**, RGB 4:4:4 / 8-bit DVI, exactly the two VGA
timings, and checksum `0xb7`. Its first check caught a missing range descriptor
in attempt `006`; that attempt was stopped before completion and replaced by
`007`. The conforming EDID has range limits 59–61 Hz vertical, 31–32 kHz
horizontal and max dot clock 30 MHz, with range interpolation disabled.
These limits are not additional timing advertisements and do not prevent a
source from transmitting a manually forced unsupported mode.

### Receiver lock reset crossing

Attempt `007` routed with WNS -3.229 ns, WHS 0.017 ns, and one failing setup
endpoint. It was rejected by the export guard. The path was from the
receiver `TMDS_ClockingX/aLocked_reg` in independent RefClk=200 MHz to
`rstpixel/U0/EXT_LPF/lpf_int_reg` in the recovered pixel-clock domain.
Its inferred 0.029 ns setup requirement cannot represent these unrelated
clocks. The inherited direct lock-to-reset-controller connection lacked a
proper synchronizer; unchanged upstream source did not guarantee safe behavior
when reused here.

`hardware/capture_lock_sync.v` now bridges the receiver lock with the vendor's
`xpm_cdc_async_rst`, active-low reset interpretation, four destination stages.
Loss of lock asserts immediately even if PixelClk stops; lock availability
releases only after four PixelClk rising edges before reaching the pixel reset
controller. No broad clock-group exception or warning suppression is added.
XPM's own synchronizer attributes and targeted reset constraints describe the
actual crossing; ordinary pixel-domain setup/hold paths remain constrained.

The actual vendor XPM model was compiled locally with XSIM 2025.2.
`hardware/capture_lock_sync_tb.sv` passes startup, four-edge qualification,
stopped-clock lock-loss assertion, and chatter recovery; log:
`artifacts/build-probe/lock-sim/simulation.log`. This is functional simulation,
not measured metastability or physical HDMI reconnect evidence. Initial XSIM
elaboration attempts failed for missing global/XPM simulation units and wrapper
timescale; the final run compiled those units and passed.

### Shared resets and source health

`008` passed setup/hold (0.221/0.017 ns) but a detailed CDC report found three
critical CDC-7 paths in inherited decoder `SyncBaseOvf` source registers:
PixelClk reset deassertion was unsynchronized to RefClk. `009` added per-instance
bridges and passed setup/hold (0.229/0.017 ns), but its six critical CDC-11 reset
fanout/reconvergence paths were not accepted as benign. Neither candidate was
qualified for physical use.

Preparation now adds one shared RefClk `ResetBridge` at the receiver root,
alongside its existing shared PixelClk reset. The three `TMDS_Decoder` instances
receive both shared resets; `SyncBase` uses the source-domain reset for its
source register and the destination-domain reset for destination synchronizers.
Independent lane reset-release events are avoided. `hardware/sync_base_reset_tb.vhd`
executes the actual patched VHDL for both reset values and crossing directions,
including stopped clocks and reset chatter. It checks that data cannot escape
before the source domain has qualified reset release. This is digital simulation
and structural CDC evidence, not a metastability-rate or cable-reconnect test.

`hardware/source_health.v` counts upstream `v_vid_in_axi4s` overflow assertion
episodes in PixelClk and VSYNC rising edges before the FIFO/gate. Coherent
32-bit Gray CDC transfers both counters to the stream clock. Underflow episodes
are counted directly in the stream domain. A held-high flag counts one episode;
episodes are not exact lost-frame counts. Counters initialize once per FPGA
load and remain monotonic modulo 2^32 across clock-lock resets. Resets only rearm
edge histories, so a stopped/restarted clock does not create a binary counter
reset jump through the Gray synchronizers or invent a VSYNC event.

The actual vendor XPM XSIM model passes the procedural monitor tests for 512
events, binary carries, stopped clocks, resets, startup faults, and episode
counting. All XPM assertions remain enabled. Two vendor S-2 diagnostics occur
at 20 ns on the first source-history sample while counters are zero and pixel
reset is asserted; no later assertion diagnostics occur. The simulation thus
passes its procedural checks with recorded startup diagnostics, not an
error-free assertion run. Full logs and replay commands are retained under
`artifacts/build-probe/source-health-sim/`.

Vivado's vendor `xpm_cdc_gray.tcl` automatically installs scoped CDC-6 waivers
for the two Gray bridges; this build adds no custom CDC waivers. AMD's
[XPM_CDC_GRAY documentation](https://docs.amd.com/r/2025.2-English/ug953-vivado-7series-libraries/XPM_CDC_GRAY)
describes this waiver and requires the destination to sample at least twice
per source-clock period. Here 142.857 MHz exceeds twice 25.2 MHz, and the source
counters change by zero or one and do not reset during FPGA lifetime. Standard
CDC report totals include the vendor waiver treatment.

The source-health output is essential: gate counters sit after the FIFO and
cannot detect complete native frames lost before SOF reaches the gate. Sender
qualification requires non-null source counters, zero new overflow/underflow
and invalid-frame events, and whole-frame/optical checks. It aborts on new fault
events before delivering the owned frame. Startup counters and deliberate gate
drops are recorded separately from the sampling interval.

Attempt `010` failed clock metadata validation because the upstream PixelClk
interface had no declared frequency and Vivado defaulted it to 100 MHz. The
local IP-XACT now declares 25.2 MHz. Attempt `011` revealed that a scalar VSYNC
tap overrides a bundled video-interface signal; the original color-swap VSYNC
input became unconnected. `012` explicitly connects the receiver output,
original consumer, and monitor to the same scalar net; generated HWH confirms
the shared signal and `C_DOUT_DEFAULT=0`. Both invalid attempts were stopped.

The build now snapshots health/lock RTL in its new output directory and hashes
those exact inputs. It refuses critical BD messages after validation/IP
generation, critical CDC/DRC findings, bus-skew violations, negative setup/hold,
and critical/error messages in child synthesis/implementation logs. Parent
Vivado message counts alone exclude child processes, so both are checked.
Warnings and constraints are preserved.

The retained VTC CDC-6 warning is in AMD's 32-bit control/readback CDC logic.
[PG016 describes internal CDC between video and AXI clocks](https://docs.amd.com/r/en-US/pg016_v_tc/S_AXI_ACLK),
and [requires clock-frequency constraints for both domains](https://docs.amd.com/r/en-US/pg016_v_tc/Constraining-the-Core).
This supports the intended use of the vendor interface; it does not prove this
board's driver behavior under clock loss. Access registers only after the video
clock is present. Missing external DDC/HPD delay warnings remain: DDC is sampled
through two-stage synchronizers and glitch filters in `TWI_SlaveCtl.vhd:105`,
and HPD is an asynchronous management level. Five input/two output timing-delay
gaps include TMDS inputs; their electrical margin is not characterized by
internal setup/hold closure. Do not claim full I/O timing qualification.

### Local CAD result (012; runtime IRQ discovery failed)

The paired outputs are `artifacts/m1-project-012/capture.bit`, `capture.hwh`,
and `build-manifest.json`. The local run completed with Vivado 2025.2; all
eight manifest file hashes were read back and matched the exact snapshots.
The bitstream SHA256 is
`6378c1f7cb7d490fd06845230be52a023b0e6f996a13c9d307388f34ad3afe34`;
the HWH SHA256 is
`c27f1cad24599bb4c8f39afb2a92ead3f1061a78cd09478007f11e4b958afe74`.
No original board image was overwritten by this build.

| Check | Local result |
|---|---|
| Setup / hold / pulse-width slack | 0.614 / 0.007 / 0.264 ns, no failing endpoints |
| Internal clock/unconstrained endpoints | zero no-clock and zero unconstrained internal endpoints |
| Bus skew | every reported constraint met |
| CDC | zero critical; 130 CDC-3 info, three CDC-9 info, one vendor VTC CDC-6 warning |
| DRC | zero error/critical; 12 warnings and one advisory retained |
| Parent and child run logs | no ERROR or CRITICAL WARNING diagnostics |
| Utilization | 5,937 LUTs, 12,476 registers, 7.5 BRAM tiles, nine DSPs |
| External delay coverage | five input and two output delay gaps retained; not complete I/O timing qualification |
| FPGA device/CPU | xc7z020clg400-1; no MicroBlaze/soft CPU in HWH |

`cdc.rpt` recognizes the four-stage lock bridge as CDC-9 and the shared decoder
resets no longer have the CDC-7/CDC-11 findings of earlier attempts. The Gray
counter crossings are recognized synchronizers. The seven omitted gate RTL
ports are outputs only (`active`, `errors`, `frame_id`, `output_frame_id`,
`valid_frames`, `orphan_pixels`, `stall_cycles`); all eight inputs are connected.
This is checked against the actual generated instance in `port-review.json`,
not inferred from source intentions.

Remaining DRC warnings describe HLS DSP pipelining, LUT equation terms and one
unused routing load; the advisory concerns write-first RAM. The retained VTC
CDC warning and external timing gaps are described above. Do not interpret a
positive WNS or zero critical CDC count as full HDMI electrical/driver or
metastability qualification. The first authorized physical smoke then exposed the interrupt-discovery
failure described above, before DMA start. `012` is retained as CAD evidence
and is not the final usable overlay. Reconnect, interlace, alternate clocks,
malformed physical inputs, prolonged downstream stalls, and hosted CI remain
unverified.

The first packaging parser assumed every HWH parameter had a `VALUE` attribute
and failed on an unrelated optional field in `008`. The corrected parser
selects only the required unique `kClkRange=5` parameter, preserves rejection
of missing/wrong/duplicate values and receivers, and passes eight regression
cases in `hardware/test_build_manifest.py`. The packaging repair does not
change the routed design.

### Local build result (013)

`artifacts/m1-project-013/{capture.bit,capture.hwh,build-manifest.json}` are
paired outputs from the real AXI INTC repair. All eight manifest hashes match
readback of the exact isolated inputs/outputs. The bitstream SHA256 is
`33f6a640cf2a6e068515f8a4e8e85ff60d4015d323a6ce67b5332479cd0e7a73`;
the HWH SHA256 is
`9d2dfef03a329807471635e3f8804e9981f7a41ee7aa905d6eb10024310c6aeb`.

| Check | Local result |
|---|---|
| Setup / hold / pulse-width slack | 0.516 / 0.020 / 0.264 ns; zero failing endpoints |
| Internal clocks/endpoints | zero no-clock and unconstrained internal endpoints |
| Bus skew | all 41 reported constraints met |
| CDC | zero critical; 131 CDC-3 info, three CDC-9 info, one VTC CDC-6 warning |
| DRC | zero error/critical; 12 warnings and one advisory retained |
| Parent/child logs | zero ERROR or CRITICAL WARNING diagnostics |
| Utilization | 6,083 LUTs, 12,567 registers, 7.5 BRAM tiles, nine DSPs |
| Exact installed RuntimeMetadataParser | 012 negative and 013 positive mapping reproduced offline |
| External delay gaps | five input/two output; retained limitation |

The routed checkpoint review finds all 256 Gray destination registers
(two 32-bit buses, four stages) with `ASYNC_REG=1`; the preserved Tcl and log
are `artifacts/m1-project-013/post-review.tcl` and `post-review.log`.
`port-review.json` verifies the same seven output-only gate omissions and no
missing inputs. Health/reset RTL and receiver patch snapshots match their
manifest hashes; enabling capture still defaults to zero.

This qualifies the artifact for the authorized 640x480 physical smoke under the
stated clock/source contract. It does not establish physical IRQ delivery,
Linux UIO behavior, correct pixels, sustained acquisition, reconnect recovery,
or complete M1 acceptance. Those newly reachable driver/DMA paths must be
verified on the board; `012` demonstrates why parsing alone is insufficient.

### Subsequent physical execution

Build013 with sender v5 subsequently passed the real HDMI→LiteX→Ethernet
600second criterion (1,201 exact distinct frames), gate control, client reconnect,
and explicit recovery after a supported VGA refresh change. The native PYNQ
interrupt driver delivered frames and PSIRQ61 counts advanced. Full evidence and
remaining physical cable-test, per-buffer sequence and electrical-margin limits
are in [the qualification report](results/2026-10-15/m1-qualification.md).
These executions supersede earlier “physical not yet run” build checkpoints;
they do not turn the retained CDC/model/I/O limitations into full qualification.
