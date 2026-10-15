# Credit-source failure reporting

Before this fix, mode/credit identity rejection occurred before the global GPIO
snapshot. A known new invalid geometry event could leave source_invalid_frames
null or a stale zero. Final-accounting cleanup then replaced the original fault
record. Three execution regressions reproduced this for a failed credit,
unsupported mode and unavailable GPIO reads before the patch.

The reader now records the real snapshot before mode/identity checks and clears
its previous snapshot before attempting a new read. Failed reads remain unknown;
they do not inherit old clean zeros. The sender reports the known invalid GPIO
delta from the disabled baseline, and marks physical overruns unknown on failed
sessions. Cleanup errors have a separate counter and the final counter update
uses the latest diagnostic snapshot. Original failure details survive cleanup.
The source invalid counter measures geometry/orphan episodes; it does not infer
an exact number of incomplete or lost source frames from a fault indication.

Supported source acceptance, DMA arm/completion/copy/release and the halt-before-
free path are unchanged. Unsupported modes still reject before DMA writes. The
newly earlier GPIO reads use the already verified system-clock register map;
read errors reject the capture and preserve unknown diagnostics. Cleanup MMIO
failures still retain buffers under the existing CLI safety hold; actual hardware
fault injection is unverified. Successful frame metadata has source_errors0 and
source_cleanup_errors0, now required by the formal qualifier. Explicit legacy
image reproduction keeps its previous acceptance. The generic unsupported-mode
error text now names Capture instead of incorrectly naming only M0.

Tests cover failed credit/unsupported mode with observed invalid count, missing
GPIO diagnostics, original fault retained after safe release, and updated final
counts after cleanup failure. Each checks supported/unsupported/error execution
rather than only parser acceptance. Local suite:308 passed,1optional skip in2.72s;
CPython3.10 compilation passed. See `credit-fault-reporting-tests.txt`.
No new physical capture or hosted CI result is claimed.

The new source archive is sender-m1-v10.tar.gz, SHA256
8c716223f7928571a3704eb049e3827045c85168081f99b186b1009b24c298ae.
It supersedes v9 for the next run; archive transfer SHA256 matched on the board,
and it has not yet been executed against hardware. The FPGA
pair remains build016; software diagnostics do not change the hardware image.
The operator's PC wake/unlock action remains pending; no capture process is active.
