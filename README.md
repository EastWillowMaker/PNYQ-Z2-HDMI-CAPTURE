# LiteX HDMI capturer

Initial hardware investigation for a PYNQ-Z2 capture project. No HDMI capture
implementation or LiteX gateware is included yet.

The first experiment measured onboard ARM processing-system Ethernet under
PYNQ Linux using single-stream IPv6 TCP, with 30-second measurements after
a three-second warmup:

| Direction | Received throughput |
| --- | ---: |
| Host → PYNQ-Z2 | 595.498 Mbps |
| PYNQ-Z2 → host | 413.802 Mbps |

An earlier forward run measured 594.296 Mbps. Receive resource errors,
overruns and TCP retransmissions occurred; these are observed rates, not a
lossless or maximum-throughput qualification. This measures the ARM Ethernet
path, not LiteX/LiteEth performance.

See the [test report](docs/results/2026-10-14/pynq-z2-ethernet.md) for setup,
limitations, cleanup and links to the accompanying raw evidence. The
[summary](docs/results/2026-10-14/summary.json) records machine-readable results.
Downloaded packages and extracted binaries remain local in ignored
`artifacts/`; their hashes are retained with the evidence.
