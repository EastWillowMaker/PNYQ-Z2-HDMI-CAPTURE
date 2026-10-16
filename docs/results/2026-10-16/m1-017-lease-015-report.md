# Held-credit hardware observation, 2026-10-16

Lease015 passed on the real PYNQ-Z2 HDMI path with the fresh017 production
bit/HWH pair. The tracked `tools/check_credit_lease.py` CLI acquired sample A,
rejected another read while A was leased, observed A remaining unchanged while
native input advanced, ACKed A, and acquired a different exact sample B.
The checker exited 0 with `passed:true` and `dma_shutdown_safe:true`. The host
controller also passed its post-halt, storage and source-restoration checks.
This result covers held-buffer ownership; it does not complete M1 or its
600-second qualification.

Read the [checker JSONL](m1-017-lease-015.jsonl) first for the observation
sequence, then the [controller result](m1-017-lease-015-controller.json) for
cleanup/storage checks and the [prepared receipt](m1-017-lease-015-prepared.json)
for loaded-image identity. The board boot ID was
`1dd70e40-85cc-4c9b-a2e2-03b9814e290f`; checker PID was 11485. Normal production
preparation used the existing same-boot receipt, without `--after-reset`,
after prepared014 had safely finished. Preparation preceded the new KMS run;
the host required two fresh completed KMS presentations before the checker.

The bounded PC source request used duration 60 seconds and starting optical
frame ID 1700000. Readiness reported XR24, 640×480, 25200 kHz and completed flips
1700001 and 1700002. Source 02 exited 0 and restored its original VT. The saved
[source presentations](m1-017-lease-015-source-source.jsonl),
[child exit](m1-017-lease-015-source-child-result.json) and
[VT restoration](m1-017-lease-015-source-restore.json) accompany this report.
Readiness is also saved in
`artifacts/operator/lease-015/source-readiness.json`.

Six observations of A covered the initial snapshot, the rejected leased read
and four dwell snapshots. Snapshot begin times below are relative to A's first
snapshot, on the board monotonic clock.

| Observation | Begin offset (seconds) | Native edge counter |
| --- | ---: | ---: |
| Initial A | 0.000000000 | 325 |
| After leased-read rejection | 0.592274448 | 360 |
| Hold 0 | 0.942976583 | 381 |
| Hold 1 | 1.293310718 | 402 |
| Hold 2 | 1.643826625 | 423 |
| Hold 3 | 1.994213886 | 444 |

The configured dwell was 1 second, divided into four sleeps. The recorded
`hold_begin_ns` to A-release observation interval was 1.402009308 seconds;
register reads, cache invalidation, hashing and Python work added overhead.
The first A snapshot began 2.094037424 seconds before the release observation.
The 119 native edges are the difference325→444 between the initial and last
held snapshots, including the rejection/pattern-verification work before the
configured dwell. They are not a count over exactly 1 second.

Across all six observations, A kept coherent busy/DONE identity native 324,
SOF 323, completion 1 and selected-frame count 1. Its raw BGR and converted RGB
hashes stayed constant. Raw DMA registers also stayed identical: control
`0x15010`, status `0x11001`, store 0 parked, geometry 480/1920/1920 and all four
store addresses 378535936, matching the owned buffer. RS and reset were clear,
HALTED/frame IRQ were set and DMA error bits were clear. The capture gate
remained enabled. Invalid-frame count stayed at its disabled-startup baseline 1;
frontend overflow and underflow episode counts stayed 0. The extra `read()`
returned the explicit previous-lease rejection while the checker guarded DMA
arm against writes.

Both analytic RGB verifications matched every byte: 480 valid optical marker
rows, no mixed IDs and zero mismatched pixels/bytes in either frame.

| Sample | Optical pattern ID | Selected native ID | Selected SOF ID | Completion |
| --- | ---: | ---: | ---: | ---: |
| A | 1700070 | 324 | 323 | 1 |
| B, after A ACK | 1700078 | 451 | 450 | 2 |

A's ACK cleared busy/DONE. B advanced native and SOF IDs by 127 together and
completion by 1; both raw and RGB hashes differed from A. B was then ACKed.
Optical IDs and hardware native/SOF IDs are separate domains here. This test
checks their respective progression and exact pixels, but establishes no
independent mapping between a specific optical ID and a native edge.
`physical_source_sequence_verified` correctly remains false.

Cooperative close reported safe DMA shutdown. Post-close raw readback retained
control `0x15010` and status `0x11001`, with capture command 0: disabled capture,
stopped/reset-clear DMA and no DMA error bits. Ext4 reported 0 errors. The
existing 16 MiB storage-check file retained SHA256
`341aacac661ccb210720bedaa9ead5d668fe5ea41a73532fc147c71e34040df1`.
Saved [before](m1-017-lease-015-before-dmesg.log) and
[after](m1-017-lease-015-after-dmesg.log) kernel logs showed no additional
`Unhandled fault: external abort` occurrence.

The checker UART log retained the PYNQ `UioController.__del__` diagnostic:
`RuntimeError: There is no current event loop in thread 'MainThread'.`
It appeared at process teardown before the terminal exit 0 marker; the final
checker result and independent raw-halt readback still passed. This inherited
PYNQ diagnostic remains unresolved; this run does not establish its cause.
Local evidence is `artifacts/operator/lease-015/lease-uart-06.log`.

The checker recorded the following SHA256 provenance. These identify the
executed image, runtime and preparation ledger rather than a hardware sequence
mapping.

| File | SHA256 |
| --- | --- |
| `capture.bit` | `ae3a65d77b1662fedef9ffbc62dd9484cdd8a155af136596da3e6b695fb6846e` |
| `capture.hwh` | `3bfbbf124960ec932a4a53bb4fcb4a5969b89b9a96d6329143bdfc8442eef9a6` |
| `build-manifest.json` | `4dc7867f34b7bfdbf782c9cde078669b5fb2d2c1ec1930187f6f646592541227` |
| `prepared.json` | `d7845eb15072e8feff06a2dfacbeebe59f973d832c4bf31e4d4a479a9efe9eed` |
| `tools/check_credit_lease.py` | `6428bd94575551746150b208efd42f5c481350582a317e2e31d7f37ba7630ba9` |
| `src/hdmi_capture/sources.py` | `90798eb897756d199d4b9967e4bb2f405837e3f2f3805f04fd0ba4cb379e1727` |

This report was checked against saved hardware evidence. No hardware command
or additional test was run while writing it. The run does not cover HDMI loss,
missing-clock startup, forced termination, unsafe-DMA recovery, every supported
configuration, long-duration resource behavior or independent optical/native
association. Sequential counter snapshots and six stable buffer hashes provide
bounded observations; they do not prove every instant of the interval.
