import os
import threading
import time

import numpy as np
import pytest

from hdmi_capture.protocol import Frame, encode_frame
from hdmi_capture.viewer import CaptureViewer, CaptureWorker, LatestFrameStore, main
from test_client import metadata, server


def make_frame(frame_id, value=None):
    if value is None:
        value = frame_id
    return Frame(np.full((2, 3, 3), value, dtype=np.uint8), {"frame_id": frame_id})


def wait_finished(worker, timeout=2.0):
    deadline = time.monotonic() + timeout
    while worker.is_alive and time.monotonic() < deadline:
        time.sleep(0.005)
    assert not worker.is_alive


def test_worker_keeps_only_latest_frame_and_has_one_reader_thread():
    frame_count = 100
    reader_threads = []

    class FiniteClient:
        def __init__(self, host, port, *, timeout):
            self.next_id = 0

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def read(self):
            reader_threads.append(threading.get_ident())
            if self.next_id == frame_count:
                raise EOFError("test stream ended")
            frame = make_frame(self.next_id)
            self.next_id += 1
            return frame

    worker = CaptureWorker("127.0.0.1", 9020, client_factory=FiniteClient)
    worker.start()
    wait_finished(worker)

    revision, latest = worker.frames.current()
    state = worker.snapshot()
    assert revision == frame_count + 1  # includes the clear performed at start
    assert state.frame_count == frame_count
    assert not state.connected
    assert state.finished
    assert state.error.startswith("EOFError: test stream ended")
    assert latest.metadata["frame_id"] == frame_count - 1
    np.testing.assert_array_equal(latest.rgb, np.full((2, 3, 3), frame_count - 1, dtype=np.uint8))
    assert len(set(reader_threads)) == 1


def test_worker_does_not_retry_a_fault_until_explicit_restart():
    calls = []

    class FailingClient:
        def __init__(self, host, port, *, timeout):
            calls.append((host, port, timeout))

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def read(self):
            raise ConnectionError("link lost")

    worker = CaptureWorker("board", 9020, client_factory=FailingClient)
    worker.start()
    wait_finished(worker)
    assert calls == [("board", 9020, 5.0)]
    assert "link lost" in worker.snapshot().error

    worker.start()
    wait_finished(worker)
    assert calls == [("board", 9020, 5.0), ("board", 9020, 5.0)]


def test_worker_uses_real_capture_client_over_local_tcp():
    first = np.arange(24, dtype=np.uint8).reshape(2, 4, 3)
    second = np.full((2, 4, 3), [17, 93, 241], dtype=np.uint8)
    with server([encode_frame(first, metadata(1)), encode_frame(second, metadata(2))]) as port:
        worker = CaptureWorker("127.0.0.1", port, timeout=2.0)
        worker.start()
        wait_finished(worker)

    state = worker.snapshot()
    _, latest = worker.frames.current()
    assert state.frame_count == 2
    assert not state.connected
    np.testing.assert_array_equal(latest.rgb, second)
    assert latest.metadata["frame_id"] == 2


def test_freeze_latest_requires_live_connection_and_keeps_copy():
    entered_read = threading.Event()
    release_read = threading.Event()
    original = make_frame(8, 18)

    class HeldClient:
        def __init__(self, host, port, *, timeout):
            self.calls = 0

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def read(self):
            self.calls += 1
            if self.calls == 1:
                return original
            entered_read.set()
            release_read.wait(1)
            raise EOFError("released")

    worker = CaptureWorker("board", 9020, client_factory=HeldClient)
    assert worker.freeze_latest() is None
    worker.start()
    assert entered_read.wait(1)
    frozen = worker.freeze_latest()
    assert frozen is not None
    assert frozen is not original
    assert frozen.rgb is not original.rgb

    original.rgb.fill(77)
    assert frozen.metadata["frame_id"] == 8
    np.testing.assert_array_equal(frozen.rgb, np.full((2, 3, 3), 18, dtype=np.uint8))
    worker.request_stop()
    release_read.set()
    wait_finished(worker)
    assert worker.freeze_latest() is None


def test_viewer_help_does_not_require_optional_gui_dependencies(capsys):
    with pytest.raises(SystemExit) as error:
        main(["--help"])
    assert error.value.code == 0
    assert "--timeout" in capsys.readouterr().out


def test_tk_window_smoke_and_waits_for_save_if_display_is_available(monkeypatch, tmp_path):
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        pytest.skip("no display is configured")
    tk = pytest.importorskip("tkinter")
    pytest.importorskip("PIL.ImageTk")
    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f"configured display is unavailable: {error}")

    clients = []

    class FailingClient:
        def __init__(self, host, port, *, timeout):
            self.reading = threading.Event()
            self.release = threading.Event()
            self.sent_frame = False
            clients.append(self)

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def read(self):
            if not self.sent_frame:
                self.sent_frame = True
                return make_frame(12, 54)
            self.reading.set()
            self.release.wait(2)
            raise EOFError("smoke test stopped")

    viewer = CaptureViewer(root, "board", 9020, timeout=0.1, client_factory=FailingClient)
    deadline = time.monotonic() + 1
    while time.monotonic() < deadline:
        state = viewer.worker.snapshot()
        if state.connected and viewer.worker.frames.current()[1] is not None:
            break
        time.sleep(0.005)
    assert viewer.worker.snapshot().connected

    save_started = threading.Event()
    save_release = threading.Event()
    save_threads = []

    def delayed_save(frame, path):
        save_threads.append(threading.get_ident())
        save_started.set()
        assert frame.metadata["frame_id"] == 12
        assert str(path).endswith("saved.bmp")
        save_release.wait(2)

    monkeypatch.setattr("hdmi_capture.viewer.save_bmp", delayed_save)
    monkeypatch.setattr(viewer._filedialog, "asksaveasfilename", lambda **_: str(tmp_path / "saved.bmp"))
    viewer.save_current()
    assert save_started.wait(1)
    assert str(viewer.save_button.cget("state")) == "disabled"
    viewer.close()
    deadline = time.monotonic() + 1
    while time.monotonic() < deadline and "Finishing save" not in viewer.status.cget("text"):
        root.update()
        time.sleep(0.005)
    assert root.winfo_exists()
    assert "Finishing save" in viewer.status.cget("text")
    save_release.set()
    clients[0].release.set()
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        try:
            root.update()
            if not root.winfo_exists():
                break
        except tk.TclError:
            break
        time.sleep(0.005)
    try:
        exists = root.winfo_exists()
    except tk.TclError:
        exists = False
    assert not exists
    assert save_threads and save_threads[0] != threading.get_ident()
