"""Trigger an already waiting board sender after fresh KMS presentation evidence."""

import argparse
import json
import math
from pathlib import Path
import shlex
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def _absent(path):
    try:
        path.lstat()
    except FileNotFoundError:
        return True
    return False


def _source_ready(output, started, clock):
    if _absent(output):
        return None
    if output.is_symlink() or not output.is_dir():
        raise ValueError("Source output must arrive as a new directory")
    if any(not _absent(output / name) for name in ("restore.json", "child-result.json")):
        raise ValueError("KMS source has already finished or restored")
    source = output / "source.jsonl"
    if _absent(source):
        return None
    if source.is_symlink() or not source.is_file():
        raise ValueError("Source metadata must be a regular file")
    contents = source.read_text()
    now = clock()
    ready, presentations = None, []
    for line in contents.splitlines(keepends=True):
        if not line.endswith("\n"):
            return None
        try:
            event = json.loads(line)
        except ValueError as error:
            raise ValueError("KMS source reported a diagnostic instead of presentation metadata") from error
        if not isinstance(event, dict):
            raise ValueError("Invalid KMS source metadata")
        if event.get("event") == "kms_ready":
            if ready is not None or any(event.get(key) != value for key, value in
                dict(format="XR24", width=640, height=480, clock_khz=25200).items()):
                raise ValueError("KMS source does not match XR24/640x480/25200")
            ready = event
        elif event.get("event") == "kms_presented":
            if ready is None:
                raise ValueError("KMS presentation preceded readiness")
            frame = event.get("frame_id")
            generated, presented = event.get("generated_monotonic"), event.get("presented_monotonic")
            if (type(frame) is not int or not 0 <= frame <= 0xFFFFFFFF or
                    any(type(value) not in (int, float) or not math.isfinite(value)
                        for value in (generated, presented)) or
                    not started <= generated <= presented <= now or
                    (presentations and (frame <= presentations[-1]["frame_id"] or
                     presented <= presentations[-1]["presented_monotonic"]))):
                raise ValueError("KMS presentation identity or timestamps are invalid")
            presentations.append(event)
        else:
            raise ValueError("Unexpected KMS source event")
    if ready is None or len(presentations) < 2:
        return None
    recent = presentations[-2:]
    if any(now - event["presented_monotonic"] > 2 for event in recent):
        return None
    if any(not _absent(output / name) for name in ("restore.json", "child-result.json")):
        raise ValueError("KMS source finished during readiness checks")
    return dict(ready=ready, presented=recent)


def wait_source_ready(output, timeout=120, *, clock=time.monotonic, sleep=time.sleep, on_waiting=None):
    if not math.isfinite(timeout) or not 0 < timeout <= 900:
        raise ValueError("Source timeout must be finite and in (0, 900]")
    output = Path(output)
    if not _absent(output):
        raise ValueError("Source output must be absent when the trigger starts")
    started = clock()
    deadline = started + timeout
    if on_waiting is not None:
        on_waiting()
    while clock() < deadline:
        evidence = _source_ready(output, started, clock)
        if evidence is not None:
            return evidence
        sleep(min(0.1, max(0, deadline - clock())))
    raise TimeoutError("Timed out waiting for fresh completed KMS presentations")


def marker_command(marker, sender_log, *, sender_timeout=90):
    if type(sender_timeout) is not int or not 1 <= sender_timeout <= 120:
        raise ValueError("Sender timeout must be an integer in [1, 120]")
    for path in (marker, sender_log):
        if not path.startswith("/") or any(ord(character) < 32 or ord(character) == 127 for character in path):
            raise ValueError("Board paths must be absolute paths without ASCII control characters")
    quoted = shlex.quote(marker)
    log = shlex.quote(sender_log)
    waiting = shlex.quote('^{"event": "waiting_for_source",')
    listening = shlex.quote('^{"listening":')
    errors = shlex.quote(r'^Traceback|^[[:alnum:]_.]*(Error|Exception):|^\{"event": "fatal_dma_shutdown_unverified"')
    return (f"( test ! -e {quoted} && test ! -L {quoted} && test -f {log} && test ! -L {log} "
            f"&& grep -q {waiting} {log} || exit 1; "
            f"if grep -q {listening} {log} || grep -Eq {errors} {log}; then exit 1; fi; "
            f"touch -- {quoted} || exit 1; capture_ready_attempt=0; "
            f'while test "$capture_ready_attempt" -lt {math.ceil(sender_timeout / 0.2)}; do '
            f"if grep -Eq {errors} {log}; then exit 1; fi; "
            f"if grep -q {listening} {log}; then grep -m 1 {listening} {log}; exit 0; fi; "
            'capture_ready_attempt=$((capture_ready_attempt + 1)); sleep 0.2; done; exit 1 )')


def trigger(output, marker, log, *, board_sender_log, uart_python=sys.executable,
            board_console=ROOT / "tools/board_console.py", timeout=120, sender_timeout=90,
            clock=time.monotonic, sleep=time.sleep, run=subprocess.run):
    command = marker_command(marker, board_sender_log, sender_timeout=sender_timeout)
    log = Path(log)
    uart_log = log.with_name(log.name + ".uart.log")
    if not _absent(log) or not _absent(uart_log):
        raise ValueError("Trigger and UART logs must be new paths")
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("x") as handle:
        def record(event, **fields):
            handle.write(json.dumps(dict(event=event, monotonic=clock(), **fields)) + "\n")
            handle.flush()
        try:
            evidence = wait_source_ready(output, timeout, clock=clock, sleep=sleep,
                on_waiting=lambda: record("waiting_for_kms", source_output=str(output),
                                         board_marker=marker, board_sender_log=board_sender_log,
                                         sender_timeout_seconds=sender_timeout))
            argv = [str(uart_python), str(board_console), "--command", command,
                    "--timeout", str(sender_timeout + 10), "--log", str(uart_log)]
            result = run(argv, capture_output=True, text=True, timeout=sender_timeout + 20)
            record("board_trigger_result", returncode=result.returncode, **evidence)
            if result.returncode:
                raise RuntimeError("Board marker command failed; inspect the UART log before retrying")
            return evidence
        except BaseException as error:
            record("trigger_failed", error=str(error))
            raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-output", type=Path, required=True)
    parser.add_argument("--board-marker", required=True)
    parser.add_argument("--board-sender-log", required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--sender-timeout", type=int, choices=range(1, 121), default=90,
                        metavar="SECONDS", help="Sender listening wait in seconds (1..120; default: 90)")
    parser.add_argument("--uart-python", type=Path, default=Path(sys.executable))
    parser.add_argument("--board-console", type=Path, default=ROOT / "tools/board_console.py")
    args = parser.parse_args(argv)
    trigger(args.source_output, args.board_marker, args.log, board_sender_log=args.board_sender_log,
            uart_python=args.uart_python,
            board_console=args.board_console, timeout=args.timeout, sender_timeout=args.sender_timeout)


if __name__ == "__main__":
    main()
