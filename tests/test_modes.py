from dataclasses import FrozenInstanceError

import pytest

from hdmi_capture.modes import CAPTURE_MODES, get_mode, mode_metadata


def test_vga_profile_preserves_existing_capture_timing():
    mode = get_mode('vga')

    assert (mode.width, mode.height) == (640, 480)
    assert mode.pixel_clock_hz == 25_200_000
    assert mode.gateware_clock_hz == 142_857_132
    assert mode.h_total == 800
    assert mode.v_total == 525
    assert mode.refresh_hz == 60
    assert mode.receiver_k_clk_range == 5
    assert mode.supported_pixel_clocks_hz == (25_175_000, 25_200_000)
    assert mode.timing == {
        'h_front_porch': 16,
        'h_sync_width': 96,
        'h_back_porch': 48,
        'h_sync_positive': False,
        'v_front_porch': 10,
        'v_sync_width': 2,
        'v_back_porch': 33,
        'v_sync_positive': False,
    }


def test_1080p30_profile_has_verified_positive_sync_timing():
    mode = get_mode('1080p30')

    assert (mode.width, mode.height) == (1920, 1080)
    assert mode.pixel_clock_hz == 74_250_000
    assert mode.gateware_clock_hz == 142_857_132
    assert mode.h_total == 2200
    assert mode.v_total == 1125
    assert mode.refresh_hz == 30
    assert mode.receiver_k_clk_range == 2
    assert mode.supported_pixel_clocks_hz == (74_250_000,)
    assert mode.timing == {
        'h_front_porch': 88,
        'h_sync_width': 44,
        'h_back_porch': 148,
        'h_sync_positive': True,
        'v_front_porch': 4,
        'v_sync_width': 5,
        'v_back_porch': 36,
        'v_sync_positive': True,
    }


def test_mode_registry_is_immutable_and_rejects_unknown_profiles():
    assert tuple(CAPTURE_MODES) == ('vga', '1080p30', '1080p60')
    with pytest.raises(TypeError):
        CAPTURE_MODES['other'] = get_mode('vga')
    with pytest.raises(FrozenInstanceError):
        get_mode('vga').width = 1920
    with pytest.raises(ValueError, match='Unsupported capture mode'):
        get_mode('720p60')


def test_manifest_mode_fields_have_stable_names():
    assert mode_metadata(get_mode('1080p30')) == {
        'capture_mode': '1080p30',
        'geometry': [1920, 1080],
        'clock_hz': 142_857_132,
        'pixel_clock_hz': 74_250_000,
        'supported_pixel_clocks_hz': [74_250_000],
        'receiver_k_clk_range': 2,
        'timing': get_mode('1080p30').timing,
    }


def test_1080p60_profile_matches_full_hd_input_clock_and_receiver_range():
    mode = get_mode('1080p60')
    assert (mode.width, mode.height) == (1920, 1080)
    assert (mode.pixel_clock_hz, mode.receiver_k_clk_range) == (148_500_000, 1)
    assert mode.refresh_hz == 60
    assert (mode.h_total, mode.v_total) == (2200, 1125)
    assert mode.timing == get_mode('1080p30').timing
    assert mode.supported_pixel_clocks_hz == (148_500_000,)
