# Start capture after the KMS source is ready

The tracked prepare/receipt interface still required starting a board command
while direct KMS hid the PC desktop. The sender now accepts --wait-ready-file
only with the credit source and prepared receipt. It checks a fresh regular
marker with finite0<timeout<=900 before constructing a source. Stale files,
directories and symlinks reject; timeout does not load video drivers, allocate
or start DMA. Marker arrival proceeds through the existing receipt/boot/state
and empty-hardware checks rather than trusting the marker as identity evidence.
The caller does not gain overlay preparation or reset from this option.

Entry chain: sender.__main__ -> main -> wait_ready_file -> filesystem lstat/
bounded sleep. It returns before source construction -> Sender.run -> start ->
LiteXCreditSource.start -> prepared attach. Errors before source construction
have no owned DMA allocation to clean up. Interrupting that wait likewise owns
no receiver hardware. The receipt check is deliberately after the wait.

Host entry chain: trigger_prepared_capture.__main__ -> main -> trigger ->
wait_source_ready -> _source_ready. It requires an absent source-output directory
at entry, the exact XR24/VGA25200 ready event, two increasing recent completed
presentations, valid same-host monotonic times and no restore/child result.
Own-wrapper metadata is trusted; this is not process or framebuffer attestation.
Malformed or unexpected records fail. The source wrapper's bounded fixture
limits these local logs; no arbitrary external metadata protocol is supported.

After that, trigger -> subprocess.run(argv) -> board_console.py -> serial shell
command is an explicit cross-process edge checked in source. The graph does not
resolve that command string. Its one normal-user subshell checks a fresh waiting
sender log, creates the marker, then polls at most30seconds for the actual new
listening JSON. Startup errors, stale status and UART failure reject without
retry. The host client runs only after trigger success with shell &&. There are
no transient TCP clients or failed qualification attempts to rebaseline.

Board marker and sender-log paths must be absolute without ASCII control bytes;
shlex quoting preserves printable metacharacters. The subshell preserves the
interactive shell for board_console's completion marker. UART40s and host50s
timeouts do not kill the native sender; its own timer/cleanup/unsafe retention
policy remains. The hardcoded serial by-id/account in board_console is unchanged
and documented as this machine's scope. Another board needs its normal access
path; this is not a generic serial/backend framework.

Read order: sender argument gates/wait, prepared.wait_ready_file, host trigger
metadata checks, marker_command, board_console shell execution, then existing
prepared attach and capture cleanup. Graph generation2026-10-15T19:15:25Z
reported no recorded gap for all six relied-on files. A first file-pattern query
returned no matches, then an exact-name query found all three relevant helpers;
no negative architecture conclusion was drawn. Nested record and subprocess
callbacks were verified directly because graph resolution is not complete.
No board_console/fixture/RTL files changed. Comments preserve existing wording
except the necessary new wait contract; no unrelated rewrites were made.

Focused tests passed131; final `.venv/bin/python -m pytest -q` passed465 with
1optional Migen/LiteX skip in4.03seconds. Coverage includes pre-construction
wait failures, fake-clock readiness, wrong geometry/timing/stale/error source
records, no UART on rejection, one failed UART attempt without retry, real
local sh execution with quoted metacharacter paths, board-log errors/stale
listening and client && only on success. Five documented shell blocks passed
bash -n. These tests do not qualify actual source-to-UART-to-board startup.

The guide uses the existing PYNQ virtual environment, first queues the normal
board root waiter, exits miniterm, queues the PC trigger/client, waits for its
fresh-output acknowledgment, then starts bounded KMS with PC sudo. It saves
private first/last NPY arrays and metadata. Quickstart now points to this tracked
flow instead of prescribing the earlier GNOME GLES reference. Actual first-frame,
loss/mode/lease checks and final600-second qualification remain NOT_RUN.

The earlier013 coordinator independently expired waiting for operator/source
readiness, with no source session or board launch. Its original coordinator JSON
and separate NOT_RUN envelope are retained; it is not a new HDMI loss failure.
The old auth window is still a local prompt, but its helper rejects the expired
coordinator before privileged board preparation. Await user presence before a
fresh test; do not contend with miniterm or blindly restart expired evidence.
