import socket
import threading
import time
from contextlib import contextmanager

import numpy as np
import pytest

from hdmi_capture import CaptureClient, ProtocolError
from hdmi_capture.protocol import encode_frame


def metadata(frame_id=0, **extra):
    return dict(width=4, height=2, stride=12, pixel_format="RGB888", frame_id=frame_id,
                timestamp_ns=123, timestamp_clock="synthetic_monotonic",
                timestamp_sample_point="frame_created", flags=[], source_origin="synthetic",
                source_color_format="RGB", source_quantization_range="full",
                baseline_only=True, **extra)


RGB = np.arange(24, dtype=np.uint8).reshape(2, 4, 3)


@contextmanager
def server(packets, *, delay=0):
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(2)
    port = listener.getsockname()[1]

    def serve():
        try:
            connection, _ = listener.accept()
            with connection:
                for packet in packets:
                    if delay:
                        time.sleep(delay)
                    connection.sendall(packet)
        except (OSError, TimeoutError):
            pass

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield port
    finally:
        listener.close()
        thread.join(timeout=3)
        assert not thread.is_alive()


def test_real_tcp_owned_arrays_and_mode_change():
    second = np.full((1, 1, 3), [250, 100, 1], dtype=np.uint8)
    changed = metadata(3)
    changed.update(width=1, height=1, stride=3)
    with server([encode_frame(RGB, metadata(1)), encode_frame(second, changed)]) as port:
        with CaptureClient("127.0.0.1", port) as client:
            first = client.read()
            later = client.read()
            np.testing.assert_array_equal(first.rgb, RGB)
            np.testing.assert_array_equal(later.rgb, second)
            later.rgb[:] = 0
            np.testing.assert_array_equal(first.rgb, RGB)
        with pytest.raises(RuntimeError, match="not connected"):
            client.read()


@pytest.mark.parametrize("second_id", [1, 0])
def test_duplicate_or_regressing_frame_poison_connection(second_id):
    with server([encode_frame(RGB, metadata(1)), encode_frame(RGB, metadata(second_id))]) as port:
        with CaptureClient("127.0.0.1", port) as client:
            client.read()
            with pytest.raises(ProtocolError, match="increase"):
                client.read()
            with pytest.raises(RuntimeError, match="not connected"):
                client.read()


def test_corrupt_frame_closes_connection():
    packet = bytearray(encode_frame(RGB, metadata()))
    packet[-1] ^= 1
    with server([packet]) as port:
        with CaptureClient("127.0.0.1", port) as client:
            with pytest.raises(ProtocolError):
                client.read()
            assert client._socket is None


def test_session_change_is_rejected_and_eof_closes_connection():
    with server([encode_frame(RGB, metadata(0, session_id="a")),
                 encode_frame(RGB, metadata(1, session_id="b"))]) as port:
        with CaptureClient("127.0.0.1", port) as client:
            client.read()
            with pytest.raises(ProtocolError, match="session"):
                client.read()
            assert client._socket is None
    with server([]) as port:
        with CaptureClient("127.0.0.1", port) as client:
            with pytest.raises(EOFError):
                client.read()
            assert client._socket is None


def test_absolute_deadline_closes_incomplete_read():
    with server([encode_frame(RGB, metadata())], delay=0.1) as port:
        with CaptureClient("127.0.0.1", port) as client:
            with pytest.raises(TimeoutError):
                client.read(deadline=time.monotonic() + 0.02)
            assert client._socket is None


def test_scoped_ipv6_is_passed_to_socket(monkeypatch):
    seen = []
    sock = socket.socket()
    monkeypatch.setattr(socket, "create_connection", lambda address, timeout: seen.append((address, timeout)) or sock)
    with CaptureClient("[fe80::123%eth0]", 9001, timeout=2):
        pass
    assert seen == [(("fe80::123%eth0", 9001), 2)]


def test_reconnect_starts_new_frame_id_scope():
    client = CaptureClient("127.0.0.1")
    for first_id in (10, 0):
        with server([encode_frame(RGB, metadata(first_id))]) as port:
            client.port = port
            with client:
                assert client.read().metadata["frame_id"] == first_id
