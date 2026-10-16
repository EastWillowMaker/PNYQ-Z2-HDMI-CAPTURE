# Failed cold handoff016 and steady-source restart017

Attempt016 did not start its strict600second client. Fresh KMS source03 was
valid XR24/VGA25200 with completed page flips, but the receiver's prepared
attach guard rejected a latched frontend underflow episode before video-driver
initialization. Source selected/completed-credit counters were0, command and
sequence faults0. Root fixed-clock inspection proved CR0x10002/SR0x10001,
capture disabled and SD persistence/ext4errors0. This is a failed startup,
not a corrupt delivered frame or a passed ten-minute result. The root supervisor
recorded childexit1 and absent final sender status; its conservative false
shutdown flag is not an independent observation that DMA was running.

The host observer also had a polling defect: it searched the whole UART text
for SUPERVISOR_PENDING, which occurs in the echoed command even when a result
exists. Root stopped only that exact normal-user, read-only observer after
checking its command and absence of a child. No board/native/KMS process was
signalled. Its pipeline and original root failure evidence are retained. New
collection parses only actual line-prefixed records; static embedded Python and
single-line checksum commands were compiled/exercised before use.

KMS source03 stayed running. In the separate fresh attempt017, production
prepare used the same current receipt without --after-reset or an HPD pulse,
then the unchanged production sender attached to the new preparation. This
established fresh fault counters after source stabilization; it did not waive
an existing fault or change the failed016 result. There was no retry loop.
The supported source clock remained present for native initialization.

017 received21 distinct exact full RGB888 frames in10.340019seconds at
2.030944FPS. All pixels/accounting passed; senderexit0, error counters0,
safe cooperative DMA close and independent fixed-clock raw halt passed.
SD persistence/ext4 health and before/after external-abort comparison passed.
This is a short explicit preparation/restart result, not600second evidence or
a physical unplug/mode-transition test. Endpoint arrays remain private.

Both attempts used the exact v14/3343dac runtime and fresh017 replay bit/HWH
pair already identified in014/015 evidence. The production capture code was
not changed. 017 ran within the same ongoing source03 session as failed016;
optical source IDs and per-attempt capture session IDs remain distinct.
All21 optical IDs matched the separate source03 presentation log. Source03
completed its720seconds with childexit0 and original VT restored; the old
bounded source worker then exited normally. Saved -source-* files accompany016.

New018 is prepared to advertise the receiver first, wait for fresh KMS
presentations, then perform normal production preparation and attach. The root
waiter owns its bounded wait and postchecks so board sudo expiry does not lose
cleanup evidence. A separate fixed PC worker needs local PC authentication
after source03 completes and its prior worker exits; no concurrent DRM source
is allowed. This is planned execution, not a qualified long run.

Evidence: m1-017-normal-016-{result,observer,startup-diagnostic}.json and saved
sender/trigger logs; m1-017-warm-017.json/.jsonl, -result.json and root before,
after, child, resource and sender files. Startup native-clock risk, physical
loss/restart, controlled input-mode changes and independent optical/native-ID
mapping remain open. Full M1 remains false.
