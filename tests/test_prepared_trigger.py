import json
from pathlib import Path
import subprocess
import shlex
import threading
import time
from types import SimpleNamespace

import pytest

from tools import trigger_prepared_capture as trigger


@pytest.fixture
def source(tmp_path):
    output, log = tmp_path / "kms-new", tmp_path / "trigger.jsonl"
    state = SimpleNamespace(now=100.0, action=None, calls=[])
    def sleep(seconds):
        state.now += seconds
        if state.action is not None:
            action, state.action = state.action, None
            action()
    def publish(events=None, **ready_changes):
        output.mkdir()
        ready = dict(event="kms_ready", format="XR24", width=640, height=480, clock_khz=25200)
        ready.update(ready_changes)
        now = state.now
        presentations = [dict(event="kms_presented", frame_id=frame,
            generated_monotonic=now - delta - .01, presented_monotonic=now - delta)
            for frame, delta in ((1, .04), (2, .02))]
        (output / "source.jsonl").write_text("".join(json.dumps(event) + "\n"
            for event in ([ready, *presentations] if events is None else events)))
    def run(argv, **kwargs):
        state.calls.append((argv, kwargs))
        return SimpleNamespace(returncode=0)
    def invoke(**kwargs):
        return trigger.trigger(output, "/tmp/capture-ready-new", log, uart_python="/venv/python",
            board_console="/repo/tools/board_console.py", board_sender_log="/tmp/sender-new.log", timeout=kwargs.pop("timeout", .3),
            clock=lambda: state.now, sleep=sleep, run=run, **kwargs)
    return SimpleNamespace(output=output, log=log, state=state, publish=publish, invoke=invoke)


def test_fresh_completed_source_triggers_one_normal_user_marker_command(source):
    source.state.action = source.publish
    evidence = source.invoke()
    assert len(source.state.calls) == 1
    argv, kwargs = source.state.calls[0]
    assert argv[:2] == ["/venv/python", "/repo/tools/board_console.py"]
    assert argv[2:4] == ["--command", trigger.marker_command("/tmp/capture-ready-new", "/tmp/sender-new.log")]
    assert "sudo" not in argv and kwargs == dict(capture_output=True, text=True, timeout=50)
    assert evidence["presented"][-1]["frame_id"] == 2
    assert [json.loads(line)["event"] for line in source.log.read_text().splitlines()] == [
        "waiting_for_kms", "board_trigger_result"]


def test_missing_source_times_out_without_uart(source):
    with pytest.raises(TimeoutError):
        source.invoke()
    assert source.state.calls == [] and not source.output.exists()


@pytest.mark.parametrize("field,value", [("format", "RGB3"), ("width", 800),
                                       ("height", 600), ("clock_khz", 25175)])
def test_wrong_source_geometry_never_sends_uart(source, field, value):
    source.state.action = lambda: source.publish(**{field: value})
    with pytest.raises(ValueError, match="does not match"):
        source.invoke()
    assert source.state.calls == []


@pytest.mark.parametrize("kind", ["directory", "symlink"])
def test_existing_output_is_rejected_without_uart(source, kind):
    if kind == "directory":
        source.output.mkdir()
    else:
        source.output.symlink_to(source.output.with_name("missing"))
    with pytest.raises(ValueError, match="absent"):
        source.invoke()
    assert source.state.calls == []


@pytest.mark.parametrize("finished", ["restore.json", "child-result.json"])
def test_finished_or_restored_source_never_sends_uart(source, finished):
    def finish():
        source.publish()
        (source.output / finished).write_text('{"exit_code":1}')
    source.state.action = finish
    with pytest.raises(ValueError, match="finished|restored"):
        source.invoke()
    assert source.state.calls == []


def test_source_diagnostic_after_presentations_never_sends_uart(source):
    def fail():
        source.publish()
        with (source.output / "source.jsonl").open("a") as output:
            output.write("KMS failure: Invalid argument\n")
    source.state.action = fail
    with pytest.raises(ValueError, match="diagnostic"):
        source.invoke()
    assert source.state.calls == []


def test_presentations_from_before_wait_are_stale(source):
    def stale():
        source.publish()
        path = source.output / "source.jsonl"
        lines = [json.loads(line) for line in path.read_text().splitlines()]
        for event in lines[1:]:
            event["generated_monotonic"] -= 10
            event["presented_monotonic"] -= 10
        path.write_text("".join(json.dumps(event) + "\n" for event in lines))
    source.state.action = stale
    with pytest.raises(ValueError, match="timestamps"):
        source.invoke()
    assert source.state.calls == []


def test_two_presentations_must_both_be_recent(source):
    def stale():
        source.publish()
        source.state.now += 3
    source.state.action = stale
    with pytest.raises(TimeoutError):
        source.invoke(timeout=3.5)
    assert source.state.calls == []


@pytest.mark.parametrize("fault", ["one", "missing_ready", "duplicate", "incomplete"])
def test_incomplete_or_invalid_presentation_evidence_never_sends_uart(source, fault):
    def incomplete():
        source.publish()
        path = source.output / "source.jsonl"
        lines = path.read_text().splitlines(keepends=True)
        if fault == "one":
            lines = lines[:2]
        elif fault == "missing_ready":
            lines = lines[1:]
        elif fault == "duplicate":
            lines[2] = lines[1]
        else:
            lines[2] = lines[2].rstrip()
        path.write_text("".join(lines))
    source.state.action = incomplete
    with pytest.raises((TimeoutError, ValueError)):
        source.invoke()
    assert source.state.calls == []


@pytest.mark.parametrize("marker", ["relative", "/tmp/a\nother", "/tmp/a\r", "/tmp/a\0", "/tmp/a\x1b", "/tmp/a\x7f"])
def test_board_marker_rejects_relative_and_terminal_control_paths(marker):
    with pytest.raises(ValueError, match="absolute paths"):
        trigger.marker_command(marker, "/tmp/sender-new.log")
    with pytest.raises(ValueError, match="absolute paths"):
        trigger.marker_command("/tmp/ready", marker)


def test_forbidden_marker_prevents_logs_and_uart(source):
    with pytest.raises(ValueError, match="absolute paths"):
        trigger.trigger(source.output, "/tmp/ready\x1b[2J", source.log, board_sender_log="/tmp/sender.log",
                        run=lambda *args, **kwargs: pytest.fail("UART command invoked"))
    assert not source.log.exists()


def test_printable_shell_metacharacters_stay_in_literal_paths(tmp_path):
    injected = tmp_path / "unexpected"
    marker = str(tmp_path / "ready;$(touch unexpected)'quoted&")
    log = tmp_path / "sender;$(touch unexpected)'quoted.log"
    log.write_text('{"event": "waiting_for_source", "ready_file": "test"}\n')
    command = trigger.marker_command(marker, str(log))
    client_started = tmp_path / "client-started"
    def listen():
        deadline = time.monotonic() + 2
        while not Path(marker).exists() and time.monotonic() < deadline:
            time.sleep(.01)
        with log.open("a") as output:
            output.write('{"listening": ["::", 9020], "session_id": "new-session"}\n')
    listener = threading.Thread(target=listen)
    listener.start()
    try:
        result = subprocess.run(["/bin/sh", "-c", command + " && touch -- " + shlex.quote(str(client_started))],
                                check=True, cwd=tmp_path,
                                capture_output=True, text=True, timeout=3)
    finally:
        listener.join(timeout=3)
    assert Path(marker).is_file() and not injected.exists()
    assert json.loads(result.stdout)["session_id"] == "new-session"
    assert client_started.exists()
    assert subprocess.run(["/bin/sh", "-c", command], cwd=tmp_path).returncode != 0


@pytest.mark.parametrize("contents", ['{"event": "waiting_for_source", "ready_file": "old"}\n'
    '{"listening": ["::", 9020]}\n', 'Traceback (most recent call last):\n',
    'hdmi_capture.sources.SourceError: rejected\n'])
def test_stale_or_failed_sender_log_prevents_marker_and_client(tmp_path, contents):
    marker, log, client_started = tmp_path / "ready", tmp_path / "sender.log", tmp_path / "client"
    log.write_text(contents)
    command = trigger.marker_command(str(marker), str(log))
    result = subprocess.run(["/bin/sh", "-c", command + " && touch -- " + shlex.quote(str(client_started))])
    assert result.returncode != 0 and not marker.exists() and not client_started.exists()


def test_fresh_output_check_precedes_waiting_log_event(tmp_path):
    output = tmp_path / "new-output"
    observed = []
    with pytest.raises(TimeoutError):
        trigger.wait_source_ready(output, .01, on_waiting=lambda: observed.append(output.exists()))
    assert observed == [False]


def test_existing_logs_prevent_uart_and_are_preserved(source):
    source.log.write_text("previous log")
    with pytest.raises(ValueError, match="new paths"):
        source.invoke()
    assert source.state.calls == [] and source.log.read_text() == "previous log"


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf"), 901])
def test_invalid_timeout_never_sends_uart(source, timeout):
    with pytest.raises(ValueError, match="finite"):
        source.invoke(timeout=timeout)
    assert source.state.calls == []


def test_uart_failure_is_not_retried(source):
    calls = []
    def fail(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(returncode=1)
    def advance(seconds):
        source.state.now += seconds
        if not source.output.exists():
            source.publish()
    with pytest.raises(RuntimeError, match="failed"):
        trigger.trigger(source.output, "/tmp/ready", source.log, board_sender_log="/tmp/sender.log", run=fail,
                        clock=lambda: source.state.now, sleep=advance)
    assert len(calls) == 1
