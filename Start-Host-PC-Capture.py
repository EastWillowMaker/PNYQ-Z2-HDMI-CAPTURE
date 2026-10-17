#!/usr/bin/env python3
"""Open the desktop capture viewer on the PC."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))
from hdmi_capture.launchers import host_main

if __name__ == '__main__':
    raise SystemExit(host_main())
