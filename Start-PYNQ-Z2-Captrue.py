#!/usr/bin/env python3
"""Connect to the PYNQ-Z2 from the PC and start HDMI capture."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))
from hdmi_capture.launchers import board_main

if __name__ == '__main__':
    raise SystemExit(board_main())
