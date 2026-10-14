import json
import socket
import time
import zlib

import numpy as np
import pytest

from hdmi_capture.protocol import (
    FrameEOF, MAGIC, MAX_METADATA_BYTES, MAX_PAYLOAD_BYTES, PREFIX,
    ProtocolError, VERSION, encode_frame, read_frame, send_frame,
)


def metadata(width=5, height=3):
    return dict(width=width, height=height, pixel_format="RGB888", stride=width * 3,
                frame_id=7, timestamp_ns=1234, timestamp_clock="board_monotonic",
                timestamp_sample_point="readframe_return", flags=[],
                source_origin="synthetic", source_color_format="RGB",
                source_quantization_range="unknown", baseline_only=True)


def pixels():
    y, x = np.indices((3, 5))
    return np.stack((x * 11, y * 29, x + y * 5 + 97), axis=-1).astype(np.uint8)


class Stream:
    """Byte-stream fixture with explicit fragmentation and injected failures."""
    def __init__(self, data=b"", chunk=7, timeout=1, delay=0):
        self.data = bytearray(data)
        self.chunk = chunk
        self.timeout = timeout
        self.written = bytearray()
        self.read_sizes = []
        self.delay = delay

    def gettimeout(self):
        return self.timeout

    def settimeout(self, value):
        self.timeout = value

    def recv_into(self, view):
        self.read_sizes.append(len(view))
        if self.delay:
            time.sleep(self.delay)
        count = min(len(view), self.chunk, len(self.data))
        view[:count] = self.data[:count]
        del self.data[:count]
        return count

    def send(self, view):
        count = min(len(view), self.chunk)
        self.written.extend(view[:count])
        return count


def packet(meta, payload=None, raw_header=None):
    payload = pixels().tobytes() if payload is None else payload
    header = json.dumps(meta).encode() if raw_header is None else raw_header
    return PREFIX.pack(MAGIC, VERSION, len(header), len(payload), zlib.crc32(payload)) + header + payload


@pytest.mark.parametrize("chunk", [1, 3, 19, 9999])
def test_fragmentation_coalescing_and_channel_order(chunk):
    rgb = pixels()
    first = encode_frame(rgb, metadata())
    other = metadata()
    other["frame_id"] += 1
    sock = Stream(first + encode_frame(rgb + 1, other), chunk=chunk)
    frame = read_frame(sock)
    np.testing.assert_array_equal(frame.rgb, rgb)
    assert frame.rgb.dtype == np.uint8 and frame.rgb.flags.writeable
    assert frame.metadata == metadata()
    np.testing.assert_array_equal(read_frame(sock).rgb, rgb + 1)
    assert sock.timeout == 1
    assert not sock.data


def test_noncontiguous_sender_packs_rows_without_color_conversion():
    rgb = pixels()[:, ::-1]
    sock = Stream(chunk=2)
    send_frame(sock, rgb, metadata())
    np.testing.assert_array_equal(read_frame(Stream(sock.written)).rgb, rgb)


@pytest.mark.parametrize("cut", [0, 1, 19, 20, 21, 100, -1])
def test_eof_at_every_frame_stage(cut):
    data = encode_frame(pixels(), metadata())
    with pytest.raises(FrameEOF):
        read_frame(Stream(data[:cut]))


def test_crc_detects_payload_damage():
    data = bytearray(encode_frame(pixels(), metadata()))
    data[-1] ^= 128
    with pytest.raises(ProtocolError, match="CRC32"):
        read_frame(Stream(data))


@pytest.mark.parametrize("key,value", [
    ("width", True), ("height", 0), ("width", 1921), ("height", 1081),
    ("stride", 16), ("stride", True), ("frame_id", -1), ("frame_id", 1 << 64),
    ("timestamp_ns", False), ("pixel_format", "BGR888"), ("flags", "ok"),
    ("flags", [1]), ("timestamp_clock", ""), ("source_origin", "camera"),
    ("baseline_only", 1), ("source_quantization_range", "guess"),
    ("source_color_format", None), ("timestamp_sample_point", ""),
])
def test_sender_and_receiver_reject_invalid_contract(key, value):
    meta = metadata()
    meta[key] = value
    with pytest.raises(ProtocolError):
        encode_frame(pixels(), meta)
    sock = Stream(packet(meta))
    with pytest.raises(ProtocolError):
        read_frame(sock)
    # Reader leaves every payload byte unread, validating before allocation.
    assert bytes(sock.data) == pixels().tobytes()


@pytest.mark.parametrize("header", [b"[]", b"{}", b"null", b"{", b"\xff",
                                       b'{"width":5,"width":5}',
                                       b'{"extra":NaN}', b'{"extra":Infinity}'])
def test_invalid_json_and_duplicate_keys(header):
    with pytest.raises(ProtocolError):
        read_frame(Stream(packet({}, raw_header=header)))


@pytest.mark.parametrize("field,value", [(0, b"NOPE"), (1, 2),
                                           (2, 0), (2, MAX_METADATA_BYTES + 1),
                                           (3, 0), (3, MAX_PAYLOAD_BYTES + 1)])
def test_bad_prefix_rejected_before_body_read(field, value):
    fields = [MAGIC, VERSION, 1, 3, 0]
    fields[field] = value
    sock = Stream(PREFIX.pack(*fields) + b"body")
    with pytest.raises(ProtocolError):
        read_frame(sock)
    assert sock.data == b"body"


def test_reserved_prefix_bytes_rejected():
    data = bytearray(encode_frame(pixels(), metadata()))
    data[5] = 1
    with pytest.raises(ProtocolError):
        read_frame(Stream(data))


@pytest.mark.parametrize("extra", [float("nan"), float("inf"), object(), {1: "x"}])
def test_sender_rejects_non_json_extensions(extra):
    meta = metadata()
    meta["extra"] = extra
    with pytest.raises(ProtocolError):
        encode_frame(pixels(), meta)


def test_metadata_limit_and_shape_mismatch():
    meta = metadata()
    meta["extra"] = "x" * MAX_METADATA_BYTES
    with pytest.raises(ProtocolError):
        encode_frame(pixels(), meta)
    with pytest.raises(ProtocolError):
        encode_frame(pixels()[:, :4], metadata())
    with pytest.raises(ProtocolError):
        encode_frame(pixels().astype(np.float32), metadata())


def test_timeout_is_total_frame_deadline_and_restored():
    sock = Stream(encode_frame(pixels(), metadata()), chunk=1, timeout=.01, delay=.002)
    with pytest.raises(socket.timeout):
        read_frame(sock)
    assert sock.timeout == .01


def test_actual_socket_timeout_and_eof():
    sender, receiver = socket.socketpair()
    try:
        receiver.settimeout(.01)
        with pytest.raises(socket.timeout):
            read_frame(receiver)
        assert receiver.gettimeout() == .01
        sender.close()
        with pytest.raises(FrameEOF):
            read_frame(receiver)
    finally:
        sender.close()
        receiver.close()


def test_actual_socket_roundtrip_and_frame_storage_independence():
    sender, receiver = socket.socketpair()
    try:
        sender.settimeout(1)
        receiver.settimeout(1)
        send_frame(sender, pixels(), metadata())
        first = read_frame(receiver)
        send_frame(sender, pixels() + 1, metadata())
        second = read_frame(receiver)
        second.rgb[:] = 0
        np.testing.assert_array_equal(first.rgb, pixels())
        assert sender.gettimeout() == 1 and receiver.gettimeout() == 1
    finally:
        sender.close()
        receiver.close()


def test_zero_send_means_disconnect():
    with pytest.raises(FrameEOF):
        send_frame(Stream(chunk=0), pixels(), metadata())


def test_json_numeric_overflow_and_nested_duplicate_keys():
    header = json.dumps(metadata()).encode()
    for extra in (b'"extra":1e999', b'"extra":{"key":1,"key":2}'):
        with pytest.raises(ProtocolError):
            read_frame(Stream(packet({}, raw_header=header[:-1] + b"," + extra + b"}")))
