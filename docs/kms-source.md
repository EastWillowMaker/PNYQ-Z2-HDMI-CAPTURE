# HDMI source outside desktop composition

Use direct DRM/KMS to scan out XRGB8888 buffers on the PYNQ-connected output.
The C source writes the analytic RGB fixture into two buffers and waits for each
page-flip completion before reusing the previous buffer. A640x480 progressive
mode at59.9–60.1Hz is required; optical IDs advance roughly four times per second.
No OpenGL, Vulkan, window, desktop screenshot, or reference-image learning is
involved. The PC receiver still compares every RGB888 byte strictly.

## Current validation and important limitation

The direct-VT path is **prepared but not hardware-qualified**. The compiled C
source matches all921600 reference bytes for five IDs, including0 and UINT32_MAX;
four invalid-ID cases fail before display access. Nine tests pass locally.
The program also refuses DRM master acquisition while the desktop owns it.
These checks do not prove live scanout, recovery, or real HDMI pixels.

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
  --output artifacts/operator/kms-vt-probe-001
```

Run the sudo command locally; never paste its password in chat. The evidence
directory must be new. Before switching, the runner validates a connected DGL
EDID oncard2-DP-2, records the original foreground VT, and requires a built
binary. It uses`openvt -s -w` to choose a free terminal; no session logout,
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
The real-VT subprocess/return path is still unexecuted; compilation and pattern
checks cannot establish that it works on this GPU or survives all signals.
Physical unplug, GPU errors, forced process termination and session recovery
remain unverified. Root is needed for VT switching, not for modifying the board.
No capture decoder, DMA policy, pixel tolerance or network protocol changed.

Local verification at21:11: the complete Python suite reported298passed and
1skipped (compiled gateware case requiresiverilog/vvp); the final CRTC-selection
change was followed by the focused9-case compiled-source suite, all passing.
No hosted CI or direct-VT hardware test was run. The CRTC selector prefers the
requested connector's existing CRTC, otherwise an unused compatible CRTC, and
fails when none exists rather than stealing another active output's CRTC.
