"""Bounded, lossless RGB888 framing over an ordered byte stream."""

from dataclasses import dataclass
import json
import math
import socket
import struct
import time
import zlib

import numpy as np

MAGIC = b"LHDC"
VERSION = 1
PREFIX = struct.Struct(">4sB3xIII")
MAX_METADATA_BYTES = 8192
MAX_WIDTH = 1920
MAX_HEIGHT = 1080
MAX_PAYLOAD_BYTES = MAX_WIDTH * MAX_HEIGHT * 3
MAX_UINT64 = (1 << 64) - 1


class ProtocolError(ValueError):
    """The stream or supplied frame violates the wire contract."""


class FrameEOF(EOFError):
    """The peer closed before a complete frame was received."""


@dataclass(frozen=True)
class Frame:
    """An owned, writable RGB array and its validated metadata."""

    rgb: np.ndarray
    metadata: dict


def _integer(metadata, name, minimum, maximum):
    value = metadata.get(name)
    if type(value) is not int or not minimum <= value <= maximum:
        raise ProtocolError(f"{name} must be an integer in [{minimum}, {maximum}]")
    return value


def _validate_json(value):
    if type(value) is str:
        if len(value) > MAX_METADATA_BYTES:
            raise ProtocolError("Metadata string exceeds protocol bounds")
        return
    if value is None or type(value) in (bool, int):
        return
    if type(value) is float and math.isfinite(value):
        return
    if type(value) is list:
        for child in value:
            _validate_json(child)
        return
    if type(value) is dict and all(type(key) is str for key in value):
        for key in value:
            _validate_json(key)
        for child in value.values():
            _validate_json(child)
        return
    raise ProtocolError("Metadata must contain finite JSON values with string keys")


def _validate_metadata(metadata, payload_length):
    if type(metadata) is not dict:
        raise ProtocolError("Metadata must be a JSON object")
    width = _integer(metadata, "width", 1, MAX_WIDTH)
    height = _integer(metadata, "height", 1, MAX_HEIGHT)
    stride = _integer(metadata, "stride", 3, MAX_WIDTH * 3)
    _integer(metadata, "frame_id", 0, MAX_UINT64)
    _integer(metadata, "timestamp_ns", 0, MAX_UINT64)
    if metadata.get("pixel_format") != "RGB888":
        raise ProtocolError("Only RGB888 is supported")
    if stride != width * 3 or payload_length != stride * height:
        raise ProtocolError("Payload length and packed RGB stride must match dimensions")
    for name in ("timestamp_clock", "timestamp_sample_point", "source_color_format"):
        value = metadata.get(name)
        if type(value) is not str or not value.strip():
            raise ProtocolError(f"{name} must be a nonempty string")
    if metadata.get("source_origin") not in ("synthetic", "hdmi"):
        raise ProtocolError("source_origin must be synthetic or hdmi")
    if metadata.get("source_quantization_range") not in ("unknown", "full", "limited"):
        raise ProtocolError("Invalid source_quantization_range")
    if type(metadata.get("baseline_only")) is not bool:
        raise ProtocolError("baseline_only must be boolean")
    flags = metadata.get("flags")
    if type(flags) is not list or any(type(flag) is not str for flag in flags):
        raise ProtocolError("flags must be a list of strings")
    _validate_json(metadata)
    return width, height


def encode_frame(rgb, metadata):
    """Validate and serialize one RGB frame; never perform color conversion."""
    if not isinstance(rgb, np.ndarray) or rgb.dtype != np.uint8:
        raise ProtocolError("rgb must be a numpy uint8 array")
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ProtocolError("rgb must have shape (height, width, 3)")
    if not 1 <= rgb.shape[1] <= MAX_WIDTH or not 1 <= rgb.shape[0] <= MAX_HEIGHT:
        raise ProtocolError("Frame dimensions exceed protocol bounds")
    try:
        width, height = _validate_metadata(metadata, rgb.size)
        if rgb.shape != (height, width, 3):
            raise ProtocolError("Array shape does not match metadata")
        # Incremental encoding caps allocation even when extra metadata is huge.
        chunks = []
        length = 0
        encoder = json.JSONEncoder(ensure_ascii=True, allow_nan=False, separators=(",", ":"))
        for chunk in encoder.iterencode(metadata):
            encoded = chunk.encode("ascii")
            length += len(encoded)
            if length > MAX_METADATA_BYTES:
                raise ProtocolError("Metadata exceeds protocol bounds")
            chunks.append(encoded)
        header = b"".join(chunks)
    except (RecursionError, TypeError, ValueError) as error:
        if isinstance(error, ProtocolError):
            raise
        raise ProtocolError("Invalid JSON metadata") from error
    payload = rgb.tobytes(order="C")
    return PREFIX.pack(MAGIC, VERSION, len(header), len(payload), zlib.crc32(payload)) + header + payload


class _IO:
    def __init__(self, sock):
        self.sock = sock
        self.timeout = sock.gettimeout()
        self.deadline = None if self.timeout is None else time.monotonic() + self.timeout

    def prepare(self):
        if self.deadline is not None:
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise socket.timeout("Frame I/O deadline exceeded")
            self.sock.settimeout(remaining)

    def restore(self):
        if self.deadline is not None:
            self.sock.settimeout(self.timeout)

    def read_exact(self, count):
        data = bytearray(count)
        view = memoryview(data)
        position = 0
        while position < count:
            self.prepare()
            received = self.sock.recv_into(view[position:])
            if received == 0:
                raise FrameEOF(f"EOF after {position} of {count} bytes")
            position += received
        return data


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ProtocolError(f"Duplicate metadata key: {key}")
        result[key] = value
    return result


def _reject_constant(value):
    raise ProtocolError(f"Nonfinite JSON value: {value}")


def read_frame(sock):
    """Read exactly one frame; any error requires closing and reconnecting.

    A finite socket timeout is a total frame deadline, restored on return.
    Blocking sockets have no deadline; nonblocking sockets are unsupported.
    """
    io = _IO(sock)
    try:
        prefix = io.read_exact(PREFIX.size)
        magic, version, metadata_length, payload_length, checksum = PREFIX.unpack(prefix)
        if magic != MAGIC or version != VERSION or prefix[5:8] != b"\0\0\0":
            raise ProtocolError("Invalid magic, version or reserved prefix bytes")
        if not 1 <= metadata_length <= MAX_METADATA_BYTES:
            raise ProtocolError("Invalid metadata length")
        if not 3 <= payload_length <= MAX_PAYLOAD_BYTES:
            raise ProtocolError("Invalid payload length")
        header = io.read_exact(metadata_length)
        try:
            metadata = json.loads(header.decode("utf-8"), object_pairs_hook=_unique_object,
                                  parse_constant=_reject_constant)
            width, height = _validate_metadata(metadata, payload_length)
        except (UnicodeError, ValueError, TypeError, RecursionError) as error:
            if isinstance(error, ProtocolError):
                raise
            raise ProtocolError("Invalid JSON metadata") from error
        # No payload allocation occurs until dimensions and packing are validated.
        payload = io.read_exact(payload_length)
        if zlib.crc32(payload) != checksum:
            raise ProtocolError("Payload CRC32 mismatch")
        rgb = np.frombuffer(payload, dtype=np.uint8).reshape(height, width, 3)
        return Frame(rgb, metadata)
    finally:
        io.restore()


def send_frame(sock, rgb, metadata):
    """Validate a frame before sending, handling arbitrary partial writes."""
    encoded = memoryview(encode_frame(rgb, metadata))
    io = _IO(sock)
    try:
        position = 0
        while position < len(encoded):
            io.prepare()
            sent = sock.send(encoded[position:])
            if sent == 0:
                raise FrameEOF("Peer disconnected during send")
            position += sent
    finally:
        io.restore()
