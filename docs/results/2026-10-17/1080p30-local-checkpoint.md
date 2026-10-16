# 1080p30 implementation checkpoint

The new explicit `1080p30` profile targets 1920×1080 at 74.25 MHz and retains
VGA as the default. It binds build EDID, receiver range, input constraints,
gateware geometry, artifact manifest, runtime allocation and qualification to
one expected profile. Legacy schema-1 VGA manifests remain accepted. Baseline
PYNQ capture remains VGA-only. The single-credit ABI and safe-halt policy are
retained.

The optional board output is a fixed PL pattern, using independent PS FCLK0
and MMCM/BUFIO/BUFR clocks with the pinned RGB-to-TMDS serializer. It has no
output DMA. The serializer boundary uses its documented RBG byte order, while
the expected image and host API remain RGB888. Output HPD is an unused input;
the transmitter ignores EDID and continues while clocked and locked. See the
dated primary-source analysis in research.md for the board electrical limits
and upstream HPD-direction discrepancy.

Validation on the integrated working tree:

```sh
.venv/bin/python -m pytest -q
PYTHONPATH=.venv/lib/python3.12/site-packages:src:. artifacts/clean-replay-001/artifacts/gate-venv/bin/python -m pytest -q tests/test_gateware.py
.venv/bin/python -m pytest -q tests/test_modes.py tests/test_build_modes.py hardware/test_build_manifest.py
```

Results: 565 passed and one module skipped in the host environment; the skipped
module needs pinned Migen/LiteX. Running that module with the pinned generator
environment and the host pytest packages passed all 45 tests. The separate
profile/build/HWH set passed 42 tests. The output simulation checks two full
2200×1125 timing frames, every active RGB byte against the Python reference,
blanking, sync pulses and a mid-frame reset/release. It does not simulate the
vendor serializer or physical TMDS link. Full host validation also includes
the GUI/BMP tests previously recorded in the desktop-viewer report.

Pinned-vendor preparation passed for VGA and 1080p30, including optional TX
staging. The VGA EDID hash is identical to the prior qualified build. The
1920×1080 generated LiteX RTL hash is
`e1f4202e8077a917d7d3a7214b2b0b6266fa5a1e3ffb33e45dd9112e7fcbaad1`.

Recommended reading follows execution: modes.py and build scripts, capture
Tcl and output RTL, source artifact verification and DMA setup, then sender
and qualification. CLI → sender source construction → start/prepare → artifact
verification → overlay/configuration → one-credit acquisition → encoding →
CaptureClient → pixel verification is the affected path. Prepared receipts
still hash the original artifact files; they do not attest a unique epoch.

Runtime verifies input dimensions and 24-bit DMA pixels. It cannot observe
the input pixel clock or actual refresh rate; source cadence requires separate
measurement. New-mode synthesis, routed timing/CDC/DRC, board loading, output
loopback, sustained capture, real GUI/BMP checks and performance measurements
remain pending at this checkpoint. There is no claim of 1080p hardware support
or unchanged physical VGA behavior based on these local tests alone.
