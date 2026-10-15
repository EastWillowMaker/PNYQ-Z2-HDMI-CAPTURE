# Fresh-card HDMI startup failure and revised sequence

The first frontend-only preload failed at `VideoIn.configure` with
`No incoming video signal detected`. Board sudo succeeded. No capture sender
was started. The native frontend waits for receiver lock before returning;
the old operator flow did not start the known-good KMS source until later.
The new-card 600-second capture criterion has not passed at this point.

## Observed failure and competing explanations

The fast host command `tools/configure_hdmi_source.py --connector DP-2` rejects
the current advertised mode list: it contains non-VGA modes. A read-only Mutter
snapshot shows DP-2 enabled at3840x2160@30, while the receiver reports lock0.
Read-only board MMIO reports S2MM CR0x10002 and SR0x10001: RS0 and Halted1.
That distinguishes this incident from an active or stalled capture DMA.

The initial hypotheses were unsupported PC timing, incomplete HPD/output
enablement, and failure of the receiver to lock a supported VGA source.
The active4K timing supports the first. Connected status and a256-byte DGL
EDID establish host detection, but do not prove that the EDID reached Linux
unchanged from the FPGA. Receiver failure at a known-good VGA input remains
unverified until the direct-KMS comparison runs.

The host-visible EDID has SHA256
`77d384bbe465a42f4bf0c444d3585c2145429e9fd10e1874a794a2552fe62daf`;
the built017 EDID is
`e716887ace476531df33bbec6ff03e4b6c1148a243a00d3d237f1b77bff1050d`.
Both have valid block checksums. The host-visible first DTD is3840x2160p30
at297MHz; its extension flag changes from0 to1. The manufacturer/name remain
DGL/LiteX VGA, and VGA timings remain available. Which component changes or
caches the EDID is unresolved. No adapter, cable or FPGA defect is proved.
Raw host EDID and Mutter data are preserved alongside this report.

## Revised sequence and behavior impact

The new one-run helper `prepare-new-card-hpd-v2.py` attaches the already-loaded,
hash-verified017 pair, checks RS0/Halted1, disables the gate, validates the fixed
one-bit output GPIO and asserts HPD. It does not call frontend.configure, wait
for video lock, allocate capture buffers or start DMA. The actual board result
passes with HPD1, lock0, CR0x10002 and SR0x10001. Input mode is explicitly
unverified at this stage. The original failed preload log remains unchanged.

Before: an unsupported4K desktop mode made the preload wait for lock and fail
before the source could switch to VGA. After: a detected but unlocked source
may reach KMS startup while DMA stays stopped. The unchanged C fixture selects
only progressive640x480 with the required clock; the coordinator requires
XR24/640x480/25200kHz readiness. Only then does the unchanged v10 sender reload
the pair, configure the frontend, validate input mode and enable capture. The
strict pixel/accounting qualifier and native DMA shutdown checks remain in use.

The normal locked/unlocked receiver path has board evidence only through HPD
preparation. Active-DMA, wrong-GPIO and wrong-artifact rejection paths in this
one-run helper were not exercised by unsafe hardware mutation. KMS startup,
VGA receiver lock, sustained frames and safe cleanup are still pending. The
public desktop configuration validator remains strict and continues to reject
the mixed-mode EDID; it was not weakened to hide the observed mismatch.

This helper attaches the017 design left by the first preload. It is not a
general cold-boot loader. No bitstream, sender implementation, pixel tolerance,
protocol acceptance or image golden reference was changed. The EDID discrepancy
and unsupported desktop restoration mode remain follow-up risks after the KMS
source exits. FullM1 and physical source interruption/mode-change checks remain
incomplete regardless of this startup repair.

## First direct-KMS attempt also failed to deliver frames

KMS became ready atXR24/640x480/25200kHz and continued page flips. The board
sender reloaded017, then exited1 after the native frontend's60-second input
wait. Full logs show configure failure, not a stalled FPGA download. The
coordinator did not reach smoke or qualification. Its shutdown_safe remains
null and full_m1_qualification remains false; the original result is preserved.
Its collection also failed when requesting the resource log, which did not
exist because sender readiness failed. This is a collection limitation.

The root supervisor captured before/after dmesg, ext4 errors_count0 and the
unchanged16MiB file hash. No old I/O failures appear in that evidence. Later
read-only MMIO establishes RS0/Halted1, gate disabled, selected0, completed0
and no advancing native VSYNC counter. This is separate evidence for current
hardware state, not a retroactive successful sender cleanup report. The
startup failed before the source allocated its capture pool or armed DMA.

The receiver clock-lock GPIO later reads1, but no native frames arrive. A
one-second HPD-low/high probe, guarded by Halted/RS0 and selected0 checks, did
not restore frame counters during eight subsequent one-second observations.
FCLK0/1/2 read100/142.857143/200MHz and SLCR FPGA reset0, matching the intended
clock setup. VTC control and detector status remain0 following failed init;
no valid640x480 input mode has been measured by PYNQ. KMS page flips alone do
not prove electrical VGA timings at the receiver. GPU scaling or bridge mode
selection remains to be checked. No new bitstream or pixel-check change was
made during these probes.
