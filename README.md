# LiteX HDMI capturer

PC Python receives real PYNQ-Z2 HDMI input through a LiteX capture gate,
VDMA/PS DDR and onboard PS Ethernet as complete raw RGB888 NumPy arrays.

The accepted640×480 progressive near60Hz M1 is verified: **1,201 distinct exact
frames in600.300346seconds,2.000665FPS**, with zero pixel, mixed/repeated-frame,
metadata or transport errors. Held-buffer ownership, clean-source first frame,
physical HDMI interruption, explicit restart and a supported timing change have
separate hardware evidence. DMA shutdown, storage and desktop restoration pass.

Read the [M1 completion report](docs/results/2026-10-16/m1-completion.md) for
exact versions, evidence and limits. Source faults fail-stop and require explicit
preparation/restart. Arbitrary modes, automatic recovery and missing-clock native
startup are not qualified. Startup native skips and independent absolute
optical/native-ID mapping remain unknown. PYNQ's ignored post-cleanup UIO warning
and build timing/CDC/external-I/O limits remain disclosed. Browser, bypass and
LCD are later milestones.

Start with [quickstart](docs/quickstart.md), [prepared capture](docs/prepared-capture.md),
[build](docs/build.md), and [progress](docs/progress.md). The supported source
uses [direct DRM/KMS outside desktop composition](docs/kms-source.md).
The [earlier frame-difference diagnosis](docs/results/2026-10-15/frame-difference-diagnosis.md)
and failed SD/native runs remain in dated evidence; they are not current status.

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

For uncompressed images, use `snapshot --output image.bmp` or
`capture --output frames --count 10 --bmp`. These commands save 24-bit BMP
images and JSON sidecars. Decoding each BMP to RGB888 preserves every received
pixel byte; headers, BGR storage order and row padding differ from raw RGB.
BMP output cannot be combined with `--png`. The optional
[desktop viewer](docs/viewer.md) uses the same client and BMP writer.

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
