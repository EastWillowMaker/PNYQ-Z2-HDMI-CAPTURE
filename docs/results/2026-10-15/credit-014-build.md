# Credit build014 and local integration checkpoint

Build014 completed bitstream export at 2026-10-15 02:53:21 Asia/Taipei.
Inputs were snapshotted under `artifacts/m1-project-014/build-source`; HLS
outputs were copied from the fresh clean-checkout replay, not rebuilt again.
Current source files match every recorded source-manifest hash. Paired bit/HWH,
gate, reset and health RTL hashes were read back and checked against the manifest.

- Bitstream SHA256: `c9d060ade5bb0d178003d665b9b483a53a2af51142d71bcaf2fe9c2582f9c954`.
- HWH SHA256: `31a0c55e39139ecac454e91ec07afe0f1945f145a4ce4e89f6e9c1ebef0cad10`.
- Setup/hold: 0.179/0.022 ns; zero no-clock or unconstrained internal endpoints.
- All 56 reported bus-skew constraints MET; no run-log ERROR/CRITICAL WARNING.
- CDC: 161 CDC-3 info, four CDC-9 info, one retained VTC CDC-6 warning.
- DRC: 12 warnings and one advisory; no error/critical findings.
- Five input/two output timing-delay gaps and vendor XPM waivers remain.
- Routed readback: 256 Gray synchronizer FFs plus all six receiver-reset
  synchronizer FFs retain ASYNC_REG. `post-review.log` records the check.
- Exact installed PYNQ metadata parser maps VDMA input0 through AXI INTC to
  raw IRQ61; GPIO/VTC inputs1/2. This is offline parser evidence only.

The timing methodology summary retains LUTAR-1, PDRC-190, TIMING-9,
TIMING-18 and XDCB-5 warnings; this is not a warning-free design. No new
broad false paths or warning suppression were added. Main CAD reports, input
snapshot, manifest and parser evidence remain in `artifacts/m1-project-014`.

Parent integration execution after all producer/qualifier changes:
`.venv/bin/python -m pytest -q tests hardware/test_build_manifest.py`:
**291 passed, 1 optional-dependency skip in 2.64s**. Dedicated Migen/Icarus and
manifest suite: **62 passed, zero skips in 5.60s**. CPython3.10 byte-compilation
of sources, sender and qualifier passed. Actual-XPM reset simulation log ends
in PASS for pulse retention, six-edge release and real gate sticky fault.
These are local tests, not hosted CI or physical capture evidence.

## Behavioral impact and remaining gate

Legacy continuous selection and unknown ring association remain available only
through the legacy adapter. The new adapter rejects missing/wrong credit ABI
before overlay load, owns one parked buffer, waits for automatic DMA halt plus
next-SOF-closed gate identity, and rechecks integrity before lease acknowledgement.
Malformed trailing pixels now fail visibly and count as invalid; busy/premature
commands, resets and missing source events fail the session. Bounded raw DMA
stop replaces the unbounded native stop loop; inability to prove halt retains
memory and enters the existing process safety hold. The default qualifier rejects
legacy/unknown accounting; explicit legacy mode preserves historical image tests.
See [gate impact](credit-gate-tests.md) and [design](../../source-accounting.md).

No build014 overlay has been loaded. Running-before-SOF, automatic one-frame halt,
cache/buffer correctness and native-VSYNC/SOF phase assumptions require actual
board execution. Full M1 remains open, including new sustained capture/accounting,
physical source unplug/replug and renewed interruption tests. Previous build013
pixel results do not qualify this new path.

Deployment packages are prepared locally in `artifacts/deploy`:
`sender-m1-v6.tar.gz` SHA256
`8fbe000ab6767f241bbb739f918c5f7fbdf8b58e6109c7381525298aa46408a4`;
`overlay-m1-014.tar.gz` SHA256
`29888b3ae884b29f2cadb04b6214dbba1408ec0a03de09595df512ecc7c32bc5`.
Only Python source and the paired overlay/manifest are included; no captured
images or credentials. Board sudo cache must be renewed locally before load.
