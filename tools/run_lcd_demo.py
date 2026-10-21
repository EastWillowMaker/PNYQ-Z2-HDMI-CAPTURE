"""Load and observe the standalone gateware LCD demo on PYNQ-Z2.

No PC frame DMA is started. The LCD engine continues after this observer exits.
Run only while no other application owns the FPGA or video receiver.
"""

import argparse
import hashlib
import json
from pathlib import Path
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('build', type=Path)
    parser.add_argument('--attach', action='store_true',
                        help='observe the same already-loaded bitfile without reprogramming')
    parser.add_argument('--prepare-only', action='store_true',
                        help='load and assert HDMI HPD without calling source detection')
    parser.add_argument('--seconds', type=int, default=30)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 3600:
        parser.error('--seconds must be 1..3600')
    build = args.build.resolve()
    manifest = json.loads((build / 'build-manifest.json').read_text())
    if manifest.get('lcd_demo', {}).get('kind') != 'single_buffer_nearest_neighbor_lcd_demo':
        parser.error('build is not an LCD demo artifact')
    for filename, key in [('capture.bit', 'bitstream_sha256'), ('capture.hwh', 'hwh_sha256')]:
        if hashlib.sha256((build / filename).read_bytes()).hexdigest() != manifest[key]:
            parser.error(f'{filename} hash does not match manifest')

    from pynq import Overlay, MMIO
    from pynq.lib.video.dvi import HDMIInFrontend

    print(json.dumps({'stage': 'attach' if args.attach else 'load',
                      'bitfile': str(build / 'capture.bit')}), flush=True)
    overlay = Overlay(str(build / 'capture.bit'), download=not args.attach)
    if not overlay.is_loaded():
        raise RuntimeError('requested overlay is not loaded')

    def registers(name):
        info = overlay.ip_dict[name]
        return MMIO(info['phys_addr'], info['addr_range'])

    dma = registers('video/axi_vdma')
    if dma.read(0x30) & 5 or not dma.read(0x34) & 1:
        raise RuntimeError('demo observer requires halted, reset-clear PC capture DMA')
    control = registers('video/capture_control')
    if control.read(0) != 0:
        raise RuntimeError('PC capture gate is owned or enabled')
    hpd = registers('video/hdmi_in/frontend/axi_gpio_hdmiin')
    hpd.write(0, 1)
    if hpd.read(0) & 1 != 1:
        raise RuntimeError('HDMI input HPD failed to assert')
    lcd = registers('video/lcd_status')
    if args.prepare_only:
        print(json.dumps({'stage': 'prepared', 'lcd_status': lcd.read(0),
                          'uploads': lcd.read(8), 'vdma_halted': True}), flush=True)
        return

    print(json.dumps({'stage': 'detect_input', 'timeout_seconds': 10}), flush=True)
    frontend = HDMIInFrontend(overlay.video.hdmi_in.frontend.description)
    frontend.start(init_timeout=10)
    mode = frontend.mode
    if [mode.width, mode.height] != manifest['geometry']:
        raise RuntimeError(f'input {mode.width}x{mode.height} differs from build profile')
    print(json.dumps({'stage': 'input_detected', 'geometry': [mode.width, mode.height]}),
          flush=True)
    start = time.monotonic()
    first = lcd.read(8)
    for second in range(args.seconds):
        time.sleep(1)
        elapsed = time.monotonic() - start
        uploads = lcd.read(8)
        print(json.dumps({'elapsed_seconds': elapsed, 'lcd_status': lcd.read(0),
                          'uploads': uploads,
                          'upload_rate': ((uploads - first) & 0xffffffff) / elapsed}),
              flush=True)
    print('Observer finished; gateware remains running. No optical latency measured.',
          flush=True)


if __name__ == '__main__':
    main()
