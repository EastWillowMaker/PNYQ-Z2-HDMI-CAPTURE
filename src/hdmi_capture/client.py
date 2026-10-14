"""Bounded TCP capture client, including scoped IPv6 host names."""

import socket
import time
import math
from collections.abc import Iterator

from .protocol import Frame, ProtocolError, read_frame


class CaptureClient:
    """Own one connection; reconnect explicitly after EOF or any invalid frame.

    A frame's array is independent of subsequent reads. Timeouts are seconds
    per complete frame; CLI duration limits additionally bound each read.
    """

    def __init__(self, host: str, port: int = 9020, *, timeout: float = 5.0):
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be positive")
        if not 1 <= port <= 65535:
            raise ValueError("port must be between 1 and 65535")
        self.host = host.removeprefix("[").removesuffix("]")
        self.port = port
        self.timeout = timeout
        self._socket: socket.socket | None = None
        self._session: str | None = None
        self._frame_id: int | None = None

    def connect(self) -> "CaptureClient":
        if self._socket is not None:
            raise RuntimeError("client is already connected")
        self._socket = socket.create_connection((self.host, self.port), self.timeout)
        self._session = None
        self._frame_id = None
        return self

    def read(self, *, deadline: float | None = None) -> Frame:
        if self._socket is None:
            raise RuntimeError("client is not connected")
        try:
            timeout = self.timeout
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("capture duration expired during frame read")
                timeout = min(timeout, remaining)
            self._socket.settimeout(timeout)
            frame = read_frame(self._socket)
            session = frame.metadata.get("session_id")
            frame_id = frame.metadata["frame_id"]
            if self._frame_id is not None and session != self._session:
                raise ProtocolError("session changed within a connection")
            if self._frame_id is not None and frame_id <= self._frame_id:
                raise ProtocolError("frame IDs must increase within a session")
            self._session, self._frame_id = session, frame_id
            return frame
        except BaseException:
            self.close()
            raise

    def set_read_timeout(self, timeout: float) -> None:
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be positive")
        if self._socket is None:
            raise RuntimeError("client is not connected")
        self._socket.settimeout(timeout)

    def close(self) -> None:
        if self._socket is not None:
            self._socket.close()
            self._socket = None

    def __enter__(self) -> "CaptureClient":
        return self.connect()

    def __exit__(self, *_: object) -> None:
        self.close()

    def __iter__(self) -> Iterator[Frame]:
        while True:
            yield self.read()
