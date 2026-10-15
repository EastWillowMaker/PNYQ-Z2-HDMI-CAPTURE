# Rejected build015 timing and watchdog optimization

The fresh-HLS free-run build completed routing/bit generation but failed the
required export gate: WNS -0.071ns, one setup endpoint; WHS0.019ns and pulse
width0.264ns were positive. The critical path runs from the native VSYNC counter
bit0 to the credit gate DONE register, with11 logic levels and7.051ns delay on a
7ns clock. Full reports/failed console remain in `artifacts/m1-project-015`.
No accepted manifest was exported and this candidate was not board-loaded.
No timing waiver, false path, clock relaxation or warning suppression was added.

The watchdog previously calculated a32-bit modular subtraction, then compared
its result with0/1. It now latches the next expected native count at each SOF and
uses direct equality checks. For all32-bit inputs, `(current-previous) mod2**32`
belongs to{0,1} exactly when current equals previous or its wrapped successor;
at SOF the required value remains the successor alone. Baseline/reset/command
and frame-closure behavior is unchanged by this algebraic replacement. Existing
normal, skipped/repeated/backward, wrap, reset, orphan and stalled closure tests
exercise the affected paths. All64 dedicated gate/manifest cases pass locally,
including the compiled full-VGA pixel check. Actual timing and physical behavior
of the replacement remain unverified until the new candidate finishes.

Build016 is isolated under `artifacts/m1-project-016`, with frozen scripts/HDL
under `artifacts/m1-project-016-source`. It reuses only the newly successful HLS
outputs from015; the failed top implementation is not reused. Generated RTL SHA
`e4515603bf95855dc1aa82ecce4104bf22dfd05f9cce8d6d8d421887675dfbec`.
Live shell handle97016; console `artifacts/m1-project-016-console.log`.

The credit GPIO snapshot label was also corrected to identify reads during
health checking rather than claiming every snapshot occurs after completion.
The per-sample timestamp still reports its actual auto-halt/cache-invalidate
sampling point. This label correction does not change accepted input or DMA
ownership behavior. The latest135 source/qualifier tests pass locally.
V9 source archive SHA256
`12a7fce8bb79aa796b433b7afafdcf65e00a79fd9c082d1ea6e99381e7c3e06a`.
It has not yet been board-deployed; v7/v8 archives are retained historical inputs.
