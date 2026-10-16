"""Tkinter live viewer for the HDMI capture client."""

from __future__ import annotations

import argparse
import copy
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

from .client import CaptureClient
from .images import save_bmp
from .protocol import Frame


class LatestFrameStore:
    """Keep one owned frame so a slow preview cannot build an unbounded queue."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._frame: Frame | None = None
        self._revision = 0

    def clear(self) -> None:
        with self._lock:
            self._frame = None
            self._revision += 1

    def publish(self, frame: Frame) -> None:
        with self._lock:
            self._frame = frame
            self._revision += 1

    def current(self) -> tuple[int, Frame | None]:
        with self._lock:
            return self._revision, self._frame

@dataclass(frozen=True)
class WorkerSnapshot:
    connected: bool
    finished: bool
    error: str | None
    frame_count: int


class CaptureWorker:
    """Own the only CaptureClient reader and publish only the latest frame."""

    def __init__(
        self,
        host: str,
        port: int,
        *,
        timeout: float = 5.0,
        client_factory: Callable[..., CaptureClient] = CaptureClient,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.client_factory = client_factory
        self.frames = LatestFrameStore()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._connected = False
        self._finished = True
        self._error: str | None = None
        self._frame_count = 0

    def start(self) -> None:
        if self.is_alive:
            raise RuntimeError("capture worker is already running")
        self.frames.clear()
        self._stop.clear()
        with self._lock:
            self._connected = False
            self._finished = False
            self._error = None
            self._frame_count = 0
        self._thread = threading.Thread(target=self._run, name="hdmi-capture-reader", daemon=True)
        self._thread.start()

    def request_stop(self) -> None:
        self._stop.set()

    @property
    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def snapshot(self) -> WorkerSnapshot:
        with self._lock:
            return WorkerSnapshot(self._connected, self._finished, self._error, self._frame_count)

    def _run(self) -> None:
        try:
            with self.client_factory(self.host, self.port, timeout=self.timeout) as client:
                if self._stop.is_set():
                    return
                with self._lock:
                    self._connected = True
                while not self._stop.is_set():
                    frame = client.read()
                    if self._stop.is_set():
                        break
                    with self._lock:
                        self.frames.publish(frame)
                        self._frame_count += 1
        except Exception as error:
            if not self._stop.is_set():
                with self._lock:
                    self._error = f"{type(error).__name__}: {error}"
        finally:
            with self._lock:
                self._connected = False
                self._finished = True

    def freeze_latest(self) -> Frame | None:
        """Atomically select and copy a frame only while the link is live."""
        with self._lock:
            if not self._connected:
                return None
            _, frame = self.frames.current()
        if frame is None:
            return None
        return Frame(np.array(frame.rgb, copy=True), copy.deepcopy(frame.metadata))


def _positive_timeout(value: str) -> float:
    try:
        result = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("timeout must be a positive number") from error
    if not np.isfinite(result) or result <= 0:
        raise argparse.ArgumentTypeError("timeout must be a positive finite number")
    return result


class CaptureViewer:
    """Responsive Tk window; all network reads stay in the worker thread."""

    def __init__(
        self,
        root: object,
        host: str,
        port: int,
        *,
        timeout: float = 5.0,
        client_factory: Callable[..., CaptureClient] = CaptureClient,
    ) -> None:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
        from PIL import Image, ImageTk

        self._tk = tk
        self._filedialog = filedialog
        self._messagebox = messagebox
        self._ttk = ttk
        self._image = Image
        self._image_tk = ImageTk
        self.root = root
        self.worker = CaptureWorker(host, port, timeout=timeout, client_factory=client_factory)
        self._last_revision = -1
        self._photo = None
        self._closing = False
        self._shutdown_deadline = 0.0
        self._save_lock = threading.Lock()
        self._save_result: tuple[Path, Exception | None] | None = None
        self._save_pending = False
        self._save_thread: threading.Thread | None = None
        self._status_override: str | None = None
        self._status_override_until = 0.0

        root.title("HDMI Capture Viewer")
        root.minsize(640, 400)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.rowconfigure(1, weight=1)
        root.columnconfigure(0, weight=1)

        toolbar = ttk.Frame(root, padding=8)
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.columnconfigure(0, weight=1)
        self.status = ttk.Label(toolbar, text="Disconnected")
        self.status.grid(row=0, column=0, sticky="w")
        self.reconnect_button = ttk.Button(toolbar, text="Reconnect", command=self.reconnect)
        self.reconnect_button.grid(row=0, column=1, padx=(8, 0))
        self.save_button = ttk.Button(toolbar, text="Save frame…", command=self.save_current, state="disabled")
        self.save_button.grid(row=0, column=2, padx=(8, 0))

        self.preview = ttk.Label(root, text="Waiting for frames", anchor="center")
        self.preview.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        root.bind("<Configure>", self._on_configure, add="+")

        self.reconnect()
        root.after(100, self._tick)

    def reconnect(self) -> None:
        if self._closing or self.worker.is_alive:
            return
        self.worker.start()
        self.status.configure(text="Connecting…")
        self.reconnect_button.configure(state="disabled")
        self.save_button.configure(state="disabled")
        self._photo = None
        self.preview.configure(image="", text="Waiting for frames")
        self._last_revision = -1

    def save_current(self) -> None:
        if self._save_pending:
            return
        frozen = self.worker.freeze_latest()
        if frozen is None:
            self.save_button.configure(state="disabled")
            return

        selected = self._filedialog.asksaveasfilename(
            parent=self.root,
            title="Save uncompressed RGB888 frame",
            defaultextension=".bmp",
            initialfile="capture.bmp",
            filetypes=(("24-bit BMP image", "*.bmp"),),
        )
        if not selected:
            return
        output = Path(selected)
        self._save_pending = True
        self.save_button.configure(state="disabled")
        self.status.configure(text="Saving frame…")

        def save() -> None:
            error = None
            try:
                save_bmp(frozen, output)
            except Exception as caught:
                error = caught
            with self._save_lock:
                self._save_result = (output, error)

        self._save_thread = threading.Thread(target=save, name="hdmi-bmp-writer", daemon=True)
        self._save_thread.start()

    def close(self) -> None:
        if self._closing:
            return
        self._closing = True
        self.status.configure(text="Stopping capture…")
        self.reconnect_button.configure(state="disabled")
        self.save_button.configure(state="disabled")
        self.worker.request_stop()
        self._shutdown_deadline = time.monotonic() + min(max(2.5, self.worker.timeout + 1.0), 6.0)
        self.root.after(25, self._finish_close)

    def _finish_close(self) -> None:
        saving = self._save_thread is not None and self._save_thread.is_alive()
        if saving:
            self.status.configure(text="Finishing save before closing…")
            self.root.after(100, self._finish_close)
            return
        if not self.worker.is_alive or time.monotonic() >= self._shutdown_deadline:
            self.root.destroy()
            return
        self.root.after(25, self._finish_close)

    def _on_configure(self, event: object) -> None:
        if getattr(event, "widget", None) is self.root:
            self._last_revision = -1

    def _tick(self) -> None:
        if self._closing:
            return
        state = self.worker.snapshot()
        with self._save_lock:
            save_result = self._save_result
            self._save_result = None
        if save_result is not None:
            output, error = save_result
            self._save_pending = False
            if error is None:
                self._status_override = f"Saved {output}"
            else:
                self._status_override = f"Save failed: {error}"
                self._messagebox.showerror("Could not save frame", str(error), parent=self.root)
            self._status_override_until = time.monotonic() + 5.0

        if self._save_pending:
            status_text = "Saving frame…"
        elif self._status_override and time.monotonic() < self._status_override_until:
            status_text = self._status_override
        elif state.connected:
            status_text = f"Connected · {state.frame_count} frames received"
        elif state.error:
            status_text = f"Disconnected: {state.error}"
        elif state.finished:
            status_text = "Disconnected. Select Reconnect to try again."
        else:
            status_text = "Connecting…"
        self.status.configure(text=status_text)

        reconnect_state = "disabled" if self.worker.is_alive else "normal"
        self.reconnect_button.configure(state=reconnect_state)
        revision, frame = self.worker.frames.current()
        can_save = state.connected and frame is not None and not self._save_pending
        self.save_button.configure(state="normal" if can_save else "disabled")
        if frame is not None and revision != self._last_revision:
            self._show_preview(frame)
            self._last_revision = revision
        self.root.after(100, self._tick)

    def _show_preview(self, frame: Frame) -> None:
        image = self._image.fromarray(frame.rgb)
        max_size = (max(1, self.root.winfo_width() - 32), max(1, self.root.winfo_height() - 100))
        image.thumbnail(max_size, self._image.Resampling.LANCZOS)
        self._photo = self._image_tk.PhotoImage(image, master=self.root)
        self.preview.configure(image=self._photo, text="")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host", help="Board hostname or IP address")
    parser.add_argument("--port", type=int, default=9020)
    parser.add_argument("--timeout", type=_positive_timeout, default=5.0,
                        help="Connect and complete-frame timeout in seconds (default: 5)")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    try:
        import tkinter as tk
        from PIL import Image  # noqa: F401
    except ImportError as error:
        print(
            "The viewer requires Tk support in Python and Pillow; install with "
            "pip install '.[gui]' and add your system's Tk package if needed.",
            file=sys.stderr,
        )
        return 2

    root = tk.Tk()
    CaptureViewer(root, args.host, args.port, timeout=args.timeout)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
