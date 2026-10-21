#!/usr/bin/env python3
"""Serve the local LCD camera alignment page on loopback."""

from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


PAGE = Path(__file__).with_name("lcd_camera_preview.html")


class PreviewHandler(BaseHTTPRequestHandler):
    server_version = "LCDCameraPreview/1.0"

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        if path not in ("/", "/lcd_camera_preview.html"):
            self.send_error(404)
            return

        page = PAGE.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(page)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; script-src 'unsafe-inline'; "
            "style-src 'unsafe-inline'; media-src blob: mediastream:; "
            "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(page)

    def log_message(self, format: str, *args: object) -> None:
        # Keep request output local and concise.
        print(f"{self.address_string()} - {format % args}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765, help="local HTTP port (default: 8765)")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    if not PAGE.is_file():
        parser.error(f"preview page not found: {PAGE}")

    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), PreviewHandler)
    except OSError as error:
        parser.exit(2, f"Could not start preview server on 127.0.0.1:{args.port}: {error}\n")

    print(f"LCD camera preview: http://127.0.0.1:{args.port}/")
    print("Press Ctrl-C to stop the local server.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nPreview server stopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
