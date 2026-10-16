"""Save received RGB888 frames as uncompressed 24-bit BMP images."""

from __future__ import annotations

import hashlib
import json
import struct
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .protocol import Frame

_FILE_HEADER = struct.Struct("<2sIHHI")
_INFO_HEADER = struct.Struct("<IiiHHIIiiII")
_PIXEL_OFFSET = _FILE_HEADER.size + _INFO_HEADER.size
_MAX_BMP_SIZE = 0xFFFFFFFF


def _rgb_array(frame: Frame) -> np.ndarray:
    rgb = getattr(frame, "rgb", None)
    if not isinstance(rgb, np.ndarray) or rgb.dtype != np.uint8:
        raise ValueError("frame RGB data must be a uint8 NumPy array")
    if rgb.ndim != 3 or rgb.shape[2] != 3 or min(rgb.shape[:2], default=0) < 1:
        raise ValueError("frame RGB data must have shape (height, width, 3)")
    height, width, _ = rgb.shape
    if width > 0x7FFFFFFF or height > 0x7FFFFFFF:
        raise ValueError("frame dimensions exceed the BMP format limit")
    return rgb


def _row_stride(width: int) -> int:
    return (width * 3 + 3) & ~3


def _rgb_sha256(rgb: np.ndarray) -> str:
    digest = hashlib.sha256()
    for row in rgb:
        digest.update(row.tobytes(order="C"))
    return digest.hexdigest()


def save_bmp(frame: Frame, path: Path) -> None:
    """Write a new BMP and JSON sidecar without changing any RGB pixel value.

    BMP stores each row bottom-up in BGR order and pads rows to four bytes.
    These are file-layout rules only; decoding the pixels to RGB888 yields the
    input array byte for byte. Existing image or sidecar files are never
    overwritten.
    """
    output = Path(path)
    if output.suffix.lower() != ".bmp":
        raise ValueError("image output path must end in .bmp")

    rgb = _rgb_array(frame)
    metadata = getattr(frame, "metadata", None)
    if not isinstance(metadata, dict):
        raise ValueError("frame metadata must be a dictionary")

    height, width, _ = rgb.shape
    stride = _row_stride(width)
    pixel_bytes = stride * height
    file_bytes = _PIXEL_OFFSET + pixel_bytes
    if file_bytes > _MAX_BMP_SIZE:
        raise ValueError("frame is too large for a BMP file")

    bmp_header = _FILE_HEADER.pack(b"BM", file_bytes, 0, 0, _PIXEL_OFFSET)
    info_header = _INFO_HEADER.pack(
        _INFO_HEADER.size,
        width,
        height,
        1,
        24,
        0,
        pixel_bytes,
        2835,
        2835,
        0,
        0,
    )
    padding = b"\0" * (stride - width * 3)
    sidecar = output.with_suffix(".json")
    details = {
        "format": "BMP",
        "compression": "BI_RGB",
        "compression_code": 0,
        "bits_per_pixel": 24,
        "width": width,
        "height": height,
        "pixel_format": "RGB888",
        "sha256_rgb": _rgb_sha256(rgb),
        "saved_at_utc": datetime.now(timezone.utc).isoformat(),
        "frame_metadata": metadata,
    }
    sidecar_data = (json.dumps(details, indent=2, allow_nan=False) + "\n").encode("utf-8")

    created: list[Path] = []
    try:
        with output.open("xb") as image_file:
            created.append(output)
            image_file.write(bmp_header)
            image_file.write(info_header)
            for row in rgb[::-1]:
                image_file.write(row[:, ::-1].tobytes(order="C"))
                image_file.write(padding)
        with sidecar.open("xb") as metadata_file:
            created.append(sidecar)
            metadata_file.write(sidecar_data)
    except Exception:
        for created_path in created:
            try:
                created_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise
