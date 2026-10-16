# First PC frame from the PYNQ-Z2

Use a PYNQ-Z2 running the tested PYNQ 3.0.1 image, its normal Linux account,
working Ethernet, and local sudo authentication. Connect the HDMI source to J10
HDMI **input**. The custom receiver supports only progressive 640×480 at
25.175 or 25.2 MHz (approximately 60 Hz). It advertises only VGA in EDID; do not
force another resolution. Loading this overlay changes the active FPGA design.
Keep any existing board bitstream/HWH and stop other capture/DMA applications.

Build from a clean checkout using [the pinned bootstrap/build recipe](build.md#reproduce)
and use its successful single-credit bit/HWH/manifest pair. The normal017/v11
run passed1,201 exact frames over600.368seconds with safe shutdown; the separate
HDMI-loss run failed. [Current evidence](results/2026-10-16/capture-011-loss-012-report.md)
and the [remaining audit](results/2026-10-16/m1-remaining-audit.md) distinguish
that pass from unfinished full M1 qualification. The tracked preparation,
receipt and source-trigger workflow passed a
[41-frame short hardware run](results/2026-10-16/m1-017-prepared-014-report.md);
[held-credit observations](results/2026-10-16/m1-017-lease-015-report.md) also
passed. The current production runtime also passed [normal019](results/2026-10-16/m1-017-normal-019.md):
1,201 exact frames over600.300346seconds with safe shutdown. Physical-loss020
[did not complete its observation](results/2026-10-16/m1-017-hdmi-loss-020.md).
An isolated clean-checkout replay and remaining fault/mode checks remain open.
Legacy013 uses the separate `--source litex` adapter and has no exact
DMA-associated source identities.

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

## Prepare the receiver and direct KMS source

Use the [prepared capture workflow](prepared-capture.md), which supplies the
board and PC command blocks. Preparation asserts HPD without native frontend
configuration, VTC reads, capture allocation or DMA start. The queued board shell
waits for a fresh source-ready file, then runs normal preparation again with the
same receipt before starting the receipt-checked sender. The PC trigger observes
completed direct DRM/KMS presentations before signaling that file, then waits
for the sender's actual TCP listening event before starting the client.

This ordering addresses the KMS transition in
[failed run016](results/2026-10-16/m1-017-normal-016-startup-diagnostic.json):
a latched FIFO underflow was correctly rejected before video setup or selected
capture. Explicit preparation on the same steady source then passed
[run017](results/2026-10-16/m1-017-warm-017-result.json), with 21 exact frames,
safe DMA cleanup and storage checks. Keep that failure evidence; do not waive
counters or automatically retry a failed preparation. The runtime is unchanged.

This source runs outside GNOME composition and needs a temporary VT switch;
see [the bounded KMS runner](kms-source.md). Keep this PC's shared USB-C Hub and
PYNQ Micro-B connected. The queued pipeline avoids typing a board command after
the desktop is hidden. Do not use the earlier GLES desktop fixture as an exact
pixel reference. No source, root authentication or device identity is inferred
from an existing file; use fresh paths and the paired artifact checks.

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

In that board terminal, follow the preparation and background-waiting sender
commands in [prepared capture](prepared-capture.md). Authenticate board sudo
locally. `--after-reset` is only an explicit assertion of a confirmed board/PL
reset with no active DMA; the command does not reset an unknown design.
The same guide then queues the PC trigger/client pipeline before the PC sudo
VT command. It uses only tracked files and does not depend on local operator
archives. `XILINX_XRT=/usr` is required by the tested image.

Do not wrap hardware capture in a forced-kill timeout. On a source or cleanup
fault, preserve the logs and establish DMA safety before another load. The
sender's duration permits cooperative cleanup; an unsafe halt retains its
native references and requires external hardware recovery.

## Take the first frame

The queued short qualifier in the preparation guide saves the first and last
received RGB arrays under a fresh ignored directory. After KMS restores the
desktop, verify the saved first frame:

```bash
.venv/bin/python tools/hdmi_pattern.py verify \
  artifacts/captures/prepared-001/first.npy
```

It must be a `(480,640,3)` uint8 RGB array with exact analytic pixels and coherent
row markers. Saving a frame alone does not prove those properties. The pipeline
logs preserve the original metadata and the strict verification result.

For a later sustained run, use [qualification.md](qualification.md): at least
600seconds and600 distinct exact frames at1FPS or more, clean accounting,
source/resource evidence and safe shutdown. A20-second smoke is not that
criterion. [Source accounting](source-accounting.md) explains the held identity
and parked-buffer contract. Physical interruption, mode/restart and an isolated
clean-checkout startup remain separate obligations; build timing and CDC
limits remain in [build.md](build.md).
