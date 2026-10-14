#!/usr/bin/env python3
"""Native Wayland SDL2/EGL 8-bit source experiment; does not change display modes."""

import argparse
import ctypes as C
import ctypes.util
import json
import hashlib
import os
from pathlib import Path
import sys
import time


def _function(library, name, result, arguments):
    function = getattr(library, name)
    function.restype, function.argtypes = result, arguments
    return function


def libraries():
    sdl = C.CDLL(ctypes.util.find_library("SDL2-2.0") or "libSDL2-2.0.so.0")
    gl = C.CDLL(ctypes.util.find_library("GLESv2") or "libGLESv2.so.2")
    signatures = {
        "SDL_Init": (C.c_int, [C.c_uint]), "SDL_Quit": (None, []),
        "SDL_GetError": (C.c_char_p, []),
        "SDL_GetCurrentVideoDriver": (C.c_char_p, []),
        "SDL_GetNumVideoDisplays": (C.c_int, []),
        "SDL_GetDisplayName": (C.c_char_p, [C.c_int]),
        "SDL_GetDisplayBounds": (C.c_int, [C.c_int, C.c_void_p]),
        "SDL_GL_SetAttribute": (C.c_int, [C.c_int, C.c_int]),
        "SDL_GL_GetAttribute": (C.c_int, [C.c_int, C.POINTER(C.c_int)]),
        "SDL_CreateWindow": (C.c_void_p, [C.c_char_p, C.c_int, C.c_int,
                                         C.c_int, C.c_int, C.c_uint]),
        "SDL_DestroyWindow": (None, [C.c_void_p]),
        "SDL_SetWindowFullscreen": (C.c_int, [C.c_void_p, C.c_uint]),
        "SDL_GetWindowDisplayIndex": (C.c_int, [C.c_void_p]),
        "SDL_GL_GetDrawableSize": (None, [C.c_void_p, C.POINTER(C.c_int),
                                         C.POINTER(C.c_int)]),
        "SDL_GL_CreateContext": (C.c_void_p, [C.c_void_p]),
        "SDL_GL_DeleteContext": (None, [C.c_void_p]),
        "SDL_GL_SetSwapInterval": (C.c_int, [C.c_int]),
        "SDL_GL_SwapWindow": (None, [C.c_void_p]),
        "SDL_PollEvent": (C.c_int, [C.c_void_p]),
    }
    for name, (result, arguments) in signatures.items():
        _function(sdl, name, result, arguments)
    gl_signatures = {
        "glGetString": (C.c_char_p, [C.c_uint]),
        "glGetError": (C.c_uint, []),
        "glGetIntegerv": (None, [C.c_uint, C.POINTER(C.c_int)]),
        "glDisable": (None, [C.c_uint]),
        "glViewport": (None, [C.c_int, C.c_int, C.c_int, C.c_int]),
        "glClearColor": (None, [C.c_float] * 4),
        "glClear": (None, [C.c_uint]),
        "glCreateShader": (C.c_uint, [C.c_uint]),
        "glShaderSource": (None, [C.c_uint, C.c_int, C.POINTER(C.c_char_p), C.c_void_p]),
        "glCompileShader": (None, [C.c_uint]),
        "glGetShaderiv": (None, [C.c_uint, C.c_uint, C.POINTER(C.c_int)]),
        "glGetShaderInfoLog": (None, [C.c_uint, C.c_int, C.c_void_p, C.c_void_p]),
        "glCreateProgram": (C.c_uint, []),
        "glAttachShader": (None, [C.c_uint, C.c_uint]),
        "glBindAttribLocation": (None, [C.c_uint, C.c_uint, C.c_char_p]),
        "glLinkProgram": (None, [C.c_uint]),
        "glGetProgramiv": (None, [C.c_uint, C.c_uint, C.POINTER(C.c_int)]),
        "glGetProgramInfoLog": (None, [C.c_uint, C.c_int, C.c_void_p, C.c_void_p]),
        "glUseProgram": (None, [C.c_uint]),
        "glGetUniformLocation": (C.c_int, [C.c_uint, C.c_char_p]),
        "glUniform1i": (None, [C.c_int, C.c_int]),
        "glGenTextures": (None, [C.c_int, C.POINTER(C.c_uint)]),
        "glBindTexture": (None, [C.c_uint, C.c_uint]),
        "glTexParameteri": (None, [C.c_uint, C.c_uint, C.c_int]),
        "glPixelStorei": (None, [C.c_uint, C.c_int]),
        "glTexImage2D": (None, [C.c_uint, C.c_int, C.c_int, C.c_int, C.c_int,
                               C.c_int, C.c_uint, C.c_uint, C.c_void_p]),
        "glTexSubImage2D": (None, [C.c_uint, C.c_int, C.c_int, C.c_int, C.c_int,
                                  C.c_int, C.c_uint, C.c_uint, C.c_void_p]),
        "glEnableVertexAttribArray": (None, [C.c_uint]),
        "glVertexAttribPointer": (None, [C.c_uint, C.c_int, C.c_uint, C.c_ubyte,
                                        C.c_int, C.c_void_p]),
        "glDrawArrays": (None, [C.c_uint, C.c_int, C.c_int]),
        "glReadPixels": (None, [C.c_int, C.c_int, C.c_int, C.c_int,
                               C.c_uint, C.c_uint, C.c_void_p]),
    }
    for name, (result, arguments) in gl_signatures.items():
        _function(gl, name, result, arguments)
    return sdl, gl


def monitor_list(sdl):
    result = []
    for index in range(sdl.SDL_GetNumVideoDisplays()):
        bounds = (C.c_int * 4)()
        if sdl.SDL_GetDisplayBounds(index, bounds):
            raise RuntimeError(sdl.SDL_GetError().decode())
        result.append({"index": index, "name": sdl.SDL_GetDisplayName(index).decode(),
                       "x": bounds[0], "y": bounds[1],
                       "width": bounds[2], "height": bounds[3]})
    return result


def require_monitor(monitors, index):
    if not 0 <= index < len(monitors):
        raise ValueError("Selected monitor index is absent")
    if (monitors[index]["width"], monitors[index]["height"]) != (640, 480):
        raise ValueError("Selected monitor must already be 640x480")


def _shader(gl, kind, source):
    shader = gl.glCreateShader(kind)
    text = (C.c_char_p * 1)(source)
    gl.glShaderSource(shader, 1, text, None)
    gl.glCompileShader(shader)
    success = C.c_int()
    gl.glGetShaderiv(shader, 0x8B81, C.byref(success))
    if not success.value:
        log = C.create_string_buffer(4096)
        gl.glGetShaderInfoLog(shader, len(log), None, log)
        raise RuntimeError(log.value.decode())
    return shader


def verify_readback(reference, bottom_up_rgba):
    """Read only this application's synthetic backbuffer, never desktop pixels."""
    import numpy as np
    actual = bottom_up_rgba[::-1, :, :3]
    if not np.array_equal(actual, reference):
        mismatches = actual != reference
        delta = actual.astype(np.int16) - reference.astype(np.int16)
        location = np.argwhere(mismatches)[0].tolist()
        raise RuntimeError(f"Synthetic GL framebuffer is not exact: "
                           f"mismatched_bytes={int(mismatches.sum())}, "
                           f"first_y_x_channel={location}, "
                           f"delta_range=[{int(delta.min())},{int(delta.max())}]")


def run(sdl, gl, index, frame_id, animate, interval_ms, duration, self_check=False,
        events=None):
    from hdmi_pattern import pattern
    pattern(frame_id)  # Input validation before window creation.
    require_monitor(monitor_list(sdl), index)
    # SDL_GL attributes: RGB8, alpha/depth/stencil0, double buffer, GLES2.
    for attribute, value in [(0, 8), (1, 8), (2, 8), (3, 0), (5, 1), (6, 0),
                             (7, 0), (17, 2), (18, 0), (21, 4), (23, 0)]:
        if sdl.SDL_GL_SetAttribute(attribute, value):
            raise RuntimeError(sdl.SDL_GetError().decode())
    centered = 0x2FFF0000 | index
    window = sdl.SDL_CreateWindow(b"HDMI exact RGB GLES fixture", centered, centered,
                                  640, 480, 0x2 | 0x4)
    if not window:
        raise RuntimeError(sdl.SDL_GetError().decode())
    context = None
    try:
        if sdl.SDL_SetWindowFullscreen(window, 0x1001):  # Existing desktop mode.
            raise RuntimeError(sdl.SDL_GetError().decode())
        context = sdl.SDL_GL_CreateContext(window)
        if not context:
            raise RuntimeError(sdl.SDL_GetError().decode())
        sdl.SDL_GL_SetSwapInterval(1)
        attributes = {}
        for name, attribute, token in [("red", 0, 0x0D52), ("green", 1, 0x0D53),
                                       ("blue", 2, 0x0D54), ("alpha", 3, 0x0D55)]:
            sdl_value, gl_value = C.c_int(), C.c_int()
            if sdl.SDL_GL_GetAttribute(attribute, C.byref(sdl_value)):
                raise RuntimeError(sdl.SDL_GetError().decode())
            gl.glGetIntegerv(token, C.byref(gl_value))
            attributes[name] = {"SDL": sdl_value.value, "GL": gl_value.value}
        print(json.dumps({"driver": sdl.SDL_GetCurrentVideoDriver().decode(),
                          "GL_version": gl.glGetString(0x1F02).decode(),
                          "GL_renderer": gl.glGetString(0x1F01).decode(),
                          "channel_bits": attributes}), flush=True)
        if any(attributes[channel]["GL"] != 8 for channel in ["red", "green", "blue"]):
            raise RuntimeError("GL framebuffer must report exactly8 bits per RGB channel")
        gl.glDisable(0x0BD0)  # GL_DITHER
        gl.glDisable(0x0BE2)  # GL_BLEND
        gl.glDisable(0x0B71)  # GL_DEPTH_TEST
        vertex = _shader(gl, 0x8B31, b"attribute vec2 p; attribute vec2 t; varying highp vec2 uv; void main(){ gl_Position=vec4(p,0.,1.); uv=t; }")
        fragment = _shader(gl, 0x8B30, b"precision highp float; varying highp vec2 uv; uniform sampler2D image; void main(){ gl_FragColor=vec4(texture2D(image,uv).rgb,1.); }")
        program = gl.glCreateProgram()
        gl.glAttachShader(program, vertex)
        gl.glAttachShader(program, fragment)
        gl.glBindAttribLocation(program, 0, b"p")
        gl.glBindAttribLocation(program, 1, b"t")
        gl.glLinkProgram(program)
        success = C.c_int()
        gl.glGetProgramiv(program, 0x8B82, C.byref(success))
        if not success.value:
            log = C.create_string_buffer(4096)
            gl.glGetProgramInfoLog(program, len(log), None, log)
            raise RuntimeError(log.value.decode())
        gl.glUseProgram(program)
        gl.glUniform1i(gl.glGetUniformLocation(program, b"image"), 0)
        texture = C.c_uint()
        gl.glGenTextures(1, C.byref(texture))
        gl.glBindTexture(0x0DE1, texture.value)
        for parameter, value in [(0x2800, 0x2600), (0x2801, 0x2600),
                                 (0x2802, 0x812F), (0x2803, 0x812F)]:
            gl.glTexParameteri(0x0DE1, parameter, value)  # nearest/clamp
        gl.glPixelStorei(0x0CF5, 1)
        rgb = pattern(frame_id)
        generated_ns = time.monotonic_ns()
        gl.glTexImage2D(0x0DE1, 0, 0x1907, 640, 480, 0, 0x1907, 0x1401,
                        C.c_void_p(rgb.ctypes.data))
        vertices = (C.c_float * 16)(-1, -1, 0, 1, 1, -1, 1, 1,
                                    -1, 1, 0, 0, 1, 1, 1, 0)
        gl.glEnableVertexAttribArray(0)
        gl.glEnableVertexAttribArray(1)
        gl.glVertexAttribPointer(0, 2, 0x1406, 0, 16, C.cast(vertices, C.c_void_p))
        gl.glVertexAttribPointer(1, 2, 0x1406, 0, 16,
                                 C.c_void_p(C.addressof(vertices) + 8))
        event = (C.c_uint8 * 128)()
        ready, running = False, True
        checked_id, checks, logged_id = None, 0, None
        started, last_update = time.monotonic(), time.monotonic()
        while running:
            while sdl.SDL_PollEvent(event):
                kind = C.cast(event, C.POINTER(C.c_uint32))[0]
                if kind == 0x100 or (kind == 0x300 and
                                    C.c_int.from_buffer(event, 20).value == 27):
                    running = False
            if not running:
                break
            width, height = C.c_int(), C.c_int()
            sdl.SDL_GL_GetDrawableSize(window, C.byref(width), C.byref(height))
            placed = sdl.SDL_GetWindowDisplayIndex(window) == index
            exact = (width.value, height.value) == (640, 480)
            if not (placed and exact):
                if ready or time.monotonic() - started >= 2:
                    raise RuntimeError(f"Wrong source placement: display={sdl.SDL_GetWindowDisplayIndex(window)}, drawable={width.value}x{height.value}")
                gl.glClearColor(0, 0, 0, 1)
                gl.glClear(0x4000)
                sdl.SDL_GL_SwapWindow(window)
                continue
            gl.glViewport(0, 0, 640, 480)
            if animate and ready and time.monotonic() - last_update >= interval_ms / 1000:
                frame_id = (frame_id + 1) & 0xFFFFFFFF
                rgb = pattern(frame_id)
                generated_ns = time.monotonic_ns()
                gl.glTexSubImage2D(0x0DE1, 0, 0, 0, 640, 480, 0x1907, 0x1401,
                                   C.c_void_p(rgb.ctypes.data))
                last_update = time.monotonic()
            gl.glDrawArrays(0x0005, 0, 4)
            if self_check and checked_id != frame_id:
                import numpy as np
                readback = np.empty((480, 640, 4), dtype=np.uint8)
                gl.glReadPixels(0, 0, 640, 480, 0x1908, 0x1401,
                                C.c_void_p(readback.ctypes.data))
                read_error = gl.glGetError()
                if read_error:
                    raise RuntimeError(f"GL readback error 0x{read_error:x}")
                verify_readback(rgb, readback)
                checked_id = frame_id
                checks += 1
                if checks == 1 or checks % 50 == 0:
                    print(f"Synthetic framebuffer exact: checks={checks}, "
                          f"frame-id={frame_id}, bytes=921600", flush=True)
            error = gl.glGetError()
            if error:
                raise RuntimeError(f"GL error 0x{error:x}")
            new_logged_id = logged_id != frame_id
            if events is not None and new_logged_id:
                events.write(json.dumps({"event": "source_pre_swap", "frame_id": frame_id,
                                         "frame_generated_monotonic_ns": generated_ns,
                                         "monotonic_ns": time.monotonic_ns(),
                                         "unix_time_ns": time.time_ns(),
                                         "framebuffer_self_check_passed":
                                         checked_id == frame_id if self_check else None}) + "\n")
                events.flush()
            sdl.SDL_GL_SwapWindow(window)
            if events is not None and new_logged_id:
                events.write(json.dumps({"event": "source_swap_return", "frame_id": frame_id,
                                         "monotonic_ns": time.monotonic_ns(),
                                         "unix_time_ns": time.time_ns()}) + "\n")
                events.flush()
                logged_id = frame_id
            if not ready:
                ready = True
                print(f"Fixture ready: monitor-index={index}, frame-id={frame_id}, renderer=GLES", flush=True)
            if duration is not None and time.monotonic() - started >= duration:
                break
    finally:
        if context:
            sdl.SDL_GL_DeleteContext(context)
        sdl.SDL_DestroyWindow(window)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list-monitors", action="store_true")
    parser.add_argument("--monitor-index", type=int)
    parser.add_argument("--frame-id", type=int, default=1)
    parser.add_argument("--animate", action="store_true")
    parser.add_argument("--interval-ms", type=int, default=17)
    parser.add_argument("--duration", type=float, help="Optional bounded source run in seconds")
    parser.add_argument("--self-check", action="store_true",
                        help="Read back each new synthetic source ID before presentation")
    parser.add_argument("--events", type=Path,
                        help="New JSONL file for per-ID generation/pre-swap timestamps")
    args = parser.parse_args(argv)
    if not args.list_monitors and args.monitor_index is None:
        parser.error("--monitor-index is required for a source window")
    if args.interval_ms < 1 or (args.duration is not None and args.duration <= 0):
        parser.error("interval/duration must be positive")
    os.environ["SDL_VIDEODRIVER"] = "wayland"  # Process local; never fallback to Xwayland.
    sdl, events = None, None
    try:
        if args.events:
            events = args.events.open("x")
            events.write(json.dumps({"event": "source_start", "monotonic_ns": time.monotonic_ns(),
                                     "unix_time_ns": time.time_ns(),
                                     "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                                     "monitor_index": args.monitor_index,
                                     "frame_id": args.frame_id, "animate": args.animate,
                                     "interval_ms": args.interval_ms, "self_check": args.self_check}) + "\n")
            events.flush()
        sdl, gl = libraries()
        if sdl.SDL_Init(0x20):
            raise RuntimeError(sdl.SDL_GetError().decode())
        if sdl.SDL_GetCurrentVideoDriver() != b"wayland":
            raise RuntimeError("Native Wayland is required")
        if args.list_monitors:
            print(json.dumps(monitor_list(sdl), indent=2))
        else:
            run(sdl, gl, args.monitor_index, args.frame_id, args.animate,
                args.interval_ms, args.duration, args.self_check, events)
    except (ValueError, RuntimeError, OSError, ImportError) as error:
        print(str(error), file=sys.stderr)
        return 2
    finally:
        if sdl:
            sdl.SDL_Quit()
        if events:
            events.write(json.dumps({"event": "source_stop", "monotonic_ns": time.monotonic_ns(),
                                     "unix_time_ns": time.time_ns()}) + "\n")
            events.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
