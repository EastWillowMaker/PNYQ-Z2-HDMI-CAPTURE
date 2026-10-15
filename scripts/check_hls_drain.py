#!/usr/bin/env python3
"""Reject a synthesized HLS video pair that retains an isolated frame tail."""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def check(hls_root: Path) -> None:
    sources = []
    for ip in ('color_convert', 'pixel_pack'):
        directory = hls_root / ip / 'solution1/syn/verilog'
        if not (directory / f'{ip}.v').is_file():
            raise RuntimeError(f'Missing synthesized HLS module: {directory}')
        sources.extend(sorted(directory.glob('*.v')))
    for width, height, input_stall, output_stall in (
        (8, 4, 0, 0), (8, 4, 1, 1), (640, 480, 0, 0), (640, 480, 1, 1)
    ):
        with tempfile.TemporaryDirectory(prefix='hdmi-hls-drain-') as temporary:
            executable = Path(temporary) / 'drain.vvp'
            subprocess.run([
                'iverilog', '-g2012', '-s', 'hls_drain_tb',
                f'-Phls_drain_tb.WIDTH={width}', f'-Phls_drain_tb.HEIGHT={height}',
                f'-Phls_drain_tb.INPUT_STALL={input_stall}',
                f'-Phls_drain_tb.OUTPUT_STALL={output_stall}',
                '-o', str(executable), str(ROOT / 'hardware/hls_drain_tb.v'),
                *(str(source) for source in sources),
            ], check=True, timeout=30)
            subprocess.run(['vvp', str(executable)], check=True, timeout=120)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('hls_root', type=Path)
    check(parser.parse_args().hls_root.resolve())


if __name__ == '__main__':
    main()
