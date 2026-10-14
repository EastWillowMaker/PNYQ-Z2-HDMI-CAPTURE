import json
import subprocess
import sys

import numpy as np
import pytest

from hdmi_capture.cli import main
from hdmi_capture.protocol import encode_frame
from test_client import RGB, metadata, server


def arguments(command, port, *rest):
    return [command, "127.0.0.1", "--port", str(port), *map(str, rest)]


def test_snapshot_roundtrip_and_metadata(tmp_path, capsys):
    output = tmp_path / "image.npy"
    with server([encode_frame(RGB, metadata())]) as port:
        assert main(arguments("snapshot", port, "--output", output)) == 0
    np.testing.assert_array_equal(np.load(output, allow_pickle=False), RGB)
    assert json.loads(output.with_suffix(".json").read_text()) == metadata()
    assert json.loads(capsys.readouterr().out)["delivered_frames"] == 1


def test_snapshot_png_preserves_rgb_and_refuses_existing_sidecar(tmp_path, capsys):
    image = pytest.importorskip("PIL.Image")
    output = tmp_path / "image.npy"
    with server([encode_frame(RGB, metadata())]) as port:
        assert main(arguments("snapshot", port, "--output", output, "--png")) == 0
    np.testing.assert_array_equal(np.asarray(image.open(output.with_suffix(".png"))), RGB)
    capsys.readouterr()
    assert main(arguments("snapshot", 1, "--output", output)) == 1
    assert json.loads(capsys.readouterr().out)["detected_errors"] == 1
    np.testing.assert_array_equal(np.load(output, allow_pickle=False), RGB)


def test_capture_count_and_no_overwrite(tmp_path, capsys):
    output = tmp_path / "capture"
    with server([encode_frame(RGB, metadata(i)) for i in range(3)]) as port:
        assert main(arguments("capture", port, "--output", output, "--count", 3)) == 0
    assert len(list(output.glob("*.npy"))) == 3
    capsys.readouterr()
    assert main(arguments("capture", 1, "--output", output, "--count", 1)) == 1
    assert "FileExistsError" in json.loads(capsys.readouterr().out)["error"]


def test_benchmark_reports_payload_gaps_without_saving(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    with server([encode_frame(RGB, metadata(i)) for i in (2, 5)]) as port:
        assert main(arguments("benchmark", port, "--count", 2)) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["delivered_frames"] == 2
    assert report["payload_bytes"] == 48
    assert report["observed_frame_id_gaps"] == 2
    assert report["detected_errors"] == 0
    assert report["delivered_fps"] > 0
    assert list(tmp_path.iterdir()) == []


def test_corruption_is_counted_and_fails(capsys):
    bad = bytearray(encode_frame(RGB, metadata(1)))
    bad[-1] ^= 1
    with server([encode_frame(RGB, metadata()), bad]) as port:
        assert main(arguments("stats", port, "--count", 2)) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["delivered_frames"] == 1
    assert report["detected_errors"] == 1
    assert report["stop_reason"] == "error"


def test_duration_is_bounded_even_without_frames(capsys):
    with server([encode_frame(RGB, metadata())], delay=0.1) as port:
        assert main(arguments("benchmark", port, "--duration", 0.02)) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["stop_reason"] == "duration"
    assert report["delivered_frames"] == 0
    assert report["incomplete_frame_at_deadline"]
    assert report["elapsed_seconds"] < 0.1


def test_unbounded_run_is_rejected():
    with pytest.raises(SystemExit) as exc:
        main(["benchmark", "127.0.0.1"])
    assert exc.value.code == 2


@pytest.mark.parametrize("command", ["snapshot", "capture", "stats", "benchmark"])
def test_subcommand_help_smoke(command):
    result = subprocess.run([sys.executable, "-m", "hdmi_capture", command, "--help"],
                            capture_output=True, text=True, timeout=5)
    assert result.returncode == 0, result.stderr
    assert "%interface" in result.stdout
    assert "--timeout" in result.stdout
