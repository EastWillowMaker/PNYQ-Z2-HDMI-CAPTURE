#!/usr/bin/env python3
"""Prepare pinned RX source and invoke isolated Vivado/Vitis builds."""
from __future__ import annotations
import argparse
import hashlib
import json
import shutil
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from build_edid import make_edid, self_test_mode
from check_hls_drain import check as check_hls_drain
from hdmi_capture.modes import CaptureMode, get_mode, mode_metadata

PIN = '93ddd21ab623883590a8c8b07f0b157b2855da4b'
_VGA_PIXEL_CLOCK_METADATA = (
    b'X_INTERFACE_PARAMETER = "FREQ_HZ 25200000, ASSOCIATED_RESET pixel_reset"')
_RGB2DVI_SYNC_RESET_PARAMETER = (
    '          <spirit:name>ASSOCIATED_RESET</spirit:name>\n'
    '          <spirit:value spirit:id="BUSIFPARAM_VALUE.SERIALCLK.ASSOCIATED_RESET">'
    'aRst:aRst_n:pRst:pRst_n</spirit:value>')
_RGB2DVI_ASYNC_RESET_PARAMETER = (
    '          <spirit:name>ASSOCIATED_ASYNC_RESET</spirit:name>\n'
    '          <spirit:value spirit:id="BUSIFPARAM_VALUE.SERIALCLK.ASSOCIATED_ASYNC_RESET">'
    'aRst:aRst_n:pRst:pRst_n</spirit:value>')

def run(command, cwd=ROOT):
    subprocess.run(command, cwd=cwd, check=True)


def require_gateware_mode(metadata: dict[str, object], mode: CaptureMode) -> None:
    if (metadata.get('width'), metadata.get('height'), metadata.get('clock_hz')) != (
            mode.width, mode.height, mode.gateware_clock_hz):
        raise ValueError(f'Gateware does not match capture mode {mode.name}')


def copy_capture_sources(output: Path, mode: CaptureMode) -> None:
    """Copy capture RTL and align its declared pixel clock with the mode."""
    for rtl_name in ('capture_lock_sync.v', 'source_health.v', 'receiver_reset_sync.v'):
        shutil.copyfile(ROOT / 'hardware' / rtl_name, output / rtl_name)

    source_health = output / 'source_health.v'
    source = source_health.read_bytes()
    if source.count(_VGA_PIXEL_CLOCK_METADATA) != 1:
        raise RuntimeError('source_health.v pixel clock metadata anchor changed')
    selected_metadata = (
        f'X_INTERFACE_PARAMETER = "FREQ_HZ {mode.pixel_clock_hz}, '
        'ASSOCIATED_RESET pixel_reset"').encode()
    if mode.pixel_clock_hz != 25_200_000:
        source = source.replace(_VGA_PIXEL_CLOCK_METADATA, selected_metadata)
        source_health.write_bytes(source)
    if source.count(selected_metadata) != 1:
        raise RuntimeError('source_health.v pixel clock metadata does not match capture mode')


def adapt_rgb2dvi_async_reset_metadata(component: Path) -> None:
    """Mark the pinned serializer reset as asynchronous in its clock metadata."""
    xml = component.read_text()
    serial_clock_interface = (
        '<spirit:busInterface>\n'
        '      <spirit:name>SerialClk</spirit:name>')
    if xml.count(serial_clock_interface) != 1:
        raise RuntimeError('Pinned rgb2dvi SerialClk interface anchor changed')
    begin = xml.index(serial_clock_interface)
    end = xml.index('</spirit:busInterface>', begin)
    interface = xml[begin:end]
    if interface.count(_RGB2DVI_SYNC_RESET_PARAMETER) != 1:
        raise RuntimeError('Pinned rgb2dvi SerialClk reset metadata anchor changed')
    interface = interface.replace(
        _RGB2DVI_SYNC_RESET_PARAMETER, _RGB2DVI_ASYNC_RESET_PARAMETER, 1)
    component.write_text(xml[:begin] + interface + xml[end:])


def copy_hdmi_output_sources(vendor: Path, output: Path) -> None:
    """Stage the test-output IP and RTL, correcting only copied IP metadata."""
    tx_ip = output / 'tx_ip'
    tx_ip.mkdir()
    shutil.copytree(vendor / 'boards/ip/rgb2dvi_v1_2', tx_ip / 'rgb2dvi_v1_2')
    adapt_rgb2dvi_async_reset_metadata(tx_ip / 'rgb2dvi_v1_2/component.xml')
    tx_source = output / 'tx'
    tx_source.mkdir()
    for name in ('hdmi_output.tcl', 'hdmi_test_pattern.v', 'hdmi_test_clock.v'):
        shutil.copyfile(ROOT / 'hardware' / name, tx_source / name)


def prepare(vendor, output, mode, with_hdmi_output=False):
    actual = subprocess.check_output(['git', '-C', str(vendor), 'rev-parse', 'HEAD'], text=True).strip()
    if actual != PIN:
        raise RuntimeError(f'Expected PYNQ {PIN}, found {actual}')
    run(['git', '-C', str(vendor), 'diff', '--exit-code', PIN, '--',
         'boards/Pynq-Z2/base/base.tcl', 'boards/Pynq-Z2/base/vivado/constraints/base.xdc',
         'boards/ip'])
    copy_capture_sources(output, mode)
    # The RTL generic already supports range 5, but v1.7 packaging exposes
    # only 1/2. Extend only the copied package's enumerated choices for VGA.
    ip_root = output / 'rx_ip'
    ip_root.mkdir()
    for name in ('dvi2rgb_v1_7', 'color_swap_1.1', 'if'):
        shutil.copytree(vendor / 'boards/ip' / name, ip_root / name)
    if with_hdmi_output:
        copy_hdmi_output_sources(vendor, output)
    component = ip_root / 'dvi2rgb_v1_7/component.xml'
    xml = component.read_text()
    anchor = '<spirit:enumeration spirit:text="&lt; 120 MHz">2</spirit:enumeration>'
    if xml.count(anchor) != 1:
        raise RuntimeError('Pinned dvi2rgb parameter-choice anchor changed')
    xml = xml.replace(anchor, anchor + '\n      <spirit:enumeration spirit:text="25-48 MHz (VGA)">5</spirit:enumeration>')
    # The original PixelClk interface lacks frequency metadata; Vivado assigns
    # a misleading 100 MHz default. Declare the selected input clock explicitly.
    clock_begin = xml.index('      <spirit:name>PixelClk</spirit:name>')
    clock_end = xml.index('    </spirit:busInterface>', clock_begin)
    if '<spirit:parameters>' in xml[clock_begin:clock_end]:
        raise RuntimeError('Pinned PixelClk clock metadata changed')
    frequency = ('      <spirit:parameters><spirit:parameter>'
                 '<spirit:name>FREQ_HZ</spirit:name>'
                 f'<spirit:value spirit:format="long">{mode.pixel_clock_hz}</spirit:value>'
                 '</spirit:parameter></spirit:parameters>\n')
    xml = xml[:clock_end] + frequency + xml[clock_end:]
    component.write_text(xml)
    # Share one reset bridge per clock at the receiver root. Independent
    # per-lane bridges can release related timeout/align flags on different
    # cycles. Each SyncBase source/destination uses its own shared-domain reset.
    reset_edits = {
        'SyncBase.vhd': {
            'aReset : in STD_LOGIC; -- active-high asynchronous reset':
                'aReset : in STD_LOGIC; -- destination-domain reset\n'
                '      iReset : in STD_LOGIC; -- source-domain reset',
            'SyncSource: process(aReset, InClk)': 'SyncSource: process(iReset, InClk)',
            "if (aReset = '1') then": "if (iReset = '1') then",
        },
        'TMDS_Decoder.vhd': {
            '      aRst : in std_logic;':
                '      rRst : in std_logic; -- shared RefClk-domain reset\n'
                '      aRst : in std_logic;',
            'aReset => aRst,\n      InClk => RefClk,':
                'aReset => aRst,\n      iReset => rRst,\n      InClk => RefClk,',
            'aReset => aRst,\n      InClk => PixelClk,':
                'aReset => rRst,\n      iReset => aRst,\n      InClk => PixelClk,',
        },
        'dvi2rgb.vhd': {
            'PixelClk_int, pLockLostRst: std_logic;':
                'PixelClk_int, pLockLostRst, rLockLostRst: std_logic;',
            '-- Three data channel decoders':
                "-- Shared reference-domain reset; avoid per-lane reset reconvergence.\n"
                "RefLockLostReset: entity work.ResetBridge\n"
                "   generic map (kPolarity => '1')\n"
                "   port map (aRst => not aLocked, OutClk => RefClk, oRst => rLockLostRst);\n\n"
                '-- Three data channel decoders',
            '         aRst                    => pLockLostRst,':
                '         rRst                    => rLockLostRst,\n'
                '         aRst                    => pLockLostRst,',
        },
    }
    for name, edits in reset_edits.items():
        path = ip_root / 'dvi2rgb_v1_7/src' / name
        rtl = path.read_text()
        for old, new in edits.items():
            if rtl.count(old) != 1:
                raise RuntimeError(f'Pinned {name} reset anchor changed: {old}')
            rtl = rtl.replace(old, new)
        path.write_text(rtl)
    source_edid = vendor / 'boards/ip/dvi2rgb_v1_7/src/720p_edid.data'
    edid = make_edid(source_edid, mode)
    (output / 'edid-check.json').write_text(
        json.dumps(self_test_mode(source_edid, mode), indent=2) + '\n')
    (output / f'{mode.name}-edid.bin').write_bytes(edid)
    (output / 'capture-mode.json').write_text(
        json.dumps(mode_metadata(mode), indent=2) + '\n')
    # Retain the packaged file name so IP-XACT file-set references remain valid;
    # replace its content only in the isolated copy and record the new identity.
    (ip_root / 'dvi2rgb_v1_7/src/720p_edid.data').write_text(
        ''.join(f'{value:08b}\n' for value in edid))
    source = (vendor / 'boards/Pynq-Z2/base/base.tcl').read_text()
    # Reuse only the pinned receiver procedures; never execute the full base
    # root design, whose peripheral processors are outside this project.
    chunks = []
    for name in ('frontend', 'hdmi_in'):
        begin = source.index(f'proc create_hier_cell_{name} ')
        end = source.index('\n# Hierarchical cell:', begin)
        chunks.append(source[begin:end])
    begin = source.index('  # Create instance: ps7_0, and set properties')
    end = source.index('\n  # Create instance:', begin + 10)
    chunks.append(source[begin:end])
    (output / 'pynq_rx.tcl').write_text(
        source[:source.index('namespace eval _tcl')] + '\n'.join(chunks))
    shutil.copyfile(vendor / 'LICENSE', output / 'PYNQ-LICENSE')
    xdc = (vendor / 'boards/Pynq-Z2/base/vivado/constraints/base.xdc').read_text()
    begin = xdc.index('## HDMI signals')
    rx_end = xdc.index('## HDMI TX', begin)
    tx_xdc = ''
    if with_hdmi_output:
        tx_begin = xdc.index('## HDMI TX', rx_end)
        next_section = xdc.find('\n## ', tx_begin + len('## HDMI TX'))
        tx_end = len(xdc) if next_section < 0 else next_section + 1
        tx_xdc = xdc[tx_begin:tx_end]
    rx_xdc = xdc[begin:rx_end]
    pixel_period_ns = 1_000_000_000 / mode.pixel_clock_hz
    half_pixel_period_ns = 500_000_000 / mode.pixel_clock_hz
    (output / 'hdmi_rx.xdc').write_text(
        rx_xdc.replace('8.334', f'{pixel_period_ns:.6f}')
        .replace('4.167', f'{half_pixel_period_ns:.6f}'))
    if with_hdmi_output:
        (output / 'hdmi_tx.xdc').write_text(tx_xdc)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--vendor', type=Path, default=ROOT / 'artifacts/vendor/PYNQ-v3.0.1')
    p.add_argument('--output', type=Path, required=True, help='New, empty artifact directory')
    p.add_argument('--vivado', default='vivado')
    p.add_argument('--vitis-run', default='vitis-run')
    p.add_argument('--stage', choices=['prepare', 'hls', 'project', 'bitstream'], default='project')
    p.add_argument('--gateware', type=Path)
    p.add_argument('--mode', choices=('vga', '1080p30'), default='vga')
    p.add_argument('--with-hdmi-output', action='store_true',
                   help='Build the 1080p30 test-pattern HDMI output for loopback')
    args = p.parse_args()
    mode = get_mode(args.mode)
    if args.with_hdmi_output and mode.name != '1080p30':
        p.error('--with-hdmi-output requires --mode 1080p30')
    if args.stage in ("project", "bitstream") and args.gateware is None:
        p.error("--gateware is required for project/bitstream stages")
    if args.gateware is not None:
        metadata = json.loads(args.gateware.with_suffix('.json').read_text())
        if metadata['rtl_sha256'] != hashlib.sha256(args.gateware.read_bytes()).hexdigest():
            p.error('Gateware provenance hash mismatch')
        try:
            require_gateware_mode(metadata, mode)
        except ValueError as exc:
            p.error(str(exc))
    vendor, output = args.vendor.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    prepare(vendor, output, mode, args.with_hdmi_output)
    if args.stage == 'prepare':
        return
    for ip in ('color_convert', 'pixel_pack'):
        # Preserve vendor source and build outputs in the new artifact tree.
        hls = output / 'hls'
        hls.mkdir(exist_ok=True)
        shutil.copytree(vendor / 'boards/ip/hls' / ip, hls / ip,
                        ignore=shutil.ignore_patterns('solution1', '.autopilot', '*.log'))
        if ip == 'color_convert':
            source = hls / ip / f'{ip}.cpp'
            original = source.read_text()
            anchor = '#pragma HLS pipeline II=1'
            if original.count(anchor) != 1:
                raise RuntimeError('Pinned color pipeline pragma changed')
            # Isolated selected frames must drain without a following pixel.
            source.write_text(original.replace(anchor, anchor + ' style=flp'))
        run([args.vitis_run, '--mode', 'hls', '--tcl', f'{ip}/script.tcl'], cwd=hls)
    check_hls_drain(output / 'hls')
    if args.stage == 'hls':
        return
    gateware = output / 'litex_capture.v'
    shutil.copyfile(args.gateware.resolve(), gateware)
    shutil.copyfile(args.gateware.with_suffix('.json'), gateware.with_suffix('.json'))
    source_manifest = {
        'pynq_commit': PIN, 'gateware_sha256': hashlib.sha256(gateware.read_bytes()).hexdigest(),
        'stage': args.stage, 'vivado': args.vivado, 'vitis_run': args.vitis_run,
        'source_health_sha256': hashlib.sha256((output / 'source_health.v').read_bytes()).hexdigest(),
        'capture_lock_sync_sha256': hashlib.sha256((output / 'capture_lock_sync.v').read_bytes()).hexdigest(),
        'receiver_reset_sync_sha256': hashlib.sha256((output / 'receiver_reset_sync.v').read_bytes()).hexdigest(),
        **mode_metadata(mode),
        'hdmi_output_enabled': args.with_hdmi_output,
    }
    if args.with_hdmi_output:
        source_manifest['hdmi_output_fixture'] = {
            'mode': mode.name,
            'pattern_sha256': hashlib.sha256((output / 'tx/hdmi_test_pattern.v').read_bytes()).hexdigest(),
            'clock_sha256': hashlib.sha256((output / 'tx/hdmi_test_clock.v').read_bytes()).hexdigest(),
            'tcl_sha256': hashlib.sha256((output / 'tx/hdmi_output.tcl').read_bytes()).hexdigest(),
            'xdc_sha256': hashlib.sha256((output / 'hdmi_tx.xdc').read_bytes()).hexdigest(),
            'rgb2dvi_component_sha256': hashlib.sha256(
                (output / 'tx_ip/rgb2dvi_v1_2/component.xml').read_bytes()).hexdigest(),
        }
    (output / 'source-manifest.json').write_text(json.dumps(source_manifest, indent=2) + '\n')
    run([args.vivado, '-mode', 'batch', '-source', str(ROOT / 'hardware/capture.tcl'),
         '-log', str(output / 'vivado.log'), '-journal', str(output / 'vivado.jou'),
         '-tclargs', str(vendor), str(output), str(gateware), args.stage, mode.name,
         str(int(args.with_hdmi_output))], cwd=output)

if __name__ == '__main__':
    main()
