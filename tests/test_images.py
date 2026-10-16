import hashlib
import json
import struct
from pathlib import Path

import numpy as np
import pytest

from hdmi_capture.images import save_bmp
from hdmi_capture.protocol import Frame


FILE_HEADER = struct.Struct("<2sIHHI")
INFO_HEADER = struct.Struct("<IiiHHIIiiII")


def decode_bmp(path: Path) -> tuple[np.ndarray, dict[str, int]]:
    data = path.read_bytes()
    magic, file_size, reserved1, reserved2, pixel_offset = FILE_HEADER.unpack_from(data)
    (header_size, width, signed_height, planes, bits_per_pixel, compression,
     image_size, _x_ppm, _y_ppm, _colors, _important) = INFO_HEADER.unpack_from(data, FILE_HEADER.size)
    assert magic == b"BM"
    assert file_size == len(data)
    assert reserved1 == reserved2 == 0
    assert header_size == 40
    assert planes == 1
    assert bits_per_pixel == 24
    assert compression == 0
    height = abs(signed_height)
    stride = (width * 3 + 3) & ~3
    assert image_size == stride * height
    result = np.empty((height, width, 3), dtype=np.uint8)
    for output_y in range(height):
        file_y = height - 1 - output_y if signed_height > 0 else output_y
        row = data[pixel_offset + file_y * stride:pixel_offset + (file_y + 1) * stride]
        bgr = np.frombuffer(row[:width * 3], dtype=np.uint8).reshape(width, 3)
        result[output_y] = bgr[:, ::-1]
    return result, {
        "width": width,
        "height": height,
        "bits_per_pixel": bits_per_pixel,
        "compression": compression,
        "pixel_offset": pixel_offset,
        "row_stride": stride,
    }


def test_1080p_bmp_roundtrips_every_rgb888_byte(tmp_path):
    y, x = np.indices((1080, 1920), dtype=np.uint16)
    rgb = np.stack(((x * 3 + y) & 255, (x + y * 7) & 255, (x ^ y) & 255), axis=-1).astype(np.uint8)
    metadata = {"frame_id": 71, "session_id": "test-session", "source": {"counter": 902}}
    output = tmp_path / "capture.bmp"

    assert save_bmp(Frame(rgb, metadata), output) is None

    decoded, header = decode_bmp(output)
    np.testing.assert_array_equal(decoded, rgb)
    assert header == {
        "width": 1920,
        "height": 1080,
        "bits_per_pixel": 24,
        "compression": 0,
        "pixel_offset": 54,
        "row_stride": 5760,
    }
    details = json.loads(output.with_suffix(".json").read_text())
    assert details["frame_metadata"] == metadata
    assert details["compression_code"] == 0
    assert details["bits_per_pixel"] == 24
    assert details["sha256_rgb"] == hashlib.sha256(rgb.tobytes()).hexdigest()


@pytest.mark.parametrize("width", [1, 2, 3, 5])
def test_bmp_padding_orientation_and_rgb_channel_order(tmp_path, width):
    height = 3
    rgb = np.empty((height, width, 3), dtype=np.uint8)
    for y in range(height):
        for x in range(width):
            rgb[y, x] = (y + 1, x + 11, y * 20 + x + 101)
    output = tmp_path / f"padded-{width}.bmp"

    save_bmp(Frame(rgb, {"frame_id": 4}), output)

    decoded, header = decode_bmp(output)
    np.testing.assert_array_equal(decoded, rgb)
    assert header["row_stride"] % 4 == 0
    raw = output.read_bytes()
    stride = header["row_stride"]
    offset = header["pixel_offset"]
    bottom_row = raw[offset:offset + stride]
    assert bottom_row[:width * 3] == rgb[-1, :, ::-1].tobytes()
    assert bottom_row[width * 3:] == b"\0" * (stride - width * 3)


def test_bmp_and_sidecar_never_overwrite_existing_files(tmp_path):
    existing_image = tmp_path / "existing.bmp"
    existing_image.write_bytes(b"keep image")
    frame = Frame(np.zeros((1, 1, 3), dtype=np.uint8), {"frame_id": 1})

    with pytest.raises(FileExistsError):
        save_bmp(frame, existing_image)
    assert existing_image.read_bytes() == b"keep image"
    assert not existing_image.with_suffix(".json").exists()

    output = tmp_path / "sidecar-conflict.bmp"
    sidecar = output.with_suffix(".json")
    sidecar.write_text("keep metadata")
    with pytest.raises(FileExistsError):
        save_bmp(frame, output)
    assert not output.exists()
    assert sidecar.read_text() == "keep metadata"


def test_sidecar_creation_error_removes_new_bmp_only(tmp_path, monkeypatch):
    output = tmp_path / "failed.bmp"
    sidecar = output.with_suffix(".json")
    frame = Frame(np.zeros((2, 2, 3), dtype=np.uint8), {"frame_id": 1})
    real_open = Path.open

    def fail_sidecar(path, mode="r", *args, **kwargs):
        if path == sidecar and mode == "xb":
            raise PermissionError("sidecar denied")
        return real_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_sidecar)
    with pytest.raises(PermissionError, match="sidecar denied"):
        save_bmp(frame, output)
    assert not output.exists()
    assert not sidecar.exists()


@pytest.mark.parametrize(
    "rgb, path, error",
    [
        (np.zeros((1, 1), dtype=np.uint8), "bad.bmp", "shape"),
        (np.zeros((1, 1, 3), dtype=np.uint16), "bad.bmp", "uint8"),
        (np.zeros((1, 1, 3), dtype=np.uint8), "bad.png", ".bmp"),
    ],
)
def test_invalid_frame_or_filename_is_rejected_without_output(tmp_path, rgb, path, error):
    output = tmp_path / path
    with pytest.raises(ValueError, match=error):
        save_bmp(Frame(rgb, {"frame_id": 1}), output)
    assert not output.exists()
    assert not output.with_suffix(".json").exists()
