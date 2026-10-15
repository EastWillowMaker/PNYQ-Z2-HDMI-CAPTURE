"""Compile the actual KMS source and compare its complete RGB payloads."""
import importlib.util
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('kms_reference_pattern', ROOT / 'tools/hdmi_pattern.py')
pattern_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pattern_module)


@pytest.fixture(scope='module')
def binary(tmp_path_factory):
    if not shutil.which('cc') or not shutil.which('pkg-config'):
        pytest.skip('C compiler and libdrm development files are required')
    flags = subprocess.run(['pkg-config', '--cflags', '--libs', 'libdrm'],
                           capture_output=True, text=True)
    if flags.returncode:
        pytest.skip('libdrm development files are required')
    target = tmp_path_factory.mktemp('kms') / 'source'
    subprocess.run(['cc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                    str(ROOT / 'tools/hdmi_pattern_kms.c'), *flags.stdout.split(),
                    '-o', str(target)], check=True)
    return target


@pytest.mark.parametrize('frame_id', [0, 1, 105036, 200000, 0xFFFFFFFF])
def test_actual_c_source_matches_every_reference_byte(binary, frame_id):
    actual = subprocess.check_output([str(binary), '--dump', str(frame_id), '1'])
    assert actual == pattern_module.pattern(frame_id).tobytes()


@pytest.mark.parametrize('frame_id', ['', '-1', '4294967296', '12x'])
def test_invalid_id_rejected_before_display_access(binary, frame_id):
    result = subprocess.run([str(binary), '--dump', frame_id, '1'], capture_output=True)
    assert result.returncode == 2
    assert not result.stdout
