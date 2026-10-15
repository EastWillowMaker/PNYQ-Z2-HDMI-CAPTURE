# Capture performance budgets and evidence

The script [tools/capture_budget.py](../tools/capture_budget.py) generates explicit
RGB, TCP, memory-touch, and storage budgets. These are calculations, not measured
DDR bandwidth, CPU utilization, packet traces, or maximum-throughput claims.

```bash
python tools/capture_budget.py --width 640 --height 480 \
  --input-fps 60 --sampled-fps 2 --delivered-fps 2 \
  --ip-version 6 --mtu 1500 --tcp-options-bytes 12 --metadata-bytes 2048 \
  --duration 600 --output /tmp/capture-budget.json
```

`--output` refuses to overwrite an existing result. To measure the encoded
metadata length for a specific saved frame, replace `--metadata-bytes` with
`--metadata-json path/to/frame-metadata.json`; a CLI report containing
`last_metadata` is also accepted. This measures that JSON encoding's size only,
not its transfer performance. Counter/time/ID digit lengths can vary by frame.

The saved [default report](results/2026-10-15/capture-budget-640x480-2fps-v2.json)
includes all assumptions, excluded costs, null measurement fields, and hashes of
the inspected source. The earlier budget record is preserved; v2 explicitly
distinguishes DMA allocation stride from active-pixel write size.

| Quantity at nominal 640x480, input 60 FPS, delivered 2 FPS | Value |
| --- | ---: |
| Packed RGB bytes/frame | 921600 |
| Packed row / DMA stride | 1920 / 1920 bytes |
| RGB payload | 14.7456 Mbps = 1.8432 MB/s = 1.7578125 MiB/s |
| Input active RGB data / assumed continuous VDMA writes | 442.368 Mbps = 55.296 MB/s = 52.734375 MiB/s |
| TCP application data including 20-byte prefix + assumed 2048-byte metadata | 14.778688 Mbps |
| Estimated Ethernet physical occupancy in data direction | 15.917408 Mbps |
| Three explicit board pixel copies, combined read+write touches | 11.0592 MB/s |
| Sender CRC payload scan | 1.8432 MB/s |
| Native writes + explicit copies + CRC logical sum | 68.1984 MB/s = 65.0390625 MiB/s |
| Five native buffers | 4608000 bytes |
| Ready+sending RGB slots | 1843200 bytes |
| Raw RGB storage for 600 seconds at 2 FPS | 1105920000 bytes |

MB/s uses 10^6 bytes; MiB/s uses 2^20 bytes; Mbps uses 10^6 bits. Link speed is not
application goodput. The table's logical sum is not actual DDR traffic: copies and
CRC can read cache-resident bytes, cache invalidation can have additional cost,
and AXI/cache/kernel behavior has not been measured by this calculator.

## Packet estimate assumptions

The default assumes IPv6 header 40 bytes, TCP header 20 bytes plus 12 bytes of
negotiated options, Ethernet MTU 1500, no VLAN, and each application frame segmented
separately. The assumed TCP data size is 1428 bytes, giving 647 segments per frame.
Per-segment overhead is 110 byte-times: IP+TCP 72, Ethernet header 14, FCS 4,
preamble/SFD 8, and interpacket gap 12. The result is 994838 byte-times of physical occupancy per frame,
7.9468% above RGB payload. Last-segment minimum-frame padding is accounted for.

ACKs, handshake, retransmissions, other control traffic, IPv6 extensions, and PHY
coding overhead are excluded. Actual options/MSS, segmentation offload and TCP
coalescing are unmeasured. These inputs are explicit assumptions, not facts about
the running connection. `--ip-version`, `--mtu`, and `--tcp-options-bytes` permit
separate budgets for other configurations.

## DMA and copy accounting

The current source configures 24-bit DMA pixels and PYNQ's packed row stride.
[PYNQ 3.0.1 VideoMode](https://github.com/Xilinx/PYNQ/blob/v3.0.1/pynq/lib/video/common.py)
defaults stride to width×bytes/pixel; the
[S2MM driver](https://github.com/Xilinx/PYNQ/blob/v3.0.1/pynq/lib/video/dma.py)
programs active row bytes and stride separately in `_writemode()`. The
[hardware configuration](../hardware/capture.tcl) uses 32-bit S2MM memory data,
four frame stores, and PS AXI HP0. A 1920-byte row aligns to both a 4-byte beat and
the report's selected 64-byte boundary. This is arithmetic alignment, not a
measured cache-line, allocator, or bus requirement.

`--dma-stride` separates reserved address space from active pixels; VDMA does not
write skipped row-padding bytes merely because stride is larger. Nonpacked stride
is hypothetical for this adapter: pinned PYNQ allocates `VideoMode.shape`, which
does not automatically reserve height×padded-stride storage. The script does not
authorize such a runtime mode. Current hardware sources enforce 640x480; budgets
for other dimensions do not establish their hardware support.

With capture enabled, the gate passes complete input frames to VDMA continuously.
Software sampling at 2 FPS does not reduce a nominal 60 FPS DMA write stream. The
board acquisition loop keeps returning/recycling complete buffers even when TCP
is slow. Cache invalidation still occurs on skipped acquisitions; its cost is
unknown. Use separate input, sampled and delivered rates: sampled frames can be
copied then dropped from the ready slot without reaching the host.

Inspected copy paths are:

1. [Sample.copy_rgb](../src/hdmi_capture/sources.py), line27: a plain ndarray view
   reverses BGR channels, then `np.array(...,copy=True)` reads native pixels and
   writes the owned RGB array. One full pixel copy per sampled frame.
2. [encode_frame](../src/hdmi_capture/protocol.py), lines124–125:
   `rgb.tobytes()` copies pixels once, CRC32 scans that payload, and concatenating
   it into the protocol envelope copies it again. Two full pixel copies and one
   scan per encoded frame. The budget assumes encoded FPS equals delivered FPS;
   failed/partial sends can make encoded FPS higher.
3. [Sender._serve_client](../src/hdmi_capture/sender.py), lines132–134:
   `writer.write()`/`drain()` can add asyncio buffering copies. The report shows
   a 0–2 additional-copy scenario, not a proven bound for every Python transport.
   Ordinary socket user→kernel copying and GEM payload reads are separate explicit
   assumptions. Packet headers, descriptor accesses and cache maintenance are
   additional unmeasured work.
4. [read_frame](../src/hdmi_capture/protocol.py), lines145–151 and197–201:
   a zero-initialized bytearray receives payload through `recv_into()`, CRC scans
   it, and `np.frombuffer(...).reshape()` creates a view without another full pixel
   copy. The report separates logical zero initialization, assumed kernel→user
   copy, and CRC reads. It does not claim a kernel or DDR zero-copy receive path.
5. [CLI save](../src/hdmi_capture/cli.py), line65, calls `np.save()` and separately
   writes metadata; optional PNG encoding has independent CPU/copy/storage cost.
   The storage budget includes RGB payload only, excluding NPY headers, metadata,
   filesystem overhead and PNG. Additional save-path copies were not profiled.

One read+write copy is two logical payload traversals. At 2 FPS, each full copy
therefore touches 3.6864 MB/s. The native five-buffer pool, two logical RGB slots,
and one encoded wire allocation are storage components, not total RSS or a peak
heap bound. Serialization temporaries, Python/PYNQ libraries, asyncio/kernel
queues, saved frames retained by applications, and optional consumers add memory.

## Measurement separation

| Path | Available evidence | Scope |
| --- | --- | --- |
| PS↔PC TCP | [Historical Ethernet report](results/2026-10-14/pynq-z2-ethernet.md): board→host 413.802 Mbps | PS transport; errors/retransmissions disclosed, not HDMI qualification |
| Board synthetic RGB→PC | [Synthetic benchmark](results/2026-10-15/synthetic-board-benchmark.json) and [pixel report](results/2026-10-15/synthetic-board-pixels.json) | Transport/parser correctness using generated pixels |
| HDMI→DDR | [M0 pool log](results/2026-10-15/m0-pool-final-status.log): 10352 returned acquisitions over 180 seconds | Driver read throughput; hardware source skips and exact source sequence unknown |
| Real M0 HDMI→PC | [30-frame host report](results/2026-10-15/m0-gl-capture.json): 2.05546 FPS, 15.15453 Mbps; [30 exact frames](results/2026-10-15/m0-gl-pixels-30.json) | Short baseline-only run; later startup/panic/fixture risks retained in [bring-up](results/2026-10-15/m0-bringup.md) |
| Formal LiteX sustained path | Final dated qualification report required | This budget does not certify a running or unfinished hardware experiment |

The calculator leaves CPU utilization, RSS, actual DDR bandwidth and segmentation
measurements null. Add board/host process CPU and memory evidence from the actual
qualification window separately, with observation intervals and units. Do not
replace those measurements with the byte arithmetic above, and do not treat a
short M0 measurement as the ten-minute LiteX acceptance result.

Local validation executed the default generator, a 1280x720 IPv4/no-TCP-options
budget with sampled 5 FPS/delivered 2 FPS, and invalid nonfinite-rate rejection. No
hardware access, live sender change, global installation, or commit was performed
for this budget task.

## Measured build013 sender v5

The real600second capture run delivered1,201 exact distinct frames at1.999981FPS
and14.745458Mbps RGBpayload. In120resource samples bounded by the board-side
first/last frame timestamps, CPU averaged39.296%of onecore (36.419–41.456%);
RSS ranged78,475,264–81,240,064bytes. Sampling is not instantaneous peak
measurement, and CPU averaging can overlap the window boundary. Actual DDR bus
bandwidth and packet-level Ethernet occupancy were not instrumented.
See [resource summary](results/2026-10-15/m1-013-v5-resource-summary.json) and
[qualification](results/2026-10-15/m1-qualification.md). The model's null measured
fields remain deliberately unchanged: its estimates are not measured bus data.

## Single-credit budget (not yet measured)

`tools/capture_budget.py --dma-fps 2 --sampled-fps 2 --delivered-fps 2`
models selection before DMA while native input remains 60 Hz. The explicit DMA
rate defaults to input rate, preserving the legacy build013 calculation. Rates
must satisfy delivered <= sampled <= DMA <= native input. At the proposed rate,
DMA payload writes are 1.8432 MB/s and logical writes/copies/CRC total 14.7456 MB/s;
neither value is measured DDR traffic. A selected frame is always written whole.
The retained five-buffer storage model is labelled legacy; the new credit reader
owns one native buffer. CPU, RSS, exact metadata size and effective rates require
new physical measurements. Existing build013 measurements do not qualify it.
