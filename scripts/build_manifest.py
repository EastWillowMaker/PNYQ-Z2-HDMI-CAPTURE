#!/usr/bin/env python3
"""Write an identity manifest after successful implementation/timing checks."""
import argparse
import hashlib
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path

from build_capture import PIN, ROOT
from build_edid import validate_vga_edid


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_vga_receiver(hwh):
    receivers = [m for m in hwh.findall('.//MODULE')
                 if m.attrib.get('FULLNAME') == '/video/hdmi_in/frontend/dvi2rgb_0']
    if len(receivers) != 1:
        raise RuntimeError('Expected exactly one HDMI receiver in HWH')
    ranges = [p.attrib.get('VALUE')
              for p in receivers[0].findall('./PARAMETERS/PARAMETER')
              if p.attrib.get('NAME') == 'kClkRange']
    # Unrelated optional HWH parameters may omit VALUE. The required clock
    # range must occur exactly once and carry the target value.
    if ranges != ['5']:
        raise RuntimeError('Receiver clock range is not configured for VGA pixel clocks')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output', type=Path)
    p.add_argument('gateware', type=Path)
    p.add_argument('tool_version')
    p.add_argument('setup_slack_ns', type=float)
    p.add_argument('hold_slack_ns', type=float)
    args = p.parse_args()
    if any(not math.isfinite(value) or value < 0 for value in
           (args.setup_slack_ns, args.hold_slack_ns)):
        p.error('Setup and hold slack must be finite and non-negative')
    gate = json.loads(args.gateware.with_suffix('.json').read_text())
    if sha256(args.gateware) != gate['rtl_sha256']:
        raise RuntimeError('Gateware provenance hash mismatch')
    if (gate['width'], gate['height'], gate['clock_hz']) != (640, 480, 142857132):
        raise RuntimeError('This integration requires 640x480 at 142857132 Hz')
    hwh = ET.parse(args.output / 'capture.hwh').getroot()
    require_vga_receiver(hwh)
    edid = (args.output / 'vga-edid.bin').read_bytes()
    validate_vga_edid(edid)
    rom = args.output / 'rx_ip/dvi2rgb_v1_7/src/720p_edid.data'
    if edid != bytes(int(line, 2) for line in rom.read_text().split()):
        raise RuntimeError('Packaged EDID ROM does not match its manifest')
    result = {
        'schema_version': 1, 'pynq_commit': PIN,
        'capture_enable_reset': 0,
        'source_health_sha256': sha256(args.output / 'source_health.v'),
        'capture_lock_sync_sha256': sha256(args.output / 'capture_lock_sync.v'),
        'source_health_counters_lifetime': 'fpga_load',
        'source_health_overruns_unit': 'overflow_episodes',
        'receiver_source_reset_policy': 'shared_per_clock',
        'gateware_sha256': sha256(args.gateware),
        'bitstream_sha256': sha256(args.output / 'capture.bit'),
        'hwh_sha256': sha256(args.output / 'capture.hwh'),
        'geometry': [gate['width'], gate['height']],
        'clock_hz': gate['clock_hz'], 'pixel_clock_hz': 25200000,
        'supported_pixel_clocks_hz': [25175000, 25200000],
        'edid_sha256': sha256(args.output / 'vga-edid.bin'),
        'receiver_k_clk_range': 5,
        'receiver_sync_base_sha256': sha256(args.output / 'rx_ip/dvi2rgb_v1_7/src/SyncBase.vhd'),
        'receiver_component_sha256': sha256(args.output / 'rx_ip/dvi2rgb_v1_7/component.xml'), 'tool_version': args.tool_version,
        'setup_slack_ns': args.setup_slack_ns, 'hold_slack_ns': args.hold_slack_ns,
    }
    with (args.output / 'build-manifest.json').open('x') as f:
        json.dump(result, f, indent=2)
        f.write('\n')


if __name__ == '__main__':
    main()
