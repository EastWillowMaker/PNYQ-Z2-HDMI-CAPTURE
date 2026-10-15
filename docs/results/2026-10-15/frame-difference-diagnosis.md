# Desktop notification changes the received HDMI pixels

## Finding

Build017/v10 sustained capture failed: 1200 complete frames in600.082827s,
1189 exact and11 pixel failures. Metadata, transport, mixed-ID and repeated-ID
failures were zero. Seven failures had all480 optical rows valid and maximum
absolute error1. Four other failures (559–562) had damaged/unavailable markers;
their precise cause is not established by the notification experiment.
The failed run remains `m1-017-v10-sustained.{json,jsonl}`; it is not qualified.

A desktop notification on the primary monitor reproducibly changes the pixels
received from the secondary HDMI test output. This is a source-presentation
fixture failure mode. It does not justify accepting approximate RGB or changing
the FPGA arithmetic. The exact hardware stage performing quantization/dithering
has not been measured with an independent HDMI analyzer.

## Feedback loop and hypotheses

A seven-second real-board probe first reproduced the symptom twice with an
animated fixture. The probe sends one ordinary `notify-send` notification after
two seconds; no framebuffer pixels are read from the desktop. Captures stay
private in ignored `artifacts/debug/frame-difference/`. Initial direct ShowOSD
DBus access was rejected; no access-control bypass was attempted.

Ranked hypotheses, recorded before controlled tests:

1. Notification-driven desktop composition changes output quantization: hide
   banners while sending the same notification and the discrepancy disappears.
2. Pattern-dependent FPGA conversion: the same source ID remains wrong without
   a notification. Replaying ID105036 falsified that deterministic prediction.
3. DMA/cache instability: failures need not track desktop state and captured
   content could vary. Repeated equal bad buffers and clean completion counters
   weigh against this; host file rereads alone do not test board cache coherence.

Minimization held source ID105036 constant, preserving all640x480 RGB bytes.
No-notification control:15/15 exact. Notification:3/15 bad; each had211307 bytes
increased by1, all480 row IDs valid, no negative differences. All three private
NPY files had identical SHA256
`d155bbeeef9757dfdef044721cc332ebc3719b6a93c02b6b5441f33bba8f24d7`.
Source GLES framebuffer readback passed before presentation.

The maintained regression command is:

```sh
.venv/bin/python tools/check_hdmi_notification.py \
  'fe80::200:5ff:fe6b:1a0%enx98fc84e0c4e8' --port 9022 \
  --notify --expected-id 105036 --output NEW.json
```

This requires a running fixed-ID source and sender.
Without `--notify` it performs the same comparison without the trigger.
It neither changes desktop settings nor loads an overlay; it is a pixel
regression, not the full metadata/source-accounting qualification.

| Same fixed source / same notification command | Frames | Pixel failures | Exit |
|---|---:|---:|---:|
| Banners suppressed |15|0|0|
| Banners enabled again |15|10|1|

Evidence: `notification-suppressed.json`, `notification-enabled.json`.
Re-enabling banners may also release queued notifications, so this establishes
the banner-state effect, not one notification's exact display duration.
An earlier suppressed attempt was interrupted by the sender's900-second
lifetime after8 exact frames; it is not counted as a passing run. The old sender
reported `dma_shutdown_safe=true`, no source/cleanup errors, and exited before
the new sender loaded the unchanged017 overlay.

## Source-side mechanism and limits

Host GNOME Shell50.1 (`50.1-0ubuntu1`), Mutter50.1-0ubuntu2.2,
Mesa26.0.3, AMD Radeon890M. The matching upstream
[messageTray.js](https://github.com/GNOME/gnome-shell/blob/50.1/js/ui/messageTray.js#L1140)
disables compositor unredirect when displaying a banner and enables it on
completion (line1281). This explains why a notification on the primary monitor
can disturb direct scanout of the secondary fullscreen fixture.

The existing metadata-only DRM sampler observed XR24 during exact capture and
XR30 during the triggered failures. In the second animated reproduction all4
bad frames' nearest samples were XR30 and all11 exact frames' samples were XR24.
The first reproduction has one transition-boundary mismatch to the nearest
sample. Sampling every250ms is not continuous scanout proof and host receipt
is later than source presentation. Source GL8-bit self-check proves the app's
backbuffer, not final compositor/physical HDMI output. The observed positive
one-LSB differences fit conversion/dithering but do not identify its exact stage.

## Mitigation, impact and remaining work

User explicitly authorized temporary desktop-wide banner suppression and
restoration. Original `org.gnome.desktop.notifications show-banners=true` was
recorded; a user systemd15-minute restoration timer was armed before suppression.
A new600-second animated qualification is running as `m1-017-v10-dnd` with the
same bitstream/sender and strict byte-for-byte comparison. No capture parser,
health validator, completion policy, or acceptance tolerance changed.

The new probe accepts only a uint32 explicit expected ID, reports any pixel
mismatch as failure, records network/notification exceptions as failure, and
requires at least3 received frames. Unsupported notification services fail the
probe rather than passing silently. Other desktops/hardware are unverified.
It does not validate all M1 health metadata; use `qualify_capture.py` for that.
Notifications are merely one compositor trigger; overview, OSD, cursor/display
changes, and other overlays may still interrupt direct scanout. A permanently
controlled independent source or demonstrated exact composed output is stronger
than relying on a normal interactive desktop. No permanent desktop change is
being prescribed. Full M1 interruption/physical recovery qualification remains
separate from this diagnosis.

### Long-run counterexample to banner suppression

At215.7seconds the new animated run had432 frames and52 pixel failures, all
with480 valid marker rows and maximum error1. Forty-three failures were at the
start; later sporadic failures also occurred with show-banners=false. Thus the
short controlled mitigation is **insufficient for sustained qualification**.
Do not report the source as fixed. The final bounded result will be appended.

Mutter50.1's
[choose_onscreen_egl_config](https://github.com/GNOME/mutter/blob/50.1/src/backends/native/meta-onscreen-native.c#L2670)
tries alphaless10bpc formats before8bpc formats. The tested display configuration
DBus interface does not expose a documented max-bpc override; even link-depth
limits would not by themselves establish8-bit compositor rendering. No desktop
restart, compositor patch, persistent monitor edit, or guessed override was made.

Validation:112 existing pattern/qualification/evidence-analysis tests passed
locally in0.97s; new probe syntax and help checked. The regression's meaningful
red/green evidence is the actual board run above, not a mocked test. No hosted CI
was run. Temporary prototypes remain clearly isolated under ignored
`artifacts/debug/frame-difference/`; production code contains no debug logging.

### Completed suppression run and source alternatives

`m1-017-v10-dnd` completed600.196309s:1201 delivered,1148 exact,53 pixel failures,
zero metadata/transport errors. It failed. Notifications were restored totrue
and the backup restoration timer stopped. The board later exited its bounded
run withdma_shutdown_safe=true and zero source/cleanup errors.

An isolated10-bit GLES prototype encoded each8-bit reference valuev as10-bit4v.
Actual packed10-bit framebuffer readback equaled the analytic values; the same
notification regression passed15/15 real RGB888 frames with banners enabled.
This is short-run evidence only. It was not promoted into the normal fixture
because the user requested an independent framebuffer/KMS source instead.

Direct DRM lease successfully produced XR24 scanout, but its teardown triggered
a GNOME50.1 signal11 crash and desktop-session restart. This was a real regression
of the experiment, not just a slow DBus response. The lease prototype is isolated
and not a normal execution path. The restored display and crash evidence are
recorded separately. A compiled direct-KMS source plus a bounded standalone-VT
runner is prepared; it requires local sudo and has not been hardware-qualified.
See [KMS source](../../kms-source.md) for the exact command, evidence and limits.

### Direct KMS sustained result

The subsequent direct KMS/017/v10 run passed1201/1201 exact frames over
600.155270s, with unchanged capture code and strict comparisons. It removes
the desktop composition failure mode in this tested source path. SD/EXT4 I/O
errors then prevented normal shutdown, and a sender SIGBUS was recovered;
DMA shutdown remains unknown, so this is not fullM1 completion. See
[m1-017-kms-001-report.md](m1-017-kms-001-report.md).
