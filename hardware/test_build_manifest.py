"""Regression checks for required receiver parameters in sparse HWH XML."""
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from build_manifest import (
    require_credit_configuration,
    require_receiver_mode,
    require_vga_receiver,
)
from hdmi_capture.modes import get_mode


def hwh(parameters):
    return ET.fromstring('<ROOT><MODULE FULLNAME="/video/hdmi_in/frontend/dvi2rgb_0">'
                         f'<PARAMETERS>{parameters}</PARAMETERS></MODULE></ROOT>')


def test_optional_parameter_without_value_does_not_reject_valid_receiver():
    require_vga_receiver(hwh('<PARAMETER NAME="unrelated"/>'
                            '<PARAMETER NAME="kClkRange" VALUE="5"/>'))


def test_1080p30_receiver_requires_and_accepts_clock_range_two():
    require_receiver_mode(hwh('<PARAMETER NAME="kClkRange" VALUE="2"/>'),
                          get_mode('1080p30'))
    with pytest.raises(RuntimeError):
        require_receiver_mode(hwh('<PARAMETER NAME="kClkRange" VALUE="5"/>'),
                              get_mode('1080p30'))


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


def credit_hwh():
    root = ET.Element('ROOT')
    modules = {
        'capture_control': dict(C_GPIO_WIDTH='32', C_IS_DUAL='1', C_ALL_OUTPUTS='1',
            C_ALL_INPUTS_2='1', C_GPIO2_WIDTH='32', C_DOUT_DEFAULT='0x00000000'),
        'axi_vdma': dict(C_INCLUDE_S2MM='1', C_INCLUDE_MM2S='0', C_NUM_FSTORES='4',
                        C_ENABLE_DEBUG_INFO_15='1', C_USE_S2MM_FSYNC='0', C_USE_FSYNC='1'),
    }
    for name in ('capture_credit', 'capture_completion', 'capture_sequence'):
        modules[name] = dict(C_GPIO_WIDTH='32', C_GPIO2_WIDTH='32', C_IS_DUAL='1',
                            C_ALL_INPUTS='1', C_ALL_INPUTS_2='1')
    for name, parameters in modules.items():
        module = ET.SubElement(root, 'MODULE', FULLNAME='/video/' + name)
        rows = ET.SubElement(module, 'PARAMETERS')
        for key, value in parameters.items():
            ET.SubElement(rows, 'PARAMETER', NAME=key, VALUE=value)
    return root


def test_credit_hwh_has_exact_default_disabled_32_bit_controls_and_frame_counter():
    require_credit_configuration(credit_hwh())


@pytest.mark.parametrize('module,parameter,value', [
    ('capture_control', 'C_GPIO_WIDTH', '1'),
    ('capture_control', 'C_DOUT_DEFAULT', '0x00000001'),
    ('capture_control', 'C_DOUT_DEFAULT', '0x00000002'),
    ('capture_control', 'C_DOUT_DEFAULT', None),
    ('axi_vdma', 'C_USE_S2MM_FSYNC', '2'),
    ('axi_vdma', 'C_USE_S2MM_FSYNC', None),
    ('axi_vdma', 'C_ENABLE_DEBUG_INFO_15', '0'),
    ('axi_vdma', 'C_ENABLE_DEBUG_INFO_15', None),
    ('capture_sequence', 'C_ALL_INPUTS_2', '0'),
])
def test_credit_hwh_rejects_legacy_enabled_and_unsupported_configurations(module, parameter, value):
    root = credit_hwh()
    row = root.find(f".//MODULE[@FULLNAME='/video/{module}']/PARAMETERS/PARAMETER[@NAME='{parameter}']")
    if value is None:
        row.attrib.pop('VALUE')
    else:
        row.set('VALUE', value)
    with pytest.raises(RuntimeError):
        require_credit_configuration(root)


def test_credit_hwh_rejects_missing_or_ambiguous_identity_gpio():
    root = credit_hwh()
    module = root.find("MODULE[@FULLNAME='/video/capture_credit']")
    root.remove(module)
    with pytest.raises(RuntimeError):
        require_credit_configuration(root)
    root.append(module)
    root.append(ET.fromstring(ET.tostring(module)))
    with pytest.raises(RuntimeError):
        require_credit_configuration(root)
