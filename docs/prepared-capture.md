# Prepare the receiver before HDMI capture

The credit receiver can advertise HDMI input before the PC starts its source.
Preparation loads the verified bitfile, leaves capture and DMA disabled, and
asserts HPD through GPIO. It does not configure the native frontend, read VTC,
allocate capture buffers or start DMA. The later sender attaches to that image
and runs the existing startup mode and integrity checks before allocation.

Use the checked-out package in the board's existing PYNQ 3.0.1 environment.
Preserve its NumPy/XRT installation; see [board capture](board-capture.md) for
the environment and privilege requirements. Supply the paired credit bitfile,
adjacent HWH and build manifest from the verified build. These commands need no
operator helper archive or fixed board boot ID. Replace the example paths with
your board paths and use the same files for both commands.

Authenticate sudo in the board terminal. For first preparation, confirm that
the board or PL was reset and no DMA is active. Then run:

```bash
sudo -n env XILINX_XRT=/usr PYTHONPATH=src \
  /usr/local/share/pynq-venv/bin/python -m hdmi_capture.sender prepare \
  --bitfile /path/to/capture.bit --manifest /path/to/build-manifest.json \
  --receipt /path/to/prepared.json --after-reset
```

`--after-reset` is the caller's assertion of that hardware state. It performs
no reset and cannot inspect DMA in an unknown previous image using the new
image's register map. A whole-board reboot is not required: a separately
verified PL reset or safe reconfiguration can establish the initial state.
For example, a known image can first be proven RS=0, Halted=1 and gate disabled
before a separately guarded PL reload. The following preparation performs its
own download again. Do not treat arbitrary reprogramming of an active or unknown
image as a safe reset procedure.

PYNQ itself can touch shutdown registers from its previous saved state before
programming. Preparation rejects saved shutdown-IP entries rather than letting
the SDK access an unknown old register map. Resolve that state through separate
verified recovery; this command does not clear PYNQ's configuration ledger.

After `receiver_prepared` reports HPD1, start the HDMI source and wait for stable
supported output. Prepare again with the same receipt, without `--after-reset`,
before starting the sender:

```bash
sudo -n env XILINX_XRT=/usr PYTHONPATH=src \
  /usr/local/share/pynq-venv/bin/python -m hdmi_capture.sender prepare \
  --bitfile /path/to/capture.bit --manifest /path/to/build-manifest.json \
  --receipt /path/to/prepared.json && \
sudo -n env XILINX_XRT=/usr PYTHONPATH=src \
  /usr/local/share/pynq-venv/bin/python -m hdmi_capture.sender \
  --source litex-credit --prepared-receipt /path/to/prepared.json \
  --bitfile /path/to/capture.bit --manifest /path/to/build-manifest.json \
  --host :: --port 9020 --fps 2 --startup-diagnostics
```

A direct KMS source switches virtual terminals and hides the PC desktop. The
following sequence starts a board waiter first, then a PC trigger and client
pipeline before switching VT. Tracked startup passed 41 exact frames in the
[short014 run](results/2026-10-16/m1-017-prepared-014-report.md), and
[lease015](results/2026-10-16/m1-017-lease-015-report.md) passed held-buffer
observations. [Clean023](results/2026-10-16/m1-017-clean-023.md) replayed the
public ordering from an isolated source export. The same acquisition runtime
passed [normal019](results/2026-10-16/m1-017-normal-019.md) for600seconds;
[the completion report](results/2026-10-16/m1-completion.md) links the separate
interruption, mode and restart checks.

Run016 correctly rejected a FIFO underflow latched during the KMS transition,
before video-driver setup or any selected credit. Its
[startup diagnostic](results/2026-10-16/m1-017-normal-016-startup-diagnostic.json)
is retained. On that same still-running stable source, explicit normal
preparation followed by the production sender passed 21 exact frames in
10.340019 seconds with safe cleanup/storage and no new external abort
([run017 result](results/2026-10-16/m1-017-warm-017-result.json)). The v14 runtime
was unchanged. The queued sequence therefore prepares after the readiness marker
as well as before source startup. It does not waive counters or retry failures.

There are two separate local authentication contexts. Enter the board password
only in its UART terminal, and the PC password only in the PC terminal. The
trigger sends no password or sudo command. Use fresh marker, sender-log, trigger
log, source-output and client-output names for every attempt; these commands do
not remove stale paths.

On the board, authenticate, prepare and launch the sender from the checkout.
Replace the paths first. For this privileged board
command, use its existing PYNQ Python and XRT environment:

```bash
sudo -v
capture_repo=/home/xilinx/litex-hdmi-capture
capture_bit=/path/to/capture.bit
capture_manifest=/path/to/build-manifest.json
capture_receipt=/tmp/prepared-001.json
capture_marker=/tmp/prepared-001.ready
capture_sender_log=/tmp/prepared-001.sender.log
cd "$capture_repo"
if sudo -n env XILINX_XRT=/usr PYTHONPATH="$capture_repo/src" /usr/local/share/pynq-venv/bin/python \
  -m hdmi_capture.sender prepare --bitfile "$capture_bit" \
  --manifest "$capture_manifest" --receipt "$capture_receipt" --after-reset; then
  test ! -e "$capture_marker" && test ! -L "$capture_marker" && \
  test ! -e "$capture_sender_log" && test ! -L "$capture_sender_log" && \
  sudo -n env XILINX_XRT=/usr PYTHONPATH="$capture_repo/src" nohup /bin/sh -c '
    set -eu
    "$1" -c "
import json
import sys
from hdmi_capture.prepared import wait_ready_file
print(json.dumps(dict(event=\"waiting_for_source\", ready_file=sys.argv[1], timeout_seconds=300)), flush=True)
wait_ready_file(sys.argv[1], 300)
" "$5"
    "$1" -m hdmi_capture.sender prepare --bitfile "$2" \
      --manifest "$3" --receipt "$4"
    exec "$1" -u -X faulthandler -m hdmi_capture.sender \
      --source litex-credit --bitfile "$2" --manifest "$3" \
      --prepared-receipt "$4" --host :: --port 9020 --fps 2 \
      --duration 90 --startup-diagnostics
  ' prepared-capture /usr/local/share/pynq-venv/bin/python \
    "$capture_bit" "$capture_manifest" "$capture_receipt" "$capture_marker" \
    >"$capture_sender_log" 2>&1 </dev/null &
else
  echo 'Initial preparation failed; preserve its output and inspect the board' >&2
fi
```

The Python path above is the tested PYNQ3.0.1 virtual environment, not the board
system Python. Before leaving UART, inspect the fresh sender log:

```bash
tail -n 5 "$capture_sender_log"
```

The first use of `--after-reset` still requires the reset/no-active-DMA condition
described above; omit it for a normal subsequent preparation with a valid
receipt. Confirm the sender log contains `waiting_for_source`, then exit the
interactive UART program so the trigger can claim the serial port. While
waiting, the shell's Python waiter performs filesystem checks only. The marker
must be absent
at startup and arrive as a regular file; files, directories and dangling
symlinks already at that path are rejected. The timeout is finite, defaults to
120 seconds, and cannot exceed 900 seconds; this command selects 300 seconds.
After arrival, normal preparation checks the existing receipt, boot and loaded
state before downloading again. Only successful preparation reaches the sender;
there is no second `--wait-ready-file` wait. No marker is removed automatically.

On the PC, build the existing fixture, authenticate locally, and paste the whole
block so the client pipeline is queued before VT changes. Set the board address
and the Python environment containing `pyserial`. The existing
`tools/board_console.py` selects this machine's fixed UART by-id path and expects
an existing normal `xilinx` shell; it is not portable to arbitrary boards or
serial adapters.

```bash
bash scripts/build_kms_fixture.sh
sudo -v
capture_board='fe80::BOARD%INTERFACE'
capture_uart_python=/path/to/serial-venv/bin/python
(
  .venv/bin/python tools/trigger_prepared_capture.py \
    --source-output artifacts/kms-prepared-001 \
    --board-marker /tmp/prepared-001.ready \
    --board-sender-log /tmp/prepared-001.sender.log \
    --uart-python "$capture_uart_python" --timeout 120 --sender-timeout 90 \
    --log artifacts/prepared-001-trigger.jsonl && \
  PYTHONPATH=src:. .venv/bin/python tools/qualify_capture.py "$capture_board" \
    --duration 20 --min-frames 20 --min-fps 1 --hard-deadline 30 \
    --log artifacts/prepared-001-frames.jsonl \
    --summary artifacts/prepared-001-summary.json \
    --save-endpoints artifacts/captures/prepared-001
) >artifacts/prepared-001-pipeline.log 2>&1 &
capture_pipeline_pid=$!
for capture_attempt in $(seq 1 50); do
  grep -q '^{"event": "waiting_for_kms",' artifacts/prepared-001-trigger.jsonl 2>/dev/null && break
  sleep 0.1
done
if grep -q '^{"event": "waiting_for_kms",' artifacts/prepared-001-trigger.jsonl; then
  sudo -n /usr/bin/python3 tools/run_kms_vt.py --duration 240 --frame-id 1500000 \
    --output artifacts/kms-prepared-001
else
  echo 'Trigger did not enter its fresh-output wait; inspect the pipeline log'
fi
wait "$capture_pipeline_pid"
```

The240-second source leaves time for the90-second sender readiness bound,
90-second sender run and cooperative cleanup. The source directory must not
exist when the trigger begins. Its
`waiting_for_kms` event confirms that fresh-path check completed before the KMS
command creates the directory. The trigger reads metadata only and requires
XR24, 640x480, 25200 kHz, two increasing completed presentations from this wait,
both no more than two seconds old, and no source failure/restore result.
The fixture's monotonic timestamps and the trigger must come from the same PC.
The helper trusts metadata from this checkout's source wrapper and fixture; it
does not attest process identity or inspect framebuffer pixels.

It then makes one normal-user UART call: create the fresh board marker and poll
the fresh sender log for at most 90 seconds by default. `--sender-timeout`
selects an integer from 1 through 120 seconds, independently of the source
readiness `--timeout`. The chosen sender bound is recorded in
`waiting_for_kms`. A prior `listening` line, startup error or missing waiting
event rejects that log. Only a new actual `listening`
JSON line makes the helper succeed and starts the client after `&&`; there are
no TCP probes or failed-qualification retries. The UART log preserves that
session line beside the trigger log as `prepared-001-trigger.jsonl.uart.log`.
Marker and sender-log paths must be absolute and contain no ASCII control
characters; printable shell metacharacters are quoted literally.

That observation covers the new preparation and native sender startup. The
UART command timeout is the sender bound plus 10 seconds, and the PC process
wait adds another 10 seconds (100 and 110 seconds at the default bound).
These observation limits do not bound a blocking native constructor. A timeout
preserves failure evidence and does not kill or automatically retry the board
process.

If any stage fails, preserve its logs and inspect the board before another
attempt. A helper timeout does not terminate a native startup or a DMA process.
The source wrapper remains responsible for VT restoration, and the sender's
existing cleanup/unsafe-DMA retention policy still applies. A short client pass
here does not establish the 600-second M1 criterion.

The receipt option attaches without reprogramming. Input clock must be present
when native frontend configuration begins. Startup still uses VTC; runtime
credit health uses fixed-clock gate, FIFO and sequence diagnostics. This path
does not provide automatic recovery after HDMI loss or a mode change.

To prepare again after a sender has exited safely, use the same `prepare`
command without `--after-reset`. It requires the previous receipt, matching
loaded-state evidence, RS=0, Halted=1, reset clear, no DMA error and capture
disabled before downloading again. Disabled request/ACK toggle bits are allowed
for this reload. An active or unclean DMA is rejected without stop commands or
reprogramming. A failed download invalidates the previous receipt; a new receipt
is published only after download, empty endpoint checks and HPD assertion pass.

Attach requires an empty reset command, no pending credit or source/command
fault, zero selected-frame and selected-credit completion counts, and a stopped,
error-free DMA before any video-driver writes. An already-used image must be
prepared again even when its last DMA has halted. Missing or stale receipts fail
closed.

The global observer's `completed_frames` counts all complete input frames,
including disabled, unselected input. It may advance with observed/dropped
frames and native edges while waiting for KMS readiness. This does not consume
a capture credit. The separate `capture_completion` selected-credit counter
must remain zero; FIFO, credit-fault and selected-frame guards still apply.

Failed preparation or attach discards unowned metadata and control references,
so caller cleanup cannot write an earlier image's register map after a reload.
An active source is rejected before its existing resources are changed. Once
attach guards pass, video initialization retains the normal cleanup path.

The receipt records the boot ID, canonical artifact paths and SHA256 hashes,
and PYNQ's saved path, SHA1, download timestamp and device name. Attach reads
this evidence before constructing an Overlay and rechecks it across metadata
construction and hardware checks. PYNQ's `is_loaded()` alone is insufficient:
Overlay construction changes its in-memory bitfile name. PYNQ's state loader
also recomputes the saved hash, so this path reads the persisted JSON directly.

Repeated preparations can produce identical receipt content. The receipt matches
configuration; it is not a unique preparation-epoch token.

These checks require exclusive ownership of PL configuration and capture.
Do not run another sender, notebook or configuration tool concurrently.
The receipt is a software ledger tied to this command's successful download,
not an independent hardware build-ID readback. JTAG, direct FPGA-manager writes,
other configuration software and PYNQ cache-only state updates invalidate its
assumptions. State checks can detect recorded changes but cannot exclude an
unrecorded reconfiguration or a concurrent change after the final check.
The existing sender route without `--prepared-receipt` retains its loading
behavior and does not gain these preparation guards.

Host tests exercise receipt validation, preparation/attach ordering, metadata
races and rejected hardware states. The linked014/015/017 results remain short
hardware evidence. Clean023
replayed the queued public workflow from an isolated source export; normal019
and the separate fault/restart evidence complete the accepted fixed-mode M1
scope in the aggregate report. Board results must identify the exact source
revision and record readiness, receiver, DMA and cleanup checks separately.
