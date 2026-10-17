import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from hdmi_capture import launchers
from hdmi_capture import prepared, sources

spec = importlib.util.spec_from_file_location('pynq_capture_runtime',
    Path(__file__).resolve().parents[1] / 'tools/pynq_capture_runtime.py')
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


def test_settings_round_trip_and_invalid_file(tmp_path):
    path = tmp_path / 'nested/connection.json'
    assert launchers.load_settings(path) == {}
    data = dict(host='fe80::1234%eth0', port=9043, scenario='loop')
    launchers.save_settings(data, path)
    assert launchers.load_settings(path) == data
    path.write_text('[]')
    assert launchers.load_settings(path) == {}


def test_host_uses_saved_board_endpoint(monkeypatch):
    import hdmi_capture.viewer as viewer
    calls = []
    monkeypatch.setattr(launchers, 'load_settings', lambda: dict(host='fe80::1%eth0', port=9043))
    monkeypatch.setattr(viewer, 'main', lambda args: calls.append(args) or 0)
    assert launchers.host_main([]) == 0
    assert calls == [['fe80::1%eth0', '--port', '9043', '--timeout', '5']]
    assert launchers.host_main(['--host', 'pynq', '--port', '9021']) == 0
    assert calls[-1][:3] == ['pynq', '--port', '9021']


@pytest.mark.parametrize('settings', [{}, {'host': '127.0.0.1'}, {'host': '::1'}])
def test_host_refuses_missing_or_local_endpoint(settings, monkeypatch):
    monkeypatch.setattr(launchers, 'load_settings', lambda: settings)
    assert launchers.host_main([]) == 1


def test_select_profile_never_uses_rx_only_for_loop():
    rx = dict(mode='1080p30', loop=False, bitfile='rx')
    vga = dict(mode='vga', loop=False, bitfile='vga')
    loop = dict(mode='1080p30', loop=True, bitfile='loop')
    assert launchers.select_profile(dict(profiles=[rx, vga, loop]), 'loop') == loop
    assert launchers.select_profile(dict(profiles=[rx, vga, loop]), 'external', 'vga') == vga
    with pytest.raises(RuntimeError, match='No 1080p30'):
        launchers.select_profile(dict(profiles=[rx, vga]), 'loop')


class FakeSerial:
    def __init__(self, reads):
        self.reads = iter(reads)
        self.writes = []

    def write(self, data):
        self.writes.append(data)

    def read(self, size):
        item = next(self.reads)
        if isinstance(item, BaseException):
            raise item
        return item


def shell(tmp_path, monkeypatch, reads):
    monkeypatch.setattr(launchers.uuid, 'uuid4', lambda: SimpleNamespace(hex='fixed'))
    obj = object.__new__(launchers.SerialShell)
    obj.port = FakeSerial(reads)
    obj.log = tmp_path / 'serial.log'
    return obj


def test_serial_does_not_accept_echo_as_completion(tmp_path, monkeypatch):
    obj = shell(tmp_path, monkeypatch, [b'printf "\\nPYNQ_DONE_fixed:%s\\n" "$?"\r\n',
                                       b'actual response\r\nPYNQ_DONE_fixed:0\r\n'])
    result = obj.command('true')
    assert 'actual response' in result
    assert len(obj.port.writes) == 1


def test_serial_forwards_only_one_interrupt_then_waits(tmp_path, monkeypatch):
    obj = shell(tmp_path, monkeypatch, [KeyboardInterrupt(), KeyboardInterrupt(),
                                       b'safe cleanup\r\nPYNQ_DONE_fixed:0\r\n'])
    obj.command('capture', timeout=None, cancellable=True)
    assert obj.port.writes.count(b'\x03') == 1


def test_serial_timeout_does_not_signal_or_retry(tmp_path, monkeypatch):
    obj = shell(tmp_path, monkeypatch, [b''])
    ticks = iter([0, 10])
    monkeypatch.setattr(launchers.time, 'monotonic', lambda: next(ticks))
    with pytest.raises(RuntimeError, match='may still be running'):
        obj.command('capture', timeout=1)
    assert len(obj.port.writes) == 1


def test_upload_wraps_lines_below_tty_limit(tmp_path):
    obj = object.__new__(launchers.SerialShell)
    commands = []
    obj.command = lambda text: commands.append(text)
    source = tmp_path / 'helper.py'
    source.write_text('print("hello")\n' * 1000)
    destination = obj.upload(source)
    assert destination.startswith('/tmp/pynq-capture-launcher-')
    assert max(map(len, commands[0].splitlines())) < 1024
    assert 'base64 -d' in commands[0]


@pytest.fixture
def fake_board(tmp_path, monkeypatch):
    events = []
    manifest = tmp_path / 'old.json'
    manifest.write_text(json.dumps({'capture_mode': 'vga'}))
    receipt = tmp_path / 'old-prepared.json'
    receipt.write_text(json.dumps({'artifacts': {
        'bitfile': {'path': str(tmp_path / 'old.bit')},
        'manifest': {'path': str(manifest)}}}))
    profile = dict(mode='1080p30', bitfile=str(tmp_path / 'new.bit'),
                   manifest=str(tmp_path / 'new.json'))

    class Source:
        def __init__(self, bitfile, manifest, **kwargs):
            self.bitfile, self.manifest_path = bitfile, manifest

    monkeypatch.setattr(runtime, 'reject_capture_processes', lambda: events.append('process_guard'))
    monkeypatch.setattr(sources, 'LiteXCreditSource', Source)
    monkeypatch.setattr(sources, 'verify_litex_artifacts', lambda *a, **k: events.append('artifacts'))
    monkeypatch.setattr(prepared, '_attach_metadata', lambda *a, **k: events.append('old_idle'))
    monkeypatch.setattr(prepared, '_check_sdk_shutdown', lambda: events.append('sdk'))
    monkeypatch.setattr(sources.LiteXSource, 'load_overlay', lambda *a, **k: events.append(('load', k)))
    monkeypatch.setattr(prepared, 'prepare', lambda *a, **k: events.append(('prepare', k)))
    return SimpleNamespace(events=events, receipt=receipt, profile=profile, tmp=tmp_path)


def test_switch_proves_old_idle_before_new_programming(fake_board):
    b = fake_board
    target = b.tmp / 'new-prepared.json'
    assert runtime.prepare_profile(b.profile, target, [str(b.receipt)]) == str(target)
    assert b.events == ['process_guard', 'artifacts', 'old_idle', 'sdk',
                        ('load', dict(download=True, video_drivers=False)),
                        ('prepare', dict(after_reset=True))]


def test_unverified_old_image_never_downloads(fake_board, monkeypatch):
    def reject(*args, **kwargs):
        raise sources.SourceError('DMA is active')
    monkeypatch.setattr(prepared, '_attach_metadata', reject)
    b = fake_board
    with pytest.raises(RuntimeError, match='No valid idle-board receipt'):
        runtime.prepare_profile(b.profile, b.tmp / 'new-prepared.json', [str(b.receipt)])
    assert b.events == ['process_guard', 'artifacts']


def test_matching_image_uses_normal_prepare(fake_board):
    b = fake_board
    record = json.loads(b.receipt.read_text())['artifacts']
    profile = dict(mode='vga', bitfile=record['bitfile']['path'], manifest=record['manifest']['path'])
    assert runtime.prepare_profile(profile, b.tmp / 'new-prepared.json', [str(b.receipt)]) == str(b.receipt)
    assert b.events[-1] == ('prepare', {})
    assert not any(isinstance(event, tuple) and event[0] == 'load' for event in b.events)


def test_after_reset_is_explicit_not_receipt_fallback(fake_board):
    b = fake_board
    with pytest.raises(RuntimeError):
        runtime.prepare_profile(b.profile, b.tmp / 'missing', [])
    assert not any(isinstance(event, tuple) for event in b.events)
    runtime.prepare_profile(b.profile, b.tmp / 'fresh', [], after_reset=True)
    assert b.events[-1] == ('prepare', dict(after_reset=True))


@pytest.mark.parametrize('edges,invalid', [(0, 0), (60, 0), (30, 1)])
def test_bad_input_blocks_native_start(fake_board, monkeypatch, edges, invalid):
    b = fake_board
    snapshots = iter([dict(snapshot_end_ns=0, native_vsync_edges=0),
                      dict(snapshot_end_ns=10**9, native_vsync_edges=edges, invalid_frames=invalid)])

    class Source:
        def __init__(self, *args, **kwargs):
            self.control = SimpleNamespace(snapshot=lambda: next(snapshots))

    monkeypatch.setattr(sources, 'LiteXCreditSource', Source)
    monkeypatch.setattr(prepared, '_hardware', lambda *a, **k: None)
    with pytest.raises(RuntimeError, match='HDMI input'):
        runtime.check_input(b.profile, str(b.receipt), sleep=lambda _: None)


def test_stable_input_cadence_allows_counter_wrap(fake_board, monkeypatch):
    snapshots = iter(dict(snapshot_end_ns=i * 10**9, native_vsync_edges=(2**32 - 10 + i * 30) % 2**32)
                     for i in range(6))

    class Source:
        def __init__(self, *args, **kwargs):
            self.control = SimpleNamespace(snapshot=lambda: next(snapshots))

    monkeypatch.setattr(sources, 'LiteXCreditSource', Source)
    monkeypatch.setattr(prepared, '_hardware', lambda *a, **k: None)
    runtime.check_input(fake_board.profile, str(fake_board.receipt), sleep=lambda _: None)


def test_process_guard_ignores_own_sudo_ancestors_but_rejects_other_capture(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime.os, 'getpid', lambda: 100)
    for pid, parent in [(100, 99), (99, 0)]:
        process = tmp_path / str(pid)
        process.mkdir()
        (process / 'status').write_text(f'PPid:\t{parent}\n')
        (process / 'cmdline').write_bytes(b'sudo\0python\0helper.py\0--action\0capture\0')
    runtime.reject_capture_processes(tmp_path)
    other = tmp_path / '200'
    other.mkdir()
    (other / 'cmdline').write_bytes(b'python\0helper.py\0--action\0capture\0')
    with pytest.raises(RuntimeError, match='Another capture'):
        runtime.reject_capture_processes(tmp_path)


@pytest.mark.parametrize('scenario,mode', [('loop', '1080p30'), ('external', '1080p60')])
def test_board_workflow_saves_endpoint_only_after_listening(scenario, mode, monkeypatch):
    commands, saved = [], []
    info = dict(runtimes=['/board/src'], profiles=[dict(mode=mode, loop=scenario == 'loop',
                bitfile='/board/overlay/capture.bit', manifest='/board/overlay/build-manifest.json')],
                state='/board/state', receipts=['/board/prepared.json'], addresses=['192.0.2.10'])

    class Shell:
        def __init__(self, port):
            assert port == 'UART'

        def upload(self, source):
            return '/tmp/helper.py'

        def close(self):
            commands.append('closed')

        def command(self, command, **kwargs):
            commands.append(command)
            if '--action discover' in command:
                return 'PYNQ_LAUNCHER_JSON:' + json.dumps(info)
            if '--action prepare' in command:
                return 'PYNQ_LAUNCHER_JSON:' + json.dumps(dict(receipt='/board/state/prepared.json'))
            if '--action capture' in command:
                assert saved == []
                kwargs['ready']('{"listening":["::",9043]}\n')
            return ''

    monkeypatch.setattr(launchers, 'SerialShell', Shell)
    monkeypatch.setattr(launchers, 'serial_port', lambda p: 'UART')
    monkeypatch.setattr(launchers, 'open_terminal', lambda p: commands.append('miniterm'))
    monkeypatch.setattr(launchers, 'load_settings', lambda: {})
    monkeypatch.setattr(launchers, 'save_settings', lambda data: saved.append(data))
    monkeypatch.setattr('builtins.input', lambda prompt: '')
    assert launchers.board_main(['--scenario', scenario, '--host', '192.0.2.10',
                                 '--port', '9043', '--after-reset']) == 0
    assert commands[0] == 'miniterm'
    assert saved == [dict(host='192.0.2.10', port=9043, scenario=scenario)]
    prepare_command = next(c for c in commands if '--action prepare' in c)
    capture_command = next(c for c in commands if '--action capture' in c)
    assert '--after-reset' in prepare_command
    assert '--after-reset' not in capture_command
    assert 'synthetic' not in capture_command
    assert commands[-1] == 'closed'


def test_single_line_sudo_and_status_share_one_shell_command(tmp_path, monkeypatch):
    obj = shell(tmp_path, monkeypatch, [b'\r\nPYNQ_DONE_fixed:0\r\n'])
    obj.command('sudo -n true')
    assert obj.port.writes[0].startswith(b'sudo -n true; printf ')


def test_miniterm_uses_same_uart_and_never_receives_a_password(monkeypatch):
    calls = []
    monkeypatch.setattr(launchers.subprocess, 'run',
                        lambda args: calls.append(args) or SimpleNamespace(returncode=0))
    launchers.open_terminal('UART')
    assert calls == [[sys.executable, '-m', 'serial.tools.miniterm', 'UART', '115200',
                      '--raw', '--eol', 'CR', '--dtr', '0', '--rts', '0']]


def test_stable_external_input_accepts_unchanged_startup_invalid_count(fake_board, monkeypatch):
    snapshots = iter(dict(snapshot_end_ns=i * 10**9, native_vsync_edges=i * 60,
                          invalid_frames=1, frontend_overflow_episodes=0,
                          frontend_underflow_episodes=0) for i in range(6))

    class Source:
        def __init__(self, *args, **kwargs):
            self.control = SimpleNamespace(snapshot=lambda: next(snapshots))

    monkeypatch.setattr(sources, 'LiteXCreditSource', Source)
    monkeypatch.setattr(prepared, '_hardware', lambda *a, **k: None)
    profile = dict(fake_board.profile, mode='vga')
    runtime.check_input(profile, str(fake_board.receipt), sleep=lambda _: None)


def test_capture_attaches_prepared_image_without_reloading(tmp_path, monkeypatch):
    import hdmi_capture.sender as sender
    events = []

    def forbidden(*args, **kwargs):
        pytest.fail('Capture must not reload FPGA after PC display readiness')

    monkeypatch.setattr(runtime, 'prepare_profile', forbidden)
    monkeypatch.setattr(runtime, 'reject_capture_processes', lambda: events.append('process_guard'))
    monkeypatch.setattr(runtime, 'check_input', lambda profile, receipt: events.append(('input', str(receipt))))
    monkeypatch.setattr(sender, 'main', lambda args: events.append(('sender', args)))
    receipt = tmp_path / 'prepared.json'
    runtime.main(['--action', 'capture', '--profile', json.dumps(dict(mode='vga', bitfile='bit', manifest='manifest')),
                  '--receipt', str(receipt)])
    assert events[0:2] == ['process_guard', ('input', str(receipt))]
    assert events[-1][0] == 'sender'
    assert events[-1][1][events[-1][1].index('--prepared-receipt') + 1] == str(receipt)


def test_external_default_requires_1080p60_without_silent_vga_fallback():
    vga = dict(mode='vga', loop=False, bitfile='vga')
    full_hd = dict(mode='1080p60', loop=False, bitfile='full-hd')
    assert launchers.select_profile(dict(profiles=[full_hd, vga]), 'external') == full_hd
    with pytest.raises(RuntimeError, match='No 1080p60'):
        launchers.select_profile(dict(profiles=[vga]), 'external')
