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

For first preparation, first confirm that the board or PL was reset and no DMA
is active. Then run:

```bash
PYTHONPATH=src python -m hdmi_capture.sender prepare \
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

After `receiver_prepared` reports HPD1, start the HDMI source. Then run:

```bash
PYTHONPATH=src python -m hdmi_capture.sender \
  --source litex-credit --prepared-receipt /path/to/prepared.json \
  --bitfile /path/to/capture.bit --manifest /path/to/build-manifest.json \
  --host :: --port 9020 --fps 2 --startup-diagnostics
```

A direct KMS source can switch virtual terminals and hide the PC desktop.
Arrange board startup and evidence collection through another console or remote
automation before that switch. These tracked commands cover receiver preparation
and capture; portable PC/board orchestration and its hardware qualification remain
separate work.

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
fault, zero selected/completed counts and a stopped, error-free DMA before any
video-driver writes. An already-used image must be prepared again even when
its last DMA has halted. Missing or stale receipts fail closed.

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
races and rejected hardware states. They do not establish physical HDMI
readiness, receiver timing, real DMA cleanup or board qualification. Board
results must identify the exact source revision and record those checks.
