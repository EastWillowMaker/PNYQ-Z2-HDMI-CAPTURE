# Build017 clean checkout recipe replay

The fresh replay is running. Its final CAD result is pending; no new hardware
qualification is claimed.

The previous clean-checkout report exercised legacy013 at `aa4e86e`, before
the single-credit interface and the color-converter drain fix. Build017 rebuilt
both HLS cores and passed implementation using frozen sources, but did not
record a clean-checkout recipe replay. This run checks that missing build path.
Current software edits do not require rebuilding RTL; their content is excluded
from the archived build source.

The isolated checkout is a `git archive` extraction of committed
`3fdf2738c125fcd2fd57edc6a01ba0c0020df295` into
`artifacts/clean-replay-017-20261016-0308/checkout`. All 15 files in the original
017 frozen-source map match this revision exactly (`source-comparison.json`).
No source files in the working checkout were changed for this run.

PYNQ was freshly cloned from the public v3.0.1 branch into the new checkout and
verified at `93ddd21ab623883590a8c8b07f0b157b2855da4b`, with a clean tree. The
existing isolated clean-replay001 gate environment was reused after generation
checked both pinned package versions and installed Python-source hashes.
Generation produced SHA256
`e4515603bf95855dc1aa82ecce4104bf22dfd05f9cce8d6d8d421887675dfbec`, matching
017. This is a clean source/HLS/CAD replay, with a verified reused Python
environment rather than a new package installation.

Vivado 2025.2 SW build6299465 and Vitis-run 2025.2 SW build6295257 were queried
before the build. A tiny independent `xc7z020clg400-1` synthesis checked out
its Synthesis/device license and exited0; its complete log is retained. Disk
preflight showed463GiB available. `preflight.json` records versions, resolved
Python packages, tool file hashes, and the vendor revision/status.

The exact invocation and start time are in `build-command.json`; terminal
session34346 runs the build wrapper. Output is the entirely new directory
`checkout/artifacts/m1-build-001`; neither HLS output nor the Vivado project is
linked or copied from017. `full-build-console.log` preserves the complete
console. The command is:

```bash
# cwd: artifacts/clean-replay-017-20261016-0308/checkout
/home/eastwillow/Documents/litex-hdmi-capture/artifacts/clean-replay-001/artifacts/gate-venv/bin/python \
  scripts/build_capture.py --output artifacts/m1-build-001 \
  --gateware artifacts/litex_capture.v \
  --vivado /home/eastwillow/Xilinx/2025.2/Vivado/bin/vivado \
  --vitis-run /home/eastwillow/Xilinx/2025.2/Vitis/bin/vitis-run \
  --stage bitstream
```

The build follows the committed CLI through source preparation, both fresh
HLS syntheses/exports, the isolated-frame drain regression, block-design
validation/IP generation, implementation, timing/CDC/DRC/log gates, and paired
manifest export. Its color-converter source copy receives the committed
`style=flp` patch; the pinned vendor checkout remains unchanged. No warning or
constraint gate has been relaxed.

Structural discovery used the codebase-memory graph generation
2026-10-15T19:05:15Z, outbound entry-point tracing and source snippets, followed
by coverage checks on relied-on tracked paths. `hardware/implement.tcl`
reported partial parsing at lines15/35; the full file was read directly.
Excluded artifact/vendor contents were read directly. Two initially guessed
Tcl filenames were absent; the actual paths are `hardware/capture.tcl` and
`hardware/implement.tcl`. Graph coverage remains a best-effort signal.

Two local launcher mistakes occurred before the build created output: a
nonexistent root gate-venv path, then wrong argument indexes in the recording
wrapper. The corrected gate invocation passed dependency checks; the corrected
wrapper started the single build attempt. These are not CAD failures or claims
that the initial launcher commands succeeded.

This replay does not access the board, UART, display, NIC, or SD image. Its new
bit/HWH pair, if exported, will require separate physical qualification. The
original017 physical evidence is not evidence for the replay pair. Existing
VTC CDC warning, XPM vendor waiver treatment, and external delay gaps remain
subject to the build report. HLS C simulation/co-simulation, hosted CI, and
physical I/O margins are outside this execution.

## Live checkpoint

Both fresh HLS syntheses and exports completed. All 15 generated Verilog
files match original017 byte for byte; see
`artifacts/clean-replay-017-20261016-0308/hls-rtl-comparison.json` and the
compact copy [credit-017-replay-hls-comparison.json](credit-017-replay-hls-comparison.json).
All four synthesized-pair drain cases passed: 8x4 and full640x480, each
with and without input/output stalls. Each full-VGA case drained307200
pixels into230400 packed words with480 line endings.

Vivado has progressed to block-design generation/validation after those checks.
Final implementation, timing/CDC/DRC checks, paired export, and routed
post-review are pending. Build session34346 continues; no hardware was
programmed and no capture qualification is claimed for these new outputs.
