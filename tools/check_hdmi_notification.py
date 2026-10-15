#!/usr/bin/env python3
"""Compare real HDMI pixels before/during/after one desktop notification.

Requires an already running optical fixture and board sender. This is a physical
regression probe, not M1 qualification. It never changes notification settings.
"""
import argparse
import json
from pathlib import Path
import subprocess
import time

from hdmi_capture import CaptureClient
try:
    from .hdmi_pattern import verify
except ImportError:
    from hdmi_pattern import verify


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('host')
    parser.add_argument('--port', type=int, default=9022)
    parser.add_argument('--notify', action='store_true',
                        help='Show one temporary desktop notification after 2 seconds')
    parser.add_argument('--expected-id', type=int)
    parser.add_argument('--output', type=Path, required=True, help='New JSON evidence file')
    args = parser.parse_args()
    if args.expected_id is not None and not 0 <= args.expected_id <= 0xFFFFFFFF:
        parser.error('expected-id must be uint32')
    with args.output.open('x') as output:
        start = time.monotonic()
        report = dict(scope='physical_notification_pixel_regression_only',
                      started_monotonic=start, notification_requested=args.notify,
                      notification_sent_monotonic=None, frames=[], error=None,
                      full_m1_qualification=False)
        try:
            with CaptureClient(args.host, args.port, timeout=5) as client:
                while time.monotonic() - start < 7:
                    if (args.notify and time.monotonic() - start >= 2
                            and report['notification_sent_monotonic'] is None):
                        subprocess.run(['notify-send', '--expire-time=1500',
                                        'HDMI diagnostic', 'Temporary frame comparison probe'],
                                       check=True, capture_output=True, timeout=3)
                        report['notification_sent_monotonic'] = time.monotonic()
                    frame = client.read(deadline=start + 12)
                    result = verify(frame.rgb, args.expected_id)
                    report['frames'].append(dict(received_monotonic=time.monotonic(),
                                                 verification=result, metadata=frame.metadata))
        except Exception as error:
            report['error'] = f'{type(error).__name__}: {error}'
        report['elapsed_seconds'] = time.monotonic() - start
        report['received_frames'] = len(report['frames'])
        report['pixel_failures'] = sum(not r['verification']['exact_match']
                                       for r in report['frames'])
        report['passed'] = bool(report['received_frames'] >= 3
                                and report['error'] is None
                                and report['pixel_failures'] == 0
                                and (not args.notify or
                                     report['notification_sent_monotonic'] is not None))
        json.dump(report, output, indent=2)
        output.write('\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'frames'}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
