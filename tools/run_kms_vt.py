#!/usr/bin/env python3
"""Run the exact KMS source on a temporary VT, then return to the original VT.

Requires local sudo. Never stops GNOME or edits persistent display settings.
Direct KMS runtime remains unverified until the operator executes this probe.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
BINARY = ROOT / 'artifacts/kms-fixture/hdmi-pattern-kms'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duration', type=int, default=10)
    parser.add_argument('--frame-id', type=int, default=400000)
    parser.add_argument('--card', choices=['/dev/dri/card2'], default='/dev/dri/card2')
    parser.add_argument('--connector', choices=['DP-2'], default='DP-2')
    parser.add_argument('--output', type=Path, required=True, help='New evidence directory under artifacts')
    parser.add_argument('--child', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not 1 <= args.duration <= 900 or not 0 <= args.frame_id <= 0xFFFFFFFF:
        parser.error('duration must be1..900 and frame ID uint32')
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / 'artifacts').resolve()):
        parser.error('output must be under repository artifacts')
    if os.geteuid() != 0:
        parser.error('Local sudo is required to switch VT; do not send the password to chat')
    if not BINARY.is_file():
        parser.error('Run bash scripts/build_kms_fixture.sh first')
    if args.child:
        # openvt already switched away from the desktop; allow DRM master release.
        time.sleep(2)
        with (output / 'source.jsonl').open('x') as events:
            try:
                result = subprocess.run([str(BINARY), '--direct', args.card, args.connector,
                                         str(args.frame_id), str(args.duration)],
                                        stdout=events, stderr=subprocess.STDOUT,
                                        timeout=args.duration + 35)
                code = result.returncode
            except subprocess.TimeoutExpired:
                code = 124
        (output / 'child-result.json').write_text(json.dumps({'exit_code': code}) + '\n')
        return code
    # Snapshot before changing the active VT. This is not a login/logout operation.
    original_vt = subprocess.check_output(['/usr/bin/fgconsole'], text=True).strip()
    if not original_vt.isdigit() or not 1 <= int(original_vt) <= 63:
        raise RuntimeError('Cannot identify original active VT')
    edids = list(Path('/sys/class/drm').glob('card2-DP-2/edid'))
    if len(edids) != 1 or not edids[0].read_bytes():
        raise RuntimeError('Expected connected DP-2 EDID is absent')
    edid = edids[0].read_bytes()
    vendor = ''.join(chr(64 + ((int.from_bytes(edid[8:10], 'big') >> shift) & 31))
                     for shift in (10, 5, 0))
    if vendor != 'DGL':
        raise RuntimeError('Refuse to modeset a non-Digilent sink')
    output.mkdir(exist_ok=False)
    (output / 'original.json').write_text(json.dumps({'vt': int(original_vt),
                                                       'card': args.card, 'connector': args.connector,
                                                       'duration': args.duration, 'vendor': vendor}) + '\n')
    child = None
    restored = False

    def interrupt(_signal, _frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupt)
    signal.signal(signal.SIGINT, interrupt)
    try:
        command = ['/usr/bin/openvt', '-s', '-w', '--', '/usr/bin/python3',
                   str(Path(__file__).resolve()), '--child', '--duration', str(args.duration),
                   '--frame-id', str(args.frame_id), '--card', args.card,
                   '--connector', args.connector, '--output', str(output)]
        child = subprocess.Popen(command, start_new_session=True)
        child.wait(timeout=args.duration + 45)
        result = json.loads((output / 'child-result.json').read_text())
        return result['exit_code']
    finally:
        if child is not None and child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)  # Host-only bounded test process group.
                child.wait()
        # openvt -s -w also switches back; explicitly verify the postcondition.
        subprocess.run(['/usr/bin/chvt', original_vt], check=True, timeout=10)
        restored = subprocess.check_output(['/usr/bin/fgconsole'], text=True).strip() == original_vt
        (output / 'restore.json').write_text(json.dumps({'original_vt_restored': restored}) + '\n')
        if 'SUDO_UID' in os.environ and 'SUDO_GID' in os.environ:
            uid, gid = int(os.environ['SUDO_UID']), int(os.environ['SUDO_GID'])
            for path in [output, *output.iterdir()]:
                os.chown(path, uid, gid)
        print(json.dumps({'output': str(output), 'original_vt_restored': restored}), flush=True)
        if not restored:
            raise RuntimeError('VT restoration failed; use Ctrl+Alt+F' + original_vt)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (Exception, KeyboardInterrupt) as error:
        print(f'KMS VT probe failed: {error}', file=sys.stderr)
        raise SystemExit(1)
