# Reduced output reset check: red and green

The original build-003 failure was reproduced in six seconds with only the
output clock module, pattern and pinned RGB-to-TMDS serializer. The red log is
`artifacts/operator/tx-reset-baseline-001.console.log`; it contains the same
`BD 41-1343` warning as the combined build. No RX or HLS was needed.

The generated module interface data and isolated probes showed three causes:

- The clock module's output name `serializer_reset` caused Vivado to infer
  `ASSOCIATED_RESET` on `serial_clk`, in addition to the explicit asynchronous
  declaration. Renaming it to `tx_reset` removed that inference, exposing two
  remaining sink-side reset warnings.
- The pattern port name `arst` also caused an inferred synchronous reset
  association. Renaming it to `async_reset` removed only its warning.
- The pinned serializer's `SerialClk` package metadata listed its asynchronous
  reset pins as synchronous. Correcting only that association in the staged
  IP copy removed only the serializer warning. Its RTL remains byte-identical.

Changing the serializer package alone did not fix the initial failure. Each
sink-only probe on the renamed source left the other sink's warning. Combining
the three corrections produced zero critical warnings; the green probe is
`artifacts/operator/tx-reset-combined-probe5-run-001.console.log`.

The reusable `hardware/check_hdmi_output_bd.tcl` was then run independently by
the parent on fresh inputs from actual `build_capture.py --stage prepare`.
It exited successfully with `HDMI_OUTPUT_BD_CRITICAL_COUNT 0` and
`HDMI_OUTPUT_BD_PASS`. The log is
`artifacts/operator/hdmi-output-bd-root-004.console.log`. The copied serializer
component hash is
`5c9570474d198badded1ee06ba97e14057d7327081e2deae66b372a77343de8c`;
the copy helper fails if the pinned metadata anchor differs. The full-frame
and reset simulation passed after the port renames; 46 profile/build/HWH tests
passed on the final integrated source.

No warning was suppressed, no reset bridge was removed, and no board design
was loaded. This check establishes only the reduced block-design integration.
Combined RX/TX synthesis, routing, clock timing, CDC/DRC and physical HDMI
operation still require a fresh full build and board tests.
