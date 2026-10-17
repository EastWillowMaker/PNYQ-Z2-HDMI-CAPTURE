"""PC launchers for the board's serial console and the desktop viewer."""
import argparse
import base64
import ipaddress
import json
import math
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
SETTINGS = ROOT / 'artifacts/launcher/connection.json'
BOARD_PYTHON = '/usr/local/share/pynq-venv/bin/python'


def load_settings(path=SETTINGS):
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(data, path=SETTINGS):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, indent=2) + '\n')
    temporary.replace(path)


def choose(label, choices):
    if not choices:
        raise RuntimeError(f'No {label} found.')
    if len(choices) == 1:
        return choices[0][1]
    print(label + ':')
    for index, (description, _) in enumerate(choices, 1):
        print(f'  {index}. {description}')
    while True:
        answer = input('Choose a number [1]: ').strip() or '1'
        if answer.isdigit() and 1 <= int(answer) <= len(choices):
            return choices[int(answer) - 1][1]
        print('Please enter one of the listed numbers.')


def serial_port(explicit=None):
    try:
        from serial.tools.list_ports import comports
    except ImportError as error:
        raise RuntimeError("Install PC dependencies first: .venv/bin/python -m pip install -e '.[gui,serial]'") from error
    if explicit:
        return explicit
    ports = list(comports())
    uart = [p for p in ports if 'if01' in p.device or 'LOCATION=' in p.hwid and p.hwid.endswith(':1.1')]
    if len(uart) == 1:
        return uart[0].device
    return choose('USB serial port (select the PYNQ UART, not JTAG)',
                  [(f'{p.device}: {p.description}', p.device) for p in ports])


def open_terminal(port):
    print('\nMiniterm opens at 115200 baud. Press Enter for the board prompt.')
    print('Log in with your board account, then run: sudo -v')
    print('Enter passwords only in that terminal. Press Ctrl+] to return here.')
    result = subprocess.run([sys.executable, '-m', 'serial.tools.miniterm', port, '115200',
                             '--raw', '--eol', 'CR', '--dtr', '0', '--rts', '0'])
    if result.returncode:
        raise RuntimeError('Could not open Miniterm. Check the USB cable and serial-port access.')


class SerialShell:
    def __init__(self, port):
        import serial
        self.port = serial.Serial(port, 115200, timeout=.2, exclusive=True)
        self.port.dtr = False
        self.port.rts = False
        self.log = ROOT / 'artifacts/launcher' / (uuid.uuid4().hex + '.log')
        self.log.parent.mkdir(parents=True, exist_ok=True)

    def close(self):
        self.port.close()

    def command(self, command, *, timeout=120, ready=None, cancellable=False):
        marker = 'PYNQ_DONE_' + uuid.uuid4().hex
        pattern = re.compile(rb'(?:\r?\n)' + marker.encode() + rb':(\d+)\r?\n')
        separator = '\n' if '\n' in command else '; '
        wire = command + separator + 'printf "\\n' + marker + ':%s\\n" "$?"\n'
        self.port.write(wire.replace('\n', '\r').encode())
        start, data, cancelled = time.monotonic(), bytearray(), False
        with self.log.open('ab') as log:
            while True:
                try:
                    chunk = self.port.read(65536)
                    if chunk:
                        log.write(chunk)
                        log.flush()
                        data.extend(chunk)
                        if ready:
                            ready(bytes(data).decode(errors='replace'))
                    match = pattern.search(data)
                    if match:
                        text = bytes(data).decode(errors='replace')
                        if int(match[1]):
                            messages = re.findall(r'(?m)^(?:RuntimeError|SourceError|PermissionError): ([^\r\n]+)', text)
                            message = messages[-1] if messages else 'Board command failed. Check the serial login and sudo -v.'
                            raise RuntimeError(f'{message} Details: {self.log}')
                        return text
                    if len(data) > 262144:
                        del data[:-262144]
                    if timeout is not None and time.monotonic() - start > timeout:
                        raise RuntimeError(f'Board response timed out. The command may still be running; '
                                           f'do not retry or reset it blindly. Details: {self.log}')
                except KeyboardInterrupt:
                    if not cancellable:
                        raise RuntimeError(f'Observation interrupted; board state must be checked. Log: {self.log}')
                    if not cancelled:
                        self.port.write(b'\x03')
                        cancelled = True
                    print('\nWaiting for safe board shutdown. Do not close this terminal or force-kill the process.')

    def upload(self, source):
        destination = '/tmp/pynq-capture-launcher-' + uuid.uuid4().hex + '.py'
        encoded = base64.b64encode(source.read_bytes()).decode()
        lines = '\n'.join(encoded[index:index + 768] for index in range(0, len(encoded), 768))
        delimiter = 'UPLOAD_' + uuid.uuid4().hex
        self.command(f"base64 -d > {shlex.quote(destination)} <<'{delimiter}'\n{lines}\n{delimiter}")
        return destination


def response(text):
    for line in reversed(text.splitlines()):
        if line.startswith('PYNQ_LAUNCHER_JSON:'):
            return json.loads(line.split(':', 1)[1])
    raise RuntimeError('The board did not return its setup information.')


def select_profile(discovery, scenario, external_mode='1080p60'):
    mode = '1080p30' if scenario == 'loop' else external_mode
    candidates = [p for p in discovery['profiles'] if p['mode'] == mode and
                  (scenario != 'loop' or p['loop'])]
    if not candidates:
        raise RuntimeError(f'No {mode} board image installed. Ask the board administrator to complete docs/quickstart.md and docs/output-loop.md.')
    return candidates[-1]


def address_for_host(addresses):
    ethernet = []
    for interface in Path('/sys/class/net').glob('*'):
        try:
            if (interface.name != 'lo' and (interface / 'device').exists() and
                    not (interface / 'wireless').exists() and
                    (interface / 'operstate').read_text().strip() == 'up'):
                ethernet.append(interface.name)
        except OSError:
            continue
    for address in addresses:
        if ipaddress.ip_address(address).version != 4:
            continue
        try:
            route = subprocess.run(['ip', '-j', 'route', 'get', address],
                                   capture_output=True, text=True, check=True)
            routes = json.loads(route.stdout)
            if any(r.get('dev') in ethernet and not r.get('gateway') for r in routes):
                return address
        except (OSError, ValueError, subprocess.CalledProcessError):
            continue
    for address in addresses:
        if ipaddress.ip_address(address).version == 6 and not ipaddress.ip_address(address).is_link_local:
            return address
    for address in addresses:
        if ipaddress.ip_address(address).is_link_local and len(ethernet) == 1:
            return address + '%' + ethernet[0]
    return 'pynq'


def port_number(value):
    value = int(value)
    if not 1 <= value <= 65535:
        raise argparse.ArgumentTypeError('Port must be between 1 and 65535')
    return value


def board_main(argv=None):
    parser = argparse.ArgumentParser(description='Run on the PC: connect by USB serial and start PYNQ-Z2 capture.')
    parser.add_argument('--scenario', choices=('loop', 'external'))
    parser.add_argument('--external-mode', choices=('1080p60', '1080p30', 'vga'), default='1080p60',
                        help='External HDMI timing and EDID (default: 1920x1080 at 60 Hz)')
    parser.add_argument('--serial-port', help='USB UART device or COM port; otherwise select from detected ports')
    parser.add_argument('--no-terminal', action='store_true', help='Use an already logged-in board shell with valid sudo')
    parser.add_argument('--board-root', help='Board checkout/deployment directory (normally detected)')
    parser.add_argument('--runtime', help='Board src directory (normally detected)')
    parser.add_argument('--host', help='Board Ethernet address as seen from the PC')
    parser.add_argument('--port', type=port_number, default=9020)
    parser.add_argument('--duration', type=float, default=0, help='Capture seconds; 0 runs until Ctrl+C')
    parser.add_argument('--after-reset', action='store_true',
                        help='Assert a confirmed board/PL reset with no active DMA; never inferred automatically')
    args = parser.parse_args(argv)
    if not math.isfinite(args.duration) or args.duration < 0:
        parser.error('--duration must be finite and nonnegative')
    shell = None
    try:
        scenario = args.scenario or choose('Capture scenario',
                    [('PYNQ-Z2 Local Loop', 'loop'), ('Capture External HDMI Signal', 'external')])
        print('Connect the PYNQ Micro-B USB data cable and Ethernet to this PC. Power on the board.')
        if scenario == 'loop':
            print('Connect HDMI OUT (J9) to HDMI IN (J10).')
        else:
            print('Connect the PC HDMI output to PYNQ HDMI IN (J10); leave J9 disconnected.')
        port = serial_port(args.serial_port)
        if not args.no_terminal:
            open_terminal(port)
        shell = SerialShell(port)
        # A unique shell response proves login; a login prompt cannot execute this probe.
        shell.command('true', timeout=5)
        shell.command('sudo -n true', timeout=5)
        remote = shell.upload(ROOT / 'tools/pynq_capture_runtime.py')
        discover = ['/usr/bin/python3', remote, '--action', 'discover']
        if args.board_root:
            discover += ['--root', args.board_root]
        info = response(shell.command(shlex.join(discover)))
        if not info['runtimes'] and not args.runtime:
            raise RuntimeError('Board capture software is not installed. Complete docs/quickstart.md first.')
        runtime = args.runtime or info['runtimes'][-1]
        profile = select_profile(info, scenario, args.external_mode)
        receipt = info['state'] + '/' + profile['mode'] + '-prepared.json'
        common = ['sudo', '-n', 'env', 'XILINX_XRT=/usr', 'PYTHONPATH=' + runtime,
                  BOARD_PYTHON, '-u', '-X', 'faulthandler', remote,
                  '--profile', json.dumps(profile), '--receipt', receipt,
                  '--previous', json.dumps(info['receipts'])]
        print('Preparing the board…')
        prepare = common + ['--action', 'prepare'] + (['--after-reset'] if args.after_reset else [])
        prepared = response(shell.command(shlex.join(prepare)))
        common[common.index('--previous') + 1] = json.dumps([prepared['receipt']])
        common[common.index('--receipt') + 1] = prepared['receipt']
        if scenario == 'external':
            from .modes import get_mode
            mode = get_mode(profile['mode'])
            print(f'On the PC, enable the HDMI display at {mode.width}×{mode.height} near {mode.refresh_hz:g} Hz.')
            print('Choose Mirror for your desktop, or Extend and move content onto that display.')
            input('When the HDMI output is stable, press Enter: ')
        settings = load_settings()
        suggested = args.host or settings.get('host') or address_for_host(info['addresses'])
        host = args.host or input(f'Board Ethernet address [{suggested}]: ').strip() or suggested
        if host in ('127.0.0.1', 'localhost', '::1'):
            raise RuntimeError('Use the board Ethernet address, not this PC\'s localhost address.')
        ready_seen = False

        def ready(text):
            nonlocal ready_seen
            if ready_seen:
                return
            for line in text.splitlines():
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if isinstance(event, dict) and 'listening' in event:
                    save_settings(dict(host=host, port=args.port, scenario=scenario))
                    ready_seen = True
                    print('\nCapture is ready. In a second PC terminal run:')
                    print('  .venv/bin/python Start-Host-PC-Capture.py')
                    print('Keep this terminal open. Press Ctrl+C once here to stop capture safely.')

        capture = common + ['--action', 'capture', '--port', str(args.port), '--duration', str(args.duration)]
        print('Checking HDMI input and starting capture…')
        shell.command(shlex.join(capture), timeout=None, ready=ready, cancellable=True)
        if not ready_seen:
            raise RuntimeError(f'Capture ended before becoming ready. Details: {shell.log}')
        print('Board capture stopped. You can close this terminal.')
        return 0
    except (RuntimeError, OSError, EOFError, KeyboardInterrupt) as error:
        print(f'Capture launcher: {error}', file=sys.stderr)
        return 1
    finally:
        if shell is not None:
            shell.close()


def host_main(argv=None):
    parser = argparse.ArgumentParser(description='Run on the PC: open the viewer for the prepared PYNQ-Z2 session.')
    parser.add_argument('--host', help='Override the saved board address')
    parser.add_argument('--port', type=port_number, help='Override the saved TCP port')
    parser.add_argument('--timeout', type=float, default=5)
    args = parser.parse_args(argv)
    settings = load_settings()
    host = args.host or settings.get('host')
    if not host:
        print('First run Start-PYNQ-Z2-Captrue.py and wait for “Capture is ready”.', file=sys.stderr)
        return 1
    if host in ('127.0.0.1', 'localhost', '::1'):
        print('Use the PYNQ-Z2 Ethernet address, not localhost.', file=sys.stderr)
        return 1
    from .viewer import main as viewer_main
    return viewer_main([host, '--port', str(args.port or settings.get('port', 9020)),
                        '--timeout', str(args.timeout)])
