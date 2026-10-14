#!/usr/bin/env python3
"""Known RGB888 fixture; GTK imports occur only for monitor/display commands."""

import argparse
import json
from pathlib import Path
import sys
import time

import numpy as np

WIDTH, HEIGHT = 640, 480


def pattern(frame_id: int) -> np.ndarray:
    """Return exact pixels, with a redundant 32-bit optical ID on every row."""
    if not 0 <= frame_id <= 0xFFFFFFFF:
        raise ValueError("frame_id must be an unsigned 32-bit integer")
    y, x = np.indices((HEIGHT, WIDTH), dtype=np.uint32)
    rgb = np.empty((HEIGHT, WIDTH, 3), dtype=np.uint8)
    rgb[:, :, 0] = (x + 3 * y + (frame_id & 255)) % 256
    rgb[:, :, 1] = (5 * x + y + ((frame_id >> 8) & 255)) % 256
    rgb[:, :, 2] = (x ^ y ^ ((frame_id >> 16) & 255)) % 256
    # Two pixels per bit plus its complement: all rows independently identify
    # the source frame, without treating that marker as proof of other pixels.
    bits = ((frame_id >> np.arange(32, dtype=np.uint32)) & 1).astype(np.uint8)
    marker = np.repeat(bits * 255, 2)
    rgb[:, :64, :] = marker[None, :, None]
    rgb[:, 64:128, :] = (255 - marker)[None, :, None]
    # Single-pixel edges and channel primaries expose scaling and permutations.
    rgb[:, 128, :] = (255, 0, 0)
    rgb[:, 129, :] = (0, 255, 0)
    rgb[:, 130, :] = (0, 0, 255)
    rgb[:, 131, :] = (0, 0, 0)
    rgb[:, 132, :] = (255, 255, 255)
    # Full-range channel ramps and coordinate texture are compared byte-for-byte.
    rgb[16:32, 160:416, :] = 0
    rgb[16:32, 160:416, 0] = np.arange(256, dtype=np.uint8)
    rgb[32:48, 160:416, :] = 0
    rgb[32:48, 160:416, 1] = np.arange(256, dtype=np.uint8)
    rgb[48:64, 160:416, :] = 0
    rgb[48:64, 160:416, 2] = np.arange(256, dtype=np.uint8)
    return rgb


def verify(rgb: np.ndarray, expected_id: int | None = None) -> dict:
    """Check all bytes against the analytic pattern; never learn a golden image."""
    if not isinstance(rgb, np.ndarray) or rgb.shape != (HEIGHT, WIDTH, 3) \
            or rgb.dtype != np.uint8:
        raise ValueError("capture must have shape (480, 640, 3) and dtype uint8")
    marker = rgb[:, :128, :]
    first = marker[:, :64, :]
    second = marker[:, 64:, :]
    valid = np.all((first == 0) | (first == 255), axis=(1, 2))
    valid &= np.all(first == first[:, :, :1], axis=(1, 2))
    valid &= np.all(first[:, ::2, :] == first[:, 1::2, :], axis=(1, 2))
    valid &= np.all(second == 255 - first, axis=(1, 2))
    ids = np.sum((first[:, ::2, 0] == 255).astype(np.uint64)
                 << np.arange(32, dtype=np.uint64), axis=1)
    unique, counts = np.unique(ids[valid], return_counts=True)
    id_from_argument = expected_id is not None
    if expected_id is None:
        expected_id = int(unique[np.argmax(counts)]) if len(unique) else None
    if expected_id is not None and not 0 <= expected_id <= 0xFFFFFFFF:
        raise ValueError("expected_id must be an unsigned 32-bit integer")
    report = {
        "expected_id": expected_id,
        "expected_id_source": ("argument" if id_from_argument else
                               "majority_valid_optical_rows" if expected_id is not None
                               else "unavailable"),
        "valid_marker_rows": int(valid.sum()),
        "invalid_marker_rows": np.flatnonzero(~valid).tolist(),
        "optical_ids": {str(int(i)): int(n) for i, n in zip(unique, counts)},
        "mixed_optical_ids": len(unique) > 1,
        "exact_match": False,
    }
    if expected_id is None:
        report["error"] = "No valid marker row; provide --frame-id for full comparison"
        return report
    reference = pattern(expected_id)
    delta = rgb != reference
    pixels = np.any(delta, axis=2)
    report.update(
        exact_match=not bool(delta.any()),
        mismatched_pixels=int(pixels.sum()),
        mismatched_bytes=int(delta.sum()),
        mismatched_bytes_by_channel=delta.sum(axis=(0, 1)).tolist(),
        mismatched_rows=np.flatnonzero(pixels.any(axis=1)).tolist(),
        first_mismatch_y_x=(np.argwhere(pixels)[0].tolist() if pixels.any() else None),
        max_absolute_error=int(np.abs(rgb.astype(np.int16)
                                      - reference.astype(np.int16)).max()),
    )
    return report


def _gtk():
    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    from gi.repository import Gdk, GLib, Gtk
    import cairo
    return Gdk, GLib, Gtk, cairo


def monitors(display) -> list[dict]:
    result = []
    for index in range(display.get_n_monitors()):
        monitor = display.get_monitor(index)
        geometry = monitor.get_geometry()
        result.append(dict(index=index, model=monitor.get_model(),
                           manufacturer=monitor.get_manufacturer(),
                           x=geometry.x, y=geometry.y, width=geometry.width,
                           height=geometry.height, scale=monitor.get_scale_factor()))
    return result


def display_pattern(index: int, frame_id: int, animate: bool, interval_ms: int):
    Gdk, GLib, Gtk, cairo = _gtk()
    display = Gdk.Display.get_default()
    if display is None:
        raise ValueError("No graphical display available")
    available = monitors(display)
    if not 0 <= index < len(available):
        raise ValueError("Monitor index is not present; run list-monitors")
    selected = available[index]
    if (selected["width"], selected["height"], selected["scale"]) != (640, 480, 1):
        raise ValueError("Selected monitor must already be 640x480 with scale 1")
    window = Gtk.Window(title="HDMI RGB888 fixture — Escape to close")
    window.set_decorated(False)
    window.set_default_size(WIDTH, HEIGHT)
    window.move(selected["x"], selected["y"])
    window.fullscreen_on_monitor(window.get_screen(), index)
    area = Gtk.DrawingArea()
    window.add(area)
    state = {"id": frame_id, "error": None, "ready": False,
             "deadline": time.monotonic() + 2.0}

    def draw(widget, context):
        monitor = display.get_monitor_at_window(window.get_window())
        if (widget.get_allocated_width(), widget.get_allocated_height()) != (WIDTH, HEIGHT) \
                or monitor != display.get_monitor(index) or monitor.get_scale_factor() != 1:
            context.set_source_rgb(0, 0, 0)
            context.paint()
            if state["ready"] or time.monotonic() >= state["deadline"]:
                state["error"] = (
                    "Compositor did not place an exact 640x480 window on selected monitor: "
                    f"allocation={widget.get_allocated_width()}x{widget.get_allocated_height()}, "
                    f"monitor={monitor.get_model()}, scale={monitor.get_scale_factor()}")
                GLib.idle_add(Gtk.main_quit)
            return True
        if not state["ready"]:
            state["ready"] = True
            print(f"Fixture ready: monitor-index={index}, frame-id={state['id']}", flush=True)
        rgb = pattern(state["id"])
        # Cairo RGB24 is native endian 0x00RRGGBB, with one storage byte unused.
        words = (rgb[:, :, 0].astype(np.uint32) << 16) \
            | (rgb[:, :, 1].astype(np.uint32) << 8) | rgb[:, :, 2].astype(np.uint32)
        surface = cairo.ImageSurface.create_for_data(words, cairo.FORMAT_RGB24,
                                                     WIDTH, HEIGHT, WIDTH * 4)
        context.set_source_surface(surface, 0, 0)
        context.get_source().set_filter(cairo.FILTER_NEAREST)
        context.paint()
        return True

    def tick():
        if not state["ready"]:
            return True
        state["id"] = (state["id"] + 1) & 0xFFFFFFFF
        area.queue_draw()
        return True

    window.connect("destroy", lambda _w: Gtk.main_quit() if Gtk.main_level() else None)
    window.connect("key-press-event", lambda _w, e: Gtk.main_quit()
                   if e.keyval == Gdk.KEY_Escape else False)
    area.connect("draw", draw)
    window.show_all()
    def settle():
        if state["ready"]:
            return False
        if time.monotonic() >= state["deadline"]:
            state["error"] = "Compositor did not settle the selected 640x480 window within 2 seconds"
            Gtk.main_quit()
            return False
        area.queue_draw()
        return True
    GLib.timeout_add(50, settle)
    if animate:
        GLib.timeout_add(interval_ms, tick)
    Gtk.main()
    window.destroy()
    if state["error"]:
        raise ValueError(state["error"])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list-monitors")
    start = commands.add_parser("start")
    start.add_argument("--monitor-index", type=int, required=True)
    start.add_argument("--frame-id", type=int, default=1)
    start.add_argument("--animate", action="store_true")
    start.add_argument("--interval-ms", type=int, default=17)
    generate = commands.add_parser("generate")
    generate.add_argument("--frame-id", type=int, required=True)
    generate.add_argument("--output", type=Path, required=True)
    validate = commands.add_parser("verify")
    validate.add_argument("capture", type=Path)
    validate.add_argument("--frame-id", type=int)
    args = parser.parse_args(argv)
    try:
        if args.command == "generate":
            rgb = pattern(args.frame_id)
            with args.output.open("xb") as handle:
                np.save(handle, rgb, allow_pickle=False)
        elif args.command == "verify":
            report = verify(np.load(args.capture, allow_pickle=False), args.frame_id)
            print(json.dumps(report, indent=2))
            return 0 if report["exact_match"] else 1
        elif args.command == "list-monitors":
            Gdk, _, _, _ = _gtk()
            display = Gdk.Display.get_default()
            if display is None:
                raise ValueError("No graphical display available")
            print(json.dumps(monitors(display), indent=2))
        else:
            pattern(args.frame_id)  # Validate before opening any window.
            if args.interval_ms < 1:
                raise ValueError("interval-ms must be positive")
            display_pattern(args.monitor_index, args.frame_id, args.animate, args.interval_ms)
    except (ValueError, OSError, ImportError, EOFError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
