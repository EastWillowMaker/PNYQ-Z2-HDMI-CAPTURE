#!/usr/bin/env python3
"""Derive a single-mode 128-byte EDID from the pinned PYNQ receiver ROM."""
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from hdmi_capture.modes import CaptureMode, get_mode


def validate_vga_edid(data):
    if len(data) != 128 or sum(data) % 256:
        raise ValueError('Invalid EDID length/checksum')
    if data[:8] != bytes.fromhex('00 ff ff ff ff ff ff 00') or data[18:20] != b'\x01\x04':
        raise ValueError('Expected EDID 1.4 base block')
    if data[126] != 0 or data[35:38] != b'\x20\x00\x00' or data[38:54] != b'\x01\x01' * 8:
        raise ValueError('Only established VGA and no other timing lists allowed')
    d = data[54:72]
    clock = int.from_bytes(d[:2], 'little') * 10000
    hactive, hblank = d[2] | ((d[4] >> 4) << 8), d[3] | ((d[4] & 15) << 8)
    vactive, vblank = d[5] | ((d[7] >> 4) << 8), d[6] | ((d[7] & 15) << 8)
    hs, hw = d[8] | ((d[11] >> 6) << 8), d[9] | (((d[11] >> 4) & 3) << 8)
    vs, vw = (d[10] >> 4) | (((d[11] >> 2) & 3) << 4), (d[10] & 15) | ((d[11] & 3) << 4)
    if (clock, hactive, hblank, vactive, vblank, hs, hw, vs, vw, d[17]) != (
            25200000, 640, 160, 480, 45, 16, 96, 10, 2, 0x18):
        raise ValueError('Expected progressive 640x480 60Hz VGA detailed timing')
    for offset in (72, 90, 108):
        if data[offset:offset + 3] != b'\x00\x00\x00' or data[offset + 3] not in (0xfc, 0xfd, 0x10):
            raise ValueError('Additional timing/extension descriptor forbidden')
    if data[90:108] != bytes.fromhex('00 00 00 fd 00 3b 3d 1f 20 03 01 0a 20 20 20 20 20 20'):
        raise ValueError('Expected VGA range-limits-only descriptor')
    if data[20] != 0xa1 or data[24] != 2:
        raise ValueError('Expected 8-bit DVI RGB-only preferred mode')
    return {'width': hactive, 'height': vactive, 'pixel_clock_hz': clock,
            'fps': clock / ((hactive + hblank) * (vactive + vblank)),
            'extension_count': 0, 'checksum': data[-1]}


def make_vga_edid(source):
    data = bytearray(int(line, 2) for line in source.read_text().split())
    if len(data) != 128 or sum(data) % 256:
        raise ValueError('Pinned source EDID length/checksum changed')
    data[19] = 4  # EDID 1.4 permits range-limits-only (no inferred GTF modes).
    data[20] = 0xa1  # 8-bit digital DVI interface, RGB capture only.
    data[21:23] = b'\x00\x00'  # Capture sink has no physical display size.
    data[24] = 0x02  # EDID 1.4 RGB-only, preferred first detailed timing.
    data[35:38] = b'\x20\x00\x00'  # Only 640x480@60 established timing.
    data[38:54] = b'\x01\x01' * 8  # No additional standard timings.
    data[54:72] = bytes.fromhex('d8 09 80 a0 20 e0 2d 10 10 60 a2 00 00 00 00 00 00 18')
    data[72:90] = b'\x00\x00\x00\xfc\x00' + b'LiteX VGA\n   '
    for offset in (90, 108):
        data[offset:offset + 18] = b'\x00\x00\x00\x10\x00' + bytes(13)
    data[90:108] = bytes.fromhex('00 00 00 fd 00 3b 3d 1f 20 03 01 0a 20 20 20 20 20 20')
    data[126] = 0
    data[127] = (-sum(data[:127])) & 255
    validate_vga_edid(data)
    return bytes(data)


def _detailed_timing(mode: CaptureMode) -> bytes:
    hblank = mode.h_front_porch + mode.h_sync_width + mode.h_back_porch
    vblank = mode.v_front_porch + mode.v_sync_width + mode.v_back_porch
    if mode.pixel_clock_hz % 10_000:
        raise ValueError('EDID detailed timing clock must use 10 kHz units')
    if any(value > 0xfff for value in (mode.width, hblank, mode.height, vblank)):
        raise ValueError('EDID geometry exceeds detailed timing fields')
    hsync_offset = mode.h_front_porch
    hsync_width = mode.h_sync_width
    vsync_offset = mode.v_front_porch
    vsync_width = mode.v_sync_width
    if any(value > 0x3ff for value in
           (hsync_offset, hsync_width, vsync_offset, vsync_width)):
        raise ValueError('EDID sync timing exceeds detailed timing fields')
    flags = 0x18 | (int(mode.h_sync_positive) << 2) | (int(mode.v_sync_positive) << 1)
    clock = mode.pixel_clock_hz // 10_000
    return bytes((
        clock & 0xff, (clock >> 8) & 0xff,
        mode.width & 0xff, hblank & 0xff,
        ((mode.width >> 8) << 4) | (hblank >> 8),
        mode.height & 0xff, vblank & 0xff,
        ((mode.height >> 8) << 4) | (vblank >> 8),
        hsync_offset & 0xff, hsync_width & 0xff,
        ((vsync_offset & 0xf) << 4) | (vsync_width & 0xf),
        (((hsync_offset >> 8) & 3) << 6) |
        (((hsync_width >> 8) & 3) << 4) |
        (((vsync_offset >> 4) & 3) << 2) | ((vsync_width >> 4) & 3),
        0, 0, 0, 0, 0, flags,
    ))


def _range_descriptor(mode: CaptureMode) -> bytes:
    vertical_hz = round(mode.refresh_hz)
    horizontal_khz = mode.pixel_clock_hz / mode.h_total / 1000
    supported_clock = max(mode.supported_pixel_clocks_hz)
    pixel_clock_units = math.ceil(supported_clock / 10_000_000)
    return bytes((0, 0, 0, 0xfd, 0, vertical_hz, vertical_hz,
                  math.floor(horizontal_khz), math.ceil(horizontal_khz),
                  pixel_clock_units, 0x01, 0x0a)) + b' ' * 6


def validate_mode_edid(data: bytes, mode: CaptureMode) -> dict[str, int | float]:
    """Require a valid base block that advertises only the selected timing."""
    if mode.name == 'vga':
        result = validate_vga_edid(data)
        if (result['width'], result['height'], result['pixel_clock_hz']) != (
                mode.width, mode.height, mode.pixel_clock_hz):
            raise ValueError('VGA EDID does not match selected profile')
        return result
    if len(data) != 128 or sum(data) % 256:
        raise ValueError('Invalid EDID length/checksum')
    if data[:8] != bytes.fromhex('00 ff ff ff ff ff ff 00') or data[18:20] != b'\x01\x04':
        raise ValueError('Expected EDID 1.4 base block')
    if data[126] != 0 or data[35:38] != b'\x00\x00\x00' or data[38:54] != b'\x01\x01' * 8:
        raise ValueError('Additional established, standard, or extension timings are forbidden')
    if data[20] != 0xa1 or data[24] != 2:
        raise ValueError('Expected 8-bit DVI RGB-only preferred mode')
    if data[54:72] != _detailed_timing(mode):
        raise ValueError('Detailed timing does not match selected capture profile')
    if data[72:90] != _monitor_name(mode) or data[90:108] != _range_descriptor(mode):
        raise ValueError('EDID monitor descriptors do not match selected profile')
    if data[108:126] != bytes.fromhex('00 00 00 10 00') + bytes(13):
        raise ValueError('Unexpected additional EDID descriptor')
    return {'width': mode.width, 'height': mode.height,
            'pixel_clock_hz': mode.pixel_clock_hz, 'fps': mode.refresh_hz,
            'extension_count': 0, 'checksum': data[-1]}


def _monitor_name(mode: CaptureMode) -> bytes:
    label = b'LiteX VGA' if mode.name == 'vga' else b'HDMI 1080p30'
    return b'\x00\x00\x00\xfc\x00' + (label + b'\n').ljust(13, b' ')


def make_edid(source: Path, mode: CaptureMode) -> bytes:
    """Build an EDID with exactly one advertised progressive detailed timing."""
    if mode.name == 'vga':
        return make_vga_edid(source)
    data = bytearray(int(line, 2) for line in source.read_text().split())
    if len(data) != 128 or sum(data) % 256:
        raise ValueError('Pinned source EDID length/checksum changed')
    data[19] = 4
    data[20] = 0xa1
    data[21:23] = b'\x00\x00'
    data[24] = 0x02
    data[35:38] = b'\x00\x00\x00'
    data[38:54] = b'\x01\x01' * 8
    data[54:72] = _detailed_timing(mode)
    data[72:90] = _monitor_name(mode)
    data[90:108] = _range_descriptor(mode)
    data[108:126] = bytes.fromhex('00 00 00 10 00') + bytes(13)
    data[126] = 0
    data[127] = (-sum(data[:127])) & 0xff
    validate_mode_edid(data, mode)
    return bytes(data)


def self_test_mode(source: Path, mode: CaptureMode) -> dict[str, int | float]:
    good = make_edid(source, mode)
    validate_mode_edid(good, mode)
    for change in ('checksum', 'geometry', 'clock', 'extension', 'extra_timing', 'sync_polarity'):
        bad = bytearray(good)
        if change == 'checksum':
            bad[127] ^= 1
        elif change == 'geometry':
            bad[56] ^= 1
        elif change == 'clock':
            bad[54] ^= 1
        elif change == 'extension':
            bad[126] = 1
        elif change == 'extra_timing':
            bad[35] = 1
        elif change == 'sync_polarity':
            bad[71] ^= 0x04
        if change != 'checksum':
            bad[127] = (-sum(bad[:127])) & 0xff
        try:
            validate_mode_edid(bad, mode)
        except ValueError:
            continue
        raise AssertionError(f'Accepted forbidden EDID: {change}')
    return validate_mode_edid(good, mode)


def self_test(source):
    good = make_vga_edid(source)
    validate_vga_edid(good)
    for change in ('checksum', 'geometry', 'extension', 'highres', 'interlace'):
        bad = bytearray(good)
        if change == 'checksum': bad[127] ^= 1
        if change == 'geometry': bad[56] += 1
        if change == 'extension': bad[126] = 1
        if change == 'highres': bad[36] = 8
        if change == 'interlace': bad[71] |= 0x80
        if change != 'checksum': bad[127] = (-sum(bad[:127])) & 255
        try:
            validate_vga_edid(bad)
        except ValueError:
            continue
        raise AssertionError(f'Accepted forbidden EDID: {change}')
    return validate_vga_edid(good)


if __name__ == '__main__':
    import argparse
    import json
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path)
    p.add_argument('--output', type=Path)
    p.add_argument('--mode', choices=('vga', '1080p30'), default='vga')
    args = p.parse_args()
    mode = get_mode(args.mode)
    print(json.dumps(self_test_mode(args.source, mode)))
    if args.output:
        args.output.write_bytes(make_edid(args.source, mode))
