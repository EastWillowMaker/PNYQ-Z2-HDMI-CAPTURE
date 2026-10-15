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


def require_credit_configuration(hwh):
    """Do not label a legacy GPIO or unsupported VDMA as the credit ABI."""
    expected = {
        '/video/capture_control': {'C_GPIO_WIDTH': '32', 'C_IS_DUAL': '1',
            'C_ALL_OUTPUTS': '1', 'C_ALL_INPUTS_2': '1', 'C_GPIO2_WIDTH': '32'},
        '/video/axi_vdma': {'C_INCLUDE_S2MM': '1', 'C_INCLUDE_MM2S': '0',
            'C_NUM_FSTORES': '4', 'C_ENABLE_DEBUG_INFO_15': '1',
            'C_USE_S2MM_FSYNC': '0'},
    }
    for name in ('capture_credit', 'capture_completion', 'capture_sequence'):
        expected['/video/' + name] = {'C_GPIO_WIDTH': '32', 'C_GPIO2_WIDTH': '32',
            'C_IS_DUAL': '1', 'C_ALL_INPUTS': '1', 'C_ALL_INPUTS_2': '1'}
    for fullname, parameters in expected.items():
        modules = [m for m in hwh.findall('.//MODULE') if m.get('FULLNAME') == fullname]
        if len(modules) != 1:
            raise RuntimeError(f'Expected exactly one credit module {fullname}')
        rows = modules[0].findall('./PARAMETERS/PARAMETER')
        for name, value in parameters.items():
            actual = [row.get('VALUE') for row in rows if row.get('NAME') == name]
            if actual != [value]:
                raise RuntimeError(f'Credit module {fullname} requires {name}={value}')
        if fullname == '/video/capture_control':
            defaults = [row.get('VALUE') for row in rows if row.get('NAME') == 'C_DOUT_DEFAULT']
            try:
                valid_default = len(defaults) == 1 and int(defaults[0], 0) == 0
            except (TypeError, ValueError):
                valid_default = False
            if not valid_default:
                raise RuntimeError('Credit GPIO must reset every control bit to zero')


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
    if gate.get('capture_interface') != 'single_credit_parked_v1':
        raise RuntimeError('This build requires single-credit gateware')
    if gate.get('gate_completion_policy') != 'next_sof_after_selected_output_drain_v1':
        raise RuntimeError('This build requires next-SOF frame-closure proof')
    hwh = ET.parse(args.output / 'capture.hwh').getroot()
    require_vga_receiver(hwh)
    require_credit_configuration(hwh)
    edid = (args.output / 'vga-edid.bin').read_bytes()
    validate_vga_edid(edid)
    rom = args.output / 'rx_ip/dvi2rgb_v1_7/src/720p_edid.data'
    if edid != bytes(int(line, 2) for line in rom.read_text().split()):
        raise RuntimeError('Packaged EDID ROM does not match its manifest')
    result = {
        'schema_version': 1, 'pynq_commit': PIN,
        'capture_enable_reset': 0,
        'capture_control_width': 32,
        'capture_control_reset': 0,
        'capture_interface': 'single_credit_parked_v1',
        'gate_completion_policy': 'next_sof_after_selected_output_drain_v1',
        'vdma_completion_mode': 'parked_frame_count_halt_v1',
        'vdma_frame_counter_enabled': True,
        'vdma_fsync_mode': 'free_run',
        'source_identity_bits': 32,
        'source_identity_policy': 'native_delta_one_per_accepted_sof_with_watchdog',
        'receiver_reset_sync_sha256': sha256(args.output / 'receiver_reset_sync.v'),
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
