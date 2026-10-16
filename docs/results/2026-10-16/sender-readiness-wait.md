The documented receiver sequence prepares again after KMS becomes steady.
The previous trigger observed preparation and native startup for only30s.
Physical run020 used a separate45s observer and still timed out before an
otherwise healthy sender listened. No client started. Its original failed
result and [physical-loss analysis](m1-017-hdmi-loss-020.md) are preserved.

The tracked trigger now observes sender readiness for90s by default, with
`--sender-timeout` accepting only integer1..120. Its source readiness bound
is independent. UART and PC process observations allow10s and20s additional
time respectively. Fresh source evidence, marker/log guards, actual listening,
error rejection and one-call/no-retry behavior remain. Observation timeout
never kills a native sender. The waiting event records the selected bound.

A real shell regression substitutes an accelerated `sleep` command in PATH.
A listening event appears after250 polling intervals (50 logical seconds),
exercising the actual marker command and downstream client gate. It failed
before the change (1failed/36deselected) and passed with the new default
(1passed/36deselected). Missing listening stops after450 intervals; a chosen
30s bound still rejects the50s event after150 intervals. A late fatal test
also exposed an inherited GNU ERE alternation issue with an unescaped opening
brace. Escaping that literal makes fatal shutdown reject before listening;
that regression failed before its fix (59passed/1failed), then passed.

The focused suite passed60tests; the full host suite passed490tests with one
optional-dependency skip. Commands were `.venv/bin/python -m pytest -q
 tests/test_prepared_trigger.py` and `.venv/bin/python -m pytest -q`.
No new RTL, bitstream, source acquisition or DMA teardown behavior changed.
No new hardware qualification or clean-checkout replay is claimed here.

Impact order: CLI `main` -> `trigger` -> `marker_command`; the shell command
is handed to `board_console.py` once, after `wait_source_ready` succeeds.
That UART command creates only the marker and observes the sender log. The
separate waiting board process owns preparation/native startup and cleanup.
The callback and serial shell are indirect process boundaries; graph edges
alone do not verify their runtime behavior. This patch reviewed the actual
command, API/CLI propagation, errors and local shell regressions. Hardware
startup duration is established only by the saved020 trace, not unit tests.
