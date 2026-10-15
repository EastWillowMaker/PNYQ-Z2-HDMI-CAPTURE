#!/usr/bin/env python3
"""Prepare pinned RX source and invoke isolated Vivado/Vitis builds."""
from __future__ import annotations
import argparse
import hashlib
import json
import shutil
from pathlib import Path
import subprocess
from build_edid import make_vga_edid, self_test

ROOT = Path(__file__).resolve().parents[1]
PIN = '93ddd21ab623883590a8c8b07f0b157b2855da4b'

def run(command, cwd=ROOT):
    subprocess.run(command, cwd=cwd, check=True)

def prepare(vendor, output):
    actual = subprocess.check_output(['git', '-C', str(vendor), 'rev-parse', 'HEAD'], text=True).strip()
    if actual != PIN:
        raise RuntimeError(f'Expected PYNQ {PIN}, found {actual}')
    run(['git', '-C', str(vendor), 'diff', '--exit-code', PIN, '--',
         'boards/Pynq-Z2/base/base.tcl', 'boards/Pynq-Z2/base/vivado/constraints/base.xdc',
         'boards/ip'])
    for rtl_name in ('capture_lock_sync.v', 'source_health.v', 'receiver_reset_sync.v'):
        shutil.copyfile(ROOT / 'hardware' / rtl_name, output / rtl_name)
    # The RTL generic already supports range 5, but v1.7 packaging exposes
    # only 1/2. Extend only the copied package's enumerated choices for VGA.
    ip_root = output / 'rx_ip'
    ip_root.mkdir()
    for name in ('dvi2rgb_v1_7', 'color_swap_1.1', 'if'):
        shutil.copytree(vendor / 'boards/ip' / name, ip_root / name)
    component = ip_root / 'dvi2rgb_v1_7/component.xml'
    xml = component.read_text()
    anchor = '<spirit:enumeration spirit:text="&lt; 120 MHz">2</spirit:enumeration>'
    if xml.count(anchor) != 1:
        raise RuntimeError('Pinned dvi2rgb parameter-choice anchor changed')
    xml = xml.replace(anchor, anchor + '\n      <spirit:enumeration spirit:text="25-48 MHz (VGA)">5</spirit:enumeration>')
    # The original PixelClk interface lacks frequency metadata; Vivado assigns
    # a misleading 100 MHz default. Declare the chosen VGA clock explicitly.
    clock_begin = xml.index('      <spirit:name>PixelClk</spirit:name>')
    clock_end = xml.index('    </spirit:busInterface>', clock_begin)
    if '<spirit:parameters>' in xml[clock_begin:clock_end]:
        raise RuntimeError('Pinned PixelClk clock metadata changed')
    frequency = ('      <spirit:parameters><spirit:parameter>'
                 '<spirit:name>FREQ_HZ</spirit:name>'
                 '<spirit:value spirit:format="long">25200000</spirit:value>'
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
    edid = make_vga_edid(source_edid)
    (output / 'edid-check.json').write_text(json.dumps(self_test(source_edid), indent=2) + '\n')
    (output / 'vga-edid.bin').write_bytes(edid)
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
    end = xdc.index('## HDMI TX', begin)
    (output / 'hdmi_rx.xdc').write_text(
        xdc[begin:end].replace('8.334', '39.682540').replace('4.167', '19.841270'))

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--vendor', type=Path, default=ROOT / 'artifacts/vendor/PYNQ-v3.0.1')
    p.add_argument('--output', type=Path, required=True, help='New, empty artifact directory')
    p.add_argument('--vivado', default='vivado')
    p.add_argument('--vitis-run', default='vitis-run')
    p.add_argument('--stage', choices=['prepare', 'hls', 'project', 'bitstream'], default='project')
    p.add_argument('--gateware', type=Path)
    args = p.parse_args()
    if args.stage in ("project", "bitstream") and args.gateware is None:
        p.error("--gateware is required for project/bitstream stages")
    if args.gateware is not None:
        metadata = json.loads(args.gateware.with_suffix('.json').read_text())
        if metadata['rtl_sha256'] != hashlib.sha256(args.gateware.read_bytes()).hexdigest():
            p.error('Gateware provenance hash mismatch')
        if (metadata['width'], metadata['height'], metadata['clock_hz']) != (640, 480, 142857132):
            p.error('This integration requires 640x480 at 142857132 Hz')
    vendor, output = args.vendor.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    prepare(vendor, output)
    if args.stage == 'prepare':
        return
    for ip in ('color_convert', 'pixel_pack'):
        # Preserve vendor source and build outputs in the new artifact tree.
        hls = output / 'hls'
        hls.mkdir(exist_ok=True)
        shutil.copytree(vendor / 'boards/ip/hls' / ip, hls / ip,
                        ignore=shutil.ignore_patterns('solution1', '.autopilot', '*.log'))
        run([args.vitis_run, '--mode', 'hls', '--tcl', f'{ip}/script.tcl'], cwd=hls)
    if args.stage == 'hls':
        return
    gateware = output / 'litex_capture.v'
    shutil.copyfile(args.gateware.resolve(), gateware)
    shutil.copyfile(args.gateware.with_suffix('.json'), gateware.with_suffix('.json'))
    (output / 'source-manifest.json').write_text(json.dumps({
        'pynq_commit': PIN, 'gateware_sha256': hashlib.sha256(gateware.read_bytes()).hexdigest(),
        'stage': args.stage, 'vivado': args.vivado, 'vitis_run': args.vitis_run,
        'source_health_sha256': hashlib.sha256((output / 'source_health.v').read_bytes()).hexdigest(),
        'capture_lock_sync_sha256': hashlib.sha256((output / 'capture_lock_sync.v').read_bytes()).hexdigest(),
        'receiver_reset_sync_sha256': hashlib.sha256((output / 'receiver_reset_sync.v').read_bytes()).hexdigest(),
    }, indent=2) + '\n')
    run([args.vivado, '-mode', 'batch', '-source', str(ROOT / 'hardware/capture.tcl'),
         '-log', str(output / 'vivado.log'), '-journal', str(output / 'vivado.jou'),
         '-tclargs', str(vendor), str(output), str(gateware), args.stage], cwd=output)

if __name__ == '__main__':
    main()
