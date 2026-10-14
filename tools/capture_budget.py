#!/usr/bin/env python3
"""Generate explicit RGB/TCP/memory budgets; no hardware measurements implied."""

import argparse
import hashlib
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def rates(bytes_per_second):
    return dict(bytes_per_second=bytes_per_second,
                Mbps=bytes_per_second * 8 / 1_000_000,
                MB_per_second=bytes_per_second / 1_000_000,
                MiB_per_second=bytes_per_second / 1_048_576)


def finite_positive(value):
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise argparse.ArgumentTypeError("Rate/duration must be finite and positive")
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--input-fps", type=finite_positive, default=60)
    parser.add_argument("--delivered-fps", type=finite_positive, default=2)
    parser.add_argument("--sampled-fps", type=finite_positive,
                        help="RGB copy rate; defaults to delivered FPS, may be higher under drops")
    parser.add_argument("--dma-stride", type=int,
                        help="Bytes per native DMA row; default is PYNQ's packed width*3")
    parser.add_argument("--alignment", type=int, default=64,
                        help="Alignment boundary to report, not an observed DMA requirement")
    parser.add_argument("--ip-version", type=int, choices=(4, 6), default=6)
    parser.add_argument("--mtu", type=int, default=1500)
    parser.add_argument("--tcp-options-bytes", type=int, default=12,
                        help="Assumed negotiated TCP option bytes; not measured")
    metadata = parser.add_mutually_exclusive_group()
    metadata.add_argument("--metadata-bytes", type=int, default=2048,
                          help="Assumed encoded JSON header bytes per frame")
    metadata.add_argument("--metadata-json", type=Path,
                          help="Actual metadata object, or a CLI report with last_metadata")
    parser.add_argument("--duration", type=finite_positive, default=600)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if not 1 <= args.width <= 1920 or not 1 <= args.height <= 1080:
        parser.error("Dimensions must fit the protocol's1920x1080 bounds")
    sampled_fps = args.delivered_fps if args.sampled_fps is None else args.sampled_fps
    if not args.delivered_fps <= sampled_fps <= args.input_fps:
        parser.error("Nominal rates must satisfy delivered <= sampled <= input")
    if args.alignment <= 0:
        parser.error("alignment must be positive")
    if not 0 <= args.tcp_options_bytes <= 40 or args.tcp_options_bytes % 4:
        parser.error("TCP options must be0..40 bytes in multiples of4")
    header_bytes = args.metadata_bytes
    metadata_source = "assumed"
    if args.metadata_json is not None:
        record = json.loads(args.metadata_json.read_text())
        if not isinstance(record, dict):
            parser.error("Metadata JSON must be an object")
        record = record.get("last_metadata", record)
        if not isinstance(record, dict):
            parser.error("last_metadata must be an object")
        header_bytes = len(json.dumps(record, ensure_ascii=True, allow_nan=False,
                                     separators=(",", ":")).encode("ascii"))
        metadata_source = str(args.metadata_json)
    if not 1 <= header_bytes <= 8192:
        parser.error("Encoded metadata length must be1..8192 bytes")
    row_bytes = args.width * 3
    dma_stride = row_bytes if args.dma_stride is None else args.dma_stride
    if dma_stride < row_bytes:
        parser.error("DMA stride cannot be smaller than the pixel row")
    frame_bytes = row_bytes * args.height
    dma_frame_bytes = dma_stride * args.height
    # Current protocol PREFIX is >4sB3xIII, exactly20 bytes.
    application_frame_bytes = frame_bytes + 20 + header_bytes
    ip_header_bytes = 40 if args.ip_version == 6 else 20
    tcp_header_bytes = 20 + args.tcp_options_bytes
    mss = args.mtu - ip_header_bytes - tcp_header_bytes
    if mss <= 0 or args.mtu > 65535:
        parser.error("MTU must exceed assumed IP/TCP headers and be <=65535")
    segments = math.ceil(application_frame_bytes / mss)
    last_payload = application_frame_bytes - (segments - 1) * mss
    # Ethernet header14 + FCS4 + preamble/SFD8 + interpacket gap12.
    physical_overhead = ip_header_bytes + tcp_header_bytes + 38
    padding = max(0, 64 - (14 + ip_header_bytes + tcp_header_bytes + last_payload + 4))
    physical_frame_bytes = application_frame_bytes + segments * physical_overhead + padding
    selected_bytes_per_second = frame_bytes * sampled_fps
    transmitted_bytes_per_second = frame_bytes * args.delivered_fps
    app_bytes_per_second = application_frame_bytes * args.delivered_fps
    copies = [
        dict(name="owned_DMA_BGR_to_RGB", full_payload_copies=1,
             rate_fps=sampled_fps, read_write_traffic=rates(2 * selected_bytes_per_second)),
        dict(name="RGB_to_protocol_payload_bytes", full_payload_copies=1,
             rate_fps=args.delivered_fps, read_write_traffic=rates(2 * transmitted_bytes_per_second)),
        dict(name="payload_to_protocol_envelope", full_payload_copies=1,
             rate_fps=args.delivered_fps, read_write_traffic=rates(2 * transmitted_bytes_per_second)),
    ]
    board_copy_traffic = 2 * selected_bytes_per_second + 4 * transmitted_bytes_per_second
    # VDMA HSIZE writes active pixels; STRIDE advances rows without writing padding.
    dma_write_traffic = frame_bytes * args.input_fps
    crc_read_traffic = transmitted_bytes_per_second
    sources = {}
    for name in ("src/hdmi_capture/sources.py", "src/hdmi_capture/sender.py",
                 "src/hdmi_capture/protocol.py", "src/hdmi_capture/cli.py", "hardware/capture.tcl"):
        sources[name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    report = dict(
        evidence_type="calculated_budget_not_measured_bandwidth",
        nominal_inputs=dict(width=args.width, height=args.height, input_fps=args.input_fps,
                            sampled_fps=sampled_fps, delivered_fps=args.delivered_fps,
                            duration_seconds=args.duration),
        frame=dict(bytes_per_pixel=3, bytes_per_frame=frame_bytes,
                   wire_row_bytes=row_bytes, dma_stride_bytes=dma_stride,
                   dma_storage_bytes_per_frame=dma_frame_bytes,
                   dma_padding_bytes_per_frame=dma_frame_bytes - frame_bytes,
                   reported_alignment_bytes=args.alignment,
                   stride_aligned=(dma_stride % args.alignment == 0),
                   suggested_aligned_stride=math.ceil(row_bytes / args.alignment) * args.alignment,
                   current_AXI_memory_beat_bytes=4,
                   stride_aligned_to_current_AXI_beat=(dma_stride % 4 == 0)),
        payload=rates(transmitted_bytes_per_second),
        input_RGB_data_rate=rates(frame_bytes * args.input_fps),
        tcp_data_direction_estimate=dict(
            ip_version=args.ip_version, mtu=args.mtu, tcp_options_bytes=args.tcp_options_bytes,
            assumed_mss_bytes=mss, protocol_prefix_bytes=20, metadata_bytes=header_bytes,
            metadata_length_source=metadata_source, application_bytes_per_frame=application_frame_bytes,
            segments_per_frame=segments, per_segment_physical_overhead_bytes=physical_overhead,
            last_segment_ethernet_padding_bytes=padding,
            physical_bytes_per_frame=physical_frame_bytes,
            physical_overhead_over_RGB_percent=(physical_frame_bytes / frame_bytes - 1) * 100,
            application_stream_rate=rates(app_bytes_per_second),
            estimated_physical_rate=rates(physical_frame_bytes * args.delivered_fps),
            excluded=["ACKs", "TCP handshake", "retransmissions", "VLAN tags", "IPv6 extensions",
                      "PHY coding overhead", "control traffic"],
            segmentation_assumption="each application frame segmented separately; offloads/coalescing unmeasured"),
        board_memory_logical_budget=dict(
            dma_write_passes_per_input_frame=1, dma_write_payload_bytes_per_input_frame=frame_bytes,
            native_dma_writes=rates(dma_write_traffic),
            explicit_copy_passes=copies,
            explicit_copy_read_write_total=rates(board_copy_traffic),
            sender_CRC_payload_scan=rates(crc_read_traffic),
            native_writes_plus_explicit_copies_plus_CRC=rates(
                dma_write_traffic + board_copy_traffic + crc_read_traffic),
            optional_asyncio_buffering_extra_copy_traffic_range=dict(
                minimum=rates(0), maximum_assuming_two_extra_copies=rates(4 * app_bytes_per_second)),
            ordinary_socket_user_to_kernel_one_copy_assumption=rates(2 * app_bytes_per_second),
            GEM_DMA_payload_read_floor_assumption=rates(app_bytes_per_second),
            warning="Logical memory touches; cache residency/maintenance, AXI bursts and kernel paths unmeasured. Not actual DDR bus bandwidth."),
        host_memory_logical_budget=dict(
            parser_bytearray_zero_initialization=rates(transmitted_bytes_per_second),
            ordinary_socket_kernel_to_user_one_copy_assumption=rates(2 * transmitted_bytes_per_second),
            parser_CRC_payload_scan=rates(transmitted_bytes_per_second),
            ndarray_full_payload_copies=0,
            optional_save_payload_read_floor=rates(transmitted_bytes_per_second),
            raw_RGB_storage_bytes_for_duration=transmitted_bytes_per_second * args.duration,
            storage_excluded=["NPY headers", "metadata files", "filesystem overhead", "optional PNG"]),
        known_storage=dict(native_pool_buffers=5, native_pool_bytes=5 * dma_frame_bytes,
                           logical_ready_plus_sending_RGB_slots=2, RGB_slot_bytes=2 * frame_bytes,
                           one_encoded_wire_bytes=application_frame_bytes,
                           warning="Not process RSS; temporary serialization, asyncio/kernel buffers and runtime allocations add memory."),
        measurements=dict(board_CPU_percent=None, host_CPU_percent=None, board_RSS_bytes=None,
                          host_RSS_bytes=None, actual_DDR_bandwidth_bytes_per_second=None,
                          actual_packet_segmentation=None),
        source_sha256=sources,
        limitations=["Current hardware adapters enforce640x480; other dimensions are budget exploration only.",
                     "Nonpacked DMA stride is hypothetical: pinned PYNQ allocation uses VideoMode.shape without automatically reserving row padding.",
                     "DMA input-rate writes assume capture selection remains enabled and all input frames reach VDMA.",
                     "Sampled rate may exceed delivered rate under whole-frame drops.",
                     "Skipped PYNQ acquisitions still invalidate caches; maintenance cost is not measured.",
                     "CRC and copy touches can hit CPU caches; do not call the aggregate measured DDR throughput.",
                     "Saving/compression and application-retained frames can add copies, storage and memory."],
    )
    encoded = json.dumps(report, indent=2) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        # Preserve earlier measurement/budget records; choose a fresh output path.
        with args.output.open("x") as output:
            output.write(encoded)
    else:
        print(encoded, end="")


if __name__ == "__main__":
    main()
