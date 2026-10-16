# HDMI source outside desktop composition

Use direct DRM/KMS to scan out XRGB8888 buffers on the PYNQ-connected output.
The C source writes the analytic RGB fixture into two buffers and waits for each
page-flip completion before reusing the previous buffer. A640x480 progressive
mode at59.9–60.1Hz is required; optical IDs advance roughly four times per second.
No OpenGL, Vulkan, window, desktop screenshot, or reference-image learning is
involved. The PC receiver still compares every RGB888 byte strictly.

## Current validation and important limitation

Current fixed-mode M1 is verified in [the completion report](results/2026-10-16/m1-completion.md):
normal019 passed1,201exact frames/600.300346s with safe shutdown; physical024
verified HDMI-only interruption and restart025 restored new exact captures.
The [011/012](results/2026-10-16/capture-011-loss-012-report.md) and earlier SD
failures below are preserved history. Runtime health uses fixed-clock checks;
native startup still requires input pixel clock. No arbitrary missing-clock
startup or automatic recovery guarantee is made.

The direct-VT source smoke test **passed** on2026-10-15: actualVT3,
640x480 progressive60Hz (25200kHz pixel clock), XR24,37 completed page flips
in the10-second run, exit0, and verified return toVT2. The compiled source also
matches all921600 reference bytes for five IDs; four invalid-ID cases fail
before display access. These9 tests pass locally. This proved the source and normal return. The subsequent720-second run also
passed the600-second PYNQ pixel/accounting criterion (1201/1201 exact frames),
but board storage errors and SIGBUS left DMA shutdown unverified; that historical run did not establish fullM1. See the [capture report](results/2026-10-15/m1-017-kms-001-report.md).
Evidence: [probe002](results/2026-10-15/kms-vt-probe-002.json).

The first VT attempt failed DRM-master acquisition because openvt choseVT1 and
GDM started a greeter compositor there. The corrected runner explicitly targets
VT3 (or another unusedVT3–12), rejects login-session VTs, and verifies the active
VT before starting KMS. It never forces DRM master away from the desktop.

A separate DRM-lease prototype did modeset DP-2 and complete18 page flips, but
GNOME50.1 crashed with signal11 during lease revocation. The preceding message
was `Failed to revoke lease: No such file or directory`. It restarted the desktop
session and affected the main screen. The prototype closed the lease descriptor
before asking the compositor to destroy the lease; this is a lifecycle suspect,
not a proven sole cause. An alternate release ordering was not live-retested.
Do not retry that prototype on the active desktop. It is retained only under
ignored `artifacts/debug/frame-difference/`, outside the supported tools.
The repository's new C source and runner use **no DRM-lease protocol**.

The main monitor's2560x1440@59.951 configuration was checked after the restart.
DP-2 was explicitly restored to640x480@59.940; readback confirmed restoration.
Notifications were restored toshow-banners=true. Evidence is in
`docs/results/2026-10-15/kms-{lease-crash,desktop-recovery}.log`.

## Build and bounded local probe

Dependencies already present on the tested machine: a C compiler, pkg-config,
libdrm development files, Python3, openvt, chvt and fgconsole. No global package
installation or permanent display configuration is performed.

```sh
bash scripts/build_kms_fixture.sh
.venv/bin/python -m pytest -q tests/test_kms_pattern.py
sudo /usr/bin/python3 tools/run_kms_vt.py --duration 10 \
  --output artifacts/operator/kms-vt-probe-NEW
```

Run the sudo command locally; never paste its password in chat. The evidence
directory must be new. Before switching, the runner validates a connected DGL
EDID oncard2-DP-2, records the original foreground VT, and requires a built
binary. It uses`openvt -c 3 -s -w` without force, after checking login sessions; no session logout,
display-manager stop, or forced DRM-master takeover occurs. Your desktop is
unavailable while this VT is active. The bounded program exits and openvt returns
to the original terminal; the runner also callschvt and verifiesfgconsole.
If necessary useCtrl+Alt+F2 to return to this machine's desktop (the runner records
the actual original VT rather than assuming2).

Inspect `source.jsonl`, `child-result.json` and `restore.json` in the new directory.
A passing source test requires a ready record, completed page flips, exit0, and
`original_vt_restored=true`. No board pixel success is implied by these records.
Do not launch the board sender until source handover has finished: changing
source mode during a single-credit capture deliberately invalidates that run.
After the short source/return test succeeds, coordinate a fresh sender and
receiver during a longer bounded VT run. Keep private captures underartifacts.

## Behavior impact and remaining risks

The added source can modeset only after the kernel grants DRM master; failure
returns nonzero. It selects the explicitly requested connector and supported VGA
mode. Invalid IDs/durations, absent connector/mode, failed allocation, failed
flip, and timeout fail rather than silently substituting output or format.
The wrapper restricts the local card/connector and refuses a non-DGL sink.
The real-VT normal subprocess/return path passed once on this GPU. It does not
establish recovery under all signals, faults or other GPU configurations.
Physical unplug, GPU errors, forced process termination and session recovery
remain unverified. Root is needed for VT switching, not for modifying the board.
No capture decoder, DMA policy, pixel tolerance or network protocol changed.

Local verification at21:11: the complete Python suite reported298passed and
1skipped (compiled gateware case requiresiverilog/vvp); the final CRTC-selection
change was followed by the focused9-case compiled-source suite, all passing.
No hosted CI was run. The subsequent direct-VT smoke test is recorded above. The CRTC selector prefers the
requested connector's existing CRTC, otherwise an unused compatible CRTC, and
fails when none exists rather than stealing another active output's CRTC.

## Kernel timing evidence

The VT runner now attempts one bounded, read-only kernel DRM state snapshot
after the new source reports readiness. It saves `kernel-state-during.txt`
and a JSON record with host monotonic sample times or the read error. This
does not read pixels or change modes. Missing/unreadable debugfs does not
change the source exit status, so inspect the JSON before claiming kernel
timing evidence. The new diagnostic has passed Python compilation; its first
20-second board/source execution is pending local PC authentication.

The fresh-card source001 completed2700 flips and restoredVT2, but the receiver
never became ready and delivered zero capture frames. Its requested VGA mode
is not sufficient proof of receiver input. The first host-visible EDID has an
unexplained4K preferred DTD. See the [startup diagnosis](results/2026-10-15/new-card-hdmi-startup-report.md).
