#!/usr/bin/env python3
"""Write an identity manifest after successful implementation/timing checks."""
import argparse
import hashlib
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path

from build_capture import PIN, ROOT
from build_edid import validate_mode_edid
from hdmi_capture.modes import CaptureMode, get_mode, mode_metadata


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_receiver_mode(hwh: ET.Element, mode: CaptureMode) -> None:
    receivers = [m for m in hwh.findall('.//MODULE')
                 if m.attrib.get('FULLNAME') == '/video/hdmi_in/frontend/dvi2rgb_0']
    if len(receivers) != 1:
        raise RuntimeError('Expected exactly one HDMI receiver in HWH')
    ranges = [p.attrib.get('VALUE')
              for p in receivers[0].findall('./PARAMETERS/PARAMETER')
              if p.attrib.get('NAME') == 'kClkRange']
    # Unrelated optional HWH parameters may omit VALUE. The required clock
    # range must occur exactly once and carry the target value.
    if ranges != [str(mode.receiver_k_clk_range)]:
        raise RuntimeError(
            f'Receiver clock range is not configured for capture mode {mode.name}')


def require_vga_receiver(hwh: ET.Element) -> None:
    """Keep the legacy VGA validation entry point for existing callers."""
    require_receiver_mode(hwh, get_mode('vga'))


def require_gateware_mode(gate: dict[str, object], mode: CaptureMode) -> None:
    if (gate.get('width'), gate.get('height'), gate.get('clock_hz')) != (
            mode.width, mode.height, mode.gateware_clock_hz):
        raise RuntimeError(f'Gateware geometry or clock does not match mode {mode.name}')


def read_capture_mode(output: Path) -> CaptureMode:
    """Read selected build mode, accepting a missing mode file as legacy VGA."""
    path = output / 'capture-mode.json'
    if not path.exists():
        return get_mode('vga')
    record = json.loads(path.read_text())
    try:
        mode = get_mode(record['capture_mode'])
    except (KeyError, TypeError) as exc:
        raise RuntimeError('Capture mode metadata is missing its profile name') from exc
    if record != mode_metadata(mode):
        raise RuntimeError(f'Capture mode metadata does not match profile {mode.name}')
    return mode


def read_hdmi_output_fixture(output: Path, mode: CaptureMode) -> dict[str, object]:
    """Return verified fixture identity from the sources used for this build."""
    source_manifest_path = output / 'source-manifest.json'
    if not source_manifest_path.exists():
        return {'enabled': False}
    source_manifest = json.loads(source_manifest_path.read_text())
    for key, value in mode_metadata(mode).items():
        if key in source_manifest and source_manifest[key] != value:
            raise RuntimeError(f'Source manifest {key} does not match capture mode {mode.name}')
    enabled = source_manifest.get('hdmi_output_enabled', False)
    if type(enabled) is not bool:
        raise RuntimeError('HDMI output build option must be a boolean')
    if not enabled:
        if 'hdmi_output_fixture' in source_manifest:
            raise RuntimeError('Disabled HDMI output must not name a test fixture')
        return {'enabled': False}
    if mode.name != '1080p30':
        raise RuntimeError('HDMI test output is supported only for 1080p30')
    fixture = source_manifest.get('hdmi_output_fixture')
    if not isinstance(fixture, dict) or fixture.get('mode') != mode.name:
        raise RuntimeError('HDMI output fixture does not match capture mode')
    paths = {
        'pattern_sha256': output / 'tx/hdmi_test_pattern.v',
        'clock_sha256': output / 'tx/hdmi_test_clock.v',
        'tcl_sha256': output / 'tx/hdmi_output.tcl',
        'xdc_sha256': output / 'hdmi_tx.xdc',
        'rgb2dvi_component_sha256': output / 'tx_ip/rgb2dvi_v1_2/component.xml',
        'rgb2dvi_clocks_xdc_sha256': output / 'tx_ip/rgb2dvi_v1_2/src/rgb2dvi_clocks.xdc',
    }
    expected = {'mode': mode.name}
    for key, path in paths.items():
        value = sha256(path)
        if fixture.get(key) != value:
            raise RuntimeError(f'HDMI output fixture hash does not match {key}')
        expected[key] = value
    return {'enabled': True, **expected}


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
    mode = read_capture_mode(args.output)
    require_gateware_mode(gate, mode)
    if gate.get('capture_interface') != 'single_credit_parked_v1':
        raise RuntimeError('This build requires single-credit gateware')
    if gate.get('gate_completion_policy') != 'next_sof_after_selected_output_drain_v1':
        raise RuntimeError('This build requires next-SOF frame-closure proof')
    hwh = ET.parse(args.output / 'capture.hwh').getroot()
    require_receiver_mode(hwh, mode)
    require_credit_configuration(hwh)
    edid_path = args.output / f'{mode.name}-edid.bin'
    edid = edid_path.read_bytes()
    validate_mode_edid(edid, mode)
    rom = args.output / 'rx_ip/dvi2rgb_v1_7/src/720p_edid.data'
    if edid != bytes(int(line, 2) for line in rom.read_text().split()):
        raise RuntimeError('Packaged EDID ROM does not match its manifest')
    hdmi_output_fixture = read_hdmi_output_fixture(args.output, mode)
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
        **mode_metadata(mode),
        'edid_sha256': sha256(edid_path),
        'hdmi_output_fixture': hdmi_output_fixture,
        'receiver_sync_base_sha256': sha256(args.output / 'rx_ip/dvi2rgb_v1_7/src/SyncBase.vhd'),
        'receiver_component_sha256': sha256(args.output / 'rx_ip/dvi2rgb_v1_7/component.xml'), 'tool_version': args.tool_version,
        'setup_slack_ns': args.setup_slack_ns, 'hold_slack_ns': args.hold_slack_ns,
    }
    source_manifest = args.output / 'source-manifest.json'
    if source_manifest.exists():
        result['source_manifest_sha256'] = sha256(source_manifest)
    with (args.output / 'build-manifest.json').open('x') as f:
        json.dump(result, f, indent=2)
        f.write('\n')


if __name__ == '__main__':
    main()
