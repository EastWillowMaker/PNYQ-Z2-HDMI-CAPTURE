# PYNQ buffer regression fixture

`pynq_3_0_1_buffer.py` is a copy of the installed PYNQ 3.0.1 board's
`pynq/buffer.py`, retained to reproduce its actual buffer lifetime behavior.
The original Xilinx copyright and BSD-3-Clause identifier remain intact.
The upstream BSD-3-Clause license is included in `PYNQ-LICENSE`, copied from
PYNQ commit `93ddd21ab623883590a8c8b07f0b157b2855da4b`.

Tests substitute hardware allocation/release dependencies; they do not execute
native DMA. This fixture is third-party source, not newly authored project code.

Only trailing blank lines at EOF were removed. The original installed/upstream
file SHA256 is `c3cfea4e2a94aa9b1981ae79210a69eee0f17b5a5c4cd26e7bc2cf7de01fb236`;
executable source is unchanged.
