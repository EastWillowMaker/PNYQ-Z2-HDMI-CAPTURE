# PC HDMI source fixture and offline pixel check

The M0/M1 source is the PC's USB-C HDMI adapter and the verified HDMI cable to
PYNQ-Z2 HDMI input. The required active image is 640×480 progressive at 60 Hz,
RGB888. Physical capture and mode setup are separate from the offline checks
below. The synthetic tests alone do not establish physical capture correctness.

`tools/hdmi_pattern.py` generates a known image analytically, and checks every
captured byte against it. Each row carries the same 32-bit optical frame ID in
two-pixel black/white bit pairs followed by their complement. The other pixels
include independent RGB texture derived from row, column and ID, one-pixel
primary/black/white lines, and all 256 levels in each isolated channel ramp.
These expose pixel corruption, row/column displacement, scaling, channel
permutation, range conversion and mixed source frames. A valid marker alone
does not establish that the rest of the image is correct.

Use the system Python for GTK3/Cairo. It has `gi`, Cairo and NumPy installed;
the client virtual environment may lack GTK. Read the monitor list first:

```sh
/usr/bin/python3 tools/hdmi_pattern.py list-monitors
```

After the selected adapter output has been independently configured to the
required mode and scale, explicitly choose its current monitor index:

```sh
/usr/bin/python3 tools/hdmi_pattern.py start --monitor-index 2 --frame-id 1
```

Replace `2` with the adapter's actual index. GTK reports geometry, manufacturer
and model; on this GTK3 interface it does not reliably expose the DRM connector
name. Cross-check the index/geometry against the adapter's connector from the
mode audit. Indices can change after hotplug; list again before starting. The
command never changes display modes, scaling, configuration files or other
monitors. It refuses a selected geometry other than 640×480 or a scale other
than 1, and checks the actual window allocation and monitor during drawing.
GTK fullscreen placement is asynchronous: startup allows up to two seconds
to settle, shows black before the first correctly placed image, and prints
`Fixture ready` when that image is drawn. Animation IDs advance only after
readiness. A later incorrect placement stops the fixture with a diagnostic.
Escape closes the source window. This is a deliberate visible fullscreen
window on the selected output; no screenshots or desktop pixels are read.

First use a static frame to isolate pixel fidelity. Capture a `.npy` RGB array
with the client, then run:

```sh
.venv/bin/python tools/hdmi_pattern.py verify artifacts/static.npy --frame-id 1
```

Exit 0 means the complete saved array equals this analytic image; exit 1 means
pixel mismatch; exit 2 means invalid input or an operational error. The JSON
report includes optical ID counts, damaged marker rows, all affected rows,
byte/pixel/channel mismatch counts, first mismatching location and maximum
absolute error. It never approves or learns a replacement golden image.
Malformed shape/dtype inputs are rejected. For a captured frame with no intact
marker, supply the independently known source ID to get full mismatch counts.

An animated fixture helps detect mixed rows:

```sh
/usr/bin/python3 tools/hdmi_pattern.py start --monitor-index 2 --frame-id 1 --animate
.venv/bin/python tools/hdmi_pattern.py verify artifacts/animated.npy
```

Without `--frame-id`, verification chooses the most frequent completely valid
row ID and still compares **every byte**. Multiple intact row IDs are reported
as `mixed_optical_ids`; a single corrupted pixel also fails. The optical ID is
the source image ID, distinct from a board/server transport frame counter.
The animation advances on a GTK timer (17 ms by default), not HDMI vertical
blank. Compositor redraw coalescing can skip IDs, and consecutive captured
images can legitimately share one ID. A gap does not prove a board drop.
The static source is therefore unsuitable for detecting temporal duplicates.

Offline test images can be generated without a display, and existing output
files are protected against accidental replacement:

```sh
.venv/bin/python tools/hdmi_pattern.py generate --frame-id 305419896 --output artifacts/reference.npy
.venv/bin/python -m pytest tests/test_pattern.py
```

The fixture requests unscaled Cairo RGB24 pixels with nearest filtering.
Monitor geometry checks do not prove physical timing, refresh rate, HDMI
encoding, color depth, RGB versus YCbCr, full versus limited range, color
management, adapter conversion or scanout atomicity. The source pipeline can
alter the intended pixels; the verifier will report such alteration rather
than silently calibrate it away. Establish actual negotiated input timing and
format from the board/adapter separately and retain those observations with
the capture result. Even exact received pixels do not establish every HDMI
timing requirement or distinguish capture-side tearing from source-side
tearing. Synthetic tests prove the offline generator/verifier only; physical
display placement, HDMI transport, DMA coherency and source/capture frame
atomicity remain unverified until the on-board experiment runs.

## GNOME Mutter hidden 640×480 modes

On this PC, GNOME Shell 50.1 runs Wayland. The USB-C adapter is physical
connector `DP-2`, identity `DGL / DigilentDVI-2`; ASUS `HDMI-1` is the main
2560×1440 display. Xwayland's `xrandr` describes its virtual desktop and does
not establish the physical adapter mode. Kernel DRM and Mutter's
`GetResources` expose 640×480@59.940 and @60.000 for DP-2. Mutter's
`GetCurrentState` omits both from its advertised list: the
[Mutter 50.1 mode code](https://github.com/GNOME/mutter/blob/50.1/src/backends/meta-monitor.c#L2445)
requires at least 800×480 pixels unless the size matches the preferred mode.
This filters advertisement; it does not remove the internal modes.

The [Mutter configuration implementation](https://github.com/GNOME/mutter/blob/50.1/src/backends/meta-monitor-manager.c#L2576)
looks up a requested mode directly. `ApplyMonitorsConfig` method 0 verifies
the complete configuration without applying it, method 1 applies it
temporarily, and method 2 persists it. The supported-scale calculation
falls back to scale 1 for this small mode. Thus an explicitly named hidden
mode can be verified and applied without altering the ASUS requested mode.
The old `ApplyConfiguration` API is unnecessary even though introspection
still lists it.

On 2026-10-15, method 0 verification and method 1 temporary application of
DP-2 `640x480@59.940` succeeded; the GTK monitor list then reported
640×480 at scale 1 while ASUS retained `2560x1440@59.951`.
Evidence is in [display-mode-0.json](results/2026-10-15/display-mode-0.json)
and [display-mode-1.json](results/2026-10-15/display-mode-1.json). This is
display configuration evidence, not exact HDMI pixels or DMA correctness.
The initial source-window attempt exited because fullscreen placement had
not completed on its first draw; the bounded startup settling described
above addresses that asynchronous placement.

`tools/configure_hdmi_source.py` makes the workaround repeatable. Its default
is verification only, with no mode changes or snapshot writes:

```sh
/usr/bin/python3 tools/configure_hdmi_source.py --connector DP-2
```

To perform a new temporary application, choose a new snapshot path:

```sh
/usr/bin/python3 tools/configure_hdmi_source.py --connector DP-2 --apply --snapshot artifacts/source-mode-before.json
```

The helper checks the explicit connector's DGL/Digilent identity, confirms
the requested mode in that output's resource mode list, requires an enabled
unmirrored output with normal orientation, and preserves every other logical
monitor's current mode, position, scale, transform, primary status, color
mode and RGB-range properties. It preserves the selected output's position
and color settings while requesting the chosen mode at scale 1. It performs
method 0 verification first, saves the original configuration to a new file
before applying method 1, and reads back the applied configuration. It never
uses persistent method 2. A stale serial, existing snapshot file, forbidden
monitor identity or unsupported mode fails instead of guessing.

Restore the original configuration using that saved snapshot:

```sh
/usr/bin/python3 tools/configure_hdmi_source.py --connector DP-2 --restore artifacts/source-mode-before.json
```

Restoration is also temporary. It verifies first, refuses changed monitor
identities or intervening changes to another monitor, and retains the file
for later inspection. A post-application discrepancy is reported as an
error; retain the snapshot to restore explicitly. This helper's default
verification command succeeded on the actual session. Its snapshot/apply
and restoration code has synthetic safety tests; live helper application
and rollback have not been executed. The earlier successful physical mode
change used the recorded operator script, so that result does not prove
this helper's complete restoration path.

## Pixel fidelity and the native GLES source

The first physical PC→HDMI→PYNQ→Ethernet→PC GTK fixture capture had optical
ID 598 on all 480 rows, but failed exact comparison: 211,675 bytes differed,
with channel counts R=70,847, G=70,543, B=70,285. Every differing value was
exactly **one greater** than expected. Marker/primary columns 0–132 were
exact; values 0–42 were exact, while identical mid/high source values
sometimes arrived unchanged and sometimes one greater, including different
rows of the otherwise identical isolated ramps. These observations do not
establish byte fidelity and must not become an accepted replacement golden.

A local Cairo RGB24→RGB24 offscreen paint using the same source array and
nearest filter had zero low-24-bit mismatches. Read-only DRM metadata showed
amdgpu DP-2 CRTC 417 at 640×480 with a 25.175 MHz pixel clock and active
framebuffer format `XR30` (10-bit XRGB2101010), while connector `max bpc`
was 16. That property is a maximum, not proof of actual wire bit depth.
DP-2's read-only gamma ramps had 4096 nearly linear entries, identical
across RGB; Night Light was disabled and an EDID-derived ICC profile was
assigned to the output. No desktop color settings were changed.

The positive, pixel-dependent quantization is consistent with 10-bit
compositor scanout followed by reduction/dithering to the captured 8-bit
values. This is a hypothesis supported by the format and numeric evidence,
not a proven attribution to the adapter, compositor or AMD output stage.
Black/white marker integrity alone does not resolve that question. The
verifier continues to reject every one-byte difference.

`tools/hdmi_pattern_gl.py` presents the same analytic fixture through a
native Wayland SDL2/EGL GLES window. It requests 8-bit RGB and zero alpha,
logs actual SDL/GL channel bits, requires 8 bits per RGB channel, disables
GL dithering and blending, and uses an ordinary RGB texture with nearest
filtering, high-precision texture coordinates and opaque fragment output.
It does not request an sRGB framebuffer, apply a gamma correction,
precompensate pixel values, or modify the verifier. SDL2/GLES libraries
already present on this PC are loaded through ctypes; no extra Python
graphics dependency is required.

```sh
/usr/bin/python3 tools/hdmi_pattern_gl.py --list-monitors
/usr/bin/python3 tools/hdmi_pattern_gl.py --monitor-index 1 --frame-id 1 --animate
```

Use the actual current SDL monitor index from the list, and close the prior
GTK source first. Escape closes the GLES source. `--duration 30` bounds a
run to 30 seconds; omit `--animate` for a static source. The tool forces
Wayland only for its own process, uses the output's existing desktop mode,
and refuses to start on a selected monitor other than 640×480. It also
checks actual drawable size and monitor placement, allows two seconds for
fullscreen placement, presents black until correct placement, and stops if
placement later changes. It never changes another output or global display
configuration. Optical IDs still advance by application timing and remain
distinct from transport frame counters.

On the actual session, this GLES source launched successfully with reported
8-bit SDL/GL RGB channels; read-only DRM metadata changed from `XR30` to
`XR24` (8-bit XRGB8888). The launch log is local
`artifacts/operator/pattern-gl.log`. That observed source/scanout change
supports the direct-scanout hypothesis, but an 8-bit GL request alone never
guarantees that path: another compositor, overlay, cursor placement, window
visibility or driver can change scanout. Retain DRM format observations and
exact physical verification for each run. Tests cover monitor selection,
640×480 refusal and missing-selection refusal; actual launch covers the
installed ctypes/SDL/GLES interface. Shader output and physical pixel
fidelity require the complete capture comparison, not those synthetic
selection tests or channel-bit logs.

The first native GLES physical capture passed comparison of all 921,600
RGB bytes: optical ID 245 on all 480 rows, zero mismatching pixels/bytes,
zero mixed row IDs and zero maximum error. The following 30 captured frames
also passed every byte, with 30 distinct optical IDs, no mixed row IDs and
zero protocol errors. The bounded M0 delivery run measured approximately
2.055 frames/s and 15.15 Mbit/s; this establishes the observed low-rate M0
path, not 60-frame/s delivery or a zero-drop guarantee. Evidence is
[m0-gl-pixels.json](results/2026-10-15/m0-gl-pixels.json),
[m0-gl-pixels-30.json](results/2026-10-15/m0-gl-pixels-30.json) and
[m0-gl-capture.json](results/2026-10-15/m0-gl-capture.json).
Keep the earlier GTK failure alongside these results: changing the source
presentation and observed framebuffer format removed the error in these
captured samples, while isolating the exact compositor/driver quantization
stage remains incomplete.

The running GLES source in those results was launched **before** the later
shader edit that explicitly requested high-precision varying coordinates
and fragment floats. It used the initial default vertex varying precision
and `mediump` fragment precision. A reconstructed copy of that launch source
is local `artifacts/operator/hdmi_pattern_gl-launched.py`, SHA-256
`adb39a576c03f939d68e4ec0532ad152f7f9a5340b3906390a1ffd1aae855749`;
its provenance note explicitly records that the hash was reconstructed by
reversing the known shader edit, rather than measured before launch.
The prior 30 exact frames do not validate code edited after that launch.
A subsequent restart using the high-precision shader captured optical ID
10017 coherently on all 480 rows but failed exact comparison again: 210,834
bytes differed by +1. A separate DRM metadata probe still reported XR24.
That probe alone does not establish the format at the instant the failing
frame entered HDMI. The run used a 250 ms source interval, so ID 10017 was
approximately 4.25 seconds into the source sequence; the ID does not support
an inference that this was merely a stale first-half-second frame.
Shader arithmetic, source/compositor presentation changes and downstream
quantization have not yet been separated. Evidence is
[m0-gl-current-pixels.json](results/2026-10-15/m0-gl-current-pixels.json).

The current GLES tool adds an optional `--self-check` to read back each new
source ID from **its own synthetic GL backbuffer before presentation**.
It checks all 921,600 RGB bytes against `pattern(frame_id)`, handling GL's
bottom-up row order, and exits with a numeric mismatch diagnostic if any
byte differs. This reads no other window or desktop image. Initial and
periodic `Synthetic framebuffer exact` logs establish that GL stage only;
compositing, scanout, HDMI and capture still require physical verification.
For the next experiment, use:

```sh
/usr/bin/python3 tools/hdmi_pattern_gl.py --monitor-index 1 --frame-id 20000 --animate --interval-ms 250 --self-check
```

Record contemporaneous source/readback logs and scanout format alongside
captured optical IDs. The self-check introduces a synchronous GPU readback
for each new source ID, so it may affect presentation timing and must be
included in the recorded source configuration. Its synthetic tests detect
a single changed RGB byte; live GL readback remains unverified until this
new source command runs. Exact physical fidelity of the current source is
unresolved, and the earlier passing captures must not be generalized to
every presentation configuration or the current revision.

## Correlating source IDs with scanout metadata

For a bounded qualification run, launch a metadata logger and source with
new output paths, then retain both beside the host capture records:

```sh
/usr/bin/python3 tools/monitor_hdmi_scanout.py --card /dev/dri/card2 --connector DP-2 --output artifacts/scanout.jsonl --duration 700 --interval 0.25
/usr/bin/python3 tools/hdmi_pattern_gl.py --monitor-index 1 --frame-id 20000 --animate --interval-ms 250 --self-check --events artifacts/source-events.jsonl
```

These are concurrent processes, so run them in separate terminals or under
the experiment's process supervisor. The metadata logger opens the selected
DRM card read-only and uses libdrm metadata getters. It never maps, exports
or reads framebuffer pixels and does not set DRM properties or modes.
Each JSONL sample records monotonic start/end and Unix timestamps, connector
connection state, selected CRTC/framebuffer IDs, mode dimensions/timing,
framebuffer fourcc/modifier, max-bpc and relevant connector properties.
It rereads the CRTC framebuffer ID after sampling and flags whether that ID
stayed unchanged during the sample. Samples and read errors remain in the
log, followed by a count/error summary after the bounded duration; any read
error makes the logger exit unsuccessfully. Output files use exclusive
creation. An initial one-second actual-session smoke produced four samples
and zero errors, reporting the disconnected connector; the active-framebuffer
branch still requires a connected-session check of this Python logger.

`--events` gives the GLES source its own exclusively created JSONL file.
The first event records source-file SHA-256 and source options, so later
edits cannot be mistaken for the launched revision. Each newly generated
optical ID gets its CPU generation-completion timestamp, a `source_pre_swap`
event after drawing/self-check, and a `source_swap_return` event after the
SDL swap call returns. A self-check flag distinguishes checked framebuffer
bytes from unchecked draws. All timestamps use the same host monotonic clock
as the metadata logger; Unix timestamps provide human correlation.
Generation, pre-swap and swap-return timestamps are **not measured HDMI
presentation times**. A compositor may queue, skip or delay presentation,
and the board's capture/transport can add latency.

Correlate each received image's decoded optical ID with its generation and
swap interval, plus metadata samples around that interval and reception.
Keep samples marked inconsistent or erroneous visible. Sampling every
250 ms can miss a shorter compositor/scanout transition; even consistent
XR24 samples do not prove that format throughout the interval or establish
exact received RGB. The full analytic pixel verifier remains the acceptance
test for each captured frame. If a source/logging process is killed, its
final event may be absent; preserve that incomplete coverage explicitly.

## Mode helper with the LiteX VGA EDID

Build 013 changes the DP-2 identity from the base overlay's `DGL / DigilentDVI-2`
to exactly `DGL / LiteX VGA / 0x00000000`. The mode helper originally refused
this new identity before configuration verification. It now accepts that
exact tuple as an additional known sink, requires that its resource modes
contain only progressive 640×480@60.000 or @59.940, and keeps the original
DigilentDVI-2 route. Other vendors, products, LiteX serials, non-VGA modes,
interlaced or double-scanned timings remain rejected. Snapshot restoration
for the LiteX identity must also stay within those two VGA modes.

Read-only method 0 verification of `640x480@59.940` succeeded on the actual
013 sink while the sustained capture was running, preserving ASUS mode,
position, scale and color/range settings. No mode was applied during that
run. Synthetic tests cover the newly supported tuple and unrelated/forbidden
identities and timings. The later operator mode-switch experiment successfully
applied and read back `640x480@59.940` for that identity with ASUS settings
preserved; see [m1-mode-switch-apply.json](results/2026-10-15/m1-mode-switch-apply.json).
The running source's placement guard then exited on a transient unexpected
2560×1440 drawable, so this configuration success does not establish
uninterrupted source/capture recovery. Snapshot restoration remains unverified.

The built 013 EDID is 128 bytes, SHA-256
`e716887ace476531df33bbec6ff03e4b6c1148a243a00d3d237f1b77bff1050d`,
with zero extension blocks. Mutter reported a 256-byte host EDID, SHA-256
`3b01e13acc1664b49df3d35d945f1a96dfcc5a86544a1e05b260525a79de31f6`:
base-byte differences are only physical-size bytes 66–68, extension-count
byte 126 and checksum byte 127; it adds a small CTA extension. The host
still advertised only the two VGA timings. This is consistent with
adapter/driver rewriting, but attribution is unverified; do not claim
byte-identical host EDID and receiver ROM from these observations.

## Offline host timing correlation

`tools/analyze_hdmi_evidence.py` reads the capture verification JSONL,
source events and scanout metadata only; it does not open image arrays.
It matches coherent per-row optical IDs to unique source events, calculates
host generation/pre-swap-to-receipt distributions, and reports metadata
formats, modes, errors, ID gaps and sampling coverage. These intervals include
source image age, rendering, presentation, acquisition and transport. They
are not wire latency; board and host clocks are not subtracted.

```sh
.venv/bin/python tools/analyze_hdmi_evidence.py --capture docs/results/2026-10-15/m1-013-v5-sustained.jsonl --source-events artifacts/m1-013-v5-source-events.jsonl --scanout artifacts/m1-013-v5-scanout.jsonl --output artifacts/correlation-preview.json
```

Default output is explicitly provisional. It tolerates a partial final line
of a growing log while reporting that gap, hashes the bytes actually read,
and never declares qualification passed. Only after the operator confirms
completion, add `--final --capture-summary path/to/completed-summary.json`
and choose a new report path. Final parsing rejects partial JSONL. Reports
retain unmatched/ambiguous IDs, failed pixel checks, inconsistent metadata
samples and intervals without a scanout sample. Format sampling and exact
pixel verification remain distinct evidence.
