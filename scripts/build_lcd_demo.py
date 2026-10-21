#!/usr/bin/env python3
"""Build the isolated LCD demo, reusing explicitly selected existing HLS IP."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

from build_capture import ROOT, PIN, prepare, get_mode, mode_metadata, require_gateware_mode
from check_hls_drain import check as check_hls_drain


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--reuse-hls', type=Path, required=True,
                   help='existing build hls directory; copied, never modified')
    p.add_argument('--gateware', type=Path, required=True)
    p.add_argument('--reuse-ip-cache', type=Path,
                   help='copy an existing Vivado IP synthesis cache into this build')
    p.add_argument('--mode', choices=('vga', '1080p30'), default='1080p30')
    p.add_argument('--with-hdmi-output', action='store_true',
                   help='also include the existing 1080p30 HDMI loopback fixture')
    p.add_argument('--stage', choices=('prepare', 'project', 'bitstream'), default='bitstream')
    p.add_argument('--vivado', default='vivado')
    p.add_argument('--vendor', type=Path, default=ROOT / 'artifacts/vendor/PYNQ-v3.0.1')
    a = p.parse_args()
    if a.with_hdmi_output and a.mode != '1080p30':
        p.error('--with-hdmi-output requires 1080p30')
    mode = get_mode(a.mode)
    gate = json.loads(a.gateware.with_suffix('.json').read_text())
    require_gateware_mode(gate, mode)
    if digest(a.gateware) != gate['rtl_sha256']:
        p.error('gateware provenance mismatch')
    out, vendor = a.output.resolve(), a.vendor.resolve()
    out.mkdir(parents=True, exist_ok=False)
    prepare(vendor, out, mode, a.with_hdmi_output)
    shutil.copytree(a.reuse_hls.resolve(), out / 'hls')
    if a.reuse_ip_cache:
        shutil.copytree(a.reuse_ip_cache.resolve(), out / 'ip-cache')
    check_hls_drain(out / 'hls')
    shutil.copyfile(a.gateware, out / 'litex_capture.v')
    shutil.copyfile(a.gateware.with_suffix('.json'), out / 'litex_capture.json')
    demo = out / 'lcd-demo'
    demo.mkdir()
    files = ('lcd_demo.v', 'lcd_demo_faults.v', 'lcd_demo_attach.tcl', 'lcd_demo.xdc')
    for name in files:
        shutil.copyfile(ROOT / 'hardware' / name, demo / name)
    metadata = {
        'kind': 'single_buffer_nearest_neighbor_lcd_demo',
        'pynq_commit': PIN, 'stage': a.stage, **mode_metadata(mode),
        'hdmi_output_enabled': a.with_hdmi_output,
        'lcd_demo_sources': {name: digest(demo / name) for name in files},
        'reused_hls_sources': {
            str(f.relative_to(out / 'hls')): digest(f)
            for f in sorted((out / 'hls').rglob('*')) if f.is_file()
        },
        'capture_tcl_sha256': digest(ROOT / 'hardware/capture.tcl'),
        'implement_tcl_sha256': digest(ROOT / 'hardware/implement.tcl'),
    }
    if a.reuse_ip_cache:
        metadata['reused_ip_cache_sources'] = {
            str(f.relative_to(out / 'ip-cache')): digest(f)
            for f in sorted((out / 'ip-cache').rglob('*')) if f.is_file()
        }
    if a.with_hdmi_output:
        fixture = {'mode': mode.name}
        for key, name in {
            'pattern_sha256': 'tx/hdmi_test_pattern.v',
            'clock_sha256': 'tx/hdmi_test_clock.v',
            'tcl_sha256': 'tx/hdmi_output.tcl',
            'xdc_sha256': 'hdmi_tx.xdc',
            'rgb2dvi_component_sha256': 'tx_ip/rgb2dvi_v1_2/component.xml',
            'rgb2dvi_clocks_xdc_sha256': 'tx_ip/rgb2dvi_v1_2/src/rgb2dvi_clocks.xdc',
        }.items():
            fixture[key] = digest(out / name)
        metadata['hdmi_output_fixture'] = fixture
    (out / 'source-manifest.json').write_text(json.dumps(metadata, indent=2) + '\n')
    if a.stage == 'prepare':
        return
    env = dict(os.environ, HDMI_LCD_DEMO_TCL=str(demo / 'lcd_demo_attach.tcl'))
    subprocess.run([a.vivado, '-mode', 'batch', '-source', str(ROOT / 'hardware/capture.tcl'),
                    '-log', str(out / 'vivado.log'), '-journal', str(out / 'vivado.jou'),
                    '-tclargs', str(vendor), str(out), str(out / 'litex_capture.v'),
                    a.stage, mode.name, str(int(a.with_hdmi_output))],
                   cwd=out, env=env, check=True)
    if a.stage == 'bitstream':
        path = out / 'build-manifest.json'
        result = json.loads(path.read_text())
        result['lcd_demo'] = {'kind': metadata['kind'], 'sources': metadata['lcd_demo_sources'],
                              'performance_qualified': False}
        path.write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
