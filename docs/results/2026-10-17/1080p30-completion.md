# Accepted 1080p30 scope complete

The PYNQ-Z2 physical HDMI OUT(J9)→HDMI IN(J10) loop delivered1,200distinct,
exact1920×1080 RGB888 images over600.076875seconds:1.999744FPS and99.520049Mbps
RGB payload. Pixel, mixed-frame, repeated optical ID, metadata and transport
errors were0. Longest delivery gap was0.605705seconds. The uninstrumented
production sender ended normally, exit0, with safe DMA shutdown and zero
source/cleanup/network errors. Storage and kernel postchecks passed.

This closes the separately accepted next scope in requirements.md. The
[aggregate record](1080p30-completion.json) evaluates that scope; it does not
rewrite original run flags or extend the earlier VGA M1 claim to arbitrary
input modes. Use [the loop guide](../../output-loop.md) to reproduce the build,
clock-readiness ordering, GUI/CLI and qualification commands.

| Requirement | Verified result |
| --- | --- |
| N1: Real1080p progressive RGB888, average>=1FPS | Controlled1080p30 loop;1,200exact images at1.999744FPS |
| N2: Board passwordless sudo | Fresh `sudo -k -n id -u` returned0; root:root0440 rule and `visudo` check passed |
| N3: Changing physical output loop | User confirmed cabling; every image matched the analytic changing PL pattern |
| N4: At least600seconds/600new exact frames |600.076875seconds/1,200distinct exact frames; longest gap recorded |
| N5: Viewer/BMP and measured performance | Actual Save button/BMP byte equality, held-buffer proof and component comparison passed |

The login password and PC sudo policy were not changed. The latest board
[sudo verification](1080p30-final-sudo-verify.log) confirms the installed
`xilinx ALL=(ALL:ALL) NOPASSWD: ALL` rule without credential caching.

The acquisition runtime was `cfd30d3`; later changes before the run were docs
only. The fresh build used immutable source `7935b71` and pinned PYNQ3.0.1 with
Vivado/Vitis2025.2. Its [manifest and CAD result](1080p30-build-005.md) bind the
1920×1080 geometry,74.25MHz expected pixel clock,142.857132MHz capture AXI
clock, receiver range2, credit ABI and optional output fixture. Routed setup
and hold slack were0.539/0.013ns; all56bus-skew paths MET, with no critical
run/CDC/DRC findings or unconstrained internal endpoints. Remaining warnings
and external I/O limits are retained in that report.

The source is a controlled progressive30Hz fixture. Fixed-clock GPIO checks
before native configuration observed approximately30VSYNC/s with clean
geometry/FIFO counters. Across599.499870board seconds between first/last
delivered acquisitions, frozen native IDs advanced17,985, approximately
30.000007Hz. This uses one board clock and counter domain. It is not a direct
pixel-clock measurement or a one-way latency measurement.

The [client summary](1080p30-sustained-001-summary.json) and
[independent saved-log audit](1080p30-sustained-001-frame-audit.json) agree on
all1,200images, all1080marker rows per image and all6,220,800RGB bytes per image.
Optical IDs1593→19578 were distinct and increasing; transport IDs2→1201 were
continuous in one session. The receive window accounts for16,786intentional
source skips, with0acquired frames missing from that window. Native startup
skips remain unknown. The raw per-frame log stays local at
`artifacts/operator/1080p-sustained-001-frames.jsonl`; its SHA256 is recorded in
the audit. First/last NPY images and metadata remain local in the adjacent
`1080p-sustained-001-captures/` directory.

The [board record](1080p30-sustained-001-board.json) reports1,300acquisitions
over its full650-second run,1,200transport enqueues,98ready-slot backpressure
drops and1connection-time discard. Those whole-run counts include time outside
the client observation; they are not host receipt acknowledgements. One final
in-flight selected credit completed during cancellation and appears as1,301
selected completions, without being published as another acquired/delivered
image. The final100ms proof observed three new VSYNC edges before disabling
capture and halting DMA. No source/FIFO/geometry fault appeared.

Read-only [resource samples](1080p30-sustained-001-resources.jsonl) covered the
remaining run after the first61.37seconds of the delivered window. Across107
sample intervals wholly inside its acquisition window, the time-weighted mean
was71.89% of one CPU core, range67.98–76.29%. RSS stayed89,571,328–101,191,680
bytes, with298,228–311,064KiB memory available. The
[resource summary](1080p30-sustained-001-resource-summary.json) retains exact
times and the startup coverage gap. This establishes bounds for the sampled
run, not absence of every possible leak or an observed startup memory peak.
The sampler observed process disappearance and ended without termination.

The final [GPIO-only state check](1080p30-sustained-001-final-state.json)
revalidated receipt, boot and artifacts before reading hardware. DMA was
RS0/Halted1, reset/error clear, control86032/status69633, command2/capture
disabled, with no task capture process. Ext4 errors stayed0; the existing16MiB
storage file retained SHA256
`341aacac661ccb210720bedaa9ead5d668fe5ea41a73532fc147c71e34040df1`.
Boot ID stayed `1dd70e40-85cc-4c9b-a2e2-03b9814e290f`.

The [kernel comparison](1080p30-sustained-001-kernel-check.json) found59matching
suffix/prefix lines between [before](1080p30-before-hardware-dmesg.log) and
[after](1080p30-sustained-001-after-dmesg.log), then146new lines. There was no
unobserved ring gap across that boundary and no new external abort, SIGBUS,
kernel panic or ext4 error. The PYNQ UIO destructor still emitted its known
ignored event-loop warning after the sender's safe final status; exit0 and
zero cleanup counters do not mean the log contains no diagnostic.

The [held-buffer proof and component measurements](1080p30-loop-performance.md)
passed separately. The copy improvement reduced actual native-buffer copy
median259.523→95.583ms and increased a20-second delivered-image comparison
1.842234→2.480469FPS,34.64%. The original old-copy board run's50ms final-proof
failure is preserved, alongside its passed client window. The
[diagnosis and regression](1080p30-loop-bringup-001.md) explain the30Hz fix;
it keeps the two-edge, health/watchdog and halt-before-free guards. Separate
DMA timing median was42.207ms and cached raw TCP capacity629.465Mbps. The
network has headroom; copying, encoding and shared event-loop/kernel work
limit this measured pipeline. These results promise no unmeasured higher FPS.

The [real GUI save](1080p30-gui-hdmi-001.md) decoded an uncompressed24-bit BMP
back to RGB888 and compared every byte with the exact click-time frame and
independent pattern. Preview scaling did not affect the saved1920×1080 image.
Its viewer and bounded production sender closed normally. The direct CLI is
retained, as are the independent PC fixture and prior qualified VGA evidence.

Validation includes592host tests passed and1optional Migen/LiteX module skip
after the final host behavior change. The unchanged capture gate had45tests
passed in its pinned generator environment; output-pattern simulation checked
two complete1080p frames and reset. The final build/mode/HWH set passed47tests
before build005. The new documentation's Python readiness example was parsed;
it follows the GPIO-only sequence actually exercised on board. No hosted CI,
fresh PC-source1080p test or fresh VGA hardware rerun at cfd30d3 is claimed.

The accepted scope is the fixed controlled1080p30 loop. Arbitrary input modes,
format/range negotiation, missing-clock native startup, physical interruption
at1080p and automatic recovery remain unqualified. Runtime source-format/range
metadata and absolute optical-to-native mapping remain unknown. The generic
qualifier's original `full_m1_qualification=false` is retained because it also
lists separate startup/fault/mode requirements; the next-scope record above
evaluates the agreed N1–N5 boundary without changing those flags.

No sender, viewer, sampler or task HTTP server remains. The005PL output fixture
continues in hardware while the capture gate and DMA are idle. Current board
artifacts/receipt are under `/tmp/hdmi-capture-1080p30-002`; verified runtime is
under `/tmp/hdmi-capture-1080p30-003/src`. Recheck these ephemeral paths after a
reboot and use normal preparation before another sender session. Changes are
local commits only; no push, PR or capture-image upload was made. The unrelated
untracked `docs/results/2026-10-15/m1-recovery-scanout.log` remains untouched.
