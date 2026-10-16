import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

from build_capture import main as build_capture_main
from build_capture import (
    adapt_rgb2dvi_async_reset_metadata,
    copy_capture_sources,
    copy_hdmi_output_sources,
)
from build_capture import require_gateware_mode as require_build_gateware_mode
from build_edid import make_edid, make_vga_edid, self_test_mode, validate_mode_edid
from build_manifest import (
    read_capture_mode,
    read_hdmi_output_fixture,
    require_gateware_mode,
    require_receiver_mode,
)
from hdmi_capture.modes import get_mode, mode_metadata


def source_edid(tmp_path):
    data = bytearray(128)
    data[:8] = bytes.fromhex('00 ff ff ff ff ff ff 00')
    data[18:20] = b'\x01\x04'
    data[127] = (-sum(data[:127])) & 0xff
    path = tmp_path / 'source-edid.data'
    path.write_text(''.join(f'{value:08b}\n' for value in data))
    return path


def receiver_hwh(k_clk_range):
    return ET.fromstring(
        '<ROOT><MODULE FULLNAME="/video/hdmi_in/frontend/dvi2rgb_0">'
        f'<PARAMETERS><PARAMETER NAME="kClkRange" VALUE="{k_clk_range}"/>'
        '</PARAMETERS></MODULE></ROOT>')


def test_vga_edid_stays_byte_for_byte_equal_to_legacy_output(tmp_path):
    source = source_edid(tmp_path)
    mode = get_mode('vga')
    output = make_edid(source, mode)

    assert output == make_vga_edid(source)
    assert hashlib.sha256(output).hexdigest() == (
        '172b62b7bad9c467eb3414e69101d4498faa77889ccc79f74b2392ea31fe62e0')
    assert validate_mode_edid(output, mode)['fps'] == 60


def test_1080p30_edid_advertises_exact_74250khz_pixel_clock_timing(tmp_path):
    source = source_edid(tmp_path)
    mode = get_mode('1080p30')
    output = make_edid(source, mode)

    assert len(output) == 128
    assert sum(output) % 256 == 0
    assert output[54:72].hex() == '011d801871382d40582c450000000000001e'
    assert validate_mode_edid(output, mode) == {
        'width': 1920,
        'height': 1080,
        'pixel_clock_hz': 74_250_000,
        'fps': 30,
        'extension_count': 0,
        'checksum': output[-1],
    }
    assert self_test_mode(source, mode)['fps'] == 30


@pytest.mark.parametrize('change', ['checksum', 'geometry', 'clock', 'extension',
                                    'extra_timing', 'sync_polarity'])
def test_1080p30_edid_rejects_unsupported_or_different_timing(tmp_path, change):
    source = source_edid(tmp_path)
    mode = get_mode('1080p30')
    data = bytearray(make_edid(source, mode))
    if change == 'checksum':
        data[127] ^= 1
    elif change == 'geometry':
        data[56] ^= 1
    elif change == 'clock':
        data[54] ^= 1
    elif change == 'extension':
        data[126] = 1
    elif change == 'extra_timing':
        data[35] = 1
    elif change == 'sync_polarity':
        data[71] ^= 0x04
    if change != 'checksum':
        data[127] = (-sum(data[:127])) & 0xff

    with pytest.raises(ValueError):
        validate_mode_edid(data, mode)


@pytest.mark.parametrize('mode_name,geometry,clock_hz,valid', [
    ('vga', (640, 480), 142_857_132, True),
    ('1080p30', (1920, 1080), 142_857_132, True),
    ('vga', (1920, 1080), 142_857_132, False),
    ('1080p30', (1920, 1080), 100_000_000, False),
])
def test_gateware_mode_checks_allow_only_matching_geometry_and_clock(
        mode_name, geometry, clock_hz, valid):
    mode = get_mode(mode_name)
    gate = {'width': geometry[0], 'height': geometry[1], 'clock_hz': clock_hz}
    checkers = (require_build_gateware_mode, require_gateware_mode)

    for checker in checkers:
        if valid:
            checker(gate, mode)
        else:
            error = ValueError if checker is require_build_gateware_mode else RuntimeError
            with pytest.raises(error):
                checker(gate, mode)


@pytest.mark.parametrize('mode_name,pixel_clock_hz', [
    ('vga', 25_200_000),
    ('1080p30', 74_250_000),
])
def test_prepared_capture_sources_declare_selected_pixel_clock(
        tmp_path, mode_name, pixel_clock_hz):
    output = tmp_path / mode_name
    output.mkdir()
    copy_capture_sources(output, get_mode(mode_name))

    source_health = (output / 'source_health.v').read_bytes()
    original_source_health = (ROOT / 'hardware/source_health.v').read_bytes()
    expected_source_health = original_source_health.replace(
        b'X_INTERFACE_PARAMETER = "FREQ_HZ 25200000, ASSOCIATED_RESET pixel_reset"',
        f'X_INTERFACE_PARAMETER = "FREQ_HZ {pixel_clock_hz}, ASSOCIATED_RESET pixel_reset"'.encode(),
    )
    assert source_health == expected_source_health
    assert (output / 'capture_lock_sync.v').read_bytes() == (
        ROOT / 'hardware/capture_lock_sync.v').read_bytes()
    assert (output / 'receiver_reset_sync.v').read_bytes() == (
        ROOT / 'hardware/receiver_reset_sync.v').read_bytes()


def test_prepared_hdmi_ip_marks_serial_clock_reset_async_without_editing_rtl(tmp_path):
    vendor_ip = tmp_path / 'vendor/boards/ip/rgb2dvi_v1_2'
    component = vendor_ip / 'component.xml'
    component.parent.mkdir(parents=True)
    original_xml = (
        '<spirit:component>\n'
        '  <spirit:busInterface>\n'
        '      <spirit:name>SerialClk</spirit:name>\n'
        '      <spirit:parameters>\n'
        '        <spirit:parameter>\n'
        '          <spirit:name>ASSOCIATED_RESET</spirit:name>\n'
        '          <spirit:value spirit:id="BUSIFPARAM_VALUE.SERIALCLK.ASSOCIATED_RESET">'
        'aRst:aRst_n:pRst:pRst_n</spirit:value>\n'
        '        </spirit:parameter>\n'
        '      </spirit:parameters>\n'
        '  </spirit:busInterface>\n'
        '</spirit:component>\n')
    component.write_text(original_xml)
    original_rtl = b'entity rgb2dvi is\n  port (aRst : in std_logic);\nend;\n'
    vendor_rtl = vendor_ip / 'src/rgb2dvi.vhd'
    vendor_rtl.parent.mkdir()
    vendor_rtl.write_bytes(original_rtl)

    output = tmp_path / 'output'
    output.mkdir()
    copy_hdmi_output_sources(tmp_path / 'vendor', output)

    staged_ip = output / 'tx_ip/rgb2dvi_v1_2'
    staged_xml = (staged_ip / 'component.xml').read_text()
    assert 'ASSOCIATED_ASYNC_RESET' in staged_xml
    assert 'BUSIFPARAM_VALUE.SERIALCLK.ASSOCIATED_ASYNC_RESET' in staged_xml
    assert 'aRst:aRst_n:pRst:pRst_n</spirit:value>' in staged_xml
    assert (staged_ip / 'src/rgb2dvi.vhd').read_bytes() == original_rtl
    assert staged_xml == original_xml.replace(
        '<spirit:name>ASSOCIATED_RESET</spirit:name>\n'
        '          <spirit:value spirit:id="BUSIFPARAM_VALUE.SERIALCLK.ASSOCIATED_RESET">',
        '<spirit:name>ASSOCIATED_ASYNC_RESET</spirit:name>\n'
        '          <spirit:value spirit:id="BUSIFPARAM_VALUE.SERIALCLK.ASSOCIATED_ASYNC_RESET">',
    )


def test_async_reset_metadata_adaptation_fails_closed_on_changed_xml(tmp_path):
    component = tmp_path / 'component.xml'
    original = ('<spirit:component><spirit:busInterface>\n'
                '      <spirit:name>SerialClk</spirit:name>'
                '</spirit:busInterface></spirit:component>')
    component.write_text(original)

    with pytest.raises(RuntimeError, match='reset metadata anchor changed'):
        adapt_rgb2dvi_async_reset_metadata(component)
    assert component.read_text() == original


def test_hdmi_output_flag_rejects_vga_before_creating_build_directory(monkeypatch, tmp_path):
    output = tmp_path / 'rejected-output-build'
    monkeypatch.setattr(sys, 'argv', [
        'build_capture.py', '--output', str(output), '--mode', 'vga', '--with-hdmi-output',
    ])

    with pytest.raises(SystemExit):
        build_capture_main()
    assert not output.exists()


def test_legacy_schema_one_build_without_mode_file_means_vga(tmp_path):
    mode = read_capture_mode(tmp_path)
    gate = {'width': 640, 'height': 480, 'clock_hz': 142_857_132}

    assert mode == get_mode('vga')
    require_gateware_mode(gate, mode)
    require_receiver_mode(receiver_hwh(5), mode)


def test_explicit_capture_mode_file_must_match_a_supported_profile(tmp_path):
    path = tmp_path / 'capture-mode.json'
    path.write_text(json.dumps(mode_metadata(get_mode('1080p30'))))

    assert read_capture_mode(tmp_path) == get_mode('1080p30')
    path.write_text(json.dumps({**mode_metadata(get_mode('1080p30')), 'pixel_clock_hz': 25_200_000}))
    with pytest.raises(RuntimeError, match='does not match profile'):
        read_capture_mode(tmp_path)


def test_receiver_hwh_must_use_profile_clock_range():
    require_receiver_mode(receiver_hwh(2), get_mode('1080p30'))
    with pytest.raises(RuntimeError, match='1080p30'):
        require_receiver_mode(receiver_hwh(5), get_mode('1080p30'))
    with pytest.raises(RuntimeError, match='vga'):
        require_receiver_mode(receiver_hwh(2), get_mode('vga'))


def _write_fixture_files(output):
    paths = {
        'pattern_sha256': output / 'tx/hdmi_test_pattern.v',
        'clock_sha256': output / 'tx/hdmi_test_clock.v',
        'tcl_sha256': output / 'tx/hdmi_output.tcl',
        'xdc_sha256': output / 'hdmi_tx.xdc',
        'rgb2dvi_component_sha256': output / 'tx_ip/rgb2dvi_v1_2/component.xml',
    }
    for index, path in enumerate(paths.values()):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'fixture-{index}\n')
    return {key: hashlib.sha256(path.read_bytes()).hexdigest()
            for key, path in paths.items()}


def test_output_fixture_manifest_binds_loopback_to_exact_sources(tmp_path):
    output = tmp_path
    hashes = _write_fixture_files(output)
    (output / 'source-manifest.json').write_text(json.dumps({
        'hdmi_output_enabled': True,
        'hdmi_output_fixture': {'mode': '1080p30', **hashes},
    }))

    result = read_hdmi_output_fixture(output, get_mode('1080p30'))
    assert result == {'enabled': True, 'mode': '1080p30', **hashes}

    (output / 'tx/hdmi_test_pattern.v').write_text('changed fixture\n')
    with pytest.raises(RuntimeError, match='pattern_sha256'):
        read_hdmi_output_fixture(output, get_mode('1080p30'))


def test_output_fixture_is_rejected_for_vga_mode(tmp_path):
    hashes = _write_fixture_files(tmp_path)
    (tmp_path / 'source-manifest.json').write_text(json.dumps({
        'hdmi_output_enabled': True,
        'hdmi_output_fixture': {'mode': '1080p30', **hashes},
    }))

    with pytest.raises(RuntimeError, match='only for 1080p30'):
        read_hdmi_output_fixture(tmp_path, get_mode('vga'))
