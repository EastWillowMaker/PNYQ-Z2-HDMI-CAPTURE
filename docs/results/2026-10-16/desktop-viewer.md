# Desktop viewer and uncompressed BMP validation

The host viewer uses one `CaptureClient` reader and keeps one latest complete
frame. Saving freezes that frame at button press, then writes an uncompressed
24-bit BMP and JSON sidecar in one background writer. Preview scaling does not
change the saved RGB pixels. The CLI also supports `.bmp` snapshots and bounded
`capture --bmp` runs; existing NPY and optional PNG paths remain available.

Executed from the working tree on 2026-10-16:

```sh
.venv/bin/python -m pytest -q tests/test_images.py tests/test_viewer.py tests/test_cli.py tests/test_client.py tests/test_protocol.py
```

Result: 93 passed. Coverage includes a complete 1920×1080 synthetic RGB image
decoded and compared byte for byte, uncompressed/24-bit BMP headers, channel
order, padded rows, file-conflict and cleanup behavior, TCP client integration,
and a Tk window/save-worker smoke test on the available display. These are
host tests, not evidence of 1080p HDMI acquisition.

Call path: CLI entry point → `cli.main` → `images.save_bmp`; GUI entry point →
`CaptureViewer.save_current` → one writer → `images.save_bmp`. GUI acquisition
is `CaptureWorker._run` → `CaptureClient.read` → protocol parsing. The save
button never opens another capture connection. Tests also cover the inherited
CLI/client/protocol behavior.

Socket loss becomes known when the reader reports it. Until that observation,
the last complete frame can still be selected; it is not relabeled as new.
The viewer waits for a pending save when closing, so a blocked filesystem can
delay closure. Reader shutdown has a six-second grace; no native board DMA is
owned by this host process. Real-board GUI preview and saved-frame validation
remain pending.
