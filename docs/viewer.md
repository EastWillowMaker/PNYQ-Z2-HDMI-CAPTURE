# Desktop frame viewer

The optional desktop viewer shows frames from the same `CaptureClient` used by
the command line. The reader runs in one background thread and keeps only the
latest complete frame for the preview. A connection or frame error stops the
reader. The default connection and full-frame timeout is five seconds; use
`--timeout` to change it. Select **Reconnect** to start a new connection.

Install the viewer extra and start it with the board address:

```sh
python -m pip install -e '.[gui]'
hdmi-capture-viewer 192.168.1.10 --port 9020
```

Python must include Tk support. On Linux, install the distribution's Tk package
if `tkinter` is unavailable. The `hdmi-capture` command line remains available
for snapshots, bounded captures, statistics, and benchmarks.

Select **Save frame…** to save the latest complete frame received when the
button was pressed. The viewer freezes a copy before opening the file dialog,
so later frames cannot change the selected image. It writes a new, uncompressed
24-bit BMP and a JSON sidecar with the frame metadata. Existing image or
sidecar files are never overwritten.

BMP stores pixels bottom-up in BGR order and pads each row to a four-byte
boundary. These rules change the file layout, but not any pixel value: decoding
the image to RGB888 reproduces the received array byte for byte. The preview
may be scaled to fit the window; the saved image remains at the received size.
The Save button stays disabled before the first frame and while disconnected.
Closing stops capture within a bounded wait. If a save is in progress, the
window stays open until the BMP and metadata sidecar finish writing.

The [real1080p HDMI save check](results/2026-10-17/1080p30-gui-hdmi-001.md)
invoked the actual button and verified every decoded RGB byte against the
selected frame and independent source pattern. To supply the board-generated
J9→J10 test image, follow [output-loop preparation](output-loop.md).
