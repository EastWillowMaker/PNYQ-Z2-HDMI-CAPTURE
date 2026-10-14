"""Run a bounded command on an already authenticated PYNQ UART shell."""
import argparse
import time
from pathlib import Path
import uuid
import serial

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--command', required=True)
p.add_argument('--timeout', type=float, default=15)
p.add_argument('--log', type=Path, required=True)
a = p.parse_args()
marker = 'CONSOLE_DONE_' + uuid.uuid4().hex
with serial.Serial('/dev/serial/by-id/usb-Xilinx_TUL_1234-tul-if01-port0', 115200,
                   timeout=.2, exclusive=True) as s:
    s.write(b'\r')
    time.sleep(.3)
    initial = s.read(8192)
    if b'xilinx@pynq:' not in initial:
        raise SystemExit('Expected existing xilinx shell; command not sent')
    s.write((a.command + (' ' if a.command.rstrip().endswith('&') else '; ') + 'printf "\\n' + marker + ':%s\\n" "$?"\r').encode())
    end = time.monotonic() + a.timeout
    data = initial
    while time.monotonic() < end:
        data += s.read(65536)
        if ('\n' + marker + ':').encode() in data:
            break
    a.log.parent.mkdir(parents=True, exist_ok=True)
    a.log.write_bytes(data)
    text = data.decode(errors='replace')
    print(text)
    lines = [x for x in text.splitlines() if x.startswith(marker + ':')]
    if not lines:
        raise SystemExit('Command timed out; inspect UART before issuing further commands')
    raise SystemExit(int(lines[-1].split(':')[-1]))
