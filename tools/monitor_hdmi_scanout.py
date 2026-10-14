#!/usr/bin/env python3
"""Bounded read-only DRM metadata sampling; never read framebuffer pixels."""

import argparse
import ctypes as C
import ctypes.util
import json
import os
from pathlib import Path
import time

U32, U64, I = C.c_uint32, C.c_uint64, C.c_int
P32, P64 = C.POINTER(U32), C.POINTER(U64)


class Resources(C.Structure):
    _fields_ = [("count_fbs", I), ("fbs", P32), ("count_crtcs", I), ("crtcs", P32),
                ("count_connectors", I), ("connectors", P32),
                ("count_encoders", I), ("encoders", P32),
                ("min_width", U32), ("max_width", U32),
                ("min_height", U32), ("max_height", U32)]


class Mode(C.Structure):
    _fields_ = [("clock", U32)] + [(name, C.c_uint16) for name in
                ["hdisplay", "hsync_start", "hsync_end", "htotal", "hskew",
                 "vdisplay", "vsync_start", "vsync_end", "vtotal", "vscan"]] + [
                ("vrefresh", U32), ("flags", U32), ("type", U32),
                ("name", C.c_char * 32)]


class Connector(C.Structure):
    _fields_ = [(name, U32) for name in ["connector_id", "encoder_id",
                "connector_type", "connector_type_id", "connection",
                "mmWidth", "mmHeight", "subpixel"]] + [
                ("count_modes", I), ("modes", C.POINTER(Mode)),
                ("count_props", I), ("props", P32), ("prop_values", P64),
                ("count_encoders", I), ("encoders", P32)]


class Property(C.Structure):
    _fields_ = [("prop_id", U32), ("flags", U32), ("name", C.c_char * 32),
                ("count_values", I), ("values", P64),
                ("count_enums", I), ("enums", C.c_void_p),
                ("count_blobs", I), ("blob_ids", P32)]


class Encoder(C.Structure):
    _fields_ = [(name, U32) for name in ["encoder_id", "encoder_type", "crtc_id",
                                       "possible_crtcs", "possible_clones"]]


class Crtc(C.Structure):
    _fields_ = [(name, U32) for name in ["crtc_id", "buffer_id", "x", "y",
                                       "width", "height"]] + [
                ("mode_valid", I), ("mode", Mode), ("gamma_size", I)]


class Framebuffer(C.Structure):
    _fields_ = [(name, U32) for name in ["fb_id", "width", "height", "pixel_format"]] + [
                ("modifier", U64), ("flags", U32), ("handles", U32 * 4),
                ("pitches", U32 * 4), ("offsets", U32 * 4)]


def fourcc(value):
    return bytes((value >> shift) & 255 for shift in [0, 8, 16, 24]).decode("ascii")


class MetadataReader:
    def __init__(self, card, connector):
        self.connector = connector
        self.drm = C.CDLL(ctypes.util.find_library("drm") or "libdrm.so.2", use_errno=True)
        for suffix, structure in [("Resources", Resources), ("Connector", Connector),
                                  ("Property", Property), ("Encoder", Encoder),
                                  ("Crtc", Crtc), ("FB2", Framebuffer)]:
            getter = getattr(self.drm, "drmModeGet" + suffix)
            getter.restype = C.POINTER(structure)
            getter.argtypes = [I] if suffix == "Resources" else [I, U32]
            freer = getattr(self.drm, "drmModeFree" + suffix)
            freer.restype, freer.argtypes = None, [C.POINTER(structure)]
        self.drm.drmModeGetConnectorCurrent.restype = C.POINTER(Connector)
        self.drm.drmModeGetConnectorCurrent.argtypes = [I, U32]
        self.fd = os.open(card, os.O_RDONLY | os.O_CLOEXEC)

    def close(self):
        os.close(self.fd)

    def get(self, suffix, identifier=None):
        function = getattr(self.drm, "drmModeGet" + suffix)
        value = function(self.fd) if identifier is None else function(self.fd, identifier)
        if not value:
            raise OSError(C.get_errno(), f"drmModeGet{suffix} failed")
        return value

    def sample(self):
        resources = self.get("Resources")
        connector = None
        try:
            # Kernel DRM names; the known source is DP-2.
            names = {10: "DP", 11: "HDMI-A", 14: "eDP"}
            for index in range(resources.contents.count_connectors):
                item = self.get("ConnectorCurrent", resources.contents.connectors[index])
                name = f"{names.get(item.contents.connector_type, 'unknown')}-{item.contents.connector_type_id}"
                if name == self.connector:
                    connector = item
                    break
                self.drm.drmModeFreeConnector(item)
            if connector is None:
                raise ValueError("Selected connector is absent from selected DRM card")
            c = connector.contents
            report = {"connector": self.connector, "connector_id": c.connector_id,
                      "connection": c.connection, "encoder_id": c.encoder_id,
                      "properties": {}}
            for index in range(c.count_props):
                prop = self.get("Property", c.props[index])
                try:
                    name = prop.contents.name.decode()
                    if name in {"max bpc", "Broadcast RGB", "Colorspace", "DPMS",
                                "link-status", "HDR_OUTPUT_METADATA", "underscan"}:
                        report["properties"][name] = int(c.prop_values[index])
                finally:
                    self.drm.drmModeFreeProperty(prop)
            if not c.encoder_id:
                report["active"] = False
                return report
            encoder = self.get("Encoder", c.encoder_id)
            try:
                crtc_id = encoder.contents.crtc_id
            finally:
                self.drm.drmModeFreeEncoder(encoder)
            if not crtc_id:
                report["active"] = False
                return report
            crtc = self.get("Crtc", crtc_id)
            try:
                state = crtc.contents
                report.update(active=bool(state.mode_valid), crtc_id=crtc_id,
                              fb_id=state.buffer_id, width=state.width, height=state.height,
                              mode={"name": state.mode.name.decode(),
                                    "pixel_clock_khz": state.mode.clock,
                                    "hdisplay": state.mode.hdisplay,
                                    "vdisplay": state.mode.vdisplay,
                                    "htotal": state.mode.htotal, "vtotal": state.mode.vtotal,
                                    "flags": state.mode.flags})
                fb_id = state.buffer_id
            finally:
                self.drm.drmModeFreeCrtc(crtc)
            if fb_id:
                fb = self.get("FB2", fb_id)  # Metadata only: no map/export/read of pixels.
                try:
                    report["framebuffer"] = {"width": fb.contents.width,
                                             "height": fb.contents.height,
                                             "format": fourcc(fb.contents.pixel_format),
                                             "modifier": int(fb.contents.modifier)}
                finally:
                    self.drm.drmModeFreeFB2(fb)
                again = self.get("Crtc", crtc_id)
                try:
                    report["crtc_fb_unchanged_during_sample"] = again.contents.buffer_id == fb_id
                finally:
                    self.drm.drmModeFreeCrtc(again)
            return report
        finally:
            if connector is not None:
                self.drm.drmModeFreeConnector(connector)
            self.drm.drmModeFreeResources(resources)


def record(reader, output, duration, interval):
    deadline = time.monotonic() + duration
    previous, errors, samples = None, 0, 0
    while time.monotonic() < deadline:
        start = time.monotonic_ns()
        try:
            state = reader.sample()
            error = None
        except (OSError, ValueError) as failure:
            state, error = None, str(failure)
            errors += 1
        end = time.monotonic_ns()
        output.write(json.dumps({"event": "scanout_sample", "sample_started_monotonic_ns": start,
                                 "sample_finished_monotonic_ns": end,
                                 "unix_time_ns": time.time_ns(), "state": state, "error": error,
                                 "state_changed": state != previous}) + "\n")
        output.flush()
        previous = state
        samples += 1
        time.sleep(min(max(0, interval - (end - start) / 1e9),
                       max(0, deadline - time.monotonic())))
    output.write(json.dumps({"event": "scanout_summary", "samples": samples,
                             "errors": errors, "monotonic_ns": time.monotonic_ns()}) + "\n")
    output.flush()
    return 1 if errors else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--card", type=Path, required=True)
    parser.add_argument("--connector", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--duration", type=float, default=700)
    parser.add_argument("--interval", type=float, default=0.25)
    args = parser.parse_args(argv)
    if not 0 < args.duration <= 3600 or not 0 < args.interval <= 60:
        parser.error("duration must be (0,3600] seconds; interval must be (0,60] seconds")
    reader = None
    try:
        reader = MetadataReader(args.card, args.connector)
        with args.output.open("x") as output:
            output.write(json.dumps({"event": "scanout_start", "card": str(args.card),
                                     "connector": args.connector, "interval_seconds": args.interval,
                                     "duration_seconds": args.duration,
                                     "monotonic_ns": time.monotonic_ns(),
                                     "unix_time_ns": time.time_ns()}) + "\n")
            return record(reader, output, args.duration, args.interval)
    except (OSError, ValueError) as error:
        parser.exit(2, str(error) + "\n")
    finally:
        if reader is not None:
            reader.close()


if __name__ == "__main__":
    raise SystemExit(main())
