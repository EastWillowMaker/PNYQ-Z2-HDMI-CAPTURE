"""Complete RGB888 frames received from a capture server."""

from .client import CaptureClient
from .protocol import Frame, ProtocolError

__all__ = ["CaptureClient", "Frame", "ProtocolError"]
