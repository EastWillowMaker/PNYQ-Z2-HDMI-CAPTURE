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


@pytest.mark.parametrize('frame_id', [0, 0x12345678, 0xFFFFFFFF])
def test_actual_c_1080p30_source_matches_every_reference_byte(binary, frame_id):
    actual = subprocess.check_output([str(binary), '--mode', '1080p30', '--dump',
                                       str(frame_id), '1'])
    assert actual == pattern_module.pattern(frame_id, '1080p30').tobytes()


@pytest.mark.parametrize('frame_id', ['', '-1', '4294967296', '12x'])
def test_invalid_id_rejected_before_display_access(binary, frame_id):
    result = subprocess.run([str(binary), '--dump', frame_id, '1'], capture_output=True)
    assert result.returncode == 2
    assert not result.stdout


def test_unknown_profile_rejected_before_display_access(binary):
    result = subprocess.run([str(binary), '--mode', '1080p60', '--dump', '1', '1'],
                            capture_output=True)
    assert result.returncode == 2
    assert not result.stdout


def test_direct_source_accepts_only_exact_profile_timing(binary, tmp_path):
    probe = tmp_path / 'mode-match.c'
    probe.write_text(f'''#define main kms_fixture_main
#include "{ROOT / 'tools/hdmi_pattern_kms.c'}"
#undef main
int main(void) {{
  const struct profile *vga = find_profile("vga");
  const struct profile *hd = find_profile("1080p30");
  drmModeModeInfo m = {{
      .clock = 74250, .hdisplay = 1920, .hsync_start = 2008,
      .hsync_end = 2052, .htotal = 2200, .vdisplay = 1080,
      .vsync_start = 1084, .vsync_end = 1089, .vtotal = 1125,
      .flags = DRM_MODE_FLAG_PHSYNC | DRM_MODE_FLAG_PVSYNC}};
  if (!matches_profile(&m, hd)) return 1;
  m.htotal++;
  if (matches_profile(&m, hd)) return 2;
  m.htotal--;
  m.clock++;
  if (matches_profile(&m, hd)) return 3;
  m.clock--;
  m.flags = DRM_MODE_FLAG_NHSYNC | DRM_MODE_FLAG_PVSYNC;
  if (matches_profile(&m, hd)) return 4;
  m.flags = DRM_MODE_FLAG_PHSYNC | DRM_MODE_FLAG_PVSYNC |
            DRM_MODE_FLAG_INTERLACE;
  if (matches_profile(&m, hd)) return 5;
  m = (drmModeModeInfo){{
      .clock = 25175, .hdisplay = 640, .hsync_start = 656,
      .hsync_end = 752, .htotal = 800, .vdisplay = 480,
      .vsync_start = 490, .vsync_end = 492, .vtotal = 525,
      .flags = DRM_MODE_FLAG_NHSYNC | DRM_MODE_FLAG_NVSYNC}};
  if (!matches_profile(&m, vga)) return 6;
  m.clock = 25200;
  if (!matches_profile(&m, vga)) return 7;
  return 0;
}}
''')
    flags = subprocess.run(['pkg-config', '--cflags', '--libs', 'libdrm'],
                           capture_output=True, text=True, check=True).stdout.split()
    target = tmp_path / 'mode-match'
    subprocess.run(['cc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                    str(probe), *flags, '-o', str(target)], check=True)
    subprocess.run([str(target)], check=True)
