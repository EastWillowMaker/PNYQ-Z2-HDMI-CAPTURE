# M0 bring-up evidence

Status: in progress. User approved the first-round contract and temporary overlay
and network operations. This report does not establish M1 completion.

## Physical transport

The dedicated host NIC uses a memory-only NetworkManager profile
`codex-hdmi-m0` / `3c670070-9c7b-4993-bed7-7f8161e80d6c` with IPv6 link-local
and IPv4 disabled. Original profile was `864ebd1d-48cd-3cc5-bddd-93475bb4700e`.
[Network evidence](network-m0.json) saves routes, interface state and ping.
No boot-media image or global Python package was replaced.

Board synthetic sender → real Ethernet → installed PC CLI delivered 30
640×480 RGB888 frames in 5.9241 seconds: 5.0641 FPS, 37.3365 Mbps payload,
zero detected protocol errors. [Raw benchmark](synthetic-board-benchmark.json).
Five additional frames matched every byte of the deterministic synthetic pattern
([pixel check](synthetic-board-pixels.json)). These are not HDMI frames.

The board wall clock reports 2022 despite the host date being 2026. Frame timestamps
use monotonic clocks with explicit domains; no one-way latency is inferred.

## Real HDMI path

The staged PYNQ probe loaded the existing base overlay, configured input, started
VDMA, returned one real `(720,1280,3)` uint8 frame and closed successfully.
[Probe log](probe-final.log). This demonstrates a real HDMI→DDR acquisition at
the source's initial automatic 720p mode; the probe did not send that frame over
Ethernet or qualify agreed 640×480 operation.

The PC identifies the source endpoint as DP-2, DGL DigilentDVI-2. Mutter 50.1 hides
640×480 from its advertised mode list although DRM retains it. Verify-only then
temporary `ApplyMonitorsConfig` accepted 640×480 at 59.940 Hz, preserving the
other monitor's then-current configuration. [Verify](display-mode-0.json),
[apply](display-mode-1.json). OS hotplug had changed the ASUS monitor refresh from
its initial approximately 144 Hz to approximately 60 Hz; the initial state is
retained locally in `artifacts/operator/display-before.json` for restoration.

The next M0 sender accepted 640×480 and began listening, but continuous reads
failed with `Invalidate Failed: 4294967274`, followed by native cleanup errors.
[Failure log](hdmi-640-status.log). No real frame was delivered by the failed
snapshot attempt ([CLI error report](first-frame-cli.json)). Do not omit this
failure from capture qualification.

## Failures and investigation

- First sender launch lost `XILINX_XRT` under sudo and failed `No Devices Found`.
  The board's `/etc/profile.d/xrt_setup.sh` declares `/usr`; explicit process-local
  `XILINX_XRT=/usr` fixes device discovery. Global environment was not changed.
- First native HDMI launch then raised SIGBUS. A subsequent staged probe succeeded;
  the kernel logged an external abort on an MMIO access. The exact transient cause
  is unresolved; no claim of stable startup or missing-source recovery.
- Exact board PYNQ 3.0.1 buffer code can return a pointer to its cache on
  `freebuffer()`, then free that cached BO when its destructor calls `freebuffer()`
  again. Repeated reuse also needs allocator-finalizer review. Adapter-local buffer
  ownership repair now retains and recycles original buffer objects, bounded to
  five allocations. Exact installed buffer-class tests and physical capture
  succeed; no global PYNQ patch applied.
- Independent sender review reproduced blocked shutdown with an active TCP client
  and retained transport buffers after slow-client timeout. Both fixes and real-socket
  regressions passed; stalled transports are aborted and active clients close
  before awaiting server shutdown.
- Stock base HWH uses `dvi2rgb kClkRange=1`; source/build review found that clock
  configuration unsuitable for formal 25 MHz VGA timing qualification. Even an
  apparent M0 capture cannot prove correct MMCM operating range. The M1 build is
  correcting the frontend range and constraints explicitly.

All raw image captures and downloaded source copies remain in ignored local
`artifacts/`; no captured images were uploaded to external services. Live HDMI
pixel fidelity, sustained delivery, source/client disconnect recovery and M1
gate/DDR/timing qualification remain outstanding.

## Buffer repair and physical delivery

The repaired deployment is identified by [source manifest](deploy-m0-v2.json).
[First successful snapshot](first-frame-success-cli.json) delivered 921600 RGB
bytes. [Thirty-frame run](m0-pool-capture.json) delivered 30 frames in 14.8866 s,
2.0152 FPS, 14.8579 Mbps payload, zero protocol errors. All thirty optical IDs
were distinct and each had 480 consistent rows, but [exact checks](m0-pool-pixels.json)
failed with maximum absolute error 1. This is delivery/coherence evidence, not
exact pixel qualification.

[Final board log](m0-pool-final-status.log) reports 180 seconds, 10352 DMA
acquisitions and zero source errors, without the prior invalidate/double-free
failure. Sampling and ready-slot replacement account for deliberate drops;
PYNQ hardware loss counts remain unknown. Thirty-one frames were enqueued to
TCP across snapshot/capture clients; this counter alone is not delivery proof.
An ignored UioController destructor error after asyncio loop shutdown remains
visible at process exit. Stable absent-source startup/recovery remains unverified.

A read-only DRM probe found the original GTK path used XR30 scanout despite
RGB24 drawing. An opaque native Wayland GLES source now reports RGB8 and XR24
scanout ([DRM evidence](source-gl-drm.txt)). Its exact capture comparison is the
next test; no tolerance or replacement golden image is used.

## Exact RGB source experiment result

Native GLES/Wayland source and XR24 scanout delivered the first exact frame
([snapshot](m0-gl-snapshot-success.json), [pixel check](m0-gl-pixels.json)).
The subsequent [30-frame run](m0-gl-capture.json) delivered 2.0555 FPS with zero
protocol errors. [Every byte matched in all thirty frames](m0-gl-pixels-30.json):
30 distinct optical IDs, no mixed rows, zero maximum error. No tolerance,
reference recapture or receiver-side gamma adjustment was used. This resolves
the observed fixture discrepancy for this source configuration; M0 is still
baseline-only, not evidence of LiteX participation or a ten-minute M1 run.
An earlier connection attempt before source readiness failed (m0-gl-snapshot.json);
the successful attempt is retained separately rather than overwriting it.

## Subsequent restart and board failure — unresolved

The current high-precision shader was restarted with its prelaunch hash saved
in `source-gl-current.sha256`. Its first received frame had coherent optical
ID 10017 but 210834 differing bytes with maximum error 1
([failed comparison](m0-gl-current-pixels.json)). The later XR24 probe was not
simultaneous with that captured image; the cause remains unresolved. Earlier
30 exact frames establish that run, not reliable startup or all configurations.

After the second bounded M0 run, a UART process-status command timed out;
initial Ethernet pings still replied, then SSH reset the connection. UART
subsequently reported `Kernel panic - not syncing: Attempted to kill init!
exitcode=0x0000008b` ([raw log](uart-recover-2.log)). Neither the trigger nor a
relationship to buffer release, DMA, or the stock receiver clock is established.
The prior UIO destructor warning does not explain this kernel panic. Board reset
was requested as a physical recovery step; hardware testing is paused pending
recovery. Independent native DMA/allocator cleanup reviews are underway.

The LiteX project007 build was also rejected for negative max timing slack.
No rejected bitstream was loaded. The receiver-lock reset crossing is being
corrected with explicit synchronization; M1 remains unqualified.

## Cleanup review and source-only follow-up

The pinned S2MM stop method clears RS, waits for status Halted, then removes
frame slots. The application releases its retained BO pool only after that call
succeeds. A delayed-halt execution stub preserved this order, and injected
KeyboardInterrupt prevented releases. These tests do not reproduce the panic.
The external `--kill-after=5` wrapper could kill a process whose native stop
never completes; allocation release before DMA quiescence is a credible hazard.
Future runs must not use forced process termination as proof of DMA shutdown.
No log establishes that the timeout actually fired during this failure.
The stopping CPU's bash stack in the panic output is not init's fault trace.

A source-only 60-second GLES run with explicit per-image glReadPixels verification
exited successfully; progress logs show at least 200 different generated images
matching every byte in the application's own framebuffer
([source log](source-gl-selfcheck.txt)). This reads only the synthetic application
backbuffer and does not qualify HDMI scanout or the panicked board's capture.

## Physical reset and non-DMA follow-up

User reset the board and refreshed sudo locally. UART login and Ethernet ping
recovered. [Fresh boot diagnostics](board-after-panic-reset.log) retain ext4
mount-with-errors/journal recovery and FAT unclean-volume warnings. No SD repair,
reimage or boot configuration change was performed. The temporary dedicated
NetworkManager profile was reactivated after automatic fallback to the original
connection; its original link-local host address returned.

A non-root synthetic sender then ran for 150 seconds and exited normally.
The host received 595 complete frames at 4.996 FPS / 36.837 Mbps before EOF at
119.087 seconds: the sender's timer began earlier than the requested 120-second
host window, so the [client correctly reports one EOF error](post-reset-synthetic-benchmark.json).
This is neither a clean 120-second qualification nor HDMI evidence.
[Resource samples](post-reset-synthetic-resources.log) cover the latter portion
of this CPU-generated synthetic run; [summary](post-reset-synthetic-resource-summary.json).
The shell remained responsive after sender exit. This does not isolate or
resolve the earlier DMA/kernel failure.
