"""Explicit synthetic and PYNQ M0 sources with owned frame lifetimes."""

import asyncio
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import time
from dataclasses import dataclass

import numpy as np


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
        pixels = base[..., ::-1] if self.bgr else base
        rgb = np.array(pixels, order="C", copy=True)
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
        if (mode.width, mode.height, mode.bits_per_pixel) != (640, 480, 24):
            raise SourceError("M0 accepts only 640x480 with 24-bit DMA pixels")

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
            if pixels.dtype != np.uint8 or pixels.shape != (480, 640, 3):
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


def verify_litex_artifacts(bitfile, manifest):
    """Reject stale or unrelated artifact pairs before loading any hardware."""
    bitfile, manifest = Path(bitfile).resolve(), Path(manifest).resolve()
    record = json.loads(manifest.read_text())
    if record.get("schema_version") != 1 or record.get("geometry") != [640, 480]:
        raise SourceError("LiteX manifest must declare schema1 and geometry640x480")
    if record.get("pynq_commit") != "93ddd21ab623883590a8c8b07f0b157b2855da4b":
        raise SourceError("LiteX manifest does not use the pinned PYNQ receiver")
    if record.get("clock_hz") != 142857132:
        raise SourceError("LiteX manifest clock does not match the capture design")
    if type(record.get("capture_enable_reset")) is not int or record["capture_enable_reset"] != 0:
        raise SourceError("LiteX manifest must declare capture enable reset0")
    if (record.get("pixel_clock_hz") != 25200000 or
            record.get("supported_pixel_clocks_hz") != [25175000, 25200000] or
            record.get("receiver_k_clk_range") != 5):
        raise SourceError("LiteX manifest must declare the corrected VGA receiver configuration")
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
    if parameters.get("kClkRange") != "5":
        raise SourceError("HWH DVI receiver clock range is not configured for VGA")
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
    return record


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

    def __init__(self, bitfile, manifest, *, progress=None):
        super().__init__(bitfile, progress=progress)
        self.manifest_path = manifest
        self.control = None
        self.integrity_baseline = None
        self.integrity_previous = None
        self.integrity_failure = None

    def load_overlay(self, download=True):
        self._stage("litex_artifact_verification")
        self.manifest = verify_litex_artifacts(self.bitfile, self.manifest_path)
        self._stage("pynq_import")
        import pynq
        if pynq.__version__ != "3.0.1":
            raise SourceError("LiteX adapter requires PYNQ3.0.1")
        from pynq.lib.video import PIXEL_BGR
        from pynq.lib.video.hierarchies import VideoIn
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
        if not download:
            # GPIO-only control must not instantiate video drivers. PixelPacker
            # construction writes its mode register even when no DMA is started.
            return
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
