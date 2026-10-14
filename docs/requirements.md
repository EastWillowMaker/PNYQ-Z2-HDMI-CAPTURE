# Requirements and decision record

Date: 2026-10-15 (Asia/Taipei). Status: M1 sustained capture, gate, client reconnect and mode restart verified; physical cable test pending.
Normative source: [complete user prompt](../PYNQ_Z2_LiteX_HDMI_Capture_Codex_Prompt.md),
SHA256 `38b149ac12077729ded5e6183f715d06e281df6ea6ba70aa7124c5cb24a744ae`.
The complete source remains applicable; this record indexes it rather than replacing it.

## Confirmed

| ID | Requirement | Source | Implementation / evidence |
| --- | --- | --- | --- |
| C1 | PC Python receives complete real HDMI input frames over Ethernet; first priority | §§1,4 | M1 1,201/1,201 exact distinct frames over 600.506s, [evidence](results/2026-10-15/m1-qualification.md) |
| C2 | PYNQ-Z2 and meaningful LiteX capture logic; no unrelated LED/import substitution | §§1,3 | 17 gateware tests pass; build013 timing/CDC/DRC reviewed; real gate disable/resume verified |
| C3 | Main capture retains RGB 4:4:4; no chroma subsampling or lossy codec | §§1,5 | Implemented and locally tested; physical M0 evidence available |
| C4 | Host array uint8 `(height,width,3)`, R/G/B, three bytes/pixel; explicit internal format conversion | §5 | Installable API/CLI and dtype/shape tests pass |
| C5 | No silent scaling, gamma, range or YCbCr conversion; unknown source range stays unknown | §5 | Source XR24/GLES RGB8; exact ramp comparison passes; metadata retains unknown HDMI range |
| C6 | Single-source complete frames, safe buffer ownership/cache handling; no stale frame passed as new | §5 | Bounded pool tests and M1 600s exact frames pass; actual DMA halt-before-free recorded |
| C7 | Bound buffers and protocol sizes; partial IO, CRC, EOF, timeout, reconnect and mode changes handled | §§5,6 | Bounded parser/socket negatives pass; physical client reconnect and mode fail-stop/restart verified |
| C8 | HDMI cannot be stopped by network backpressure; whole-frame loss policy and separate counters required | §5 | P4 accepted; bounded ready slot and immutable sending frame; real drop counters |
| C9 | Frame IDs/timestamps with actual clock domain and sample point; counts for skips/overrun/invalid/delivered | §§5,6 | Clock/sample metadata implemented; M0 hardware loss unknown; M1 PL snapshot not per-buffer association |
| C10 | Installable library/CLI: connect/read/close, snapshot, capture, stats; raw/.npy plus optional PNG | §6 | Implemented and locally tested; physical M0 evidence available |
| C11 | Separate transport, synthetic, HDMI→DDR and end-to-end measurements; CPU/memory/copies/DDR budget | §7 | Transport/synthetic/HDMI measurements separated; script budget and sustained resource samples recorded |
| C12 | Synthetic patterns, protocol negatives, ownership, RTL adapter/reset/backpressure, API/CLI tests | §8 | 195 software tests plus17 gateware tests pass; physical cable removal pending |
| C13 | Real source, controlled patterns, sustained capture, source reconnect, client reconnect, mode change | §8 | 195 software tests plus17 gateware tests pass; physical cable removal pending |
| C14 | Distinguish static/unit/simulation/synthesis/timing/bitstream/on-board evidence; reproducible versions/IP/constraints/DRC | §§8,9 | Pinned source/HLS build; build013 paired bit/HWH and runtime IRQ parser verified |
| C15 | Later browser preview, active bypass, then LCD C first; no delay to capture | §§1,4 | Deferred M2/M3/M4 |
| C16 | Reuse completed-frame consumers; preview JPEG cannot replace RGB main path; LCD conversion isolated | §4 | Deferred |
| C17 | Preserve dirty work; no SD/boot/global package/network changes without confirmation; authorize disruptive overlay loads | §9 | Observed; temporary overlay/network operations explicitly authorized |
| C18 | No automatic commit/push/PR; no captured images/secrets/private code uploaded | §9 | Observed; temporary overlay/network operations explicitly authorized |

M0 may use existing PYNQ overlay as baseline-only; M1 requires reproducible LiteX
capture integration and real end-to-end validation. M2 browser endpoint location,
M3 buffering/latency/EDID behavior and M4 SPI terminology remain deferred proposals.
The LCD target C is confirmed; interpreting “ISP Driver” as SPI is not confirmed.

## Accepted first-round defaults (2026-10-15)

- P1: First source mode 640×480 progressive approximately 60 Hz, unencrypted
  eight-bit RGB; main representation RGB888. HDCP/audio/CEC/HDR/deep color/interlace
  and full repeater certification excluded from the initial milestone.
- P2: Single client, raw RGB888 over TCP; no UVC device requirement. PS Linux/PYNQ
  uses onboard Ethernet. M0 base overlay; M1 LiteX frame control/statistics in PL,
  reused HDMI frontend and VDMA, board-specific PS preset. No new soft CPU needed.
- P3: M1 >=1 delivered new frame/s for >=10 minutes and >=600 complete frames,
  with corrupt/mixed/invalid frames reported, never silently removed from results.
  M0 first establishes saved true frames and repeatable acquisition; it does not
  satisfy M1 even if it meets the same throughput.
- P4: Prefer freshness when PC is slow: bounded ready queue, drop whole unsent
  frames, never replace the buffer currently sending. Keep sampling/overrun/network
  drop counters distinct. Source sequence counting needs PL support for M1;
  assigning IDs to readframe calls alone cannot prove skipped-source counts.
- P5: Permission granted for temporary base-overlay loading (replaces active PL
  design and may interrupt users), temporary sender and dedicated NIC link-local
  setup with saved/restored configuration. No boot media replacement or global install.

## First-round questions and answers

1. **Capture contract (P1/P3/P4)**: accept 640×480p60 input, RGB888, >=1 FPS
   delivered, M1 ten-minute/600-frame criterion, whole-frame skips under backpressure?
   Recommend yes. Slow clients lose intermediate complete frames rather than accumulating
   unbounded delay; no claim of all 60 input frames delivered. Source full-range RGB
   preferred for controlled patterns; unknown range must be disclosed.
2. **Path and experiment authorization (P2/P5)**: accept PS Linux TCP, M0 baseline
   then M1 LiteX integration; authorize temporary overlay replacement and reversible
   dedicated Ethernet configuration? Recommend yes after ensuring no PL service needs
   preservation. Current NIC has carrier but no IP. This permission is required by
   prompt §9; the old iperf authorization is not reused as overlay authorization.
   If privileged execution needs human elevation, perform it locally on the board
   terminal; never supply a password in chat. Authorization alone does not grant root.
3. **Physical HDMI fixture**: what source and HDMI cable can be connected to HDMI IN now, and can
   it be set to unencrypted RGB 640×480p60 with a changing test pattern? Recommend a
   controllable PC HDMI output. If unavailable, implement offline tests and synthetic
   transport after agreement, but real capture remains BLOCKED, not complete.

User answered Q1 "ok", Q2 "ok"; Q3 source is this PC through a USB-C to HDMI
display adapter, with an already verified HDMI cable. This confirms P1–P5 and
the M0→M1 path; implementation now proceeds. Actual source mode, RGB encoding,
range and physical HDMI IN lock remain measurements, not inferred facts.
Shared understanding: deliver real RGB frames to PC first, then qualify meaningful
LiteX participation; web, bypass and LCD remain later milestones.

## Initial inventory (historical; later measurements supersede it)

- Current HEAD `abd512e`; initial only untracked file is the supplied prompt.
- No repository-local AGENTS.md found (including hidden-file search); user-supplied
  AGENTS instructions and `/home/eastwillow/.codex-coding/RTK.md` were read.
- Existing README explicitly says no HDMI/LiteX implementation. Tracked inventory
  contains documentation and Ethernet evidence, not capture source/build scripts.
- Historical board→host TCP 413.802 Mbps is not an HDMI or lossless qualification.
- Current TUL USB serial interfaces enumerate; dedicated RTL8153 reports 1000 Mbps,
  carrier=1, no IP address. UART read-only commands confirm running board Linux,
  PYNQ 3.0.1 and a base.bit file. HDMI source mode and loaded overlay remain unverified.
- User requests subagent execution, preferably GPT-6.1 Sol medium (2026-10-15).

## Startup integrity attribution (implementation decision, 2026-10-15)

M1 qualification retains malformed startup input counts rather than clearing
counters. A nonzero startup invalid count is attributable to unselected input
only when paired HWH/manifest prove capture reset disabled and the baseline is
sampled while enable remains false with zero selected frames, before first
enable. Startup FIFO over/underflow must remain zero. Every later invalid or FIFO
error change fails; full-pixel/optical-ID requirements remain unchanged.

The original build013/v4 after-enable, non-atomic snapshot lacks that proof and
remains a failed qualification despite exact received pixels. Two gate simulation
cases establish no forwarded pixels for malformed input while disabled. V5's
held-disabled baseline and strict host validation enforce the narrow exception;
see [M1 bring-up](results/2026-10-15/m1-bringup.md). This operational attribution
does not prove a counter snapshot belongs to a particular DDR buffer.

## Incremental commit instruction

The active goal explicitly requests frequent local commits when meaningful
progress is verified, using GPT-6.1 Sol medium subagents where useful. This
supersedes the earlier absence of commit authorization. Push and PR publication
remain unauthorized. The first verified capture milestone is being committed
with its failed attempts and remaining physical-test limitations retained.
