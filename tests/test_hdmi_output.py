"""The PL output fixture matches the host's full-frame analytic pattern."""

import importlib.util
from pathlib import Path
import shutil
import subprocess

import numpy as np
import pytest


ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location(
    "hdmi_pattern", ROOT / "tools" / "hdmi_pattern.py"
)
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


def test_verilog_output_matches_two_complete_1080p30_frames(tmp_path):
    if shutil.which("iverilog") is None or shutil.which("vvp") is None:
        pytest.skip("full-frame HDMI fixture simulation requires iverilog and vvp")

    executable = tmp_path / "hdmi_pattern_tb"
    pixel_stream = tmp_path / "rgb888.bin"
    subprocess.run(
        ["iverilog", "-g2012", "-s", "bench", "-o", str(executable),
         str(ROOT / "hardware" / "hdmi_test_pattern.v"),
         str(ROOT / "hardware" / "hdmi_test_pattern_tb.v")],
        check=True, capture_output=True, text=True, timeout=30,
    )
    result = subprocess.run(
        ["vvp", str(executable), f"+OUT={pixel_stream}"],
        check=True, capture_output=True, text=True, timeout=120,
    )
    assert "PASS 2 full 2200x1125 frames" in result.stdout

    actual = np.fromfile(pixel_stream, dtype=np.uint8)
    expected_bytes = 2 * 1920 * 1080 * 3
    assert actual.size == expected_bytes
    actual = actual.reshape((2, 1080, 1920, 3))
    expected = np.stack([
        fixture.pattern(1, "1080p30"),
        fixture.pattern(2, "1080p30"),
    ])
    assert np.array_equal(actual, expected)
