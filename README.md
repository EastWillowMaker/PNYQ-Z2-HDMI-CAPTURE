# LiteX HDMI capturer

PC Python receives real PYNQ-Z2 HDMI input through a LiteX capture gate,
VDMA/PS DDR and onboard PS Ethernet as complete raw RGB888 NumPy arrays.

Legacy013 passed the 640×480p60 delivered-image criterion: **1,201 distinct exact frames in
600.506 seconds, 2.000 FPS, 14.745 Mbps**, with zero pixel, mixed, repeat,
metadata or transport errors. LiteX gate control, client pause/reconnect and
explicit restart after a 60→59.94 Hz mode change were also exercised.
Physical HDMI cable removal/reinsertion remains pending.

M1 is incomplete: the new single-credit path adds required physical source IDs
and sampling counts. Build017 passed CAD and its first real capture smoke:
11 distinct byte-exact frames with automatic DMA halt and reconciled source IDs.
Its first ten-minute run failed pixel comparison (1189/1200 exact). Desktop
notifications reproducibly trigger one-LSB differences through source composition;
suppressing banners alone is insufficient. See the
[diagnosis](docs/results/2026-10-15/frame-difference-diagnosis.md).
Ten-minute and interruption qualification remain pending. See
[current progress](docs/progress.md).

See the [qualification report](docs/results/2026-10-15/m1-qualification.md)
for raw evidence, startup invalid attribution, resource use, timing and limits.
VDMA physical sequence/drop attribution is incomplete; earlier M0 failures and
PYNQ cleanup warnings remain disclosed. Web, bypass and LCD are deferred.

For a source outside GNOME composition, see the experimental
[direct DRM/KMS source](docs/kms-source.md). Its VT hardware run is still pending;
the failed DRM-lease prototype must not be treated as a safe desktop path.

Start with the [clean-checkout-to-first-frame guide](docs/quickstart.md),
[build guide](docs/build.md), and [current progress](docs/progress.md).

## Install and receive a frame

Use Python 3.10 or newer and an isolated environment:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test,png]'
.venv/bin/python -m pytest -q
.venv/bin/hdmi-capture benchmark --help
```

`png` is optional; use `.[test]` if you only need raw `.npy` frames. No global
package installation is required. Dependencies have bounded compatible ranges;
the tested installed versions should be retained alongside each result.

First exercise the synthetic path in one terminal:

```sh
.venv/bin/python -m hdmi_capture.sender --source synthetic --host 127.0.0.1 --port 9020 --fps 1
```

In another terminal:

```sh
.venv/bin/hdmi-capture snapshot 127.0.0.1 --output synthetic.npy --png
.venv/bin/hdmi-capture capture 127.0.0.1 --output captures/run-001 --count 10
.venv/bin/hdmi-capture benchmark 127.0.0.1 --duration 10
```

These are synthetic frames, not HDMI evidence. For an authorized live board
sender, replace `127.0.0.1` with its address. A link-local IPv6 address includes
the host interface scope, for example `'fe80::1234%enp1s0'`. The default port is
9020. Board overlay loading and source configuration are described in the
[sender guide](docs/board-capture.md); loading the base overlay is M0.

`snapshot` saves an exact uint8 RGB array plus a JSON metadata sidecar;
`--png` additionally saves lossless PNG. `capture` creates a new output
directory and saves numbered arrays and sidecars. Existing files/directories
are refused. `capture`, `stats` and `benchmark` require `--count` or
`--duration`; supplying both stops at the first limit. `stats` and `benchmark`
save no frames and print the same measurement JSON.

Reports include complete delivered frames, elapsed seconds, FPS, RGB payload
goodput in Mbps, detected errors, frame ID gaps and final source metadata.
Frame ID gaps are observations, not independently measured source drops;
source counters and unknown values remain in metadata. Sender counters are
cumulative and `transport_enqueued` measures TCP enqueue, not host receipt.
An incomplete frame at a normal duration cutoff is explicitly reported and
excluded from delivered totals. Protocol/CRC failures, premature EOF and idle
timeout stop the run with an error count and exit status 1. Saving time is
included in capture FPS; benchmark measures the receive/parse path.

```python
from hdmi_capture import CaptureClient

with CaptureClient("BOARD_ADDRESS", timeout=5) as client:
    frame = client.read()
    rgb = frame.rgb  # numpy uint8, (height, width, 3), R/G/B
    print(frame.metadata)
```

Arrays own their memory and remain valid after the next read. IDs must increase
within each TCP connection, with a stable optional sender session ID. EOF,
timeout or invalid framing closes the connection; reconnect explicitly to
start a fresh read scope. RGB bytes receive no scaling or color conversion.
Board and host monotonic clocks cannot be subtracted as one-way latency.
See [protocol](docs/protocol.md) for wire bounds and validity rules.

## Existing Ethernet evidence

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
