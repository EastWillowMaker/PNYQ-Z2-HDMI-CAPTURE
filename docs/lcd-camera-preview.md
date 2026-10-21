# LCD camera alignment preview

Run the local camera framing page with Python 3:

```sh
python3 tools/lcd_camera_preview.py
```

Open the printed `http://127.0.0.1:8765/` address, choose **Start preview**,
and allow camera access. The page serves only the preview HTML on loopback and
uses the browser's camera API. It does not need packages, a board connection,
or an internet connection. Press Ctrl-C in the terminal to stop the server.

Choose another camera from the menu at any time. The page prefers a camera
whose browser label contains “Brio” after permission reveals camera names; a
manual camera choice is kept. If the browser hides names before permission,
the menu uses numbered camera names until permission is granted.

Use the size slider to scale the centered LCD outline, or enable portrait mode
to change it from landscape 3:2 to portrait 2:3. The crosshair is on by
default. Mirror mode is off by default. The preview shows the full camera image
with letterboxing when its aspect ratio differs from the viewing area.

The browser keeps camera access only while preview is running. This page has no
recording, upload, or save controls. It helps align framing against the LCD
area; it does not measure camera-to-display optical latency.
