"""Offline fixture checks do not certify the compositor or physical HDMI path."""

import importlib.util
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

spec = importlib.util.spec_from_file_location(
    "hdmi_pattern", Path(__file__).parents[1] / "tools" / "hdmi_pattern.py"
)
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


@pytest.mark.parametrize("frame_id", [0, 1, 0x12345678, 0xFFFFFFFF])
def test_exact_full_image(frame_id):
    rgb = fixture.pattern(frame_id)
    report = fixture.verify(rgb)
    assert rgb.shape == (480, 640, 3)
    assert report["exact_match"]
    assert report["expected_id"] == frame_id
    assert report["valid_marker_rows"] == 480
    assert report["expected_id_source"] == "majority_valid_optical_rows"


@pytest.mark.parametrize("frame_id", [0, 0x12345678, 0xFFFFFFFF])
def test_exact_1080p30_full_image(frame_id):
    rgb = fixture.pattern(frame_id, "1080p30")
    report = fixture.verify(rgb, mode="1080p30")
    assert rgb.shape == (1080, 1920, 3)
    assert report["exact_match"]
    assert report["expected_id"] == frame_id
    assert report["valid_marker_rows"] == 1080


def test_1080p30_verification_rejects_vga_geometry():
    with pytest.raises(ValueError, match="1080p30.*shape"):
        fixture.verify(fixture.pattern(1), mode="1080p30")


def test_body_corruption_fails_even_with_all_markers_intact():
    rgb = fixture.pattern(42)
    rgb[200, 300, 1] ^= 1
    report = fixture.verify(rgb)
    assert not report["exact_match"]
    assert report["valid_marker_rows"] == 480
    assert report["mismatched_bytes"] == 1
    assert report["first_mismatch_y_x"] == [200, 300]


def test_mixed_source_frames_are_rejected():
    rgb = fixture.pattern(123)
    rgb[200:] = fixture.pattern(124)[200:]
    report = fixture.verify(rgb, 123)
    assert not report["exact_match"]
    assert report["mixed_optical_ids"]
    assert report["optical_ids"] == {"123": 200, "124": 280}
    assert report["mismatched_rows"] == list(range(200, 480))


def test_marker_damage_is_not_silently_learned():
    rgb = fixture.pattern(123)
    rgb[10, 0, 2] = 12
    report = fixture.verify(rgb)
    assert not report["exact_match"]
    assert report["invalid_marker_rows"] == [10]


@pytest.mark.parametrize("transform", [
    lambda rgb: rgb[:, :, ::-1].copy(),
    lambda rgb: (16 + rgb.astype(np.uint16) * 219 // 255).astype(np.uint8),
    lambda rgb: np.roll(rgb, 1, axis=1),
    lambda rgb: np.repeat(rgb[:, ::2], 2, axis=1),
])
def test_channel_range_alignment_and_scaling_corruption_fail(transform):
    report = fixture.verify(transform(fixture.pattern(0x12345678)), 0x12345678)
    assert not report["exact_match"]
    assert report["mismatched_pixels"] > 0


def test_no_markers_requires_id_and_never_passes():
    rgb = np.zeros((480, 640, 3), dtype=np.uint8)
    assert not fixture.verify(rgb)["exact_match"]
    report = fixture.verify(rgb, 1)
    assert report["mismatched_bytes"] > 0


@pytest.mark.parametrize("rgb", [
    np.zeros((480, 640, 4), dtype=np.uint8),
    np.zeros((480, 640, 3), dtype=np.float32),
    np.zeros((240, 320, 3), dtype=np.uint8),
])
def test_invalid_capture_contract_rejected(rgb):
    with pytest.raises(ValueError, match="shape"):
        fixture.verify(rgb)


def test_cli_requires_selected_monitor_without_launching():
    with pytest.raises(SystemExit) as failure:
        fixture.main(["start"])
    assert failure.value.code == 2


def test_cli_generate_verify_and_existing_output(tmp_path, capsys):
    path = tmp_path / "source.npy"
    assert fixture.main(["generate", "--frame-id", "77", "--output", str(path)]) == 0
    assert fixture.main(["verify", str(path), "--frame-id", "77"]) == 0
    assert fixture.main(["generate", "--frame-id", "78", "--output", str(path)]) == 2
    rgb = np.load(path, allow_pickle=False)
    rgb[100, 200, 0] ^= 1
    np.save(path, rgb, allow_pickle=False)
    assert fixture.main(["verify", str(path), "--frame-id", "77"]) == 1


def test_cli_1080p30_generate_verify(tmp_path):
    path = tmp_path / "source-1080p30.npy"
    assert fixture.main(["generate", "--mode", "1080p30", "--frame-id", "77",
                         "--output", str(path)]) == 0
    assert fixture.main(["verify", str(path), "--mode", "1080p30",
                         "--frame-id", "77"]) == 0


def test_script_works_without_an_installed_hdmi_capture_package(tmp_path):
    path = tmp_path / "source.npy"
    script = Path(__file__).parents[1] / "tools" / "hdmi_pattern.py"
    env = dict(os.environ, PYTHONPATH="")
    generated = subprocess.run([sys.executable, str(script), "generate", "--mode",
                                "1080p30", "--frame-id", "91", "--output", str(path)],
                               env=env, capture_output=True, text=True)
    assert generated.returncode == 0, generated.stderr
    checked = subprocess.run([sys.executable, str(script), "verify", str(path),
                              "--mode", "1080p30", "--frame-id", "91"],
                             env=env, capture_output=True, text=True)
    assert checked.returncode == 0, checked.stderr


@pytest.mark.parametrize("frame_id", [-1, 0x100000000])
def test_id_range(frame_id):
    with pytest.raises(ValueError, match="32-bit"):
        fixture.pattern(frame_id)


def test_invalid_generate_does_not_create_output(tmp_path):
    path = tmp_path / "invalid.npy"
    assert fixture.main(["generate", "--frame-id", "-1", "--output", str(path)]) == 2
    assert not path.exists()


def test_npz_is_not_accepted_as_rgb(tmp_path):
    path = tmp_path / "archive.npz"
    np.savez(path, rgb=fixture.pattern(1))
    assert fixture.main(["verify", str(path)]) == 2


config_spec = importlib.util.spec_from_file_location(
    "configure_hdmi_source", Path(__file__).parents[1] / "tools" / "configure_hdmi_source.py"
)
configuration = importlib.util.module_from_spec(config_spec)
config_spec.loader.exec_module(configuration)


def configuration_inputs():
    specs = [["HDMI-1", "AUS", "XG27AQMR", "main"],
             ["DP-2", "DGL", "DigilentDVI-2", "0"]]
    state = [11, [
        [specs[0], [["2560x1440@59.951", 2560, 1440, 59.951, 1, [1],
                    {"is-current": True}]], {"color-mode": 0, "rgb-range": 1}],
        [specs[1], [], {"color-mode": 0, "rgb-range": 1, "is-underscanning": False}],
    ], [[0, 0, 1.0, 0, True, [specs[0]], {}],
        [2560, 0, 1.0, 0, False, [specs[1]], {}]], {"layout-mode": 1}]
    resources = [11, [(0, 0, 0, 0, 2560, 1440, 1, 0, [], {}),
                      (4, 4, 2560, 0, 640, 480, 2, 0, [], {})],
                 [(0, 0, 0, [], "HDMI-1", [1], [], {}),
                  (1, 1, 4, [], "DP-2", [2], [], {})],
                 [(1, 1, 2560, 1440, 59.951, 0), (2, 2, 640, 480, 59.940475, 0)],
                 65535, 65535]
    return state, resources


def test_hidden_current_mode_retained_and_other_output_preserved():
    state, resources = configuration_inputs()
    original = configuration.read_configuration(state, resources)
    proposed = configuration.candidate(original, resources, "DP-2", "640x480@59.940")
    assert original["configs"][1][5][0][1] == "640x480@59.940"
    assert proposed["configs"][0] == original["configs"][0]
    assert proposed["configs"][1][5][0][2]["rgb-range"] == 1


def test_wrong_monitor_and_absent_mode_rejected():
    state, resources = configuration_inputs()
    original = configuration.read_configuration(state, resources)
    with pytest.raises(ValueError, match="not a known DGL"):
        configuration.candidate(original, resources, "HDMI-1", "640x480@59.940")
    with pytest.raises(ValueError, match="absent"):
        configuration.candidate(original, resources, "DP-2", "640x480@60.000")


def test_mirror_and_stale_state_rejected():
    state, resources = configuration_inputs()
    original = configuration.read_configuration(state, resources)
    original["configs"][1][5].append(original["configs"][0][5][0])
    with pytest.raises(ValueError, match="mirrored"):
        configuration.candidate(original, resources, "DP-2", "640x480@59.940")
    resources[0] += 1
    with pytest.raises(ValueError, match="changed"):
        configuration.read_configuration(state, resources)


def test_restore_preserves_intervening_other_monitor_changes():
    state, resources = configuration_inputs()
    original = configuration.read_configuration(state, resources)
    snapshot = {"format": "hdmi-source-mutter-v1", "connector": "DP-2",
                "original": original}
    current = copy.deepcopy(original)
    current["serial"] += 1
    current["configs"][1][5][0][1] = "1280x720@60.000"
    restored = configuration.restore_candidate(current, snapshot, "DP-2")
    assert restored["serial"] == current["serial"]
    assert restored["configs"] == original["configs"]
    current["configs"][0][2] = 2.0
    with pytest.raises(ValueError, match="Another monitor"):
        configuration.restore_candidate(current, snapshot, "DP-2")


gl_spec = importlib.util.spec_from_file_location(
    "hdmi_pattern_gl", Path(__file__).parents[1] / "tools" / "hdmi_pattern_gl.py"
)
gl_fixture = importlib.util.module_from_spec(gl_spec)
gl_spec.loader.exec_module(gl_fixture)


def test_gl_source_monitor_selection_and_mode_contract():
    monitors = [{"width": 2560, "height": 1440}, {"width": 640, "height": 480}]
    gl_fixture.require_monitor(monitors, 1)
    for invalid in [-1, 2]:
        with pytest.raises(ValueError, match="absent"):
            gl_fixture.require_monitor(monitors, invalid)
    with pytest.raises(ValueError, match="640x480"):
        gl_fixture.require_monitor(monitors, 0)


def test_gl_cli_requires_selection_before_loading_graphics():
    with pytest.raises(SystemExit) as failure:
        gl_fixture.main([])
    assert failure.value.code == 2


def test_gl_synthetic_backbuffer_check_uses_every_rgb_byte():
    rgb = fixture.pattern(567)
    rgba = np.full((480, 640, 4), 255, dtype=np.uint8)
    rgba[:, :, :3] = rgb[::-1]
    gl_fixture.verify_readback(rgb, rgba)
    rgba[0, 500, 1] ^= 1
    with pytest.raises(RuntimeError, match="mismatched_bytes=1"):
        gl_fixture.verify_readback(rgb, rgba)


scanout_spec = importlib.util.spec_from_file_location(
    "monitor_hdmi_scanout", Path(__file__).parents[1] / "tools" / "monitor_hdmi_scanout.py"
)
scanout = importlib.util.module_from_spec(scanout_spec)
scanout_spec.loader.exec_module(scanout)


def test_scanout_fourcc_and_bounded_metadata_log():
    assert scanout.fourcc(int.from_bytes(b"XR24", "little")) == "XR24"
    assert scanout.fourcc(int.from_bytes(b"XR30", "little")) == "XR30"

    class Reader:
        def sample(self):
            return {"framebuffer": {"format": "XR24"}, "active": True}

    output = io.StringIO()
    assert scanout.record(Reader(), output, 0.005, 0.001) == 0
    rows = [json.loads(line) for line in output.getvalue().splitlines()]
    assert rows[0]["state_changed"]
    assert rows[0]["sample_finished_monotonic_ns"] >= rows[0]["sample_started_monotonic_ns"]
    assert rows[-1]["event"] == "scanout_summary"
    assert rows[-1]["samples"] == len(rows) - 1
    assert rows[-1]["errors"] == 0


def test_scanout_read_failures_remain_visible_and_fail_run():
    class Reader:
        def sample(self):
            raise OSError("metadata unavailable")

    output = io.StringIO()
    assert scanout.record(Reader(), output, 0.002, 0.001) == 1
    rows = [json.loads(line) for line in output.getvalue().splitlines()]
    assert rows[0]["state"] is None
    assert rows[0]["error"] == "metadata unavailable"
    assert rows[-1]["errors"] == rows[-1]["samples"]


def test_litex_vga_identity_is_narrow_and_vga_only():
    state, resources = configuration_inputs()
    original = configuration.read_configuration(state, resources)
    original["identities"]["DP-2"] = ["DP-2", "DGL", "LiteX VGA", "0x00000000"]
    configuration.candidate(original, resources, "DP-2", "640x480@59.940")
    for identity in [["DP-2", "OTHER", "LiteX VGA", "0x00000000"],
                     ["DP-2", "DGL", "Unknown sink", "0x00000000"],
                     ["DP-2", "DGL", "LiteX VGA", "different"]]:
        original["identities"]["DP-2"] = identity
        with pytest.raises(ValueError, match="not a known DGL"):
            configuration.candidate(original, resources, "DP-2", "640x480@59.940")
    original["identities"]["DP-2"] = ["DP-2", "DGL", "LiteX VGA", "0x00000000"]
    resources[3].append((3, 3, 1280, 720, 60.0, 0))
    resources[2][1][5].append(3)
    with pytest.raises(ValueError, match="only supported progressive VGA"):
        configuration.candidate(original, resources, "DP-2", "640x480@59.940")


@pytest.mark.parametrize("flags", [16, 32])
def test_litex_vga_interlace_and_double_scan_rejected(flags):
    state, resources = configuration_inputs()
    original = configuration.read_configuration(state, resources)
    original["identities"]["DP-2"] = ["DP-2", "DGL", "LiteX VGA", "0x00000000"]
    resources[3][1] = (2, 2, 640, 480, 59.940475, flags)
    with pytest.raises(ValueError, match="only supported progressive VGA"):
        configuration.candidate(original, resources, "DP-2", "640x480@59.940")
