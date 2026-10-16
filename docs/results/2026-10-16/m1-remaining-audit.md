Current resolution, after the historical audits below: the accepted fixed-mode
M1 gates are closed in[m1-completion.md](m1-completion.md) and the
[final bounded audit](m1-final-evidence-audit.md). Normal019, held-buffer015,
clean-source023, confirmed physical024 and explicit restart025 provide separate
proofs; mode021 retains its actual fail-stop evidence and original failed
observer flags. The dated tables below describe what remained at their own
checkpoints and are not the current task list.

# M1 completion audit

Current-state addendum — 2026-10-16, HEAD `a4613f0`.
The historical audit below describes the pre-v12 state and is preserved.
Its software-promotion and clean-build gaps have since advanced; its hardware
requirements remain open. Full M1 is still unqualified.

Tracked receiver preparation, preparation receipts, guarded attach, the
source-ready wait/trigger and the bounded credit-lease checker now exist.
Quickstart uses the tracked direct-KMS workflow. The latest saved host result
is **466 passed, one optional skip**, including the `3343dac` regression that
allows global unselected-frame completions while still rejecting nonempty
selected-credit state. This is software evidence, not successful board startup.
See [prepared/lease integration](prepared-lease-integration.md),
[trigger integration](prepared-trigger-integration.md) and
[the counter correction](prepared-counter-guard.md).

The [fresh017 replay](credit-017-clean-replay.md) closes the clean-source
HLS/CAD recipe gap: archived `3fdf273`, fresh vendor clone, both fresh HLS
exports, generated-RTL drain checks, full implementation and routed review
passed. Setup/hold slack is 0.401/0.014 ns, all 56 skew constraints met, with zero
critical CDC/DRC findings. It reused a verified isolated Python environment;
retained VTC CDC warning and external timing gaps remain. The newly produced
bit/HWH pair has different hashes from the pair physically tested in run011 and
has **not** been board-qualified.

[Immutable v14](prepared-v14-package.json), source revision
`3343dac618ada6099453415b5554c4185a544801`, contains that new pair and the
corrected runtime. Archive SHA256 is
`306f8d3234721bfa174cd2e2df66c5f7ef17ab55de2b3802eb2f3c5bced0080f`.
HEAD `a4613f0` only adds staging records after that source revision.
[014 preparation](prepared-014-auth-ready.md) and
[its preflight](prepared-014-preflight.json) say authentication and actual
privileged preparation/capture remain pending. They do not establish a current
live process or credential state. Run013 expired before source/preparation/DMA;
its NOT_RUN result is not a failed HDMI experiment. V13's incorrect guard was
found before execution; that archive remains historical and must not be used.

| Remaining gate, in execution order | Required evidence |
| --- | --- |
| **1. Current tracked first-frame path and new pair** | After local authentication, recheck actual known-idle state, then run014's tracked prepare/receipt/readiness/attach route with v14 and stable KMS. Require the planned 20-second exact-frame smoke, actual listening/startup, error-free raw DMA halt, storage/kernel checks and source/VT restoration. Retain exact package/pair hashes. This closes the first physical integration gate; a session-specific ignored idle-bootstrap helper alone does not demonstrate the clean-checkout user procedure. Record a replay using the documented tracked commands from a clean checkout/staging tree. |
| **2. Physical loss, safe cleanup and restart** | On the fixed current runtime, repeat a correctly armed HDMI-cable-only interruption with Hub/Micro-B intact and board continuity recorded. Require explicit source failure, no SIGBUS/new external abort, bounded halt before free and truthful child exit. After supported input stabilizes, explicitly reprepare/restart and receive new exact frames/session with safe cleanup. Recovery by an external emergency helper cannot substitute for successful sender cleanup. |
| **3. Held-buffer/source association and client pressure** | Run the tracked credit-lease checker on the new pair: refreshed complete-buffer hashes and held IDs remain stable while native edges advance, raw parked DMA remains safely halted, ACK precedes a second newer exact optical pattern, and final cleanup is safe. Include current-path client pause/reconnect/whole-ready-frame-drop evidence; cite runs010/011 as prior evidence and repeat affected paths through the final prepared runtime. The checker is currently host-tested only. |
| **4. Input-mode transition and supported restart** | Exercise the current credit runtime through a controlled timing/relock change and a safely available unsupported-geometry case; record acceptance/rejection, complete-frame handling, fail-stop where applicable, cleanup and explicit supported-mode restart. Runtime geometry/FIFO/sequence checks do not independently measure same-dimension timing-only changes. Do not claim arbitrary forbidden HDMI formats are classified, or force unsafe clocks to manufacture coverage. Mark unavailable stimuli unverified. |
| **5. Final unchanged long criterion and completion report** | After earlier gates pass, use the final tracked runtime and exact new pair for ≥600 seconds, ≥600 distinct exact frames and ≥1 FPS, with zero received corruption/mixing/repeats/metadata/transport failures, retained startup and runtime health/accounting, KMS optical correlation, CPU/memory samples, safe cleanup, storage and VT-return evidence. Cite build/source hashes and all failed attempts; update current requirement/status summaries without erasing history. A short smoke and CAD success do not replace this run. |

Normal011 remains a valid v11/original017 pass: 1,201 exact distinct frames in
600.368226 seconds with safe cleanup and storage checks. Loss012 remains a
confirmed HDMI-only SIGBUS failure after 88 exact frames, followed by a separate
successful emergency halt. Neither has been reclassified by software tests or
the fresh build. The [011/012 report](capture-011-loss-012-report.md) preserves
both results and the startup native-clock risk, which the runtime fix does not
remove. Start only after stable supported input; automatic recovery is absent.

No accepted M1 requirement is shown technically impossible. Existing logs cannot
recover exact startup native skips or independently map an optical pattern ID
to an absolute native VSYNC counter value. The held-credit test can strengthen
buffer/identity association evidence but cannot supply that independent physical
mapping. Keep startup skips unknown, global snapshots non-atomic and
`physical_source_sequence_verified=false` unless new independent evidence
justifies changing it. Receipt checks likewise identify software-managed
configuration history, not a hardware build-ID register. Do not convert these
limits into fabricated zeros or require M2–M4 to close M1.

This addendum uses the linked saved reports, package/preflight records, current
prompt/requirements and quickstart. No new tests, board/UART/display operations
or source review were performed for this documentation update.

---

2026-10-16, after normal011 and failed loss012, before v12 physical retest.
Scope is the accepted PC Python / Ethernet / real HDMI RGB888 M1. Browser,
active bypass and LCD are later M2–M4 work and do not block this delivery.

Normal011 establishes the ten-minute delivered-image criterion for build017
and runtime v11: 1,201 distinct exact frames in 600.368226 seconds at
2.000439 FPS. All 1,201 frame records have zero metadata errors and exact
pixels; the independent KMS log matches every optical ID. Sender exit0,
halt-before-free, independent RS0/Halted1/gate-off readback and before/after
storage checks passed. This is substantial real-path evidence, but the actual
working startup still depends on ignored operator prototypes.

| Requirement / priority | Evidence and present limit | Bounded next action / completion evidence |
| --- | --- | --- |
| **1. Safe physical HDMI loss** — prompt §§5,8; C6/C7/C13 | Loss012 received 88 exact frames, then sender SIGBUS(-7) during native VTC mode access; sender cleanup is absent. The user confirmed HDMI-only removal for about five seconds, with Hub/Micro-B untouched. A separate fixed-clock emergency helper proved RS0/Halted1/gate off. That recovery is not successful sender fail-stop. | Deploy the hash-identified v12 runtime. Repeat one armed, correctly timed HDMI-only interruption; record board boot/UART continuity, source outcome, explicit sender error, bounded DMA halt before native free, and unchanged storage. Preserve the failed012 result. Verify the client/supervisor reports child failure rather than a successful outer-worker exit. |
| **2. Restore service after loss** — §§5,6,8 | Emergency halt passed; no successful post012 capture restart exists. Automatic recovery is absent and is not required if explicit restart is the documented policy. | With supported input stable again, use the production restart procedure and receive new exact optical frames under a new session. Prove no stale ready frame crosses sessions and cleanup succeeds. Do not reuse same-boot or credential assumptions without checking them. |
| **3. Mode change and unsupported geometry** — §§5,8; C7/C13 | Legacy013 timing-change fail-stop/restart exists, but does not validate the credit runtime. v12 removes runtime VTC dimension polling; fixed-clock geometry/FIFO/sequence checks remain. Same-dimension timing-only changes are not independently measured. | On017/v12, test a controlled supported timing transition/relock and a safely generated unsupported-geometry stimulus. Require rejected incomplete frames, explicit fail-stop, safe halt, then supported-mode restart with exact pixels. If the physical source cannot produce a forbidden mode, report that path unverified and retain local negative evidence; do not force an unsafe clock merely to fill a matrix. State the same-size timing detection limit. |
| **4. Clean-checkout first frame** — §§4,9; C10/C14 | Quickstart invokes the normal loader and GLES fixture. The reliable011 path first prepared HPD, started direct KMS, then used `artifacts/deploy/attached-credit-sender.py`; that and `prepare-after-replug-005.py` are ignored, absent from `git ls-files`, and tied to local staging/boot assumptions. A clean checkout cannot reproduce this workflow from the quickstart. | Promote a small supported prepare/attach interface into tracked code, with paired artifact identity, stopped DMA and disabled gate guards, explicit startup ordering and no hidden monkeypatch. Document deployment, local authentication, input readiness, sender, first snapshot verification and cooperative cleanup using tracked commands. Replay that procedure from an isolated checkout; record revisions/hashes and a first exact frame. A hardware build need not be repeated solely for a software-only fix if the existing exact artifact provenance is retained. |
| **5. Normal regression on delivered runtime** — P3, §§4,8 | 011 is v11, not v12. Local clock-loss regression evidence is red then green, with 93 initial focused passes and a final316 host passes/one optional skip; these are not physical tests. | After startup is promoted and fault paths pass, run the unchanged 600-second / 600-distinct-frame / ≥1 FPS criterion on the final production runtime, with complete native health/accounting, source log, resource samples, safe cleanup and storage evidence. A short smoke can precede it; it cannot replace it. |
| **6. Source identity and loss accounting** — P4, §5 | 011 metadata validates held single-credit IDs, parked DMA completion and received-window equation: 36,001 native intervals = 1,200 acquisition intervals + 34,801 intentional skips; zero acquired frames omitted inside that received window. KMS optical-ID correlation independently supports image identity/freshness. It does not independently map an optical ID to a native VSYNC counter value. Qualifier retains `physical_source_sequence_verified=false`. | Assemble a bounded association evidence record linking the exact017 RTL/HWH/manifest, one owned parked buffer, running→error-free auto-HALTED/IRQ, next-SOF-closed held identity, stable copy/lease and ACK-before-next-credit. Include one delayed/slow-consumer and interruption observation exercising that ownership boundary. Separate direct hardware readback from software assertions and metadata arithmetic; leave independent native-ID association unverified unless additional instrumentation proves it. Do not relabel KMS IDs as native VSYNC IDs. |
| **7. Honest accounting boundaries** — P4, §5 | Startup native skips remain unknown at the phase boundary by design. Startup invalid3 is retained under the disabled-zero-selected baseline; FIFO startup counts are0. Final011 selected1301 versus acquired1300 includes a cancelled final credit; global endpoint totals are not the received-window equation. Sender's whole-session 82 ready-slot replacements are outside the zero-gap received-window statement. | Retain these scopes in the final report. Distinguish selected/completed/acquired/delivered, intentional source sampling, ready-slot drops, invalid geometry and FIFO episodes. Explicitly disclose unknown startup native skips; do not invent a zero or treat it alone as a requirement to count every pre-session source frame. Explain the cancelled boundary credit and final source-proof interval using existing raw evidence. |
| **8. Current docs and build provenance** — §§8,9; C14 | Build017 CAD/HLS drain evidence exists; the documented isolated clean-build replay is for legacy013. Requirements, board-capture and source-accounting still contain historical headers such as hardware validation pending and old013 evidence in their current summaries. Source runtime v12 has no new HDL. | Update current status/reading order around017 and the final runtime while preserving dated history. State which build steps were freshly replayed and which exact017 artifacts were hardware-tested; retain timing/CDC/external-I/O limitations. Link final first-frame, normal, interruption/restart, mode, accounting and local-test evidence from one completion report. |

Recommended execution order is safe v12 smoke, physical loss/cleanup and restart,
production prepare/attach promotion with focused guard tests, mode transition and
restart, then the final unchanged long criterion through the tracked workflow.
If promotion changes startup behavior, repeat its short physical checks before
the long run. Existing current-path client reconnect010 and normal011 resource
measurements should be cited rather than discarded; repeat only affected paths.

The final report must keep independent facts separate: exact image delivery,
source-mode observations, held-ID/DDR association proof, accounting arithmetic,
safe process shutdown and storage health. A passed image criterion alone does
not close all six.

Evidence inspected: full supplied prompt; requirements, quickstart,
board-capture, qualification, source-accounting and progress; the
[011/012 report](capture-011-loss-012-report.md), 011 summary/evidence/board-session/
endpoint records and all 1,201 JSONL frame records; 012 client/board-session/
coordinator records, summarizing its 88 frames programmatically. The two ignored
deployment prototypes were read directly. No board UART, display or hardware
operation was performed, and no current production-code behavior was inferred
from an unverified graph edge. This is a bounded delivery/evidence audit, not a
new source-code or complete CAD review.
