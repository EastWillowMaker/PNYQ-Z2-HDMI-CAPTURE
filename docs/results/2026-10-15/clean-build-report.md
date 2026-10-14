# Clean checkout replay: full CAD build passed

The isolated checkout is `artifacts/clean-replay-001`, cloned locally with
`git clone --no-hardlinks . artifacts/clean-replay-001` at exact commit
`aa4e86ee8bcee1c9a3b10af207180a6f9a7c6407`. No prior artifact directory was
removed, no board was programmed, and no global Python installation was changed.

The documented bootstrap initially inherited the host's configured
`http://devpi.home.arpa:3141/root/pypi/+simple/` package index and stalled while
installing build dependencies. Its original log is `bootstrap.log`; only that
owned pip process was stopped. Retrying with explicit
`--index-url https://pypi.org/simple` succeeded. The public index argument is now
included in the portable instructions. This is a documented correction to the
replay, not a claim that the uncorrected sequence completed unchanged.

CPython 3.12.13 created a new `artifacts/gate-venv` inside the checkout. Public
Git sources were installed at Migen
`e19524c963a8342952840983047557707fbe0b6a` and LiteX
`b2759f69bcae8be0357fb2ee5eebe216365d1f00`. Generation passed both installed-source
hash checks in `gateware/dependencies.json`; generated RTL SHA256 is
`3d170c5815c939ea6849c1c876311a638c6d9e92156149f1d9aac5a730ac3c50`, matching the
physically tested `013` gate RTL. `gate-dependencies.txt` records the complete
resolved gate environment; `bootstrap-public-index.log` records fresh wheel
builds and installation. No sibling environment was used.

PYNQ was freshly cloned from its public v3.0.1 branch and HEAD explicitly checked
against `93ddd21ab623883590a8c8b07f0b157b2855da4b`; its working tree was clean.
The new output is `artifacts/m1-build-001` **inside the isolated checkout**.
Its HLS tree is a fresh real directory; it has no link to `m1-project-001/hls`.

The full build uses installed Vivado/Vitis 2025.2 executable paths via the
script's explicit arguments and a 2400-second host-only timeout:

```bash
# Working directory: artifacts/clean-replay-001
artifacts/gate-venv/bin/python -m gateware.generate \
  --output artifacts/litex_capture.v
timeout --signal=TERM 2400 artifacts/gate-venv/bin/python scripts/build_capture.py \
  --output artifacts/m1-build-001 --gateware artifacts/litex_capture.v \
  --vivado /home/eastwillow/Xilinx/2025.2/Vivado/bin/vivado \
  --vitis-run /home/eastwillow/Xilinx/2025.2/Vitis/bin/vitis-run \
  --stage bitstream
```

The full build completed with exit status **0** at 2026-10-15 02:23:21
Asia/Taipei (2026-10-14 18:23:21 UTC). HLS began at 02:15:23: roughly eight
minutes from fresh HLS start to paired artifact export, excluding dependency
bootstrap. Shell session `35598` finished. The original console remains
`artifacts/clean-replay-001/full-build-console.log`.

## Executed checks and outputs

The exact PYNQ receiver/PS7 configuration, AXI INTC topology, original VDMA
configuration, and legacy gate ABI from `aa4e86e` were retained. No tracked
checkout source changed; final `git diff --exit-code aa4e86e` and vendor
`git diff --exit-code` both passed. Evidence logs are untracked local files.
No one-credit changes from later work were included in this replay.

Both HLS IPs ran new `csynth_design` and `export_design` invocations from newly
copied public source. Their generated Verilog compares byte-for-byte equal to
the prior HLS001 output: six color-converter and nine pixel-packer files; the
comparison is `artifacts/hls-rtl-comparison.json` within the replay checkout.
The old output was read only for this comparison, not used by the build.
Estimated HLS Fmax values are 221.24 MHz and 218.26 MHz respectively; these
estimates are distinct from physical implementation timing. The upstream
scripts do not run C simulation or co-simulation, and this replay does not
claim either. Vendor warnings remain in the logs.

| Check | Fresh replay result |
|---|---|
| Setup / hold / pulse-width slack | 0.568 / 0.017 / 0.264 ns; zero failing endpoints |
| Internal clocks/endpoints | zero no-clock and unconstrained internal endpoints |
| Bus skew | all 41 reported constraints MET; zero violations |
| CDC | zero critical; 131 CDC-3 info, three CDC-9 info, one VTC CDC-6 warning |
| DRC | zero error/critical; 12 warnings and one advisory retained |
| Main and child synthesis/implementation logs | zero ERROR or CRITICAL WARNING diagnostics |
| Utilization | 6,063 LUTs, 12,567 registers, 7.5 BRAM tiles, nine DSPs |
| External timing coverage | five input and two output delay gaps retained |
| Routed Gray synchronizers | all 256 destination registers retain ASYNC_REG=1 |
| Gate connectivity | all eight inputs connected; seven intentionally unused outputs |
| Exact installed metadata parser | PASS for real controller and VDMA interrupt routing |

The output directory is
`artifacts/clean-replay-001/artifacts/m1-build-001`:

- `capture.bit`: SHA256
  `7f75ada24d2a601a38f18ca3a906448d57b924c48fa331e0bf28f11ab08ea04d`.
- `capture.hwh`: SHA256
  `f4cfa598abd5392bad414e3c90638d900d7a8ad2bb75a630625f2f0ab809ee2c`.
- `build-manifest.json`: all eight recorded file hashes match readback of the
  exact isolated files (gate, health/lock RTL, receiver SyncBase/component,
  EDID, bitstream, HWH).

The parser evidence `artifacts/runtime-irq-parser-regression.json` within the
replay records the same HWH hash, exact copied board metadata source hashes,
and dependencies. It discovers `system_interrupts` at raw IRQ 61, with VDMA
`s2mm_introut` at controller input 0, GPIO at 1, and VTC at 2. This is offline
parser execution; physical IRQ/UIO delivery is not established by it.
`post-review.tcl`/`post-review-v2.log` check the routed Gray registers and
`port-review.json` checks the generated gate instance. The first optional
post-review command used the wrong working-directory prefix and failed before
opening a checkpoint; its `post-review.log` is preserved. The corrected check
passed. This tooling typo did not change the full build or its exit result.

## Portable bootstrap and scope

A separate new client `.venv` in the checkout installed CPython 3.12.13's
compatible pinned NumPy 2.5.4 and Pillow 12.3.0, then installed this package
editable without dependencies. `hdmi-capture --help` ran successfully;
`host-bootstrap.log`, `client-help.log`, and `artifacts/host-python.txt` preserve
that bootstrap. The read-only SSH doctor/deployment examples and first-frame
commands were not executed against the board in this replay. The original
physical tests used the separate `013` pair and locally authenticated UART,
not a clean-checkout normal-user SSH deployment.

This completes a fresh clean-checkout **build** replay after the documented
public-index correction. It is not bit-for-bit reproduction: paired hashes and
physical implementation results differ from `013`, while generated gate/HLS
RTL and receiver snapshot hashes match. The replay bitstream was **not loaded**.
Existing physical qualification does not automatically qualify this new pair,
and neither legacy artifact establishes source-to-DMA frame association.
The forthcoming one-credit implementation requires its own build and tests.

The retained VTC CDC warning, vendor internal XPM Gray CDC waivers, and external
I/O timing gaps remain as described in [build.md](../../build.md). AXI INTC also
retains its manual edge mask `0xFFFFFFFF` versus inferred level metadata
`0xFFFFFFF8`, and scalar IRQ wiring overrides the output bus interface. The
original base Tcl creates the controller without an explicit trigger mask;
therefore only topology preservation is established, not identical inferred
trigger configuration. The exercised board VDMA driver clears frame status
before returning, supporting edge rearming, but unexercised GPIO/VTC interrupt
wait paths and pathological event/ack timing are not validated by this replay.
No warnings were suppressed or custom CDC waivers added.
