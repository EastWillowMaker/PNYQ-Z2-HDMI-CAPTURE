"""Explicit synthetic and PYNQ M0 sources with owned frame lifetimes."""

import asyncio
import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET
import time
from dataclasses import dataclass

import numpy as np

from .modes import CAPTURE_MODES, get_mode, mode_metadata


class SourceError(RuntimeError):
    """Source stopped, lost lock, or changed to an unsupported mode."""


@dataclass
class Sample:
    pixels: np.ndarray
    timestamp_ns: int
    sequence: int | None = None
    bgr: bool = False
    release: object = None
    extra_metadata: dict | None = None

    def copy_rgb(self):
        if self.pixels.dtype != np.uint8 or self.pixels.ndim != 3 or self.pixels.shape[2] != 3:
            raise SourceError("Source sample must be uint8 with three channels")
        # Keep channel conversion in plain ndarray views, independent of the
        # native-owning PynqBuffer subclass's finalization behavior.
        base = np.asarray(self.pixels)
        if self.bgr:
            rgb = np.empty(base.shape, dtype=np.uint8, order="C")
            rgb[..., 0] = base[..., 2]
            rgb[..., 1] = base[..., 1]
            rgb[..., 2] = base[..., 0]
        else:
            rgb = np.array(base, order="C", copy=True)
        rgb.flags.writeable = False
        return rgb

    def close(self):
        if self.release is not None:
            release, self.release = self.release, None
            release()


def synthetic_pattern(width, height, sequence):
    """RGB column ramp, row ramp, and changing full-frame blue marker."""
    rgb = np.empty((height, width, 3), dtype=np.uint8)
    rgb[..., 0] = np.arange(width, dtype=np.uint32)[None, :] % 256
    rgb[..., 1] = np.arange(height, dtype=np.uint32)[:, None] % 256
    rgb[..., 2] = sequence % 256
    # Distinct isolated channel markers expose channel swaps and subsampling.
    if width >= 3:
        rgb[0, :3] = ((255, 0, 0), (0, 255, 0), (0, 0, 255))
    return rgb


class SyntheticSource:
    origin = "synthetic"
    color_format = "RGB"
    quantization_range = "full"
    baseline_only = False

    def __init__(self, width=640, height=480, input_fps=60):
        if not (1 <= width <= 1920 and 1 <= height <= 1080):
            raise ValueError("Synthetic dimensions exceed protocol bounds")
        if not 0 < input_fps <= 240:
            raise ValueError("input_fps must be in (0, 240]")
        self.width, self.height, self.input_fps = width, height, input_fps
        self.sequence = 0
        self._next = None

    def start(self):
        self._next = time.monotonic()

    async def read(self):
        await asyncio.sleep(max(0, self._next - time.monotonic()))
        sequence = self.sequence
        self.sequence += 1
        self._next = max(self._next + 1 / self.input_fps, time.monotonic())
        pixels = synthetic_pattern(self.width, self.height, sequence)
        return Sample(pixels, time.monotonic_ns(), sequence)

    def close(self):
        pass


class PynqFramePool:
    """Reuse original DMA objects without PYNQ3.0.1 pointer-cache finalizers.

    The pinned freebuffer() can free an allocation on its second invocation,
    after returning its pointer to the DMA cache on its first invocation.
    Pointer reuse also attaches repeated native finalizers. Keep original
    objects alive, transfer ownership through this pool, and free once after
    the DMA stops. This modifies only the active channel's cache instance.
    """

    def __init__(self, channel):
        self.cache = channel._cache
        if self.cache._cache:
            raise SourceError("DMA pointer cache must be empty when installing the object pool")
        self.original_getframe = self.cache.getframe
        self.owned = {id(frame): frame for frame in channel._frames if frame is not None}
        self.capacity = len(self.owned) + 1
        self.available = []
        self.available_ids = set()
        self.cache.getframe = self.getframe

    def getframe(self):
        if self.available:
            frame = self.available.pop()
            self.available_ids.remove(id(frame))
            return frame
        if len(self.owned) >= self.capacity:
            raise SourceError("DMA object pool exhausted; previous sample is still owned")
        frame = self.original_getframe()
        self.owned[id(frame)] = frame
        return frame

    def release(self, frame):
        if id(frame) not in self.owned or id(frame) in self.available_ids:
            raise SourceError("DMA buffer ownership released incorrectly")
        self.available.append(frame)
        self.available_ids.add(id(frame))

    def close(self):
        # Caller must stop DMA first. Never rewrap pointers with pynq.allocate.
        self.cache.getframe = self.original_getframe
        self.available.clear()
        self.available_ids.clear()
        for frame in self.owned.values():
            frame.pointer = 0
            frame.freebuffer()
        self.owned.clear()


class PynqSource:
    """PYNQ 3.0.1 base overlay only; no LiteX qualification is implied.

    Use BGR identity conversion and reorder only while copying the owned DMA
    frame. PYNQ readframe_async invalidates the captured buffer before return.
    """

    origin = "hdmi"
    color_format = "unknown"
    quantization_range = "unknown"
    baseline_only = True

    def __init__(self, bitfile="base.bit", *, hdmi=None, pixel_format=None,
                 progress=None):
        self.bitfile = bitfile
        self.hdmi = hdmi
        self.pixel_format = pixel_format
        self.progress = progress
        self.width, self.height = 640, 480
        self._started = False
        self._pool = None
        self.dma_shutdown_safe = True

    def _check_mode(self, mode):
        expected = (self.width, self.height, 24)
        if (mode.width, mode.height, mode.bits_per_pixel) != expected:
            raise SourceError(
                f"Capture accepts only {self.width}x{self.height} with 24-bit DMA pixels")

    def _stage(self, name, details=None):
        if self.progress is not None:
            self.progress(name if details is None else dict(stage=name, **details))

    def start(self):
        if self.hdmi is None:
            self._stage("pynq_import")
            import pynq
            if pynq.__version__ != "3.0.1":
                raise SourceError("PYNQ M0 adapter requires version 3.0.1")
            from pynq.overlays.base import BaseOverlay
            from pynq.lib.video import PIXEL_BGR
            self._stage("overlay_load")
            self.overlay = BaseOverlay(self.bitfile)
            self.hdmi = self.overlay.video.hdmi_in
            self.pixel_format = PIXEL_BGR
        try:
            self._stage("hdmi_configure_wait_input_lock")
            self.hdmi.configure(self.pixel_format)
            self._stage("hdmi_mode_check")
            self._check_mode(self.hdmi.mode)
            self._check_mode(self.hdmi.frontend.mode)
            self._stage("dma_start")
            # A failure inside native start can leave partially started DMA.
            self.dma_shutdown_safe = False
            self.hdmi.start()
            self._started = True
            if hasattr(self.hdmi, "_vdma"):
                self._pool = PynqFramePool(self.hdmi._vdma.readchannel)
            self._stage("source_ready")
        except BaseException:
            if self._started or not self.dma_shutdown_safe:
                self.close()
            else:
                self.hdmi.close()
            raise

    async def read(self):
        self._check_mode(self.hdmi.frontend.mode)
        pixels = await self.hdmi.readframe_async()
        timestamp = time.monotonic_ns()
        try:
            self._check_mode(self.hdmi.frontend.mode)
            if pixels.dtype != np.uint8 or pixels.shape != (self.height, self.width, 3):
                raise SourceError("Unexpected DMA frame shape or dtype")
        except BaseException:
            self._release(pixels)
            raise
        return Sample(pixels, timestamp, bgr=True, release=lambda: self._release(pixels))

    def _release(self, pixels):
        if self._pool is not None:
            self._pool.release(pixels)
        else:
            pixels.freebuffer()

    def close(self):
        if self.hdmi is not None and (self._started or not self.dma_shutdown_safe):
            channel = (self.hdmi._vdma.readchannel
                       if hasattr(self.hdmi, "_vdma") else None)
            self._stage("dma_stop_begin")
            if self.progress is not None and channel is not None:
                self._stage("dma_stop_status_before", dict(
                    control=channel._mmio.read(0x30), status=channel._mmio.read(0x34)))
            self.hdmi.close()
            # Failure/interruption above retains buffers. Never free live DMA BOs.
            if channel is not None and channel.running:
                raise SourceError("DMA did not halt; retaining capture buffers")
            if self.progress is not None and channel is not None:
                self._stage("dma_stop_status_after", dict(
                    control=channel._mmio.read(0x30), status=channel._mmio.read(0x34)))
            self._stage("dma_stop_complete")
            if self._pool is not None:
                self._stage("pool_free_begin", dict(buffers=len(self._pool.owned)))
                self._pool.close()
                self._pool = None
                self._stage("pool_free_complete")
            self._started = False
            self.dma_shutdown_safe = True


def verify_litex_artifacts(bitfile, manifest, *, expected_mode="vga"):
    """Reject stale or unrelated artifact pairs before loading any hardware."""
    bitfile, manifest = Path(bitfile).resolve(), Path(manifest).resolve()
    record = json.loads(manifest.read_text())
    if not isinstance(record, dict):
        raise SourceError("LiteX manifest must be a JSON object")
    if type(record.get("schema_version")) is not int or record["schema_version"] != 1:
        raise SourceError("LiteX manifest must declare schema1")
    try:
        requested_mode = get_mode(expected_mode)
        manifest_mode = get_mode(record.get("capture_mode", "vga"))
    except (TypeError, ValueError) as error:
        raise SourceError(f"Unsupported LiteX capture mode: {error}") from error
    if manifest_mode.name != requested_mode.name:
        raise SourceError(
            f"LiteX manifest mode {manifest_mode.name} does not match requested mode "
            f"{requested_mode.name}")
    expected_profile = mode_metadata(manifest_mode)
    if "capture_mode" not in record:
        if manifest_mode.name != "vga":
            raise SourceError("Legacy LiteX manifests are accepted only for VGA")
        expected_profile.pop("capture_mode")
        expected_profile.pop("timing")
    for key, expected in expected_profile.items():
        actual = record.get(key)
        if not _profile_value_matches(actual, expected):
            raise SourceError(
                f"LiteX manifest {key} does not match capture mode {manifest_mode.name}")
    # Normalize legacy VGA manifests in memory; the receipt still hashes the
    # original manifest bytes and remains compatible with existing receipts.
    record.setdefault("capture_mode", manifest_mode.name)
    if record.get("pynq_commit") != "93ddd21ab623883590a8c8b07f0b157b2855da4b":
        raise SourceError("LiteX manifest does not use the pinned PYNQ receiver")
    if type(record.get("capture_enable_reset")) is not int or record["capture_enable_reset"] != 0:
        raise SourceError("LiteX manifest must declare capture enable reset0")
    edid_hash = record.get("edid_sha256")
    if (not isinstance(edid_hash, str) or len(edid_hash) != 64 or
            any(c not in "0123456789abcdef" for c in edid_hash)):
        raise SourceError("LiteX manifest must contain a valid EDID SHA256")
    if "source_health_sha256" in record:
        health_hash = record["source_health_sha256"]
        if (not isinstance(health_hash, str) or len(health_hash) != 64 or
                any(c not in "0123456789abcdef" for c in health_hash) or
                record.get("source_health_counters_lifetime") != "fpga_load" or
                record.get("source_health_overruns_unit") != "overflow_episodes" or
                record.get("receiver_source_reset_policy") != "shared_per_clock"):
            raise SourceError("Unsupported source-health monitor provenance")
    for path, key in ((bitfile, "bitstream_sha256"),
                      (bitfile.with_suffix(".hwh"), "hwh_sha256")):
        if hashlib.sha256(path.read_bytes()).hexdigest() != record.get(key):
            raise SourceError(f"LiteX artifact hash mismatch: {key}")
    # The receiver has no AXI register map and need not appear in ip_dict.
    # Inspect its HWH module parameters directly, before overlay programming.
    root = ET.parse(bitfile.with_suffix(".hwh")).getroot()
    receivers = [module for module in root.findall(".//MODULE")
                 if module.attrib.get("FULLNAME") == "/video/hdmi_in/frontend/dvi2rgb_0"]
    if len(receivers) != 1:
        raise SourceError("HWH must contain the expected single DVI receiver")
    parameters = {parameter.attrib.get("NAME"): parameter.attrib.get("VALUE")
                  for parameter in receivers[0].findall("./PARAMETERS/PARAMETER")}
    if parameters.get("kClkRange") != str(manifest_mode.receiver_k_clk_range):
        raise SourceError("HWH DVI receiver clock range does not match the capture mode")
    controls = [module for module in root.findall(".//MODULE")
                if module.attrib.get("FULLNAME") == "/video/capture_control"]
    if len(controls) != 1:
        raise SourceError("HWH must contain the expected capture control")
    control_parameters = {parameter.attrib.get("NAME"): parameter.attrib.get("VALUE")
                          for parameter in controls[0].findall("./PARAMETERS/PARAMETER")}
    try:
        reset = int(control_parameters.get("C_DOUT_DEFAULT", ""), 0)
    except ValueError as error:
        raise SourceError("HWH capture control reset is unspecified") from error
    if reset != 0:
        raise SourceError("HWH capture control must reset disabled")
    if record.get("capture_interface") == "single_credit_parked_v1":
        if record.get("vdma_fsync_mode") != "free_run":
            raise SourceError("Single-credit DMA requires free-run frame synchronization")
        dmas = [module for module in root.findall(".//MODULE")
                if module.get("FULLNAME") == "/video/axi_vdma"]
        if len(dmas) != 1:
            raise SourceError("HWH must contain one credit VDMA")
        for name, expected in (("C_USE_S2MM_FSYNC", "0"),
                               ("C_ENABLE_DEBUG_INFO_15", "1")):
            actual = [row.get("VALUE") for row in dmas[0].findall("./PARAMETERS/PARAMETER")
                      if row.get("NAME") == name]
            if actual != [expected]:
                raise SourceError(f"Credit HWH requires {name}={expected}")
    return record


def _profile_value_matches(actual, expected):
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return (actual.keys() == expected.keys() and
                all(_profile_value_matches(actual[key], value)
                    for key, value in expected.items()))
    if isinstance(expected, list):
        return (len(actual) == len(expected) and
                all(_profile_value_matches(actual_value, expected_value)
                    for actual_value, expected_value in zip(actual, expected)))
    return actual == expected


class LiteXControl:
    """HWH-discovered GPIO registers; counters are sequential snapshots."""

    def __init__(self, overlay, mmio_factory):
        self.registers = {}
        for name in ("capture_control", "capture_counts", "capture_errors"):
            description = overlay.ip_dict.get("video/" + name)
            if description is None or description.get("type") != "xilinx.com:ip:axi_gpio:2.0":
                raise SourceError(f"Missing expected LiteX GPIO: {name}")
            self.registers[name] = mmio_factory(description["phys_addr"],
                                                 description["addr_range"])
        description = overlay.ip_dict.get("video/source_health")
        if description is not None:
            if description.get("type") != "xilinx.com:ip:axi_gpio:2.0":
                raise SourceError("Unexpected LiteX source-health GPIO type")
            self.registers["source_health"] = mmio_factory(description["phys_addr"],
                                                           description["addr_range"])
        description = overlay.ip_dict.get("video/source_faults")
        if description is not None:
            if description.get("type") != "xilinx.com:ip:axi_gpio:2.0":
                raise SourceError("Unexpected LiteX source-faults GPIO type")
            self.registers["source_faults"] = mmio_factory(description["phys_addr"],
                                                           description["addr_range"])

    def enable(self, value):
        if type(value) is not bool:
            raise ValueError("Capture enable must be boolean")
        self.registers["capture_control"].write(0, int(value))

    def snapshot(self, sample_point="sequential_gpio_reads_after_dma_read_complete"):
        started = time.monotonic_ns()
        control, counts, errors = (self.registers[name] for name in
                                   ("capture_control", "capture_counts", "capture_errors"))
        snapshot = dict(enabled=bool(control.read(0) & 1),
                    observed_frames=counts.read(0), selected_frames=counts.read(8),
                    completed_frames=control.read(8), dropped_frames=errors.read(0),
                    invalid_frames=errors.read(8),
                    snapshot_begin_ns=started, snapshot_end_ns=time.monotonic_ns(),
                    timestamp_clock="board_monotonic", snapshot_atomic=False,
                    sample_point=sample_point,
                    counter_bits=32)
        health = self.registers.get("source_health")
        if health is not None:
            snapshot.update(frontend_overflow_episodes=health.read(0),
                            native_vsync_edges=health.read(8),
                            overflow_units="assertion_episodes_not_lost_frames")
        else:
            snapshot.update(frontend_overflow_episodes=None, native_vsync_edges=None)
        faults = self.registers.get("source_faults")
        snapshot["frontend_underflow_episodes"] = faults.read(0) if faults is not None else None
        snapshot["snapshot_end_ns"] = time.monotonic_ns()
        return snapshot


class LiteXSource(PynqSource):
    """Verified custom artifact capture; qualification still requires hardware evidence."""

    baseline_only = False

    def __init__(self, bitfile, manifest, *, capture_mode="vga", progress=None):
        super().__init__(bitfile, progress=progress)
        self.mode_profile = get_mode(capture_mode)
        self.capture_mode_name = self.mode_profile.name
        self.width, self.height = self.mode_profile.width, self.mode_profile.height
        self.manifest_path = manifest
        self.control = None
        self.integrity_baseline = None
        self.integrity_previous = None
        self.integrity_failure = None

    def load_overlay(self, download=True, *, video_drivers=True):
        self._stage("litex_artifact_verification")
        self.manifest = verify_litex_artifacts(
            self.bitfile, self.manifest_path, expected_mode=self.capture_mode_name)
        if self.manifest.get("capture_interface") != getattr(self, "capture_interface", None):
            raise SourceError("Capture artifact ABI does not match the explicit source adapter")
        self._stage("pynq_import")
        import pynq
        if pynq.__version__ != "3.0.1":
            raise SourceError("LiteX adapter requires PYNQ3.0.1")
        self._stage("overlay_load" if download else "overlay_attach")
        self.overlay = pynq.Overlay(str(Path(self.bitfile).resolve()), download=download)
        if not self.overlay.is_loaded():
            raise SourceError("Custom capture overlay is not currently loaded")
        vdma_description = self.overlay.ip_dict.get("video/axi_vdma", {})
        parameters = vdma_description.get("parameters", {})
        if (vdma_description.get("type") != "xilinx.com:ip:axi_vdma:6.3" or
                parameters.get("C_INCLUDE_S2MM") != "1" or
                parameters.get("C_INCLUDE_MM2S") != "0"):
            raise SourceError("Custom overlay requires S2MM-only VDMA6.3")
        self.control = LiteXControl(self.overlay, pynq.MMIO)
        if "source_health_sha256" in self.manifest and (
                "source_health" not in self.control.registers or
                "source_faults" not in self.control.registers):
            raise SourceError("Manifest requires the complete source-health GPIO resources")
        if not download or not video_drivers:
            # GPIO-only control must not instantiate video drivers. PixelPacker
            # construction writes its mode register even when no DMA is started.
            return
        self._initialize_video()

    def _initialize_video(self):
        from pynq.lib.video import PIXEL_BGR
        from pynq.lib.video.hierarchies import VideoIn
        self.hdmi = VideoIn(self.overlay.video.hdmi_in.description,
                            self.overlay.video.axi_vdma)
        self.pixel_format = PIXEL_BGR

    def start(self):
        self.load_overlay()
        # Consume/drop whole input frames while VDMA is halted during lock wait.
        self.control.enable(False)
        super().start()
        try:
            self.integrity_baseline = self.control.snapshot(
                sample_point="sequential_gpio_reads_after_dma_start_before_capture_enable")
            self.integrity_previous = self.integrity_baseline
            self._stage("integrity_baseline", dict(counters=self.integrity_baseline))
            selected = self.integrity_baseline.get("selected_frames")
            if (self.integrity_baseline.get("enabled") is not False or
                    type(selected) is not int or selected != 0):
                raise SourceError("Capture baseline requires disabled gate and zero selected frames")
            self._stage("capture_enable_after_disabled_baseline")
            self.control.enable(True)
        except BaseException:
            self.close()
            raise

    async def read(self):
        sample = await super().read()
        try:
            current = self.control.snapshot()
            changed = []
            for name in ("invalid_frames", "frontend_overflow_episodes", "frontend_underflow_episodes"):
                before, after = self.integrity_previous.get(name), current.get(name)
                if before is not None and after != before:
                    changed.append(f"{name}: {before}->{after}")
            before = self.integrity_previous.get("native_vsync_edges")
            after = current.get("native_vsync_edges")
            if before is not None and (after is None or after < before):
                changed.append(f"native_vsync_edges reset/rollback: {before}->{after}")
            self.integrity_previous = current
            if changed:
                self.integrity_failure = dict(changed_counters=changed,
                                              snapshot=current,
                                              frame_association="unknown_session_stopped")
                raise SourceError("Capture integrity counter changed; session stopped: " +
                                  "; ".join(changed))
            sample.extra_metadata = dict(
                capture_implementation="litex_video_gate",
                capture_artifact_sha256=self.manifest["bitstream_sha256"],
                frame_source_id=None, litex_counters=current,
                litex_startup_counters=self.integrity_baseline,
                capture_enable_reset=self.manifest["capture_enable_reset"],
                integrity_policy="disabled_zero_selected_baseline_then_stop_on_integrity_change",
                source_health_provenance={name: self.manifest.get(name) for name in
                    ("source_health_sha256", "source_health_counters_lifetime",
                     "source_health_overruns_unit", "receiver_source_reset_policy")},
                hardware_qualification="unverified")
        except BaseException:
            sample.close()
            raise
        return sample


CREDIT_ABI = "single_credit_parked_v1"
DMA_ERRORS = 0xC9F0


class OneFrameDMA:
    """One owned allocation, parked store0, automatic halt after one frame."""

    CONTROL = 0x15011

    def __init__(self, mmio, buffer, frame_stores=4, *, width=640, height=480):
        address = getattr(buffer, "physical_address", None)
        stride = width * 3 if type(width) is int and width > 0 else 0
        frame_bytes = stride * height if type(height) is int and height > 0 else 0
        supported_geometry = {(mode.width, mode.height) for mode in CAPTURE_MODES.values()}
        buffer_bytes = getattr(buffer, "nbytes", None)
        if (type(frame_stores) is not int or frame_stores != 4 or
                type(width) is not int or type(height) is not int or
                (width, height) not in supported_geometry or
                stride % 64 or frame_bytes <= 0 or
                not isinstance(address, (int, np.integer)) or isinstance(address, bool) or
                not isinstance(buffer_bytes, (int, np.integer)) or isinstance(buffer_bytes, bool) or
                buffer_bytes < frame_bytes or
                not 0 <= address <= 0xFFFFFFFF - (frame_bytes - 1) or
                address % 64):
            raise SourceError(
                "DMA requires a supported geometry, a full-size buffer, four stores, "
                "a 64-byte-aligned stride, and a full frame within the aligned 32-bit "
                "buffer address space")
        address = int(address)
        self.mmio, self.buffer, self.frame_stores = mmio, buffer, frame_stores
        self.width, self.height, self.stride = width, height, stride
        self.seen_running = False

    def status(self):
        value = self.mmio.read(0x34)
        if value & DMA_ERRORS:
            raise SourceError(f"Raw VDMA error before clear: 0x{value:08x}")
        return value

    def arm(self):
        if not self.status() & 1:
            raise SourceError("Cannot arm a DMA that has not halted")
        self.seen_running = False
        self.mmio.write(0x34, 0x1000)  # Only a previously inspected frame IRQ.
        # Change threshold2->1 to reload it explicitly, while initially halted.
        self.mmio.write(0x30, 0x25010)
        self.mmio.write(0x28, self.mmio.read(0x28) & ~(0x1F << 8))
        self.mmio.write(0x30, self.CONTROL)
        for slot in range(self.frame_stores):
            self.mmio.write(0xAC + 4 * slot, self.buffer.physical_address)
        self.mmio.write(0xA8, self.stride)
        self.mmio.write(0xA4, self.stride)
        self.mmio.write(0xA0, self.height)
        if (self.mmio.read(0x30) & 0xFFFFFF7F) != self.CONTROL:
            raise SourceError("VDMA single-frame control readback mismatch")
        if self.mmio.read(0x28) & (0x1F << 8):
            raise SourceError("VDMA parked reference is not store0")
        for offset, expected in ((0xAC, self.buffer.physical_address),
                                 (0xA8, self.stride), (0xA4, self.stride),
                                 (0xA0, self.height)):
            if self.mmio.read(offset) != expected:
                raise SourceError("VDMA address/geometry readback mismatch")
        if any(self.mmio.read(0xAC + 4 * slot) != self.buffer.physical_address
               for slot in range(self.frame_stores)):
            raise SourceError("VDMA store addresses do not all match the owned buffer")

    def running_observed(self):
        status = self.status()
        if not status & 1:
            self.seen_running = True
        return self.seen_running

    def completed(self):
        status = self.status()
        if not self.seen_running or status & 0x1001 != 0x1001:
            return None
        control = self.mmio.read(0x30)
        if control & 1 or not control & 0x10:
            raise SourceError("Halted DMA is not a confirmed one-frame auto-halt")
        if (self.mmio.read(0x28) >> 24) & 0x1F:
            raise SourceError("DMA completed in an unexpected frame store")
        return status

    def stop(self, timeout):
        self.stop_mmio(self.mmio, timeout)

    @staticmethod
    def stop_mmio(mmio, timeout):
        # Abort/reject any incomplete credit. No buffer is released here.
        mmio.write(0x30, mmio.read(0x30) & ~1)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if mmio.read(0x34) & 1:
                return
            time.sleep(0.001)
        raise SourceError("DMA halt timed out; process and native buffer must remain alive")


class CreditControl(LiteXControl):
    """Single-credit GPIO ABI; identity is immutable through DONE and ACK."""

    def __init__(self, overlay, mmio_factory):
        super().__init__(overlay, mmio_factory)
        for name in ("capture_credit", "capture_completion", "capture_sequence"):
            description = overlay.ip_dict.get("video/" + name)
            if description is None or description.get("type") != "xilinx.com:ip:axi_gpio:2.0":
                raise SourceError(f"Missing credit ABI GPIO: {name}")
            self.registers[name] = mmio_factory(description["phys_addr"], description["addr_range"])
        self.command = self.registers["capture_control"].read(0)
        if self.command != 0:
            raise SourceError("Credit command register must start at reset0")

    def enable(self, enabled):
        if type(enabled) is not bool:
            raise ValueError("Capture enable must be boolean")
        self.command = (self.command & ~1) | int(enabled)
        self.registers["capture_control"].write(0, self.command)

    def snapshot(self, sample_point="sequential_gpio_reads_during_credit_health_check"):
        return super().snapshot(sample_point)

    def request(self):
        self.command ^= 2
        self.registers["capture_control"].write(0, self.command)

    def acknowledge(self):
        self.command ^= 4
        self.registers["capture_control"].write(0, self.command)

    def identity(self):
        credit = self.registers["capture_credit"]
        completion = self.registers["capture_completion"]
        sequence = self.registers["capture_sequence"]
        before = credit.read(0)
        result = dict(credit_busy=bool(before & 1), credit_done=bool(before & 2),
                      credit_failed=bool(before & 4), request_seen=(before >> 3) & 1,
                      ack_seen=(before >> 4) & 1, source_sequence_fault=bool(before & 32),
                      native_armed=bool(before & 64), selected_sof_id=credit.read(8),
                      selected_native_vsync_id=sequence.read(0),
                      selected_completed=completion.read(0), command_errors=completion.read(8),
                      source_sequence_faults=sequence.read(8))
        if before != credit.read(0):
            return None
        result["identity_snapshot_coherent"] = bool(result["credit_busy"] and result["credit_done"])
        return result


class LiteXCreditSource(LiteXSource):
    """Paced one-credit capture with exact latched source/DMA association."""

    paces_capture = True
    capture_interface = CREDIT_ABI

    def __init__(self, bitfile, manifest, *, capture_mode="vga", capture_fps=2,
                 progress=None, timeout=3, prepared_receipt=None):
        super().__init__(bitfile, manifest, capture_mode=capture_mode, progress=progress)
        if not math.isfinite(capture_fps) or not 0 < capture_fps <= 60:
            raise ValueError("Credit capture FPS must be in(0,60]")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Credit timeout must be finite and positive")
        self.capture_fps, self.timeout = capture_fps, timeout
        self.native = None
        self.leased = False
        self.acquired = 0
        self.first_native = self.first_sof = self.last_native = self.last_sof = None
        self.intentional_total = 0
        self.next_request = 0
        self.ack_pending = False
        self.final_accounting = None
        self.prepared_receipt = prepared_receipt

    def load_overlay(self, download=True):
        if self.prepared_receipt is None:
            return super().load_overlay(download=download)
        from .prepared import attach_prepared
        attach_prepared(self, self.prepared_receipt, video_drivers=download)

    def start(self):
        record = verify_litex_artifacts(
            self.bitfile, self.manifest_path, expected_mode=self.capture_mode_name)
        if (record.get("capture_interface") != CREDIT_ABI or
                record.get("vdma_completion_mode") != "parked_frame_count_halt_v1" or
                record.get("vdma_frame_counter_enabled") is not True or
                record.get("vdma_fsync_mode") != "free_run" or
                record.get("gate_completion_policy") != "next_sof_after_selected_output_drain_v1"):
            raise SourceError("Artifact does not declare the single-credit DMA ABI")
        if "source_health_sha256" not in record:
            raise SourceError("Credit ABI requires source-health provenance")
        if (type(record.get("capture_control_width")) is not int or record["capture_control_width"] != 32 or
                type(record.get("capture_control_reset")) is not int or record["capture_control_reset"] != 0 or
                record.get("source_identity_bits") != 32 or
                record.get("source_identity_policy") != "native_delta_one_per_accepted_sof_with_watchdog"):
            raise SourceError("Unsupported credit control or native identity provenance")
        for name in ("receiver_reset_sync_sha256", "capture_lock_sync_sha256", "gateware_sha256"):
            value = record.get(name)
            if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise SourceError(f"Missing credit artifact provenance: {name}")
        modules = {m.attrib.get("FULLNAME"): {p.attrib.get("NAME"): p.attrib.get("VALUE")
                   for p in m.findall("./PARAMETERS/PARAMETER")}
                   for m in ET.parse(Path(self.bitfile).with_suffix(".hwh")).getroot().findall(".//MODULE")}
        if (modules.get("/video/capture_control", {}).get("C_GPIO_WIDTH") != "32" or
                modules.get("/video/axi_vdma", {}).get("C_ENABLE_DEBUG_INFO_15") != "1"):
            raise SourceError("Credit HWH requires 32-bit control and S2MM frame counter")
        self.load_overlay()
        import pynq
        self.control = CreditControl(self.overlay, pynq.MMIO)
        self.control.enable(False)
        try:
            self._started = True  # Configure may start native frontend resources.
            channel = self.hdmi._vdma.readchannel
            if channel.running:
                self.dma_shutdown_safe = False
                raise SourceError("DMA was unexpectedly active before frontend configuration")
            self.hdmi.configure(self.pixel_format)
            self._check_mode(self.hdmi.mode)
            self._check_mode(self.hdmi.frontend.mode)
            channel = self.hdmi._vdma.readchannel
            parameters = self.overlay.ip_dict["video/axi_vdma"]["parameters"]
            if parameters.get("C_ENABLE_DEBUG_INFO_15") != "1":
                raise SourceError("S2MM frame-counter feature is not enabled")
            if channel.running:
                raise SourceError("DMA must be halted during disabled startup baseline")
            deadline = time.monotonic() + self.timeout
            identity = None
            while time.monotonic() < deadline:
                identity = self.control.identity()
                if identity is not None:
                    self._check_identity(identity)
                    if identity["native_armed"]:
                        break
                time.sleep(0.001)
            baseline = self.control.snapshot("before_first_credit_while_gate_disabled_dma_halted")
            if (baseline["enabled"] or baseline["selected_frames"] != 0 or identity is None or
                    identity["credit_busy"] or identity["credit_done"] or identity["selected_completed"] != 0):
                raise SourceError("Credit startup baseline is not disabled/empty")
            self._check_identity(identity)
            if not identity["native_armed"]:
                raise SourceError("Native/SOF pairing is not armed")
            if baseline["frontend_overflow_episodes"] != 0 or baseline["frontend_underflow_episodes"] != 0:
                raise SourceError("Startup frontend loss is not clean")
            self.integrity_baseline = self.integrity_previous = baseline
            buffer = pynq.allocate(shape=(self.height, self.width, 3), dtype=np.uint8,
                                   target=channel.memory, cacheable=True)
            try:
                native = OneFrameDMA(channel._mmio, buffer, self.hdmi._vdma.framecount,
                                     width=self.width, height=self.height)
            except BaseException as error:
                try:
                    buffer.freebuffer()
                except BaseException as cleanup_error:
                    self.integrity_failure = dict(
                        setup_error=str(error), buffer_release_error=str(cleanup_error))
                    raise SourceError(
                        f"Cannot release unarmed frame buffer after DMA setup failed: "
                        f"{cleanup_error}") from error
                raise
            self.native = native
            self.native.status()
            self.control.enable(True)
            self._stage("credit_source_ready", dict(counters=baseline))
        except BaseException:
            self.close()
            raise

    @staticmethod
    def _check_identity(identity):
        if (identity["credit_failed"] or identity["source_sequence_fault"] or
                identity["command_errors"] or identity["source_sequence_faults"]):
            raise SourceError("Single-credit command/source-sequence fault")

    def _healthy(self):
        # Preserve the actual diagnostic snapshot even when identity rejects
        # the source. A failed read must not leave an older clean snapshot behind.
        self.integrity_previous = None
        try:
            current = self.control.snapshot()
            self.integrity_previous = current
            # VTC registers require the HDMI pixel clock even with an independent
            # AXI clock (PG016). Loss of that clock can cause SIGBUS, not a Python
            # exception. Startup checks mode before allocation; runtime uses the
            # fixed-clock gate geometry, FIFO and native-sequence fault signals.
            identity = self.control.identity()
            if identity is None:
                return None
            self._check_identity(identity)
            if not identity["native_armed"]:
                raise SourceError("Native source pairing lost")
            for name in ("invalid_frames", "frontend_overflow_episodes", "frontend_underflow_episodes"):
                if current[name] != self.integrity_baseline[name]:
                    self.integrity_failure = dict(counter=name, snapshot=current)
                    raise SourceError(f"Credit integrity counter changed: {name}")
            return identity
        except BaseException as error:
            if self.integrity_failure is None:
                self.integrity_failure = dict(error=str(error), snapshot=self.integrity_previous)
            raise

    async def _wait(self, predicate):
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            value = predicate()
            if value:
                return value
            await asyncio.sleep(0.001)
        raise SourceError("Single-credit acquisition/ACK timed out")

    async def read(self):
        if self.leased:
            raise SourceError("Previous DMA lease must be released before requesting another frame")
        await asyncio.sleep(max(0, self.next_request - time.monotonic()))
        period = 1 / self.capture_fps
        now = time.monotonic()
        self.next_request = now + period if not self.next_request else max(self.next_request + period, now)
        def idle():
            identity = self._healthy()
            return identity and not identity["credit_busy"] and not identity["credit_done"] and (
                identity["ack_seen"] == ((self.control.command >> 2) & 1))
        await self._wait(idle)
        self.dma_shutdown_safe = False
        self.native.arm()
        def armed():
            identity = self._healthy()
            return identity is not None and self.native.running_observed()
        await self._wait(armed)
        self.control.request()
        def complete():
            identity = self._healthy()
            status = self.native.completed()
            if identity is None or not status or not identity["credit_done"]:
                return None
            if (not identity["credit_busy"] or identity["request_seen"] != ((self.control.command >> 1) & 1) or
                    identity["selected_completed"] != self.acquired + 1):
                raise SourceError("Completed credit does not match this request")
            return identity, status
        identity, status = await self._wait(complete)
        native_id, sof_id = identity["selected_native_vsync_id"], identity["selected_sof_id"]
        skipped = None
        if self.last_native is not None:
            if native_id <= self.last_native or sof_id <= self.last_sof:
                raise SourceError("Source identity wrapped/reset/repeated; end session")
            if native_id - self.last_native != sof_id - self.last_sof:
                raise SourceError("Native and accepted-SOF identity deltas differ")
            skipped = native_id - self.last_native - 1
            self.intentional_total += skipped
        else:
            self.first_native, self.first_sof = native_id, sof_id
        self.native.buffer.invalidate()
        self.last_native, self.last_sof = native_id, sof_id
        self.acquired += 1
        self.leased = True
        accounting = dict(identity, abi=CREDIT_ABI, dma_completion_mode="parked_frame_count_halt_v1",
                          vdma_fsync_mode="free_run",
                          gate_completion_policy="next_sof_after_selected_output_drain_v1",
                          buffer_slot=0, raw_dma_status=status, dma_auto_halted=True,
                          buffer_stable_until_release=True, acquired_frames_total=self.acquired,
                          first_acquired_source_id=self.first_native,
                          startup_intentional_accepted_sof_skips=self.first_sof, startup_native_skips=None,
                          intentional_skips_since_previous=skipped,
                          source_intentional_sampling_total=self.intentional_total)
        metadata = dict(frame_source_id=sof_id, source_sequence_domain="native_vsync_edge_counter",
                        source_sequence_bits=32, source_sequence_policy="reject_wrap_or_reset",
                        source_accounting=accounting, capture_implementation="litex_single_credit_gate",
                        capture_mode=self.capture_mode_name,
                        capture_artifact_sha256=self.manifest["bitstream_sha256"], capture_enable_reset=0,
                        litex_counters=self.integrity_previous, litex_startup_counters=self.integrity_baseline,
                        source_health_provenance={name: self.manifest.get(name) for name in
                            ("source_health_sha256", "source_health_counters_lifetime",
                             "source_health_overruns_unit", "receiver_source_reset_policy")},
                        integrity_policy="single_credit_parked_auto_halt_fail_closed_v1",
                        timestamp_sample_point="after_one_frame_auto_halt_and_cache_invalidate",
                        hardware_qualification="unverified")
        return Sample(self.native.buffer, time.monotonic_ns(), native_id, bgr=True,
                      release=self._release_credit, extra_metadata=metadata)

    def _release_credit(self):
        identity = self._healthy()
        if identity is None or not identity["credit_done"] or not identity["credit_busy"]:
            raise SourceError("Completed identity changed before lease release")
        if (identity["selected_native_vsync_id"], identity["selected_sof_id"]) != (self.last_native, self.last_sof):
            raise SourceError("Identity changed while DMA buffer was leased")
        self.control.acknowledge()
        self.leased = False

    def close(self):
        failure = None
        if self.native is not None and self.control.command & 1:
            try:
                # Keep the source proof enabled for more than two input periods;
                # expose a missing final AXI SOF before disabling its watchdog.
                initial = self.control.snapshot()["native_vsync_edges"]
                interval = 3 / self.mode_profile.refresh_hz
                deadline = time.monotonic() + interval
                while time.monotonic() < deadline:
                    self._healthy()
                    time.sleep(0.001)
                self._healthy()
                if self.integrity_previous["native_vsync_edges"] - initial < 2:
                    raise SourceError("Native source stopped during final accounting interval")
                self.final_accounting = dict(identity=self._healthy(),
                    native_edges_begin=initial,
                    native_edges_end=self.integrity_previous["native_vsync_edges"],
                    interval_seconds=interval, passed=True)
            except Exception as error:
                failure = error
                self.integrity_failure = dict(self.integrity_failure or {}, final_accounting_error=str(error))
        if self.control is not None:
            self.control.enable(False)
        if self.native is not None or not self.dma_shutdown_safe:
            self.dma_shutdown_safe = False
            mmio = self.native.mmio if self.native is not None else self.hdmi._vdma.readchannel._mmio
            self._stage("dma_stop_status_before", dict(
                control=mmio.read(0x30), status=mmio.read(0x34)))
            OneFrameDMA.stop_mmio(mmio, self.timeout)
            self._stage("dma_stop_status_after", dict(
                control=mmio.read(0x30), status=mmio.read(0x34)))
        if self._started:
            # The credit path never invokes the driver's circular-frame cache or
            # its unbounded S2MM.stop loop. Frontend teardown follows raw halt.
            self.hdmi.frontend.stop()
            self._started = False
        if self.native is not None:
            self.native.buffer.freebuffer()
            self.native = None
        self.dma_shutdown_safe = True
        if failure is not None:
            raise failure
