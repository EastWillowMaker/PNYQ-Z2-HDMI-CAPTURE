# First PC frame from the PYNQ-Z2

Use a PYNQ-Z2 running the tested PYNQ 3.0.1 image, its normal Linux account,
working Ethernet, and local sudo authentication. Connect the HDMI source to J10
HDMI **input**. The custom receiver supports only progressive 640×480 at
25.175 or 25.2 MHz (approximately 60 Hz). It advertises only VGA in EDID; do not
force another resolution. Loading this overlay changes the active FPGA design.
Keep any existing board bitstream/HWH and stop other capture/DMA applications.

Build from a clean checkout using [the pinned bootstrap/build recipe](build.md#reproduce)
and use its successful single-credit bit/HWH/manifest pair. The new source
requires the `single_credit_parked_v1` ABI and deferred next-SOF closure proof;
its hardware qualification is pending. Legacy `013` results are retained
historical evidence and require the separate `--source litex` adapter. They do
not supply exact DMA-associated source identities. A first frame is a smoke
test, not the [ten-minute qualification](qualification.md).

## Host setup and read-only doctor

Run at the repository root. The tested host environment is CPython 3.12.13,
NumPy 2.5.4, Pillow 12.3.0. Use installed CPython 3.12 for this pinned host
recipe (NumPy 2.5.4 requires Python 3.12+); Python 3.10+ is the application
requirement with compatible NumPy versions, as on the existing board image.
Migen/LiteX source commits and content hashes are separately pinned in
`gateware/dependencies.json`. No system Python packages need replacement.

```bash
export PYTHON_BIN=python3.12 # Or the path to your installed CPython 3.12.
"$PYTHON_BIN" --version
"$PYTHON_BIN" -m venv .venv
.venv/bin/python -m pip install --index-url https://pypi.org/simple 'numpy==2.5.4' 'Pillow==12.3.0'
.venv/bin/python -m pip install --index-url https://pypi.org/simple --no-deps -e .
.venv/bin/hdmi-capture --help
mkdir -p artifacts
.venv/bin/python -m pip freeze > artifacts/host-python.txt
.venv/bin/python --version

# Set your normal SSH account/address and board TCP address separately.
export BOARD_SSH=xilinx@pynq
export BOARD_ADDRESS=pynq
export BUILD_DIR=/path/to/successful-single-credit-build
# For a new build, use its actual successful output directory instead.
python3 - "$BUILD_DIR" <<'PY'
import hashlib, json, pathlib, sys
root = pathlib.Path(sys.argv[1])
m = json.loads((root / 'build-manifest.json').read_text())
for key, name in [('bitstream_sha256', 'capture.bit'), ('hwh_sha256', 'capture.hwh')]:
    assert hashlib.sha256((root / name).read_bytes()).hexdigest() == m[key], name
assert m['geometry'] == [640, 480] and m['capture_enable_reset'] == 0
print('Paired artifact hashes and VGA geometry verified')
PY
ssh -o ConnectTimeout=10 "$BOARD_SSH" '/usr/local/share/pynq-venv/bin/python -c "import pynq,sys; print(sys.version); print(pynq.__version__); assert pynq.__version__ == \"3.0.1\""; ip -brief address show eth0; uname -a'
```

The doctor commands only inspect local artifacts and the board environment.
If SSH or sudo is unavailable, establish normal access locally before proceeding;
never put credentials in a command, repository, or chat. This session used an
already authenticated UART shell plus bounded Ethernet file transfer because
SSH was unavailable. `tools/board_console.py` is tied to that specific UART
identity and is evidence tooling, not a portable SSH substitute.

## Configure the HDMI source before programming

Select progressive 640×480 at 59.94/60 Hz, scale 1, normal orientation, RGB
full range, with no desktop mirroring. On the tested GNOME/Wayland host, the
helper accepts only the identified Digilent output and preserves other outputs.
Use its actual connector, not the example `DP-2`. Inspect first; `--apply`
explicitly changes that output temporarily and records its previous state.

```bash
/usr/bin/python3 tools/configure_hdmi_source.py --connector DP-2
# Only if the reported mode needs changing:
/usr/bin/python3 tools/configure_hdmi_source.py --connector DP-2 \
  --mode 640x480@60.000 --apply --snapshot artifacts/source-before.json
```

Configure this mode **before loading the overlay**, and keep it active through
startup. EDID alone does not prevent a source from forcing an unsupported clock.

## Deploy the pair and start the sender

Copy as the normal account. Keep `capture.bit`, same-stem `capture.hwh`, and
`build-manifest.json` together; the sender verifies their hashes before loading.
The source tree is copied so the board uses its existing PYNQ environment.

```bash
ssh "$BOARD_SSH" 'mkdir -p hdmi-capture/src hdmi-capture/overlay'
scp -r src/hdmi_capture "${BOARD_SSH}:hdmi-capture/src/"
scp "$BUILD_DIR/capture.bit" "$BUILD_DIR/capture.hwh" \
  "$BUILD_DIR/build-manifest.json" "${BOARD_SSH}:hdmi-capture/overlay/"
ssh -t "$BOARD_SSH"
```

In that board terminal, authenticate sudo locally, then run the bounded sender:

```bash
cd ~/hdmi-capture
sudo -v
sudo -n env XILINX_XRT=/usr PYTHONPATH="$PWD/src" \
  /usr/local/share/pynq-venv/bin/python -u -X faulthandler \
  -m hdmi_capture.sender --source litex-credit \
  --bitfile "$PWD/overlay/capture.bit" \
  --manifest "$PWD/overlay/build-manifest.json" \
  --host :: --port 9020 --fps 2 --duration 120 --startup-diagnostics
```

`XILINX_XRT=/usr` is required by this tested image; another image is unverified.
Expect startup verification/configuration, disabled-gate/native-pairing checks, single-frame DMA arm, and
then listening/capture. The timer allows cleanup; do not wrap hardware capture
in a kill timeout or send SIGKILL. Stop with one Ctrl-C and wait for the native
DMA cleanup report. If the sender reports a source/cleanup fault, resolve it
before another load; preserve the diagnostics. The latest sender drains frames
without a client and keeps a bounded ready slot.

## Take the first frame

Once the sender reports readiness, start the source fixture in a PC terminal:

```bash
/usr/bin/python3 tools/hdmi_pattern_gl.py --list-monitors
# Replace 1 with the identified HDMI output's current SDL monitor index.
/usr/bin/python3 tools/hdmi_pattern_gl.py --monitor-index 1 \
  --frame-id 1 --self-check --duration 90
```

The GLES fixture requires the system SDL2/GLES libraries and a native Wayland
session. It checks its framebuffer and target geometry; see
[source fixture requirements and limitations](hdmi-fixture.md). A different
source may show its own image, but its scanout mode must meet the same contract.
After the fixture is ready and the board sender is running, use another PC
terminal at the repository root:

```bash
mkdir -p captures
.venv/bin/hdmi-capture snapshot "$BOARD_ADDRESS" --port 9020 \
  --output captures/first.npy --png
.venv/bin/python tools/hdmi_pattern.py verify captures/first.npy
```

Successful output is a `(480, 640, 3)` uint8 RGB array, lossless PNG, and JSON
metadata. The optical verifier checks every RGB byte and row marker; a saved
frame alone does not prove integrity. Output paths must be new. Close the source
window with Escape; if its mode was changed, restore the saved source state:

```bash
/usr/bin/python3 tools/configure_hdmi_source.py --connector DP-2 \
  --restore artifacts/source-before.json
```

For sustained evidence, use [qualification.md](qualification.md), including
required non-null native health counters, fault checks, unique coherent optical
IDs, and the source/scanout logs. The new source waits for held hardware identity plus verified one-frame DMA
auto-halt; global counter snapshots remain non-atomic. See
[source accounting](source-accounting.md) for the required proof and pending
hardware validation. Clock loss/reconnect and unsupported sources
remain separate unverified scenarios; retained CDC and external timing limits
are recorded in [build.md](build.md).
