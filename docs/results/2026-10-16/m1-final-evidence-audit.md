# Bounded final M1 evidence audit

2026-10-16; repository HEAD `c1487b0` when inspected. The accepted delivery is
PC Python receiving real HDMI IN RGB888 over Ethernet on PYNQ-Z2 with meaningful
LiteX capture, fixed 640×480 progressive near60Hz, at least1 fresh FPS for at
least600seconds and600 complete frames. Browser, active bypass and LCD remain
later milestones. This audit evaluates saved evidence, not new execution.

The saved evidence supports that fixed-mode delivery and its main safety and
reproduction obligations. At this checkpoint, the remaining execution gate is
the explicit supported-source restart after the confirmed physical loss024:
`m1-017-restart-025-controller.json` was absent when checked. Do not infer its
success from an active source or a preceding passing run. After that result,
the completion report must reconcile the evidence and current documentation;
the individual qualifier's conservative `full_m1_qualification=false` is not
itself a new product requirement for absolute optical/native-ID instrumentation.

| Accepted requirement | Concrete evidence and conclusion |
| --- | --- |
| Real LiteX HDMI→DDR→Ethernet→Python RGB888; sustained P1/P3 | [Normal019](m1-017-normal-019.md), its summary and root result:1,201 distinct exact frames in600.300346seconds,2.000665FPS; zero delivered corrupt/mixed/repeated frames, metadata/transport errors or in-window acquired-delivery gaps. All1,201 JSONL records independently re-parsed exact with no metadata errors. Native interval reconciliation is36,001 =1,200 acquisitions +34,801 intentional skips. Normal sender exit0 and zero source/cleanup/network errors; raw halt, storage, source exit and VT restoration passed. Its measured resource window is documented; samples are not peak/leak guarantees. |
| RGB array/API, saved first frame, reproducible public runtime | [Clean023](m1-017-clean-023.md) and [verification](m1-017-clean-023-verified.json): complete isolated git archive of`ad6c966`, public wait→normal prepare→production sender and clean trigger/qualifier;41 exact frames in20.309945seconds. Saved endpoints verified `(480,640,3)` uint8 with exact analytic RGB. New session and new source presentations exclude stale-session reuse in this observed restart. Existing pinned dependencies and the built pair were reused; fresh dependency installation is not claimed. |
| Actual LiteX build and board provenance | [Clean017 build replay](credit-017-clean-replay.md): fresh HLS exports, generated-RTL drain/stall checks, full CAD and routed review,606.745seconds/exit0, setup/hold0.401/0.014ns,56 skew checks met, zero critical CDC/DRC. Its exact bit/HWH/manifest hashes match the pair in019/015/023. This is clean-source build evidence plus separate hardware evidence, not a claim that CAD alone verifies capture. Retained timing/CDC warnings and external delay gaps remain. |
| Safe buffer lifetime, source accounting and whole-frame policy, P4 | [Lease015](m1-017-lease-015-report.md): six cache-refreshed raw/RGB hashes and held identities stable while native edges advanced325→444; parked error-free auto-HALTED DMA, one selected credit, ACK then a second newer exact pattern/credit, safe final close. Optical and native counters are separate domains.019 provides received-window accounting; its post-client97 ready-slot replacements remain separate from in-window source sampling. This satisfies a bounded ownership observation without inventing exact startup skips. |
| Client disconnect/reconnect and slow consumer | [Reconnect010](reconnect-010-report.md) preserves failed009 and the immediate smoke→strict reconnect pass:21 exact frames, no inserted retry/delay, safe close. The real local paused-source TCP regression also covers slot release. Sender diff`8996951..3343dac` changes only imports/CLI/preparation/readiness construction, leaving `_watch_disconnect`, `_serve_client`, `_capture` and lifecycle methods unchanged.010 is historical hardware evidence for that retained mechanism;015 and019 add current-runtime ownership/drop evidence. This does not claim every cancellation race or an independent Ethernet-cable pull was tested. |
| Physical source unplug and explicit fail-stop | [Verified024](m1-017-hdmi-loss-024-verified.json): user confirmed only HDMI IN unplug/reconnect about5seconds, Hub/Micro-B unchanged;101 exact frames, boundary EOF at source102.938seconds, no partial-frame error or delivered corruption. Sender exit1/source error1, no SIGBUS/new external abort, raw halt/storage/boot continuity passed, source exit0 and desktop restored. All13 referenced evidence hashes rechecked. Its original controller remains false pending human confirmation; the separate verified record supplies that confirmation without editing it. |
| Input-mode change and resynchronization | [Mode021](m1-017-mode-021.md) and [analysis](m1-017-mode-021-analysis.json):47 exact pretransition frames, advertised25200→25175kHz/640×480 nominal CRTC change; boundary EOF46.923ms into the1.578776second modeset, safe fail-stop/halt/free and no new abort. Original failed observer verdicts remain; EOF must not be described as after acknowledgment. Clean023 then demonstrates explicit supported-source restart under a new session. No automatic recovery claim is needed or made. |
| Protocol negatives, host tools and reproducibility checks | Existing source/protocol/API tests remain prior evidence; [readiness correction](sender-readiness-wait.md) records focused60/full490 passes with one optional skip, red/green real-shell regressions and no acquisition/teardown change. The corrected90second trigger was exercised by clean023. No tests were rerun for this audit, and local evidence is distinct from hosted CI. |

Physical-loss cleanup needs its exact classification.024 recorded
`source_cleanup_errors=1`: the saved traceback ends in the known final
source-proof rethrow after gate disable, raw halt, frontend stop, native free
and `dma_shutdown_safe=true`. The raw result independently confirms halt.
This is the predeclared trace-specific intentional-loss case, not zero errors
or a general cleanup waiver. Any unknown halt/free error would remain a blocker.
Normal019 and clean023 still require and report zero source/cleanup errors.

Earlier failures remain part of the delivery record:012's physical SIGBUS,
020's readiness-observer timeout/no client,021's premature acknowledgment
observer, and023's original root/controller false verdict.023's separate
verification establishes161 exact overlapping kernel lines and41 new lines
without an abort; historical abort count1→0 was ring rolloff, not evidence of
a new fault. The originals must not be rewritten as passes.

Remaining gates at this checkpoint are to inspect025's actual client,
sender/root cleanup, raw halt/storage/kernel continuity, new-session/source
identity and eventual source exit/VT restoration; then publish the aggregate
completion/status record with the exact source/build scopes above.025 must
demonstrate post024 recovery, not merely reuse clean023's earlier post021
restart. No additional ten-minute rerun is required solely by the unchanged
acquisition runtime or host observer correction.

Legitimate limitations must remain explicit in that record: unsupported-geometry
physical stimulus was unavailable because this fixture advertises only VGA;
local rejection tests are not that missing hardware experiment. Nominal CRTC
timing is not an independent wire-clock measurement. Source format/range fields
that are unknown remain unknown. Startup native skips and an independently
corroborated absolute optical-ID/native-edge mapping remain unmeasured;
`physical_source_sequence_verified=false` stays truthful. Receipt identity is a
software configuration ledger requiring exclusive ownership, not a hardware
build-ID readback. Native startup still needs input clock; arbitrary missing-clock
startup and forced process termination are not safe-operation guarantees.
The ignored PYNQ UIO destructor event-loop warning after verified safe cleanup
is unresolved and must be disclosed. These bounded limitations do not require
expanding the accepted fixed-source M1 into arbitrary HDMI support or M2–M4.

Read-only audit scope: saved reports/raw summaries/JSONL and024 traceback;
normal019 and clean023 frame records;024 evidence hashes; historical sender
diff. Sender graph coverage generation2026-10-16T14:14:09Z reported no recorded
gap and matching metadata, a best-effort signal only. No board, UART, display,
signals, tests, source changes or new hardware verification occurred here.

Parent addendum after the checkpoint: actual025controller/root results now
pass.21exactframes/10.109394s, new session/source IDs, zero normal source/cleanup/
network errors, raw halt/storage/kernel continuity and sourceexit0/VTrestoration
are verified. The root024→025chain passed and the idle PC worker ended normally.
No active board sender remained in the final read-only check. The execution
gate identified above is closed; see m1-completion.md for the aggregate scope.
