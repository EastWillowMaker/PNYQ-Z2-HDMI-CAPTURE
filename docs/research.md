# Initial research

Initial research: 2026-10-15 Asia/Taipei, static unless stated. Current on-board
M1 results and source/build scopes are in the[2026-10-16 completion report](results/2026-10-16/m1-completion.md).
The initial findings and skill versions below remain historical records.

## Loaded skills

No Skill invocation tool is exposed. Read local files directly, including the
underlying skills rather than only the wrapper. Local directory has no Git revision;
SHA256 identifies what was read:

| Path under `/home/eastwillow/.agents/skills/` | SHA256 |
| --- | --- |
| grill-with-docs/SKILL.md | 7de372c13488f1ee96cc11cd8907b56b6809cc93eef776eeddd37de6b6cbe3fe |
| grilling/SKILL.md | befdff1e27a1dfe2a294d5871169ac1afe16d983911daa4f32627514a48c1e15 |
| domain-modeling/SKILL.md | 7b925d7b1e341a2eeae33ad68a8a8c0ab889a38ddd22a7598e4c240e5a7556a3 |
| domain-modeling/GLOSSARY-FORMAT.md | 21dcc40cdec8e151a829b98ab1517c1867bc444e3665134a98c6983411996801 |
| domain-modeling/ADR-FORMAT.md | 944c92aa790e8fbdc9199640b170979abb8a34ba8d0fe18c2a01a63bce140ca0 |

Also read codebase-memory/SKILL.md and research/SKILL.md. Grilling and research
explicitly request fact-finding agents; delegated environment and hardware inspection.
No accepted architecture ADR yet: proposed path remains subject to shared understanding.

## Source findings

- [PYNQ-Z2 base overlay, version 3.1](https://pynq.readthedocs.io/en/v3.1/pynq_overlays/pynqz2/pynqz2_base_overlay.html),
  HDMI and Rebuilding sections: Z2 has PL HDMI connected through memory, and board-specific
  build files. This supports a baseline candidate, not proof of local overlay health.
  Its 1080p warning prevents treating 1080p60 as a qualified board specification.
- [PYNQ video documentation](https://pynq.readthedocs.io/en/latest/pynq_libraries/video.html),
  Configuration/Pixel Format sections, accessed 2026-10-15: default is 24-bit BGR;
  RGB channel ordering must be intentional. Latest docs are not a pinned board driver.
- [TUL Reference Manual v1.1, 2019-10-28](https://dpoauwgwqsy2x.cloudfront.net/Download/PYNQ_Z2_User_Manual_v1.1.pdf),
  printed pp6–7,12–16: PHY clock feeds H16 and PHY reset disables it; DDR attaches to
  PS, board-specific configuration matters; Ethernet is PS MIO. Link-loss clock
  behavior is untested. See detailed hardware research for pin crosschecks.
- PYNQ upstream master resolved with `git ls-remote` to
  `d90670c69f7b71ea1a5d23aaa3e0ec713ff5fa9f`. It is a research reference, not a
  selected compatible build dependency or the board's installed version.
- [Existing on-board Ethernet experiment](results/2026-10-14/pynq-z2-ethernet.md):
  independent transport evidence, no HDMI data. Existing SD boot reported filesystem
  errors; no repair/reimage performed. This remains a deployment risk.

Detailed bounded audits: [environment](environment-audit.md),
[board/source feasibility](hardware-research.md). Missing facts there are gates,
not assumptions to replace with generic PS7 or another board's pinout.

## Recommended minimum path (not approved)

M0: HDMI IN → existing Z2 frontend → VDMA → PS DDR → owned RGB888 copy →
single-client TCP sender → PC parser → numpy RGB array/.npy.

M1: insert LiteX-generated complete-frame control and statistics into the capture
stream; reuse verified frontend/VDMA, PS board preset and Linux Ethernet. Vivado
integrates IP, constraints and clocks; LiteX emits participating PL logic; PS owns
buffer lifecycle and sender. No new soft CPU. Integration costs include stream
SOF/EOL semantics, clock/reset crossing, DMA framing and rebuilding old PYNQ IP
under available tools. No build compatibility or license pass is claimed.

Completed frames form the later web/LCD consumer boundary; forwarding remains a
separate consumer with its own future timing/latency acceptance. M0 does not prove
bypass or LiteX functionality. Do not infer DDR-free routing from `tie()`.

## Payload calculation (executed with Python)

`b = width * height * 3; payload_bps = b * delivered_fps * 8`

| Mode | bytes/frame | MiB/frame | Mbps at 1 FPS | Mbps at 60 FPS | DMA write MB/s at 60 FPS |
| --- | ---: | ---: | ---: | ---: | ---: |
| 640×480 | 921600 | 0.87890625 | 7.3728 | 442.368 | 55.296 |
| 1280×720 | 2764800 | 2.63671875 | 22.1184 | 1327.104 | 165.888 |
| 1920×1080 | 6220800 | 5.9326171875 | 49.7664 | 2985.984 | 373.248 |

These are arithmetic, not throughput measurements. 640×480 rows are 1920 bytes
packed, but actual VDMA stride is still to inspect. Continuous 60 Hz capture can
write 55.296 MB/s even when only 1 FPS is sent. At 1 FPS, one full PS copy adds
0.9216 MB/s read plus 0.9216 MB/s write; socket/kernel copies add further traffic.
For full-sized MTU1500 IPv6 TCP segments without options, 1440 payload bytes consume
1538 wire bytes including Ethernet header/FCS/preamble/IFG: ratio 1.0681, excluding
ACKs/options/short segments/application metadata. Actual overhead and CPU remain
unmeasured. A 1 Gb/s link cannot carry 720p60 raw RGB888 payload.

## 2026-10-15: requested KMS timing is not complete physical proof

Official Linux DRM documentation separates userspace `mode` from driver
`adjusted_mode`, and documents connector scaling modes. Sources:
https://cdn.kernel.org/doc/html/latest/gpu/drm-kms.html#c.drm_crtc_state
and https://cdn.kernel.org/doc/html/latest/gpu/drm-kms.html#standard-connector-properties.
Read on2026-10-15. They support checking adjusted hardware timing/scaling, not
a conclusion that this AMD GPU is currently scaling. Local directKMS reports
640x480/25200kHz and page flips, yet no board native VSYNC edges are observed.
Host-visible EDID contains4K although the paired FPGA artifact was built for
VGA. Actual source scaling, bridge behavior and EDID changes remain unverified.
The inactive desktop user's DRM access returns EACCES while VT3 is active;
a connector-property query is prepared for after normal VT restoration.

## 2026-10-16: 1080p capture and same-board loop feasibility

This review uses the locally pinned PYNQ v3.0.1 source at commit
`93ddd21ab623883590a8c8b07f0b157b2855da4b`, plus the current capture build
sources and its clean implementation report. No 1080p bitstream was built or
loaded, and no 1080p signal was measured on the board. The timing below is a
feasible first candidate, not a qualification result.

The recommended first mode is **1920×1080 progressive at 30 Hz**, using the
standard 2200×1125 total timing and 74.25 MHz pixel clock. Derive it from the
pinned PYNQ 1080p60 mode by keeping its porch positions and halving the pixel
clock: 88 front-porch pixels, 44 horizontal-sync pixels, 148 back-porch
pixels; 4 front-porch lines, 5 vertical-sync lines, 36 back-porch lines. The
same source lists 1920×1080 at 148.5 MHz/60 Hz. This calculation gives exactly
30 Hz because 74.25 MHz / (2200 × 1125) = 30. The source-derived timing is
standard, but 1080p30 is not an existing mode in the pinned output driver; it
needs a new mode entry or explicit VTC/clock programming.

| Mode | Pixel clock and approximate TMDS rate per data lane | Assessment |
| --- | --- | --- |
| 1080p30 | 74.25 MHz; 742.5 Mbit/s | Recommended candidate. It uses the same pixel clock as the PYNQ 720p60 mode, while keeping the requested 1080-line image. The PYNQ-Z2 differential pins are documented as officially supported only through 720p, so the actual 1080p30 input and output still need cable/device testing. |
| 1080p60 | 148.5 MHz; 1.485 Gbit/s | Present in PYNQ's software timing table, and its video documentation says the 142 MHz one-pixel-per-clock stream pipeline can accommodate active video once blanking is counted. However, PYNQ and TUL warn that the board does not meet the official HDMI 1080p electrical specification; some devices may work. Do not make 60 Hz the initial acceptance timing. |

The PYNQ video-library documentation says the Z1/Z2 DVI front end can reach
1080p in its design, but the differential pins are officially rated only up to
720p because of their speed rating. The Z2 overlay documentation separately
warns that 1080p is outside the board's official HDMI specification, although
some connected devices may work. Together these sources support trying 1080p30
at the 720p60 pixel clock; they do not establish a guaranteed 1080p30 mode or
connector compatibility. Sources: [pinned PYNQ video guidance](https://github.com/Xilinx/PYNQ/blob/93ddd21ab623883590a8c8b07f0b157b2855da4b/docs/source/pynq_libraries/video.rst), [pinned PYNQ-Z2 overlay guidance](https://github.com/Xilinx/PYNQ/blob/93ddd21ab623883590a8c8b07f0b157b2855da4b/docs/source/pynq_overlays/pynqz2/pynqz2_base_overlay.rst), and the [TUL reference manual, pages 15–16](https://dpoauwgwqsy2x.cloudfront.net/Download/PYNQ_Z2_User_Manual_v1.1.pdf).

For receive clocking, the pinned Digilent `dvi2rgb` RTL generates a 5× serial
clock and its clocking entity uses `kClkRange` as both the multiplier/divider
selector. At 74.25 MHz, range 2 gives a 742.5 MHz MMCM VCO and the desired
74.25 MHz pixel clock plus 371.25 MHz serial clock. That is within the RTL's
stated 600–1200 MHz VCO range. The current VGA build uses range 5 at 25.2 MHz,
sets an input-clock constraint for 25.2 MHz, and advertises only VGA through its
EDID. The new mode therefore needs a matching range-2 receiver configuration,
74.25 MHz input-clock constraint, 1080p30 EDID, and revised static geometry
checks. The upstream package's supported range-2 choice already exists; the
local package extension for range 5 was specific to VGA. The [pinned receiver
Tcl](https://github.com/Xilinx/PYNQ/blob/93ddd21ab623883590a8c8b07f0b157b2855da4b/boards/Pynq-Z2/base/base.tcl), [clocking RTL](https://github.com/Xilinx/PYNQ/blob/93ddd21ab623883590a8c8b07f0b157b2855da4b/boards/ip/dvi2rgb_v1_7/src/TMDS_Clocking.vhd), and [current build clock contract](build.md#corrected-vga-clock-and-edid-contract) document these facts.

The stock PYNQ design has separate HDMI input and output ports and separate
package pins. Its [pinned constraints](https://github.com/Xilinx/PYNQ/blob/93ddd21ab623883590a8c8b07f0b157b2855da4b/boards/Pynq-Z2/base/vivado/constraints/base.xdc) place RX clock/data on N18/P19, V20/W20, T20/U20, and N20/P20, with input HPD on T19 and DDC on U14/U15. TX uses L16/L17, K17/K18, K19/J19, and J18/H18, with its HPD signal on R19. These sets do not overlap, and PYNQ's base design includes both directions. This establishes a feasible pin assignment for a J9 HDMI OUT → J10 HDMI IN cable loop, subject to confirming the physical board revision and routing the correct HDMI XDC ports.

The TX clock is separate from the recovered RX clock. The pinned output
hierarchy uses `axi_dynclk`, `v_tc`, `v_axi4s_vid_out`, and `rgb2dvi`; its
dynamic clock reference comes from PS FCLK0 at 100 MHz. FCLK1 at 142.857 MHz
clocks the AXI video stream, while the generated TX pixel clock drives VTC and
the RGB-to-TMDS serializer. The stock output setting disables the serializer's
internal clock generator and supplies its 5× clock from `axi_dynclk`. The
PYNQ software clock search calculates a target of five times the pixel rate; a
direct evaluation of its pinned 100 MHz reference-clock search finds about
74.2857 MHz pixel clock for the 74.25 MHz target (about 0.048% high). This is a
software calculation, not an MMCM run or physical measurement. The pinned
[1080p mode table](https://github.com/Xilinx/PYNQ/blob/93ddd21ab623883590a8c8b07f0b157b2855da4b/pynq/lib/_pynq/_video/video_modes.h) contains a 1080p60 entry only, so the base `HDMIOutFrontend` cannot select the 30 Hz candidate without a mode-table/driver change or direct clock/VTC control.

The current custom overlay has **no HDMI output path**. Its block design creates
only the input hierarchy and a write-only VDMA (`MM2S` disabled); the build
extracts only the pinned RX procedures and stops before the TX constraints.
The stock TX hierarchy is a useful integration reference, but copying it alone
would not make an end-to-end design: it also needs TX ports and constraints,
AXI control and interrupts, VTC configuration, a clock/reset policy, HWH
metadata, and a stream source. A practical first pattern can use a board-side
frame buffer with a changing visible frame ID through the stock display path.
A small PL test-pattern source could avoid the extra DDR read traffic, but
requires another AXI-stream timing/boundary integration. Either option must
keep the RX capture's source identity tied to complete frames.

The 1080p30 raw RGB888 payload is 6,220,800 bytes per frame, or 186.624 MB/s
if every input frame is written. At 1080p60 it is 373.248 MB/s. These values
exclude memory padding, intermediate 32-bit pixels, output reads, CPU copies,
and Ethernet. A DDR-backed HDMI output adds another full-frame read at its
refresh rate. The 1 FPS host-delivery goal only sets roughly 49.77 Mbit/s of
RGB888 application payload; it does not reduce the rate at which the input
receiver and VDMA must accept pixels. Measure input/DDR copy, output-loop and
network costs separately.

The latest clean VGA build used 6,690/53,200 LUTs, 15,938/106,400 registers,
7.5/140 BRAM tiles, 9/220 DSPs, and one of four MMCMs. Adding the stock TX
clock generator would add another MMCM and output serializers; the existing
logic counts leave apparent LUT/BRAM/DSP headroom. This utilization does not
predict final placement, clock routing, I/O timing, resource interaction, or
1080p closure. The replay report retained five input and two output external
delay gaps even for VGA. See [clean build 017](results/2026-10-16/credit-017-clean-replay.md).

Minimum next implementation steps are to add an explicit 1080p30 build profile
for the receiver, EDID, constraints, gateware dimensions, HWH manifest, sender,
and host frame parser; then integrate the output hierarchy and a known changing
pattern source. Run block-design validation, synthesis, routed timing/CDC/DRC,
and report the external I/O constraint gaps before programming a board. Only
then run a short same-board OUT→IN test and compare its embedded frame IDs and
pixels. The 1080p sustained 10-minute acceptance remains separate. The current
source statically rejects dimensions other than 640×480 and uses a 25.2 MHz
RX constraint, so changing the HDMI timing alone cannot produce a supported
capture.

Sources inspected locally and pinned above: `hardware/capture.tcl`,
`scripts/build_capture.py`, `gateware/dependencies.json`, the PYNQ v3.0.1
checkout, and `artifacts/clean-replay-017-20261016-0308` implementation output.
The local dependency versions are Migen 0.9.2 at
`e19524c963a8342952840983047557707fbe0b6a` and LiteX 2026.8 at
`b2759f69bcae8be0357fb2ee5eebe216365d1f00`. No RX/TX 1080p IP build,
board output-loop execution, 1080p input test, EDID interoperability test,
or 1080p DDR/network performance measurement has been performed. The physical
board revision, input/output connector margin at 74.25 MHz, and 1080p30
compatibility with the chosen loop cable and source remain unverified.

## 2026-10-17: standalone PL HDMI output fixture

The optional `--with-hdmi-output` path adds a fixed 1080p30 source without
connecting a second DMA or AXI video stream. It drives the pinned `rgb2dvi`
video input directly from PL counters and pattern logic. This avoids DDR read
traffic and does not take ownership of the capture VDMA. The normal capture
overlay still has no TX path unless the option is selected.

The source uses 1920×1080 active pixels within 2200×1125 totals. Its frame ID
increments at the frame boundary, and the marker, color bars, ramps, and
analytic RGB values match the host fixture in `tools/hdmi_pattern.py`. The
fixture simulation compares two complete frames, including active pixels,
sync positions, and blanking, then reasserts reset mid-frame and checks that
the next active pixel restarts at the frame origin. The test is
`python -m pytest -q tests/test_hdmi_output.py`; it passed in Icarus Verilog.
This verifies the pattern RTL against the host formula, but does not simulate
the clocking primitives, TMDS serializer, or board signals.

The optional output clock takes the existing PS FCLK0 100 MHz reference and
does not use the recovered RX clock or the FCLK1 AXI-video/DMA clock. Its
`MMCME2_ADV` settings use a 37.125 multiplier and divide-by-5 input path:
100 MHz × 37.125 / 5 = 742.5 MHz VCO. The MMCM output divided by 2 is
371.25 MHz; `BUFIO` drives the serializer's 5× clock and `BUFR` divided by 5
provides 74.25 MHz pixels. The 37.125 setting is an allowed 1/8 fractional
multiplier step according to AMD's [Clocking Wizard guide, PG065](https://docs.amd.com/r/en-US/pg065-clk-wiz/Configuring-Output-Clocks).
The topology follows the pinned PYNQ `axi_dynclk` use of a high-speed clock
for `rgb2dvi` plus a /5 pixel clock. The arithmetic and RTL structure are
source-checked; Vivado clock placement, routing, timing closure, and board
clock behavior still require the combined implementation build and hardware.

The pinned `rgb2dvi` input expects bytes in RBG order: bits 23:16 are red,
7:0 are green, and 15:8 are blue. The pattern therefore feeds `{R,B,G}` to
the IP; the simulation reorders these bytes before comparing with the RGB888
host fixture. The IP receives pixel clock, 5× serial clock, active-video,
HSync, and VSync directly. See the pinned
[`rgb2dvi.vhd`](https://github.com/Xilinx/PYNQ/blob/93ddd21ab623883590a8c8b07f0b157b2855da4b/boards/ip/rgb2dvi_v1_2/src/rgb2dvi.vhd)
and [`axi_dynclk.vhd`](https://github.com/Xilinx/PYNQ/blob/93ddd21ab623883590a8c8b07f0b157b2855da4b/boards/ip/axi_dynclk_v1_0/src/axi_dynclk.vhd).

The fixed transmitter does not read DDC/EDID or gate output on HPD; it keeps
sending 1080p30 when no monitor is connected. Its R19 `hdmi_out_hpd[0]` port is
left as an unused constrained input because the TUL manual describes the pin
as inverted HPD input, while the pinned upstream base Tcl declares and drives
it as an output. The schematic labels the net `HDMI_TX_HPDN`; this direction
conflict is unresolved, so this test path does not drive R19. The schematic
shows TX 5 V supplied from `VCC5V0` through fuse PS1, rather than by a PL GPIO.
These connector facts are in the [TUL schematic, sheet 6](https://dpoauwgwqsy2x.cloudfront.net/Download/TUL_PYNQ_Schematic_R12.pdf)
and [TUL reference manual, pp. 15–16](https://dpoauwgwqsy2x.cloudfront.net/Download/PYNQ_Z2_User_Manual_v1.1.pdf).

The pinned RX and TX constraints use disjoint package pins, so the build can
include both HDMI connectors in one design. This makes a short board-side
OUT→IN loop a practical test of the receiver and transmitter together, but
does not qualify 1080p electrical margin: the PYNQ-Z2 documentation rates the
HDMI pins officially only through 720p, and no 1080p30 cable loop has been
measured. Full Vivado DRC, routed timing/CDC review, and board testing remain
required. The loop also needs a source or sink that accepts the fixed timing;
the transmitter does not negotiate a mode.
