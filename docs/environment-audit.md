# Local environment audit

Checked 2026-10-15. This is a read-only inventory; no board, overlay, package,
SD-card, or network configuration was changed. No gateware build or license
checkout was attempted.

## Host tools and packages

- System Python is CPython 3.14.4 and has no LiteX, LiteX-Boards, Migen,
  LiteEth, or PYNQ package installed.
- The reference project's `../litex-network-router/.venv` uses CPython 3.12.13
  with LiteX 2026.8, LiteX-Boards 2026.8, LiteEth 2026.8, and Migen 0.9.2.
  It does not contain the PYNQ Python package. This venv is useful for local
  LiteX development, but is not a project-specific environment yet.
- Vivado at `/home/eastwillow/Xilinx/2025.2/Vivado/bin/vivado` starts and
  reports v2025.2, build 6299465. The local catalog contains `axi_vdma` 6.3,
  `v_hdmi_rx` 3.0, `v_hdmi_rx_ss` 3.2, `v_hdmi_rxss1` 1.2,
  `v_hdmi_phy1` 1.0, and `v_frmbuf_wr` 2.5. These are installed catalog
  sources; this audit did not instantiate them or test a design build.
- `XILINXD_LICENSE_FILE`, `LM_LICENSE_FILE`, and `XILINX_LICENSE_FILE` are
  unset; `lmutil` is not on PATH. Only the vendor's bundled IP license files
  were found in the checked Xilinx directories. Vivado startup and installed
  IP files do not establish that a required IP or implementation feature can
  be licensed. Actual synthesis/IP license feasibility remains unverified.
- `verilator` and `yosys` are on PATH. No HDL tests or builds were run.

## Current host and board access

- The host sees a Realtek RTL8153 adapter as `enx98fc84e0c4e8`; it is UP but
  currently has no IP address. Wi-Fi is connected. The Xilinx TUL FTDI device
  and `/dev/ttyUSB0` and `/dev/ttyUSB1` are present.
- A separate read-only serial preflight on 2026-10-15 found the board running
  kernel `5.15.19-xilinx-v2022.1` as `uid=1000(xilinx)`. Board `eth0` was UP
  with link-local IPv6 `fe80::200:5ff:fe6b:1a0`; Python is
  `/usr/local/share/pynq-venv/bin/python3`, with PYNQ 3.0.1 installed. The
  default PYNQ base overlay bitstream exists at
  `/usr/local/share/pynq-venv/lib/python3.10/site-packages/pynq/overlays/base/base.bit`.
  File presence does not show that this overlay is loaded. The read-only
  preflight did not inspect SD contents or load an overlay.
- The saved 2026-10-14 boot log independently records PYNQ Linux based on
  Ubuntu 22.04 and automatic login as `xilinx`. The saved `sudo -n true`
  attempt reported that a password is required. Membership in the `sudo`
  group was visible in the new preflight, but root access was not tested; do
  not assume it is available.
- Current `sudo -n true` also returned status 1, “a password is required”;
  see `docs/results/2026-10-15/elevation-check.log`. Privileged deployment needs
  a locally authenticated execution route; no password was requested or supplied.
- `overlay-files.log` records SHA256 for existing base.bit/base.hwh and FPGA
  manager state `operating`. This does not identify the loaded image.
- The saved Ethernet report measured board-to-host TCP at 413.802 Mbps for one
  30-second run, with no sender retransmissions. This was the onboard Zynq PS
  Ethernet path, not LiteX/LiteEth or an HDMI capture test. The report also
  observed RX resource errors and overruns in the board's other test runs, so
  the number is not a lossless or sustained-capture qualification.
- At 640x480 RGB888, one active frame is 921,600 bytes (7.373 Mbit). One such
  frame per second is modest relative to the historical Ethernet result.
  Sending every frame at 60 Hz is 442.368 Mbps before framing and application
  overhead, above that measured TCP rate. The proposed 1 fps acceptance rate
  therefore looks plausible for transport capacity, but capture continuity,
  buffer behavior, and ten-minute stability have not been demonstrated.

## Existing LiteX board and video support

The installed `litex_boards/targets/tul_pynq_z2.py` creates a LiteX SoC, but
explicitly raises `NotImplementedError` when `cpu_type="zynq7000"` is selected
(lines 44-58). The accompanying platform declares PL clock, LEDs, switches,
buttons, and serial pads, then PS7 MIO and DDR resources. It declares no HDMI
input or PL Ethernet pads (`litex_boards/platforms/tul_pynq_z2.py`, lines
13-66). The board's onboard Ethernet PHY is on PS MIO per the existing
hardware report, so the Rise Pro LiteEth PHY target cannot be reused unchanged.

The installed LiteX `VideoFrameBuffer` reads pixel data from Wishbone or
LiteDRAM memory using DMA (`litex/soc/cores/video.py`, lines 1022-1059).
`VideoHDMIPHY` encodes and serializes its stream toward HDMI output
(`video.py`, lines 1237 onward). I found no corresponding HDMI receiver in
this module. The repository itself still has no HDMI capture gateware, as
stated in `README.md`.

The sibling `../litex-network-router/sfp_loopback/target.py` defines a
Rise-Pro-specific platform, not a PYNQ-Z2 target. Its separate
`cable_target.build_target(run=True)` removes existing `.bit` and `.bin` files
in its output directory before building (`cable_target.py`, lines 453-466); it
was not invoked. The indexed reference project was at `84c9617`; graph coverage
reported no recorded issues for these two source files, and I read the source
snippets directly. The installed venv package sources are outside that graph
and were inspected from disk.

## Recommended data path and remaining evidence gap

For the first complete-frame milestone, keep the already demonstrated onboard
PS Ethernet and Linux TCP endpoint as the PC transport. The missing path is
from the real HDMI receiver in PL to frame buffers in PS-accessible DDR, with
explicit frame sequence, dimensions, pixel format, and drop/error reporting;
the Linux endpoint can then send complete buffers to the PC Python client.
The installed LiteX board target does not supply that capture-to-PS-DMA path.
M0 can first use the existing PYNQ base overlay; a custom integrated PL/PS
design is needed for M1, not as a prerequisite for the first baseline frame.
Use TCP for the initial
lossless transport, and count whole-frame drops explicitly because HDMI input
cannot be backpressured by the host.

This audit establishes tool availability and a currently running board Linux
shell, not a fresh reboot test. It does not establish that the HDMI input receiver
and source mode work, that the required Vivado IP is licensed, or that captured
RGB frames can reach the PS DDR and host reliably.

## Evidence paths

- `docs/results/2026-10-14/pynq-z2-ethernet.md` — historical Ethernet setup,
  measured results, and LiteX-Boards compatibility findings.
- `docs/results/2026-10-15/board-preflight.log` — current read-only kernel,
  user, IP, Python, PYNQ-version, and base-overlay-file observations.
- `docs/results/2026-10-14/uart-boot.log` and `board-inspect.log` — historical
  PYNQ Linux boot and non-root access observations.
- Installed LiteX-Boards sources under
  `../litex-network-router/.venv/lib/python3.12/site-packages/litex_boards/`.
- Installed LiteX video sources under
  `../litex-network-router/.venv/lib/python3.12/site-packages/litex/soc/cores/video.py`.
- Vivado IP metadata under
  `/home/eastwillow/Xilinx/2025.2/Vivado/data/ip/xilinx/`.
- `../litex-network-router/sfp_loopback/target.py` and
  `../litex-network-router/sfp_loopback/cable_target.py` — reference target and
  build behavior checked without running a build.
