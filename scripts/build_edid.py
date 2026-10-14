#!/usr/bin/env python3
"""Derive a VGA-only 128-byte EDID from the pinned PYNQ receiver ROM."""
from pathlib import Path


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
    args = p.parse_args()
    print(json.dumps(self_test(args.source)))
    if args.output:
        args.output.write_bytes(make_vga_edid(args.source))
