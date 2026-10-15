"""Calculated rate relationships; these tests do not establish hardware traffic."""

import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "capture_budget", Path(__file__).parents[1] / "tools" / "capture_budget.py"
)
budget = importlib.util.module_from_spec(spec)
spec.loader.exec_module(budget)


def report(arguments, capsys):
    budget.main(arguments)
    return json.loads(capsys.readouterr().out)


def test_default_preserves_continuous_dma_budget(capsys):
    result = report([], capsys)
    assert result["nominal_inputs"]["input_fps"] == 60
    assert result["nominal_inputs"]["dma_fps"] == 60
    assert result["board_memory_logical_budget"]["native_dma_writes"]["bytes_per_second"] == 55_296_000
    assert result["board_memory_logical_budget"]["native_writes_plus_explicit_copies_plus_CRC"]["bytes_per_second"] == 68_198_400
    assert result["board_memory_logical_budget"]["dma_write_passes_per_input_frame"] == 1


def test_credit_rate_separates_native_dma_and_delivery(capsys):
    result = report(["--input-fps", "60", "--dma-fps", "2",
                     "--sampled-fps", "2", "--delivered-fps", "2"], capsys)
    assert result["input_RGB_data_rate"]["bytes_per_second"] == 55_296_000
    assert result["dma_RGB_write_data_rate"]["bytes_per_second"] == 1_843_200
    assert result["payload"]["bytes_per_second"] == 1_843_200
    memory = result["board_memory_logical_budget"]
    assert memory["dma_write_passes_per_dma_frame"] == 1
    assert memory["dma_write_payload_bytes_per_dma_frame"] == 921_600
    assert memory["dma_write_passes_per_input_frame"] == pytest.approx(2 / 60)
    assert memory["native_writes_plus_explicit_copies_plus_CRC"]["bytes_per_second"] == 14_745_600
    assert result["measurements"]["actual_DDR_bandwidth_bytes_per_second"] is None


@pytest.mark.parametrize("dma_fps", ["0", "-1", "nan", "inf", "-inf", "61", "1"])
def test_invalid_dma_rates_rejected(dma_fps):
    with pytest.raises(SystemExit) as failure:
        budget.main(["--dma-fps", dma_fps])
    assert failure.value.code == 2


def test_sampled_rate_cannot_exceed_dma_or_fall_below_delivery():
    for arguments in [["--dma-fps", "2", "--sampled-fps", "3"],
                      ["--dma-fps", "2", "--sampled-fps", "1"]]:
        with pytest.raises(SystemExit) as failure:
            budget.main(arguments)
        assert failure.value.code == 2


def test_stride_reservation_does_not_increase_active_pixel_writes(capsys):
    result = report(["--dma-fps", "2", "--dma-stride", "1984"], capsys)
    assert result["frame"]["dma_storage_bytes_per_frame"] == 1984 * 480
    assert result["dma_RGB_write_data_rate"]["bytes_per_second"] == 640 * 480 * 3 * 2


def test_budget_output_cannot_replace_previous_evidence(tmp_path):
    output = tmp_path / "existing.json"
    output.write_text("historical evidence")
    with pytest.raises(FileExistsError):
        budget.main(["--dma-fps", "2", "--output", str(output)])
    assert output.read_text() == "historical evidence"
