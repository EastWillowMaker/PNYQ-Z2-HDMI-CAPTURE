# Initial research

Date: 2026-10-15 Asia/Taipei. Evidence level: static inspection unless stated.

## Loaded skills

No Skill invocation tool is exposed. Read local files directly, including the
underlying skills rather than only the wrapper. Local directory has no Git revision;
SHA256 identifies what was read:

| Path under `/home/eastwillow/.agents/skills/` | SHA256 |
| --- | --- |
| grill-with-docs/SKILL.md | 7de372c13488f1ee96cc11cd8907b56b6809cc93eef776eeddd37de6b6cbe3fe |
| grilling/SKILL.md | befdff1e27a1dfe2a294d5871169ac1afe16d983911daa4f32627514a48c1e15 |
| domain-modeling/SKILL.md | 7b925d7b1e341a2eeae33ad68a8a8c0ab889a38ddd22a7598e4c240e5a7556a3 |
| domain-modeling/GLOSSARY-FORMAT.md | 21dcc40cdec8e151a829b98ab1517c1867bc444e3665134a98c6983411996801 |
| domain-modeling/ADR-FORMAT.md | 944c92aa790e8fbdc9199640b170979abb8a34ba8d0fe18c2a01a63bce140ca0 |

Also read codebase-memory/SKILL.md and research/SKILL.md. Grilling and research
explicitly request fact-finding agents; delegated environment and hardware inspection.
No accepted architecture ADR yet: proposed path remains subject to shared understanding.

## Source findings

- [PYNQ-Z2 base overlay, version 3.1](https://pynq.readthedocs.io/en/v3.1/pynq_overlays/pynqz2/pynqz2_base_overlay.html),
  HDMI and Rebuilding sections: Z2 has PL HDMI connected through memory, and board-specific
  build files. This supports a baseline candidate, not proof of local overlay health.
  Its 1080p warning prevents treating 1080p60 as a qualified board specification.
- [PYNQ video documentation](https://pynq.readthedocs.io/en/latest/pynq_libraries/video.html),
  Configuration/Pixel Format sections, accessed 2026-10-15: default is 24-bit BGR;
  RGB channel ordering must be intentional. Latest docs are not a pinned board driver.
- [TUL Reference Manual v1.1, 2019-10-28](https://dpoauwgwqsy2x.cloudfront.net/Download/PYNQ_Z2_User_Manual_v1.1.pdf),
  printed pp6–7,12–16: PHY clock feeds H16 and PHY reset disables it; DDR attaches to
  PS, board-specific configuration matters; Ethernet is PS MIO. Link-loss clock
  behavior is untested. See detailed hardware research for pin crosschecks.
- PYNQ upstream master resolved with `git ls-remote` to
  `d90670c69f7b71ea1a5d23aaa3e0ec713ff5fa9f`. It is a research reference, not a
  selected compatible build dependency or the board's installed version.
- [Existing on-board Ethernet experiment](results/2026-10-14/pynq-z2-ethernet.md):
  independent transport evidence, no HDMI data. Existing SD boot reported filesystem
  errors; no repair/reimage performed. This remains a deployment risk.

Detailed bounded audits: [environment](environment-audit.md),
[board/source feasibility](hardware-research.md). Missing facts there are gates,
not assumptions to replace with generic PS7 or another board's pinout.

## Recommended minimum path (not approved)

M0: HDMI IN → existing Z2 frontend → VDMA → PS DDR → owned RGB888 copy →
single-client TCP sender → PC parser → numpy RGB array/.npy.

M1: insert LiteX-generated complete-frame control and statistics into the capture
stream; reuse verified frontend/VDMA, PS board preset and Linux Ethernet. Vivado
integrates IP, constraints and clocks; LiteX emits participating PL logic; PS owns
buffer lifecycle and sender. No new soft CPU. Integration costs include stream
SOF/EOL semantics, clock/reset crossing, DMA framing and rebuilding old PYNQ IP
under available tools. No build compatibility or license pass is claimed.

Completed frames form the later web/LCD consumer boundary; forwarding remains a
separate consumer with its own future timing/latency acceptance. M0 does not prove
bypass or LiteX functionality. Do not infer DDR-free routing from `tie()`.

## Payload calculation (executed with Python)

`b = width * height * 3; payload_bps = b * delivered_fps * 8`

| Mode | bytes/frame | MiB/frame | Mbps at 1 FPS | Mbps at 60 FPS | DMA write MB/s at 60 FPS |
| --- | ---: | ---: | ---: | ---: | ---: |
| 640×480 | 921600 | 0.87890625 | 7.3728 | 442.368 | 55.296 |
| 1280×720 | 2764800 | 2.63671875 | 22.1184 | 1327.104 | 165.888 |
| 1920×1080 | 6220800 | 5.9326171875 | 49.7664 | 2985.984 | 373.248 |

These are arithmetic, not throughput measurements. 640×480 rows are 1920 bytes
packed, but actual VDMA stride is still to inspect. Continuous 60 Hz capture can
write 55.296 MB/s even when only 1 FPS is sent. At 1 FPS, one full PS copy adds
0.9216 MB/s read plus 0.9216 MB/s write; socket/kernel copies add further traffic.
For full-sized MTU1500 IPv6 TCP segments without options, 1440 payload bytes consume
1538 wire bytes including Ethernet header/FCS/preamble/IFG: ratio 1.0681, excluding
ACKs/options/short segments/application metadata. Actual overhead and CPU remain
unmeasured. A 1 Gb/s link cannot carry 720p60 raw RGB888 payload.
