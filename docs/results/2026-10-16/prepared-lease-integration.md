# Guarded preparation and held-credit observation

Normal011 met the new-SD delivered-image criterion through build017/v11, but
its startup depended on ignored helpers with fixed paths and boot assumptions.
The new tracked interface separates receiver preparation from capture startup.
It remains host-tested only; source/capture startup and the final600-second
criterion through these commands still need board evidence. Physical013 runs
an immutable deployedv12 package from6cfe75c and does not use this new interface.

sender.main -> prepare_main -> prepared.prepare is the preparation entry.
Without --after-reset it requires a prior receipt, raw PYNQ state identity,
paired artifact hashes, current boot and stopped/reset-clear/error-free DMA
with capture disabled before reprogramming. Nonzero transaction toggles may
remain only in this disabled re-preparation case. --after-reset is an explicit
caller assertion of board/PL reset and no active DMA; it performs no reset.
Unknown register maps are never probed using a new image's HWH. Saved SDK
shutdown IP maps are rejected because PYNQ would otherwise access them before
programming. Download uses the existing artifact verifier and GPIO-only loader;
post-checks require reset-empty credit/selected/completed state and clean FIFO
monitors. HPD must be the one-bit fixed-output dual GPIO. The receipt is
published atomically only after successful download, HPD and post-checks.

Capture follows sender.main -> Sender.run -> Sender.start ->
LiteXCreditSource.start -> load_overlay -> attach_prepared -> _attach_metadata.
Receipt/boot/artifact and raw saved-state checks precede the Overlay constructor;
state is rechecked across metadata and hardware inspection. Empty endpoint,
RS0/Halted1/reset-clear/error-free DMA precede _initialize_video. The existing
configure/mode/startup baseline checks still precede allocation. Runtime credit
read -> _wait -> idle/armed/complete -> _healthy retains the6cfe75c fixed-clock
health checks. Sample.close -> _release_credit -> _healthy -> ACK still owns
release; sender close -> source.close -> disable -> raw halt -> frontend stop
-> free retains the buffer-lifetime contract. Prepared load_overlay(False)
stays GPIO-only, even when a receipt was supplied. Legacy load behavior remains
the default when no receipt is specified; tests cover the affected common loader.

PYNQ software state is an operational ledger under exclusive configuration
ownership, not independent hardware readback. Important pinned SDK facts:
Overlay.__init__ changes device.bitfile_name before is_loaded can compare it
(overlay.py:319,464; pl_server/device.py:116). GlobalState.__init__ recalculates
saved hashes from current bytes (pl_server/global_state.py:40,87). gen_cache can
save state without download (embedded_device.py:635). New checks read raw JSON
instead of that object loader. Unrecorded JTAG/FPGA-manager programming invalidates
the receipt's contract; no hardware build-ID proof is claimed.

The generated fixed-output AXI GPIO returns all ones for TRI readback, so
checking TRI==0 would reject correct hardware. The source is
artifacts/m1-project-011/vivado/capture.gen/sources_1/bd/capture/ipshared/0271/hdl/axi_gpio_v2_0_vh_rfs.vhd:675,
with reg2 assigned ones at695. The new code verifies its three HWH parameters
and only writes/reads HPD data. No fixed-output direction transaction remains.

Root review also found a cleanup integration gap: after a guard rejected an
existing active DMA or enabled gate, newly retained metadata allowed a caller's
finally-close to disable that unowned gate. The actual Sender.start calls
source.start before its server-error try, so it is not itself that cleanup edge;
Sender.close in caller finally and the new checker run_session are concrete
callers. Two no-write regressions failed before metadata invalidation and passed
after. Owned/active source reuse rejects before references are changed. A second regression rebuilt the same-path HWH for a new image, failed a
post-download check, then observed cleanup write an old address. Failure now
discards all unowned metadata instead of restoring earlier maps; both red cases
passed after the fix. Active ownership rejects before references change. Successful guards followed by video
initialization failure still retain access for legitimate cleanup.

The new tools/check_credit_lease.py performs a bounded board observation through
run_session -> source.start -> check_lease -> source.read. It hashes the complete
halted native buffer and RGB copy while retaining sampleA, reads held identity
and raw parked-VDMA registers repeatedly, requires continuing native edge
progress, then ACKs and reads a newer exact sampleB. A guarded second read
checks lease rejection without permitting an unintended DMA arm. It saves only
metadata, raw registers, hashes and analytic verification, never image payload.
Failures do not ACK suspect data. run_session always attempts cooperative close;
main retains source/native references in _hold_unsafe_dma if halt safety remains
unknown, including startup/hash/output failures. Frozen edges without fault
flags fail its validator. The18 local tests exercise these paths with a fake
source; actual cache coherency, DDR association and clock-loss halt are NOT_RUN.

Review order was configuration identity/ownership, hardware guard boundaries,
SDK side effects, native construction, acquisition/lease and error cleanup.
Graph coverage generation2026-10-15T18:55:23Z reported no recorded gap for the
three runtime modules, two new test modules and checker. Dynamic PYNQ driver
and callback edges were checked in source; this is not a complete graph claim.
Overlay._register_drivers imports pynq.lib before _complete_description, so
deferring explicit video imports does not omit SDK driver registration
(overlay.py:316,531; pynq/lib/__init__.py imports video). Drivers instantiate
lazily through _IPMap.__getattr__; the GPIO-only path does not access VideoIn.
Vendor/generated/operator sources are excluded from the graph and were read
directly. No new bitstream/CAD run, hosted CI, hardware prepare or lease check
was executed for these changes. The exact017 timing/CDC limitations still apply.

Initial combined full suite:412passed/1optional Migen-LiteX module skipped,
3.44seconds. The separate45 gateware simulations passed for the preceding
runtime-only change; no RTL changed here. New cleanup changes justify one final
host rerun after integration, whose log and result will be appended. User auth
for013 remains pending; its coordinator and wizard are live, with no new DMA.

Final integration after both cleanup fixes: `.venv/bin/python -m pytest -q`
passed413 with1optional Migen/LiteX skip in3.62seconds. New prepared suite has
79cases; held-credit checker has18cases. CLI help and Python compilation pass
without PYNQ. No new HDL changed, so the earlier45 gateware simulation result
is cited without another identical run. Actual prepare/attach/lease hardware
checks and normal qualification through this final runtime remain NOT_RUN.
Comments were reviewed in the combined patch: only the required loader split
and clock/safety constraints changed; no unrelated comment rewrite was made.
