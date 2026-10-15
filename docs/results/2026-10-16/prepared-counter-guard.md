# Allow unselected input before prepared attach

The source-ready trigger waits for completed KMS presentations before attaching
the prepared receiver. Those input frames advance the global observer even
while capture is disabled. The original empty-endpoint guard incorrectly
required its completed_frames counter to remain zero, rejecting valid warmed
input before video-driver writes. This defect was found before run014 started;
it is not a new hardware failure or the cause of the earlier loss012 SIGBUS.

The guard now permits global observer completions while requiring zero selected
frames and zero selected-credit completions. DMA stopped/reset-clear/error-free,
command zero, credit state, command/source faults and FIFO checks remain.
The wiring in hardware/capture.tcl:69-70 distinguishes global completed_frames
from selected_completed. gateware/capture.py increments global completions for
unselected frames too; sources.py snapshots that global GPIO at offset8.

Attach path: sender.main -> Sender.run -> Sender.start -> LiteXCreditSource.start
-> load_overlay -> attach_prepared -> _attach_metadata -> _hardware. Preparation
also reaches this check through sender.prepare_main -> prepare -> _prepare.
Receipt/boot/artifact/state checks still precede MMIO, and failed attach still
discards unowned metadata before caller cleanup. Allowing a warmed observer now
admits native video-driver initialization; this change does not make startup
clock loss safe. Runtime VTC-read avoidance is a separate earlier fix.

The regression calls real LiteXCreditSource.load_overlay with valid mocked
receipt/MMIO state and completed37/observed38/dropped38/native39 while selected
and selected-credit completion remain zero. Root reran this test against an
isolated copy of pre-fix e180171 source: one expected failure, empty-credit
SourceError before video initialization. Current source passes. A companion
case keeps selected-credit completion1 and confirms rejection before video or
register writes. Focused suite:96 passed. Full host command
PYTHONPATH=src:. python -m pytest -q:466 passed,1 optional skip in3.64seconds.
No board operation occurred during these tests. No RTL or source comments changed.

Tier2 graph generation2026-10-15T19:36:40Z reported no recorded coverage gap for
prepared.py, sources.py, sender.py, test_prepared.py, gateware/capture.py and
capture.tcl; direct source/wiring checks support the counter distinction.
Graph relationships do not resolve every dynamic MMIO or remote process edge.

Immutable v13 contains the incorrect guard and remains preserved. Run014 must
use a new v14 archive with this correction. Fresh-replay bitstream qualification,
actual prepared startup, physical loss/restart, held-credit observations and
final600second criterion remain pending. Full M1 is not qualified.
