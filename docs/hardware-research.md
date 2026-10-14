# PYNQ-Z2 HDMI and PS path feasibility

Date: 2026-10-15 (Asia/Taipei). Evidence level: official board documents and
upstream source inspection. No Vivado build or new HDMI capture run was made.

## Confirmed board wiring

The PYNQ-Z2 HDMI input connector is J10, wired to PL pins. TUL's manual calls
the HDMI ports unbuffered and lists the sink-side pins as follows: TMDS clock
N18/P19; data lane 0 V20/W20; lane 1 T20/U20; lane 2 N20/P20; DDC SCL/SDA
U14/U15; CEC H17; and HPD output T19. The HDMI-input XDC in the PYNQ-Z2
reference design assigns `TMDS_33` to the differential TMDS signals and
`LVCMOS33` to DDC and HPD. This pinout and these constraints are corroborated
by the [TUL Reference Manual v1.1, printed pages 15–16](https://dpoauwgwqsy2x.cloudfront.net/Download/PYNQ_Z2_User_Manual_v1.1.pdf),
the [TUL schematic, HDMI sheet 6](https://dpoauwgwqsy2x.cloudfront.net/Download/TUL_PYNQ_Schematic_R12.pdf),
and [PYNQ v3.1 `base.xdc`, lines 118–143](https://github.com/Xilinx/PYNQ/blob/19ed17d4fd4ea71f95a97d30f8ccd0d62b8dbaaa/boards/Pynq-Z2/base/vivado/constraints/base.xdc#L118-L143).
The schematic shows low-speed DDC level shifting and HPD buffering; these do
not change the direct PL connection of the high-speed TMDS pairs.

The onboard RTL8211E-VL Ethernet PHY is wired to the Zynq PS GEM through MIO,
not to PL pins: RGMII is MIO 16–27, MDIO/MDC are MIO 52–53, PHY reset is MIO 9,
and PHY interrupt is MIO 10. This is stated in the [TUL manual, printed page
12](https://dpoauwgwqsy2x.cloudfront.net/Download/PYNQ_Z2_User_Manual_v1.1.pdf)
and visible on [schematic sheet 5](https://dpoauwgwqsy2x.cloudfront.net/Download/TUL_PYNQ_Schematic_R12.pdf).
The official [TUL PS preset archive](https://dpoauwgwqsy2x.cloudfront.net/Download/pynq-z2.zip)
also selects GEM0 on MIO 16–27, MDIO on 52–53 and reset on MIO 9. Thus the
onboard RJ45 is available to a Linux/PYNQ sender through the PS Ethernet stack;
it is not directly usable as a LiteEth PL PHY. A PL Ethernet test would need an
external PL-connected PHY or a separate PS-to-PL data interface.

The board's 125 MHz PL reference at H16 comes from the Ethernet PHY. TUL
explicitly says the clock output is disabled while `PHYRSTB` is low. Do not make
that resettable PHY clock the only clock source for capture or frame control.
The board also feeds a 50 MHz oscillator to `PS_CLK`; the PYNQ base design
derives its PL clocks from PS `FCLK` outputs. This is suitable for the control
and AXI clocks once PS configuration is running. The documents establish what
happens on PHY reset; they do not establish a tested capture response to cable
removal or link renegotiation. See the [manual, printed page 6](https://dpoauwgwqsy2x.cloudfront.net/Download/PYNQ_Z2_User_Manual_v1.1.pdf)
and [Ethernet schematic sheet 5](https://dpoauwgwqsy2x.cloudfront.net/Download/TUL_PYNQ_Schematic_R12.pdf).

The board has 512 MB of 16-bit DDR3 attached to the PS hard memory controller.
TUL says its board files include board-specific DDR controller and training
parameters; the downloaded A.0 preset sets a 50 MHz PS input, 16-bit DDR, and
1050 MHz DDR PLL. The preset enables `M_AXI_GP0` but leaves `S_AXI_HP0–3`
disabled and enables only `FCLK0`. These are preset defaults, not a limitation
of the hardware; a DMA-to-DDR design must explicitly enable and clock a PS HP
port. See the [manual, printed page 7](https://dpoauwgwqsy2x.cloudfront.net/Download/PYNQ_Z2_User_Manual_v1.1.pdf)
and the [official TUL board preset archive](https://dpoauwgwqsy2x.cloudfront.net/Download/pynq-z2.zip).

The actual PCB revision of the user's board remains unknown. The schematic
download is named R12, while its title block identifies document revision R10;
neither establishes the revision printed on the physical board. The pin mapping
above follows TUL's PYNQ-Z2 manual and the official PYNQ-Z2 reference design,
but should be checked against the board revision before final constraints are
frozen.

## Existing video path and software boundary

PYNQ's Z2 base-overlay documentation says its HDMI interfaces connect to PL and
the HDMI IP streams video to PS DRAM. The PYNQ v3.1 reference source makes that
path concrete: its video hierarchy lists Digilent `dvi2rgb:1.7`, Xilinx
`v_vid_in_axi4s:5.0`, and `axi_vdma:6.3`; the capture video master connects to
PS `S_AXI_HP0`, and the design enables HP0 and HP2. The corresponding clocks
are PS FCLK0=100 MHz for control/AXI, FCLK1=142.857 MHz for the video/HP0
domain, FCLK2=200 MHz for video, and FCLK3=100 MHz for HP2. These are reference
design settings, not a guarantee that every custom LiteX design should use the
same clock plan. Sources: [PYNQ v3.1 `base.tcl`](https://github.com/Xilinx/PYNQ/blob/19ed17d4fd4ea71f95a97d30f8ccd0d62b8dbaaa/boards/Pynq-Z2/base/base.tcl#L404-L451),
[PS port settings](https://github.com/Xilinx/PYNQ/blob/19ed17d4fd4ea71f95a97d30f8ccd0d62b8dbaaa/boards/Pynq-Z2/base/base.tcl#L4108-L4120),
[DMA-to-HP0 connection](https://github.com/Xilinx/PYNQ/blob/19ed17d4fd4ea71f95a97d30f8ccd0d62b8dbaaa/boards/Pynq-Z2/base/base.tcl#L4238-L4241),
and [FCLK connections](https://github.com/Xilinx/PYNQ/blob/19ed17d4fd4ea71f95a97d30f8ccd0d62b8dbaaa/boards/Pynq-Z2/base/base.tcl#L4321-L4324).

The smallest board path for the highest-priority outcome is therefore:

```text
HDMI J10 -> existing PYNQ HDMI receiver -> video AXI stream -> VDMA -> PS DDR
          -> PS/Linux Ethernet -> PC Python -> complete RGB888 frame
```

For the next LiteX milestone, keep the onboard network on PS GEM and have a
small LiteX-generated PL block participate in capture control, frame boundary
tracking, or frame metadata before DMA. Keep the capture frontend and proven
DMA path until a LiteX replacement is independently qualified. This limits the
first integration to a documented PS/PL AXI seam and avoids treating the RJ45
as a PL PHY. It still requires a Vivado integration build and a deliberate RGB
channel-order/stride contract: the board pinout does not determine the byte
order in DDR, and the existing PYNQ video stack can expose BGR by default.

At 640x480 RGB888, one packed frame is 921,600 bytes (7.3728 Mbit at one
delivered frame per second). That rate is only arithmetic; the existing PS
Ethernet experiment is transport evidence, not evidence that capture frames
were transferred. See [the measured Ethernet report](results/2026-10-14/pynq-z2-ethernet.md).

## Version and verification limits

The PYNQ commit identified for current upstream is
[`d90670c69f7b71ea1a5d23aaa3e0ec713ff5fa9f`](https://github.com/Xilinx/PYNQ/tree/d90670c69f7b71ea1a5d23aaa3e0ec713ff5fa9f),
the PYNQ v4.0 release merge. Its documentation still describes the Z2 HDMI
overlay, and its tree has the `dvi2rgb` IP source, but its tree does not contain
`boards/Pynq-Z2/base/base.tcl` or the matching Z2 constraints. The rebuildable
Z2 design source inspected here is the official PYNQ v3.1 source, whose Tcl
requires Vivado 2024.1. This is not the board's installed source version: the
current board preflight records PYNQ 3.0.1 and an installed `base.bit`
([preflight log](results/2026-10-15/board-preflight.log)). Therefore the local
overlay is a strong M0 candidate, but the v3.1 rebuild source is only a
reference until its compatibility with that image and the available Vivado/IP
catalog is checked.

The inspected Digilent `dvi2rgb` source carries a modified-BSD license header;
the reference design also depends on versioned Xilinx video/VDMA IP. No Vivado
project was generated, license state or IP-catalog resolution was tested, and
no bitstream was built. The PYNQ v3.1 Tcl's stated Vivado version and IP names
are evidence of declared dependencies, not proof of build compatibility on the
local machine. The exact local 3.0.1 HDMI API, capture pixel order, stride,
supported-input-mode list, and stable runtime frame delivery remain unverified.

The official PYNQ overlay documentation says HDMI input auto-detects standard
resolutions and can stream to PS DRAM; that is design documentation, not a
measurement of this board's J10, source timing, or image quality. Qualify the
installed overlay with a 640x480 progressive RGB source, save captured frames
over Ethernet, and inspect dimensions/channel order before calling the M0 path
complete. It does not verify LiteX participation or HDMI bypass.
