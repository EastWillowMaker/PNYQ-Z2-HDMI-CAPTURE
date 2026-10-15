# Fresh-card input diagnosis after attach003

The90-second source run returned normally. Attached-source startup also failed
in frontend.configure, so avoiding FPGA reload did not fix this incident.
There were no capture frames, no smoke pass and no ten-minute qualification.
The original failed result remains in../2026-10-15/m1-017-newcard-attach-003-*.
The supervisor's before/after ext4 error counts are0 and the16MiB file hash is
unchanged. Its final dma_shutdown_safe is null because startup never reached
the sender status-report path. A later preflight found no sender process; the
next MMIO probe independently asserted DMA RS0/Halted1 and command reset0.
Do not replace the original null result with a successful cleanup claim.

## Native initialization004

Using the still-open local source worker, requested a60-second VGA source and
ran frontend-only _video._capture with a5-second native timeout. A separate
Python MMIO process sampled HPD, clock-lock GPIO, raw VTC registers and source
counters during the call. No DMA or capture pool was started.

HPD and clock-lock GPIO read1 throughout. The native call enabled VTC control
from0 to0xa and the raw detector-status register read0x2. The call failed in
about4.93seconds with the original no-video error. This demonstrates that the
native GPIO wait reached VTC initialization; it does not support blaming a
simple Python/native GPIO address mismatch. No valid detected active size was
obtained. Raw VTC registers are retained without interpreting generator default
size registers as measured receiver dimensions.

The native counter was already frozen at1018 before the native child began
(atboardmonotonic4777.3427s) and stayed frozen throughout. Thus this experiment
also does not prove that the native call's HPD toggle caused the freeze.
Source page flips and the kernel's requested VGA mode remain weaker evidence
than actual input edges. Timing002 earlier observed60Hz native edges, so the
state varies across source starts; no sole root cause is established yet.

The root source worker's normal paths executed twice and restored the desktop.
Its signal/error/expiry paths remain unverified. The attach subclass remains an
operator-only failed experiment, not a supported production CLI feature.

## Read-only build/EDID cross-check and next physical step

The017 build input, receiver IP copy and generated Vivado IP source EDID are
all128bytes with SHA256e716887ace476531df33bbec6ff03e4b6c1148a243a00d3d237f1b77bff1050d.
The host-visible256-byte EDID still differs and contains4K preferred timing.
The dvi2rgb source instantiates the EEPROM with kAddrBits7/kWritablefalse;
that is static source evidence, not bitstream ROM extraction or wire tracing.
No EDID ROM change, new bitstream or source-format waiver was made.

Requested one physical unplug/replug of the PC USB-C-to-HDMI adapter, leaving
the PYNQ powered and the HDMI input cable connected. Software HPD pulse had
not restored native frames, so the next probe distinguishes a fresh adapter/
link state from the current one. This is not a media/cable hardware-failure
verdict. A read-only sysfs watcher records disconnect/reconnect, mode list and
EDID hashes under artifacts/operator/usb-replug-005. At the time of that request it had not observed the
manual action yet; the completed action is recorded below. The root source worker remains idle, and request03 is not
queued. No capture starts merely because the adapter reconnects.


## Physical replug005 and changed board boot

The user replied Done. The watcher recorded disconnected at host00:33:12.628
and connected at00:33:22.631. The new256-byte EDID SHA256 is
1b05659cc35a23dd81455c7e1c4212c75c5611f4b22d74f9172ff5e8c72c80dc.
It prefers1080p, has a zero manufacturer field and a blank display name. This
is neither the017 VGA EDID nor the earlier DGL/4K-derived EDID. Its origin is
not established. The source runner's DGL identity guard remains unchanged;
no request03 was queued and no non-DGL sink was modeset by the test runner.

UART also found a different board boot ID:
1dd70e40-85cc-4c9b-a2e2-03b9814e290f, replacing888441ac-9433-48f9-816a-38b40be71c0e.
Uptime was61.30seconds, the shell was at~ and the old/tmp deployment was gone.
No agent reboot command was sent in this experiment. We asked whether the
operator also reset or removed board power/UART. Until that answer arrives,
this is a combined reboot/replug observation, not a controlled adapter-only
result. There is no recorded UART shutdown/boot trace for the transition.
The FPGA manager state reads unknown; the earlier raw Halted result belongs
to the previous boot and is not a current-boot hardware-state proof.

The captured current dmesg reports a system journal corrupted or uncleanly
shut down, plus a FAT volume not properly unmounted. This does not establish
new-card hardware failure. Root remains rw, ext4 errors_count is0 and the
existing16MiB persistence file still has the expected SHA256341aacac661ccb210720bedaa9ead5d668fe5ea41a73532fc147c71e34040df1.
The board clock reset to2022; use host timestamps and boot ID for this event.

The dedicated Ethernet interface was recreated with ifindex13 instead of12
and its profile was inactive. Reactivated the existing codex-hdmi-m0 profile;
Wi-Fi default remains unchanged. The old HTTP server was bound to stale
scope if12, so the first download failed with connection refused. A new
link-local-only staging server on8766 transferred both archives successfully.
Their SHA256 values and the extracted bit/HWH match the established017/v10
artifacts. This only writes the new/tmp staging directory, not boot media.

Prepared prepare-after-replug-005.py, SHA256
c1563a633d024f72fa72ccb24f5cd96ade0ae81227e1e081d3e28b200d27b9a2.
It checks this exact boot, loads the verified pair, disables the gate, asserts
RS0/Halted1, validates the fixed HPD GPIO and sets HPD high without waiting
for input or allocating capture buffers. It reuses the original loader and
HPD-v2 checks; Python compilation passed, hardware execution is NOT RUN.
It is an operator-only cold-boot preparation, not a production sender change.
The direct script entry calls the original loader, which checks artifacts,
ABI/PYNQ version, Overlay.is_loaded, S2MM-only VDMA and source-health resources
before VideoIn construction. SDK/FPGA programming internals are not fully
traced. Current board sudo requires interactive authentication after reboot.
Do not run the older attach-only helper on this unprepared boot or infer
DMA safety from its previous-boot log. No new capture DMA has been requested.

Next: establish why the boot changed, authenticate the board once for the
fixed preparation, then inspect the resulting EDID before using any remaining
bounded local source-worker slots. The worker's deadline still applies; do
not reuse previous source evidence or weaken the DGL/mode/pixel checks.


## Shared Hub explanation and next guarded probe006

The user confirmed that the PYNQ Micro-B is connected to the same USB-to-HDMI
Hub that was removed. This accounts for the shared connection interruption observed alongside
the board reboot and recreated Ethernet interface; the action cannot isolate an HDMI adapter
reset. Keep the Hub connected. Future HDMI-only interruption should be at
the HDMI cable, with board power/UART continuity checked first. This does not
explain the input failures that preceded the physical replug.

A fresh preflight still finds boot1dd70e40, the staged helper's expected hash,
ext4 errors_count0 and sudo authentication required. Opened one local terminal
with prepare-shared-hub-006.sh: existing board-only authentication wizard,
then immediate guarded fixed-boot receiver load/HPD preparation. It verifies
the helper hash and rejects a running sender before loading; it neither starts
capture DMA nor asks for a host password. Shell syntax passed. The wizard's
library is reused unchanged. Actual privileged preparation is pending.

watch-shared-hub-006.py waits for successful preparation and UART-client exit.
It requires connected DGL EDID, a live worker with time for the bounded run,
and unused request03/output. It stages and hashes the native frontend probe,
checks real board sudo, then requests90s fixed VGA KMS and checks XR24/VGA/
25200kHz readiness before probing. The native call has5s input timeout, parent
MMIO observation25s, and never allocates a capture buffer or starts DMA. Root
source return/VT restoration are collected even when the native probe fails.
The output is artifacts/operator/shared-hub-006, watcher exec session88428.
No unsupported sink fallback or acceptance change was introduced. Compilation
passed; this new coordinator's real preparation/source/probe paths are pending.
If auth is delayed beyond the worker deadline, it stops without queuing a run.

The board power jumper and supply voltage were not measured. The confirmed
fact is the shared Hub wiring and coincident reboot, not an electrical fault
diagnosis or evidence that all earlier input failures had the same cause.
