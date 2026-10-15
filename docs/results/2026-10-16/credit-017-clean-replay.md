# Build017 clean checkout recipe replay passed

The committed build017 recipe completed from isolated archived source with
both fresh HLS syntheses/exports, all four generated-RTL drain cases, complete
Vivado implementation, and paired manifest export. The build exited 0 at
2026-10-16 03:17:42 Asia/Taipei after 606.745 seconds. Routed post-review then
exited 0 at 03:18:02. No board, UART, display, NIC, or SD image was accessed.
The new pair has not been physically qualified.

The previous [clean-checkout report](../2026-10-15/clean-build-report.md)
covered legacy013 at `aa4e86e`, before the credit interface and HLS drain fix.
[Original017](../2026-10-15/credit-017-build.md) rebuilt both HLS cores and
passed CAD using frozen sources, but did not record this clean-checkout
recipe replay. This run closes that build-evidence gap. Current software edits
do not require an RTL rebuild and were excluded from the archived source.

## Source and environment

The checkout is a `git archive` extraction of committed
`3fdf2738c125fcd2fd57edc6a01ba0c0020df295` into
`artifacts/clean-replay-017-20261016-0308/checkout`. All 15 files in the original
017 frozen-source map match this revision exactly; see
[the source comparison](credit-017-replay-source-comparison.json).
After completion, every archived regular file still matched its archive entry.

PYNQ was freshly cloned from its public v3.0.1 branch into this checkout,
verified at `93ddd21ab623883590a8c8b07f0b157b2855da4b`, and remained clean
after the build. HLS and Vivado outputs were new real directories, with no
links or copied implementation outputs from017. Only the committed isolated
color-converter copy received the `style=flp` patch; original vendor source
remained untouched.

The existing isolated clean-replay001 CPython 3.12.13 gate environment was
reused. Generation passed both pinned package version/source-hash checks:
Migen `e19524c963a8342952840983047557707fbe0b6a` and LiteX
`b2759f69bcae8be0357fb2ee5eebe216365d1f00`. Regenerated gate SHA256 is
`e4515603bf95855dc1aa82ecce4104bf22dfd05f9cce8d6d8d421887675dfbec`, matching
017. This replay verifies clean source/HLS/CAD with a verified reused Python
environment; it does not claim a new dependency installation.

Vivado 2025.2 SW build 6299465 and Vitis-run 2025.2 SW build 6295257 were queried
before execution. A separate tiny `xc7z020clg400-1` synthesis checked out its
Synthesis/device license and exited 0. Disk preflight showed 463 GiB available.
[Preflight evidence](credit-017-replay-preflight.json) records versions,
resolved Python packages, tool launcher/binary hashes and vendor identity.

## Exact command and results

[The command record](credit-017-replay-build-command.json) preserves the
working directory, start/end timestamps, arguments, tool hashes and exit 0.
The complete local console remains
`artifacts/clean-replay-017-20261016-0308/full-build-console.log`.

```bash
# cwd: artifacts/clean-replay-017-20261016-0308/checkout
/home/eastwillow/Documents/litex-hdmi-capture/artifacts/clean-replay-001/artifacts/gate-venv/bin/python \
  scripts/build_capture.py --output artifacts/m1-build-001 \
  --gateware artifacts/litex_capture.v \
  --vivado /home/eastwillow/Xilinx/2025.2/Vivado/bin/vivado \
  --vitis-run /home/eastwillow/Xilinx/2025.2/Vitis/bin/vitis-run \
  --stage bitstream
```

Both new HLS `csynth_design`/`export_design` executions completed. All 15
synthesized Verilog files match original017 byte for byte;
[the full comparison](credit-017-replay-hls-comparison.json) records each hash.
The actual synthesized pair passed 8x4 and 640x480 isolated-frame cases, each
with and without input/output stalls. Each full-VGA case drained 307200 pixels
into 230400 packed words with 480 line endings and exact data/boundaries.

| Check | Fresh replay result |
| --- | --- |
| BD validation/IP generation | Passed; critical BD message count 0 |
| Setup / hold / pulse-width slack | 0.401 / 0.014 / 0.264 ns; zero failing endpoints |
| No-clock / unconstrained internal endpoints | 0 /0 |
| Bus skew | All 56 constraints MET; zero violations |
| CDC | 161 CDC-3 info,4 CDC-9 info,1 retained VTC CDC-6 warning; 0 critical |
| DRC | 8 warnings, 1 advisory; 0 error/critical |
| Main/Vivado/all 42 child run logs | No ERROR or CRITICAL WARNING diagnostics |
| Routed synchronizers | 256 Gray registers and 6 receiver-reset/data FFs ASYNC_REG=1 |
| Utilization | 6690 LUTs, 15938 registers, 7.5 BRAM tiles, 9 DSPs |
| External delay coverage | Retained 5 input / 2 output gaps |
| Manifest/source readback | All 9 file hashes match; archive/vendor source unchanged |

The new paired outputs are under
`artifacts/clean-replay-017-20261016-0308/checkout/artifacts/m1-build-001`:

- `capture.bit`: SHA256
  `ae3a65d77b1662fedef9ffbc62dd9484cdd8a155af136596da3e6b695fb6846e`.
- `capture.hwh`: SHA256
  `3bfbbf124960ec932a4a53bb4fcb4a5969b89b9a96d6329143bdfc8442eef9a6`.
- `build-manifest.json`: every field matches original017 except the two
  bitstream/HWH hashes. This includes the credit ABI, VDMA mode, native source
  identity policy, source hashes, receiver range, clocks, geometry and slacks.

The replay therefore reproduces the recipe/source configuration, not identical
paired-file hashes. The prior017 physical evidence does not qualify this new
pair. The replay pair was never loaded or sent to the board.

Full local evidence is preserved under
`artifacts/clean-replay-017-20261016-0308`: `source.tar`,
`source-revision.txt`, `source-comparison.json`, `preflight.json`,
`gate-generation-verified.log`, `vendor-clone.log`, `license-probe*.log`,
`build-command.json`, `build-result.json`, `hls-rtl-comparison.json`,
`verification.json`, `post-review.tcl`, and `post-review*.log`.
The build output retains `timing.rpt`, `bus-skew.rpt`, `cdc.rpt`, `drc.rpt`,
`utilization.rpt`, both HLS trees and all child synthesis/implementation logs.
The routed post-review verifies synchronizer attributes explicitly, beyond
relying on CDC counts. `verify-result.py` records hash/source/log checks.

## Scope and limitations

No timing/CDC/DRC gate, clock constraint or warning policy was relaxed.
Existing VTC CDC warning, vendor XPM constraints/waiver treatment and external
delay gaps remain. HLS C simulation/co-simulation, hosted CI, physical IRQ/UIO,
DMA/RGB/capture correctness, reconnect behavior and electrical margins were
not tested by this build replay. Build success is separate from physical M1.

Structural discovery used codebase-memory graph generation
2026-10-15T19:05:15Z, entry-point tracing, snippets and coverage checks.
`hardware/implement.tcl` reported partial parsing at 15/35; its full source was
read directly. Excluded artifacts/vendor sources were read directly. Two
initially guessed Tcl names were absent; actual paths are
`hardware/capture.tcl` and `hardware/implement.tcl`. Coverage remains a
best-effort signal.

Two launcher mistakes occurred before any build output was created: an absent
root gate-venv path, then wrong recording-wrapper argument indexes. Corrected
generation passed pinned dependency checks and the corrected wrapper launched
the single full build. Neither mistake is represented as a successful command
or a CAD failure. The earlier checkpoint commit correctly marked final CAD as
pending; the results above supersede that checkpoint.
