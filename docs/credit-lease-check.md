# Observe a held single-credit buffer

`tools/check_credit_lease.py` runs on the PYNQ board to observe a completed
single-credit buffer while its lease is deliberately held. It leaves the HDMI
source running, requires the native edge counter to advance, and checks that
the parked buffer and its held identity remain unchanged. It then ACKs that
lease and requires a second complete, exact analytic RGB pattern with new
native/SOF identities and a different optical pattern ID.

This check has host-side fake-board coverage only until a dated hardware result
is linked here. It is not the ten-minute qualification or independent proof
that an optical pattern ID equals a particular native VSYNC count.

Run it during an authorized experiment with the supported stable direct-KMS
pattern source already active. Keep the shared USB-C Hub and HDMI cable
connected. Stop other sender/DMA applications first; this checker owns the
single native allocation. Use the production receiver preparation command and
its same-boot receipt before starting KMS, then use that receipt here. A receipt
from a previous capture is insufficient: the prepared attach requires the
verified reset/empty credit state. Follow the current [quickstart](quickstart.md)
for preparation rather than the ignored operator prototypes.

Copy the tracked `tools/check_credit_lease.py` and `tools/hdmi_pattern.py` beside
each other on the board, plus the current `src/hdmi_capture` package, verified
bit/HWH/manifest pair and prepared receipt. From the board checkout/staging
root, use its existing PYNQ environment and authenticate sudo locally:

```sh
sudo -v
sudo -n env XILINX_XRT=/usr PYTHONPATH="$PWD/src" \
  /usr/local/share/pynq-venv/bin/python -u -X faulthandler \
  tools/check_credit_lease.py overlay/capture.bit \
  overlay/build-manifest.json --prepared-receipt prepared.json \
  --hold-seconds 1 --output lease-check-NEW.jsonl
```

The output must be new and its parent directory must exist. The file is opened
exclusively before hardware initialization. The checker requires a prepared
receipt and never performs an implicit overlay load or mode change. Source
startup retains artifact, native mode, disabled-baseline and pairing checks.
Native startup still needs a running HDMI pixel clock; a lost clock during
native configuration can cause an uncatchable MMIO fault. The acquisition
timeout cannot bound a blocking native constructor. Do not treat this checker
as a missing-source startup test.

The dwell defaults to one second; accepted values are finite, from 0.1 to
3 seconds. Four evenly spaced observations recheck fixed-clock GPIO and raw
VDMA registers, invalidate the halted native buffer cache and hash all raw BGR
and converted RGB bytes. Register/CPU work adds to the configured dwell; all
sample times are recorded. At least two native edges must advance during the
lease. Global observed/completed/dropped input counters can advance while
unselected input is discarded; selected count, held credit identity and
integrity counters must remain stable. Every RGB byte of both acquired frames
must match `hdmi_pattern.verify`; no tolerance or captured golden image is used.

The extra leased `read()` call is bounded by 0.2 seconds and must return the
source's explicit lease rejection. Its DMA `arm` method is temporarily replaced
with a guard that raises before any arm writes. A missing lease check therefore
fails the experiment without intentionally granting a second credit. The guard
is removed before ACK and the next real acquisition. An unexpected timeout or
rejection reason also fails the experiment.

The flushed JSONL file contains configuration/file hashes, each bracketed
identity/counter/raw-VDMA snapshot, physical buffer address, cache-refreshed
raw/RGB hashes, full pattern verification, sample metadata, ACK observations
and the final result. It saves no NPY, image or pixel payload. Counter reads
are sequential rather than atomic; the held tuple uses the producer's separate
ownership/coherence contract. The checker does not equate KMS optical IDs with
hardware source counter values or infer lost-frame counts from FIFO episodes.

A successful run exits0 only after cooperative source close reports DMA safe.
Any validation, cancellation, startup or cleanup error exits1 after attempting
cooperative close. On a validation failure, the checker does not ACK a suspect
lease; source close disables selection and halts DMA before native free. Final
proof/cleanup failure remains a failed result even when halt succeeds. If halt
safety is unknown, the checker retains the source/native references and enters
the sender's indefinite unsafe-DMA hold. It writes a failed result first when
the output remains writable. Output/event-loop failures also enter that hold
when DMA safety is unknown. Never wrap this tool with forced-kill escalation.
Use one cooperative interrupt and wait; an unsafe hold requires an authorized
external hardware recovery before process teardown. SIGKILL and native crashes
cannot be made safe by Python cleanup.

Run the local seam tests without PYNQ or display access:

```sh
PYTHONPATH=src:. python3 -m pytest -q tests/test_credit_lease.py
```

Those tests cover the complete fake ownership sequence, moving held IDs,
buffer mutation, running/erroring DMA, absent native progress, the guarded
leased-read path, a repeated optical pattern and cleanup failure. They prove
checker rejection/control flow, not actual cache coherence, DMA completion,
receiver CDC, physical association or hardware recovery.
