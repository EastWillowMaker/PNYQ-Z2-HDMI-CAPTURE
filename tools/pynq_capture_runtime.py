"""Board-side operations uploaded by the PC launcher; no credentials are stored."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import time


def discover(extra_root=None):
    roots = [Path.home() / 'litex-hdmi-capture', Path.home() / 'hdmi-capture']
    roots.extend(sorted(Path('/tmp').glob('hdmi-capture-*')))
    if extra_root:
        roots.insert(0, Path(extra_root).expanduser())
    roots = list(dict.fromkeys(path.resolve() for path in roots if path.is_dir()))
    runtimes, profiles, receipts = [], [], []
    for root in roots:
        if (root / 'src/hdmi_capture/sender.py').is_file():
            runtimes.append(str(root / 'src'))
        for manifest in sorted(root.glob('overlay*/build-manifest.json')):
            try:
                data = json.loads(manifest.read_text())
                bit = manifest.with_name('capture.bit')
                if not bit.is_file() or not bit.with_suffix('.hwh').is_file():
                    continue
                mode = data.get('capture_mode', 'vga')
                if mode not in ('vga', '1080p30'):
                    continue
                profiles.append(dict(mode=mode, bitfile=str(bit), manifest=str(manifest),
                                     loop=data.get('hdmi_output_fixture', {}).get('enabled') is True))
            except (OSError, ValueError, AttributeError):
                continue
        receipts.extend(str(path) for path in root.glob('*prepared*.json'))
    state = Path.home() / '.local/state/hdmi-capture'
    receipts.extend(str(path) for path in state.glob('*-prepared.json'))
    addresses = []
    result = subprocess.run(['ip', '-j', 'address', 'show', 'eth0'],
                            capture_output=True, text=True, check=True)
    for interface in json.loads(result.stdout):
        for address in interface.get('addr_info', []):
            if address.get('family') in ('inet', 'inet6'):
                addresses.append(address['local'])
    runtimes.sort(key=lambda path: (Path(path) / 'hdmi_capture/sender.py').stat().st_mtime)
    return dict(runtimes=runtimes, profiles=profiles, receipts=receipts,
                addresses=addresses, state=str(state))


def reject_capture_processes(proc=Path('/proc')):
    ancestors = set()
    pid = os.getpid()
    while pid and pid not in ancestors:
        ancestors.add(pid)
        status = (proc / str(pid) / 'status').read_text()
        pid = int(next(line.split()[1] for line in status.splitlines() if line.startswith('PPid:')))
    for process in proc.iterdir():
        if not process.name.isdigit() or int(process.name) in ancestors:
            continue
        try:
            argv = (process / 'cmdline').read_bytes().split(b'\0')
        except (FileNotFoundError, ProcessLookupError):
            continue
        if any(arg == b'hdmi_capture.sender' or
               arg.endswith((b'/check_credit_lease.py', b'/profile-sender.py')) or
               b'attached-credit-sender' in arg or
               (arg == b'--action' and b'capture' in argv)
               for arg in argv):
            raise RuntimeError('Another capture is running. Stop it safely before starting again.')


def prepare_profile(profile, receipt, previous, *, after_reset=False):
    from hdmi_capture.prepared import _attach_metadata, _check_sdk_shutdown, prepare
    from hdmi_capture.sources import LiteXCreditSource, LiteXSource, verify_litex_artifacts

    reject_capture_processes()
    verify_litex_artifacts(profile['bitfile'], profile['manifest'], expected_mode=profile['mode'])
    new = LiteXCreditSource(profile['bitfile'], profile['manifest'], capture_mode=profile['mode'])
    if after_reset:
        prepare(new, receipt, after_reset=True)
        return str(receipt)
    failures = []
    for path in dict.fromkeys([str(receipt), *previous]):
        try:
            record = json.loads(Path(path).read_text())
            artifacts = record['artifacts']
            old_manifest = json.loads(Path(artifacts['manifest']['path']).read_text())
            old = LiteXCreditSource(artifacts['bitfile']['path'], artifacts['manifest']['path'],
                                   capture_mode=old_manifest.get('capture_mode', 'vga'))
            _attach_metadata(old, path, empty=False)
        except (OSError, ValueError, KeyError, RuntimeError) as error:
            failures.append(str(error))
            continue
        _check_sdk_shutdown()
        same = (Path(old.bitfile).resolve() == Path(profile['bitfile']).resolve() and
                Path(old.manifest_path).resolve() == Path(profile['manifest']).resolve())
        if same:
            # Keep the existing ledger until normal preparation has checked it again.
            prepare(new, path)
            return path
        # The previous image is verified halted before touching the new register map.
        LiteXSource.load_overlay(new, download=True, video_drivers=False)
        prepare(new, receipt, after_reset=True)
        return str(receipt)
    raise RuntimeError('No valid idle-board receipt. Power-cycle the board, then use '
                       '--after-reset only before any capture starts. Setup details: '
                       'docs/prepared-capture.md. Last check: ' + (failures[-1] if failures else 'no receipt'))


def check_input(profile, receipt, *, sleep=time.sleep):
    from hdmi_capture.prepared import _attach_metadata, _hardware
    from hdmi_capture.sources import LiteXCreditSource

    source = LiteXCreditSource(profile['bitfile'], profile['manifest'], capture_mode=profile['mode'])
    _attach_metadata(source, receipt, empty=True)
    previous = source.control.snapshot()
    expected = 30 if profile['mode'] == '1080p30' else 60
    for _ in range(5):
        sleep(1)
        current = source.control.snapshot()
        _hardware(source, empty=True)
        elapsed = (current['snapshot_end_ns'] - previous['snapshot_end_ns']) / 1e9
        edges = (current['native_vsync_edges'] - previous['native_vsync_edges']) & 0xffffffff
        rate = edges / elapsed if elapsed > 0 else 0
        if not expected * .95 <= rate <= expected * 1.05:
            raise RuntimeError(f'HDMI input is missing or unstable ({rate:.2f} Hz; expected about {expected} Hz). '
                               'Check the cable and source display mode.')
        print(json.dumps(dict(event='input_observation', measured_vsync_hz=rate,
                              invalid_frames=current.get('invalid_frames', 0),
                              frontend_overflow_episodes=current.get('frontend_overflow_episodes'),
                              frontend_underflow_episodes=current.get('frontend_underflow_episodes'))), flush=True)
        # The runtime baselines invalid geometry before capture; FIFO loss must be clean.
        if (current.get('invalid_frames', 0) != previous.get('invalid_frames', 0) or
                any(current.get(name, 0) for name in
                    ('frontend_overflow_episodes', 'frontend_underflow_episodes'))):
            raise RuntimeError('HDMI input reports a source fault. Inspect the source before restarting.')
        previous = current


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--action', choices=('discover', 'prepare', 'capture'), required=True)
    parser.add_argument('--root')
    parser.add_argument('--profile')
    parser.add_argument('--receipt')
    parser.add_argument('--previous', default='[]')
    parser.add_argument('--after-reset', action='store_true')
    parser.add_argument('--port', type=int, default=9020)
    parser.add_argument('--duration', type=float, default=0)
    args = parser.parse_args(argv)
    if args.action == 'discover':
        print('PYNQ_LAUNCHER_JSON:' + json.dumps(discover(args.root)), flush=True)
        return
    profile = json.loads(args.profile)
    receipt = Path(args.receipt)
    receipt.parent.mkdir(parents=True, exist_ok=True)
    with Path('/tmp/hdmi-capture-launcher.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another launcher is using the board. Stop that session first.')
        if args.action == 'prepare':
            actual_receipt = prepare_profile(profile, receipt, json.loads(args.previous),
                                             after_reset=args.after_reset)
            print('PYNQ_LAUNCHER_JSON:' + json.dumps(dict(receipt=actual_receipt)), flush=True)
            return
        reject_capture_processes()
        actual_receipt = str(receipt)
        check_input(profile, actual_receipt)
        from hdmi_capture.sender import main as sender_main
        command = ['--source', 'litex-credit', '--mode', profile['mode'], '--bitfile', profile['bitfile'],
                   '--manifest', profile['manifest'], '--prepared-receipt', actual_receipt,
                   '--host', '::', '--port', str(args.port), '--fps', '2', '--startup-diagnostics']
        if args.duration:
            command += ['--duration', str(args.duration)]
        sender_main(command)


if __name__ == '__main__':
    main()
