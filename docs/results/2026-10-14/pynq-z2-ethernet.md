# PYNQ-Z2 Ethernet preflight, 2026-10-14

Status: throughput measured on onboard ARM PS Ethernet under PYNQ Linux.
This does not measure a LiteX/LiteEth data path.

Reference project: ../litex-network-router, confirmed by user (the requested
../litex-router path is absent). Reference revision:
84c9617f63cacfedbf5a25998935e804a26dfe0e.
LiteX-Boards revision: c2abe2465dbe72de385a4c8b453ffb31c2d86bbb.

## Observations

- USB 0403:6010 enumerates with Xilinx_TUL_1234-tul serial interfaces.
- Host RTL8153 interface enx98fc84e0c4e8 reports carrier, 1000 Mb/s,
  full duplex, MTU 1500. This is negotiation, not measured throughput.
- Interface has no IPv4 address, no neighbor entry, and zero received packets
  at inspection. Physical peer identity has not been confirmed.
- USB UART if01 (/dev/ttyUSB1), 115200 baud: no bytes during a bounded read
  or after carriage return. This does not prove the board cannot boot.
- iperf and iperf3 are not on the current PATH.
- Initial preflight made no configuration changes. Subsequent temporary changes
  and cleanup are recorded below. No FPGA image or SD image was programmed.

## Compatibility findings

The PYNQ-Z2 Reference Manual v1.1, section 11, connects the RTL8211E-VL
Ethernet PHY to Zynq processing-system MIO, including RGMII MIO16–27.
https://dpoauwgwqsy2x.cloudfront.net/Download/PYNQ_Z2_User_Manual_v1.1.pdf

The installed litex-boards/litex_boards/targets/tul_pynq_z2.py BaseSoC
has no Ethernet integration and raises NotImplementedError for zynq7000.
Its platform file defines PS MIO but no directly accessible PL Ethernet pads.
These two files were read in full because graph coverage marks the dependency
subtree excluded. A Rise Pro LiteEth PHY target cannot be reused unchanged.

The reference project's README reports 941.405/941.403 Mbps received TCP
for its two-port Rise Pro bridge. Those are historical results for different
hardware, not evidence for this PYNQ-Z2.

## Initial decision (resolved below)

Choose onboard PS Ethernet with a bootable Linux endpoint, external PL PHY
for a LiteEth test, or a new LiteX-to-PS data path. A Linux iperf run measures
PS networking and alone does not establish LiteX data-path performance.
Confirm direct cable mapping and SD boot availability. Once an endpoint is
available, record separate forward/reverse received throughput, duration,
loss/retransmissions and configuration, and restore temporary host settings.

## Follow-up

User selected onboard PYNQ/Linux throughput and confirmed an inserted SD card
with unknown contents. No SD overwrite is authorized or attempted. A 180-second
115200-baud console capture was started in uart-boot.log while requesting a
physical SD-mode reset. Host iperf3 3.20 works via the reference project wrapper
at artifacts/bridge/iperf3; no package installation is needed.

## Completed physical throughput test

After the user selected SD boot and reset the board, it booted PYNQ Linux
(Ubuntu 22.04), kernel 5.15.19-xilinx-v2022.1, with automatic xilinx login.
The board eth0 MAC is 00:00:05:6b:01:a0; link is 1000 Mb/s full duplex.
Direct IPv6 link-local ping passed 3/3 (0.374–0.689 ms).

Single TCP stream, MTU 1500, 30 measured seconds following 3 omitted seconds;
separate directions, host iperf3 3.20 and board iperf3 3.9:

| Direction | Received Mbps | Sender TCP retransmissions |
| --- | ---: | ---: |
| Host → PYNQ | 594.296 | 112 |
| PYNQ → host | 413.802 | 0 |
| Host → PYNQ repeat | 595.498 | 97 |

Machine-readable evidence: summary.json and per-run JSON, including server
output. The first reverse attempt did not connect because NetworkManager
removed the host link-local address after automatic IPv4 configuration failed;
its error is retained in pynq-to-host.json. A temporary, memory-only IPv6
link-local profile made the subsequent reverse and forward-repeat tests stable.

Board RX errors began at zero and ended at 706: 417 resource errors plus 289
overruns. Final CRC, symbol and alignment errors were zero. These runs are
measured achievable throughput with receive-side loss/retransmissions, not a
lossless or maximum-performance qualification. UDP, simultaneous bidirectional
traffic, IPv4 and a LiteX-to-PS data path were not tested. No CPU-frequency
reading was available from cpufreq sysfs. The runs used the existing SD image
and its background services without performance tuning.

Boot reported ext4 filesystem errors and journal recovery, plus a failed
haveged service. The existing image also ran its filesystem resize service.
No manual filesystem repair or reimaging was performed; ordinary Linux boot
can write the SD card, so this was not a read-only filesystem examination.

ARM packages were fetched from ports.ubuntu.com, extracted into a local archive
and transferred over direct-link HTTP to /tmp/codex-iperf-20261014. Package and
archive hashes are in tool-sha256.txt. No system package installation or sudo
was needed. Temporary server PID1079 was stopped, its output saved, and the
board temporary directory removed with CLEANUP_OK readback. The one-request
host HTTP server exited. Temporary NetworkManager profile
2f70cada-bc40-463d-b670-b6ce53cbe0ff was deactivated and deleted. Original
profiles and Wi-Fi remained in place; the test NIC ended disconnected with
no IP address, matching its state immediately before the temporary profile.
Its initial automatically assigned link-local address was not restored.
