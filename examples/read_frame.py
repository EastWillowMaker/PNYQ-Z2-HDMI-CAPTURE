"""Read one complete frame without saving a real capture by default."""

import argparse

from hdmi_capture import CaptureClient

parser = argparse.ArgumentParser()
parser.add_argument("host", help="Board IP; IPv6 can include %interface")
parser.add_argument("--port", type=int, default=9020)
args = parser.parse_args()
with CaptureClient(args.host, args.port) as client:
    frame = client.read()
    print(frame.rgb.shape, frame.rgb.dtype, frame.metadata)
