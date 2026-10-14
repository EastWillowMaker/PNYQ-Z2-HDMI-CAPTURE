import pytest

from hdmi_capture.protocol import Frame, ProtocolError
from tools.check_capture_reconnect import parser, run
from tools.hdmi_pattern import pattern


def execute(tmp_path, frames):
    now = [0.0]
    args = parser().parse_args(["unused", "--output", str(tmp_path / "report.json"),
                              "--reconnect-frames", "2"])
    sequence = iter(frames)

    class Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def read(self, **k):
            now[0] += 0.1
            item = next(sequence)
            if isinstance(item, BaseException):
                raise item
            return item

    def sleep(seconds):
        now[0] += seconds

    return run(args, client_factory=Client, clock=lambda: now[0], sleep=sleep)


def frame(i):
    return Frame(pattern(i), dict(frame_id=i, session_id="test", source_origin="hdmi", counters={
        "network_errors": i, "acquired": i*10, "source_skips": None}))


def test_pause_reconnect_distinct_and_counter_deltas(tmp_path):
    report = execute(tmp_path, [frame(1), frame(2), frame(3)])
    assert report["passed"]
    assert report["actual_pause_seconds"] == 8
    assert report["distinct_exact_optical_frames"] == 3
    assert report["counter_deltas"] == {"network_errors": 2, "acquired": 20}
    assert report["detected_errors"] == 0


def test_crc_protocol_error_never_silently_retried(tmp_path):
    report = execute(tmp_path, [frame(1), ProtocolError("CRC mismatch")])
    assert not report["passed"]
    assert report["detected_errors"] == 1
    assert "CRC" in report["error"]


def test_single_client_guard_eof_is_recorded_then_retried(tmp_path):
    report = execute(tmp_path, [frame(1), EOFError("guard closes"), frame(2), frame(3)])
    assert report["passed"]
    assert report["reconnect_attempts"][0]["status"] == "failed"
    assert report["reconnect_attempts"][1]["status"] == "connected"


def test_repeat_does_not_pass_as_fresh(tmp_path):
    report = execute(tmp_path, [frame(1), frame(1), frame(2)])
    assert not report["passed"]
    assert report["repeated_optical_frames"] == 1
