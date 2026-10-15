# Credit gate impact and local execution evidence

Date: 2026-10-15, Asia/Taipei. Interface `single_credit_parked_v1`; completion
policy `next_sof_after_selected_output_drain_v1`. This report covers local unit,
compiled RTL and vendor-model simulation. It does not qualify DDR completion,
new bitstream timing/CDC, board capture or the ten-minute/600-frame M1 run.

## Behavior before and after

The previous build013 gate selects every SOF accepted with enable high; global
geometry counters include unselected frames. Its latest output ID is not tied to
a VDMA buffer. Stock PYNQ3.0.1 starts with IRQ threshold four, reads a rotating
`(activeframe + 2) % 4` slot and clears some errors before returning the buffer.
Adding a latest-ID read to that path cannot establish source/buffer association.

The new gate defaults disabled, accepts one request while idle/enabled and selects
one later accepted SOF. It freezes both accepted-SOF and synchronized native-VSYNC
IDs for that credit, consumes every other observed frame as an unselected frame,
and forbids further requests until ownership release is acknowledged. A request
accepted on the same edge as SOF applies to a later SOF. ACK while not DONE, a new
request while busy/disabled, or ACK plus request on one edge sets sticky failure.
The selected ID never changes to an unselected frame's ID.

The selected last pixel is first an output transfer, then a pending tail. DONE
and `selected_completed` are published once, only at the following accepted
unselected SOF with no intervening geometry/protocol fault. Final transfer and
following SOF may coincide; ACK on that same edge is still premature. This closes
the delayed-extra-pixel race without assuming CPU timing. DONE remains a stream
proof; the separate reader must verify one-frame parked VDMA **automatic HALTED**
and raw status errors before cache invalidation or copying. An IRQ alone is a
frame-start indication; manually clearing RS may truncate an in-progress stream.
See [AMD PG020 S2MM control](https://docs.amd.com/r/en-US/pg020_axi_vdma/S2MM_VDMACR-S2MM-VDMA-Control-Register-Offset-30h).

Missing/extra EOL or premature SOF in a selected frame sets failed and prevents
DONE; already emitted pixels cannot be retracted. Independent audit reproduced
a inherited observer gap: after a configured-length frame, an extra non-SOF
pixel previously set only unexported orphan/error counters while DONE remained
successful. Now an accepted orphan while enabled/busy sets the exported source
fault, clears DONE and prevents future selection. The global invalid counter
increments once per consecutive orphan episode, including disabled startup, so
overlong input cannot be described as zero invalid merely because it was dropped.
Disabled startup remains reported and must be baselined before enable with zero
selected frames; counters are not cleared to conceal it. An error in a later
unselected frame is a subsequent session failure, not retroactive corruption of
an already SOF-closed selected frame.

Every enabled SOF must advance the native-VSYNC sample by exactly one modulo32;
native progress of two before another SOF is a missing-SOF fault. Native IDs and
accepted-SOF IDs therefore retain a constant offset in a no-fault enabled session.
Receiver reset while enabled or busy is sticky failure. A completely stopped
source still requires the reader timeout and shutdown evidence interval; no clock
or missing event is invented. Hardware wrap is modular; the software contract
rejects wrap/reset within a session. Native-VSYNC/active-video phase, FIFO latency
and continuous drain assumptions require the new integrated build/board evidence.

Source locations: [capture implementation](../../../gateware/capture.py),
[handshake and compiled tests](../../../tests/test_gateware.py),
[reset CDC](../../../hardware/receiver_reset_sync.v),
[GPIO plumbing](../../../hardware/capture.tcl),
[manifest/HWH guards](../../../scripts/build_manifest.py).

## Executed checks

From repository root:

```sh
../litex-network-router/.venv/bin/python -m pytest -q tests/test_gateware.py hardware/test_build_manifest.py
../litex-network-router/.venv/bin/python -m gateware.generate --output artifacts/litex_capture_credit.v
```

The initial credit implementation passed **55 tests in 4.43s**. Following the
independent overlong-frame finding and the next-SOF closure refinement, the final
suite passed **62 tests in 5.85s**, zero failures or skips: 44 Migen cases, one
compiled generated-Verilog case and 17 HWH/manifest cases. The compiled Icarus12.0
case processes four complete 640x480 source frames (1,228,800 pixels), selects two,
drops two, and checks all 614,400 output pixels, SOF/EOL markers, source IDs,
completion counts, deterministic backpressure and mid-frame synchronous reset.

Focused cases cover immutable identity while later frames are dropped; forbidden
commands; every EOL position; early SOF; reset during enabled idle/active credit,
including enable cleared while still busy; repeated/missing native events;
trailing missing-SOF watchdog; source/native wrap; stalled final output; following
SOF closure; a 200-cycle delayed orphan before closure; orphans before/after DONE
and ACK; once-only invalid/closure counters; and simultaneous tail transfer,
following SOF and premature ACK. HWH guards reject legacy one-bit GPIO, nonzero
reset controls, missing/duplicate metadata resources and disabled S2MM frame count.

Final generated RTL SHA256:
`a32ba8e8362835911511cb34c39827561cdca170b63d3541950b26e50ac3f441`.
Capture Python source SHA256:
`aac6d5bffe3dc1634b8d4e1989f68ea65eb847f80ff6eb01ff30d87eea3f5941`.
Exact installed Migen/LiteX versions, Git revisions and Python-source hashes are
checked by generation and stored in `gateware/dependencies.json` and the RTL JSON.

The vendor reset test used a fresh directory
`artifacts/build-probe/credit-reset-final/`, with commands:

```sh
cd artifacts/build-probe/credit-reset-final
xvlog -sv -work xpm /home/eastwillow/Xilinx/2025.2/Vivado/data/ip/xpm/xpm_cdc/hdl/xpm_cdc.sv
xvlog -sv /home/eastwillow/Documents/litex-hdmi-capture/hardware/receiver_reset_sync.v /home/eastwillow/Documents/litex-hdmi-capture/artifacts/litex_capture_credit.v /home/eastwillow/Documents/litex-hdmi-capture/hardware/receiver_reset_sync_tb.sv /home/eastwillow/Xilinx/2025.2/Vivado/data/verilog/src/glbl.v
xelab --timescale 1ns/1ps -L xpm receiver_reset_sync_tb glbl -s receiver_reset_sim
xsim receiver_reset_sim -runall
```

Actual AMD XPM async-reset4FF plus XPM single2FF data observation, connected to
the real final generated gate, passed stopped-clock 40ns source-pulse retention,
synchronous observation, six-edge release and sticky gate fault. All assertions
remain enabled. `xsim.log`, `xelab.log` and `xvlog.log`
in that directory contain the final execution logs; the commands and source hashes are recorded above. The pulse width is a
digital fixture value, not an analog minimum-width qualification. Elaboration
retains `LIBRARY_PATH` environment and unconnected output testbench warnings;
neither was disabled or waived.

A prior incremental rerun in `artifacts/build-probe/credit-reset-sim/` failed
elaboration because generated RTL lacks an explicit timescale, then a stale
snapshot launch failed during initialization. That failed attempt is preserved
and is not passing evidence. Fresh compilation in the documented order with an
explicit default timescale resolves the test setup without changing or weakening
the source, assertions, warnings or timing checks.

## Remaining evidence and risks

New CAD must recognize both reset-observation synchronizers, retain ASYNC_REG
attributes and pass CDC/timing without broad waivers. Global source counters are
sequential snapshots, while the selected tuple is stable only for its held credit.
PYNQ frontend FIFO overflow, VDMA status behavior, one-frame restart/reload, AXI
write completion and cache/buffer ownership are downstream paths covered by the
reader's independent tests and pending new hardware execution; this RTL suite
does not establish them. No hosted CI, hardware load, measurement or formal M1
claim was performed by this subtask.
