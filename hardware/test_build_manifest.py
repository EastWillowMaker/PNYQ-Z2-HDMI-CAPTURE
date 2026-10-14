"""Regression checks for required receiver parameters in sparse HWH XML."""
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from build_manifest import require_vga_receiver


def hwh(parameters):
    return ET.fromstring('<ROOT><MODULE FULLNAME="/video/hdmi_in/frontend/dvi2rgb_0">'
                         f'<PARAMETERS>{parameters}</PARAMETERS></MODULE></ROOT>')


def test_optional_parameter_without_value_does_not_reject_valid_receiver():
    require_vga_receiver(hwh('<PARAMETER NAME="unrelated"/>'
                            '<PARAMETER NAME="kClkRange" VALUE="5"/>'))


@pytest.mark.parametrize('parameters', [
    '', '<PARAMETER NAME="kClkRange"/>',
    '<PARAMETER NAME="kClkRange" VALUE="1"/>',
    '<PARAMETER NAME="kClkRange" VALUE="2"/>',
    '<PARAMETER NAME="kClkRange" VALUE="5"/>'
    '<PARAMETER NAME="kClkRange" VALUE="5"/>',
])
def test_required_clock_range_is_unique_and_exact(parameters):
    with pytest.raises(RuntimeError):
        require_vga_receiver(hwh(parameters))


def test_absent_receiver_rejected():
    with pytest.raises(RuntimeError):
        require_vga_receiver(ET.fromstring('<ROOT/>'))


def test_duplicate_receiver_rejected():
    root = hwh('<PARAMETER NAME="kClkRange" VALUE="5"/>')
    root.append(ET.fromstring(ET.tostring(root.find('MODULE'))))
    with pytest.raises(RuntimeError):
        require_vga_receiver(root)
