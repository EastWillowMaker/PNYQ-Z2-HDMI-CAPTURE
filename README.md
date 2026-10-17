# LiteX HDMI capturer

PC Python receives real PYNQ-Z2 HDMI input through a LiteX capture gate,
VDMA/PS DDR and onboard PS Ethernet as complete raw RGB888 NumPy arrays.

The fixed1920×1080p30 board HDMI OUT→IN loop is verified: **1,200distinct exact
frames in600.076875seconds,1.999744FPS**, with zero pixel, mixed/repeated-frame,
metadata or transport errors and safe DMA shutdown. The desktop viewer's
uncompressed24-bit BMP reproduces every received RGB byte after decoding.
Board passwordless sudo, held-buffer ownership and measured performance work
are complete for this scope. Start with the [1080p loop guide](docs/output-loop.md)
and [completion evidence](docs/results/2026-10-17/1080p30-completion.md).

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

To view HDMI input, use one of the [two GUI scenarios](#use-the-desktop-gui)
below. The following optional synthetic test generates a pattern; it cannot
show your PC desktop. Run it in one terminal:

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

## Use the desktop GUI

Run both launchers on your **PC**, from this repository. They start real HDMI
capture on the PYNQ-Z2 and open the viewer on your PC. The synthetic localhost
commands above only generate a test pattern; they do not capture your desktop.

Install once in the PC virtual environment (Python must include Tk support):

```sh
.venv/bin/python -m pip install --index-url https://pypi.org/simple -e '.[gui,serial]'
```

Connect the powered PYNQ-Z2 to your PC with **Ethernet** and a **Micro-B USB
data cable** for its serial console. Keep the shared USB-C Hub connected.
The board must already have the capture software and paired image files
installed; see [one-time board setup](docs/quickstart.md) and
[local-loop image setup](docs/output-loop.md). The launchers find the existing
board deployment and prepare it for each run.

### 1. PYNQ-Z2 Local Loop

Connect **PYNQ HDMI OUT (J9) → HDMI IN (J10)**. This shows the board's changing
1080p30 test pattern, with a capture target of 2 FPS.

In the first PC terminal:

```sh
.venv/bin/python Start-PYNQ-Z2-Captrue.py --scenario loop
```

Follow the serial login steps below. When it says **Capture is ready**, leave
that terminal open and run this in a second PC terminal:

```sh
.venv/bin/python Start-Host-PC-Capture.py
```

### 2. Capture External HDMI Signal

Connect **PC HDMI output → PYNQ HDMI IN (J10)** and disconnect the J9-to-J10
loop cable. To see your desktop, enable the PYNQ-connected HDMI display in your
PC display settings at **640×480 near 60 Hz**. Select **Mirror**, or select
**Extend** and move the content onto that HDMI display. The external scenario
uses the qualified VGA receiver profile; external 1080p30 remains unqualified.

In the first PC terminal:

```sh
.venv/bin/python Start-PYNQ-Z2-Captrue.py --scenario external
```

Follow the serial login steps below. After the launcher prepares the receiver,
it pauses so you can enable the HDMI display and confirm that the output is
stable. The launcher checks and attaches to that prepared receiver without
reloading it again. When it says **Capture is ready**, run this in a second PC
terminal:

```sh
.venv/bin/python Start-Host-PC-Capture.py
```

### Connect and log in through Miniterm

The board launcher opens **Miniterm** at 115200 baud. If several serial devices
are attached, select the PYNQ UART port (not JTAG).

1. Press **Enter** to display the board prompt.
2. If asked, enter your board username and password in Miniterm.
3. At the board shell prompt, run `sudo -v` and enter the board password if asked.
4. Press **Ctrl+]** to leave Miniterm and let the launcher continue.
5. Accept or enter the board's Ethernet address when prompted. The viewer
   remembers this address and the matching port automatically.

The existing board login password and PC settings are preserved. No passwords
are stored. On Linux, if the serial port reports permission denied, ask your
administrator to grant your account access to that device. Close other serial
terminals before running the launcher.

### Save and stop

Select **Save frame…** in the viewer to save a full-resolution, uncompressed
24-bit BMP and its JSON metadata sidecar. Decoding the BMP to RGB888 preserves
every received pixel byte; preview scaling does not affect the saved image.
Choose a new filename because existing files are not overwritten.

To stop, press **Ctrl+C once in the first PC terminal** and wait for
**Board capture stopped**. Closing the viewer only disconnects it. For a new
session or a different scenario, run the board launcher again before opening
the viewer. Source faults require explicit restart; the launchers do not retry
or force-kill capture.

If the board was just power-cycled and has no valid preparation receipt, add
`--after-reset` to the board launcher **only before any capture has started**.
This flag asserts an actual board/PL reset; it does not perform one. An unknown
or failed DMA state needs the [recovery procedure](docs/prepared-capture.md).
Advanced connection overrides are listed by each script's `--help`.
See the [viewer guide](docs/viewer.md) for reconnect behavior and
[external-source evidence](docs/kms-source.md) for exact-pixel test limits.

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
