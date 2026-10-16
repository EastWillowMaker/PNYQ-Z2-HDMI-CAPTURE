# Capture the board's 1080p30 HDMI output

The optional PL fixture sends a changing1920×1080 progressive pattern from
HDMI OUT(J9). Connect J9 to HDMI IN(J10), keeping the shared USB-C Hub and
Micro-B connected. The receiver still uses the single-credit capture path,
PS DDR and Ethernet. There is no output DMA. The PC HDMI fixture remains
available as an independent source; this loop does not implement active bypass.

Build the explicit `1080p30` profile with `--with-hdmi-output` as described in
[build](build.md). Use its paired bitfile, adjacent HWH and build manifest.
The [verified build005](results/2026-10-17/1080p30-build-005.md) has real short
capture, held-lease and GUI/BMP evidence. Check [progress](progress.md) for the
separate ten-minute criterion. An RX-only build does not generate this pattern.

Stop other capture programs and verify their safe DMA shutdown before changing
the loaded image. For first loading or switching profiles, follow the verified
reset/old-image procedure in [prepared capture](prepared-capture.md).
`--after-reset` asserts a state already established by the caller; it does not
make an unknown or active DMA safe. Preparation configures GPIO and HPD without
constructing native video drivers. The PL output begins after programming.

The examples below assume a checkout on the board, artifacts under `overlay/`
and an existing valid same-boot `prepared.json` for those artifacts. Use the
board's PYNQ environment and its configured passwordless sudo. Reprepare before
each new sender session after the preceding one exits safely:

```sh
sudo -n env XILINX_XRT=/usr PYTHONPATH="$PWD/src" \
  /usr/local/share/pynq-venv/bin/python -m hdmi_capture.sender prepare \
  --mode 1080p30 --bitfile overlay/capture.bit \
  --manifest overlay/build-manifest.json --receipt prepared.json
```

Confirm a stable input before constructing native HDMI drivers. A preparation
receipt does not prove an input clock. For this controlled loop, the following
GPIO-only check observes five intervals with approximately30VSYNC/s, halted
DMA, disabled capture and clean source-health counters. Run it in the same
board checkout before the sender:

```sh
sudo -n env XILINX_XRT=/usr PYTHONPATH="$PWD/src" \
  /usr/local/share/pynq-venv/bin/python - <<'PY'
import time
from hdmi_capture.sources import LiteXCreditSource
from hdmi_capture.prepared import _attach_metadata, _hardware

source = LiteXCreditSource("overlay/capture.bit", "overlay/build-manifest.json",
                          capture_mode="1080p30")
_attach_metadata(source, "prepared.json", empty=True)
previous = source.control.snapshot()
for _ in range(5):
    time.sleep(1)
    current = source.control.snapshot()
    _hardware(source, empty=True)
    elapsed = (current["snapshot_end_ns"] - previous["snapshot_end_ns"]) / 1e9
    rate = (current["native_vsync_edges"] - previous["native_vsync_edges"]) / elapsed
    if not 28 <= rate <= 32:
        raise RuntimeError(f"Unstable loop input: {rate} VSYNC/s")
    if current["invalid_frames"]:
        raise RuntimeError("Invalid input geometry")
    print(f"Observed {rate:.3f} VSYNC/s", flush=True)
    previous = current
PY
```

This observes cadence, not the pixel-clock frequency. If it fails, preserve
the output and inspect the source; do not start native configuration or
automatically reload/retry. Stable input remains a prerequisite throughout
native startup. General missing-clock startup and automatic recovery are not
supported.

Then start the production sender on the board:

```sh
sudo -n env XILINX_XRT=/usr PYTHONPATH="$PWD/src" \
  /usr/local/share/pynq-venv/bin/python -u -X faulthandler \
  -m hdmi_capture.sender --source litex-credit --mode 1080p30 \
  --bitfile overlay/capture.bit --manifest overlay/build-manifest.json \
  --prepared-receipt prepared.json --host :: --port 9020 \
  --fps 2 --duration 650 --startup-diagnostics
```

After its `listening` line, use one PC client at a time. For preview and a
full-size uncompressed BMP, install the optional GUI and run:

```sh
.venv/bin/python -m pip install -e '.[gui]'
.venv/bin/hdmi-capture-viewer 'BOARD_ADDRESS%INTERFACE' --port 9020
```

The viewer's save button selects the latest complete received frame. Preview
scaling does not affect saved pixels. See [viewer](viewer.md) for exact BMP
semantics. For a bounded command-line image instead:

```sh
.venv/bin/hdmi-capture snapshot 'BOARD_ADDRESS%INTERFACE' \
  --port 9020 --output capture-NEW.bmp
```

For the ten-minute criterion, start the following promptly after the sender
listens. It requires600new exact frames and average>=1FPS over at least600seconds;
every full image is checked against the analytic pattern. Paths must be new:

```sh
PYTHONPATH=src:. .venv/bin/python tools/qualify_capture.py \
  'BOARD_ADDRESS%INTERFACE' --port 9020 --mode 1080p30 \
  --duration 600 --min-frames 600 --min-fps 1 --hard-deadline 660 \
  --log artifacts/loop-NEW-frames.jsonl \
  --summary artifacts/loop-NEW-summary.json
```

Do not disconnect the loop or change modes during that criterion. Sender
errors stop the session rather than recover automatically. A client result
must be combined with the sender's final status and verified DMA shutdown;
an observation timeout does not authorize killing a native process or freeing
its buffers. The known ignored PYNQ UIO destructor diagnostic can appear after
safe cleanup. The [measured performance](results/2026-10-17/1080p30-loop-performance.md)
does not promise a higher target FPS on every source or system.
