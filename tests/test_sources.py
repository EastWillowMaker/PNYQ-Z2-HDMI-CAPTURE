import asyncio
from types import SimpleNamespace

import numpy as np
import pytest

from hdmi_capture.sources import PynqSource, Sample, SourceError, SyntheticSource, synthetic_pattern


def test_pattern_channels_rows_columns_and_frames():
    a = synthetic_pattern(640, 480, 13)
    b = synthetic_pattern(640, 480, 14)
    np.testing.assert_array_equal(a[0, :3], [[255, 0, 0], [0, 255, 0], [0, 0, 255]])
    assert a[277, 301].tolist() == [45, 21, 13]
    assert b[277, 301].tolist() == [45, 21, 14]
    assert a.dtype == np.uint8 and a.shape == (480, 640, 3)


def test_owned_copy_and_exactly_once_release():
    pixels = np.array([[[1, 2, 3]]], dtype=np.uint8)
    released = []
    sample = Sample(pixels, 1, bgr=True, release=lambda: released.append(True))
    rgb = sample.copy_rgb()
    sample.close()
    sample.close()
    pixels[:] = 0
    assert rgb.tolist() == [[[3, 2, 1]]]
    assert not rgb.flags.writeable
    assert released == [True]


@pytest.mark.parametrize("bgr", [False, True])
def test_full_hd1080_copy_is_plain_owned_contiguous_and_exact_for_native_strided_buffer(bgr):
    width, height = 1920, 1080

    class NativeFrame(np.ndarray):
        def __array_finalize__(self, source):
            self.native_owner = getattr(source, "native_owner", None)

    storage = np.empty((height, width, 4), dtype=np.uint8)
    x = np.arange(width, dtype=np.uint8)[None, :]
    y = np.arange(height, dtype=np.uint8)[:, None]
    storage[..., 0] = x
    storage[..., 1] = y
    storage[..., 2] = (x.astype(np.uint16) + y.astype(np.uint16) + 17) % 256
    pixels = storage[..., :3].view(NativeFrame)
    pixels.native_owner = object()
    assert not pixels.flags.c_contiguous

    released = []
    sample = Sample(pixels, 1, bgr=bgr, release=lambda: released.append(True))
    rgb = sample.copy_rgb()

    assert type(rgb) is np.ndarray
    assert rgb.shape == (1080, 1920, 3)
    assert rgb.flags.c_contiguous and rgb.flags.owndata and not rgb.flags.writeable
    assert not hasattr(rgb, "native_owner")
    channels = (2, 1, 0) if bgr else (0, 1, 2)
    for output_channel, input_channel in enumerate(channels):
        np.testing.assert_array_equal(rgb[..., output_channel], pixels[..., input_channel])
    assert released == []

    sample.close()
    pixels[:] = 0
    assert rgb[0, 0].tolist() == ([17, 0, 0] if bgr else [0, 0, 17])
    assert released == [True]


class Buffer(np.ndarray):
    def freebuffer(self):
        self.freed += 1
        self[:] = 0


class FakeHDMI:
    def __init__(self, width=640, height=480):
        self.mode = SimpleNamespace(width=width, height=height, bits_per_pixel=24)
        self.frontend = SimpleNamespace(mode=self.mode)
        self.buffer = np.zeros((height, width, 3), dtype=np.uint8).view(Buffer)
        self.buffer.freed = 0
        self.buffer[:] = [1, 2, 3]
        self.closed = False

    def configure(self, pixel_format):
        self.configured = pixel_format

    def start(self):
        pass

    def close(self):
        self.closed = True

    async def readframe_async(self):
        return self.buffer


def test_pynq_bgr_copy_and_mode_change_rejection():
    async def run():
        hdmi = FakeHDMI()
        source = PynqSource(hdmi=hdmi, pixel_format="BGR")
        source.start()
        sample = await source.read()
        rgb = sample.copy_rgb()
        sample.close()
        assert rgb[2, 3].tolist() == [3, 2, 1]
        assert hdmi.buffer.freed == 1 and hdmi.configured == "BGR"
        hdmi.frontend.mode = SimpleNamespace(width=1280, height=720, bits_per_pixel=24)
        with pytest.raises(SourceError):
            await source.read()
        source.close()
        assert hdmi.closed
    asyncio.run(run())


def test_mode_changes_during_read_release_dma_buffer():
    async def run():
        hdmi = FakeHDMI()
        async def changed_read():
            hdmi.frontend.mode = SimpleNamespace(width=800, height=600, bits_per_pixel=24)
            return hdmi.buffer
        hdmi.readframe_async = changed_read
        source = PynqSource(hdmi=hdmi, pixel_format="BGR")
        source.start()
        with pytest.raises(SourceError):
            await source.read()
        assert hdmi.buffer.freed == 1
        source.close()
    asyncio.run(run())


def test_unsupported_start_closes_source():
    hdmi = FakeHDMI()
    hdmi.mode.width = 800
    with pytest.raises(SourceError):
        PynqSource(hdmi=hdmi, pixel_format="BGR").start()
    assert hdmi.closed


@pytest.mark.parametrize("kwargs", [{"width": 0}, {"height": 1081}, {"input_fps": 0}, {"input_fps": float("nan")}])
def test_synthetic_bounds(kwargs):
    with pytest.raises(ValueError):
        SyntheticSource(**kwargs)


def test_invalid_dtype_is_rejected_without_conversion():
    sample = Sample(np.ones((2, 2, 3), dtype=np.float32), 1)
    with pytest.raises(SourceError):
        sample.copy_rgb()


def test_startup_stages_are_optional_and_ordered():
    hdmi = FakeHDMI()
    stages = []
    source = PynqSource(hdmi=hdmi, pixel_format="BGR", progress=stages.append)
    source.start()
    assert stages == ["hdmi_configure_wait_input_lock", "hdmi_mode_check", "dma_start", "source_ready"]
    source.close()


def make_litex_artifacts(tmp_path):
    import hashlib
    import json
    from hdmi_capture.modes import get_mode, mode_metadata
    mode = get_mode("vga")
    bitfile = tmp_path / "capture.bit"
    hwh = tmp_path / "capture.hwh"
    bitfile.write_bytes(b"synthetic-bitstream-fixture")
    hwh.write_text('<ROOT><MODULE FULLNAME="/video/hdmi_in/frontend/dvi2rgb_0">'
                   f'<PARAMETERS><PARAMETER NAME="kClkRange" VALUE="{mode.receiver_k_clk_range}"/>'
                   '</PARAMETERS></MODULE><MODULE FULLNAME="/video/capture_control">'
                   '<PARAMETERS><PARAMETER NAME="C_DOUT_DEFAULT" VALUE="0x00000000"/>'
                   '</PARAMETERS></MODULE></ROOT>')
    manifest = tmp_path / "build-manifest.json"
    legacy_profile = mode_metadata(mode)
    legacy_profile.pop("capture_mode")
    legacy_profile.pop("timing")
    record = dict(schema_version=1, **legacy_profile, capture_enable_reset=0,
                  edid_sha256="f" * 64,
                  pynq_commit="93ddd21ab623883590a8c8b07f0b157b2855da4b",
                  bitstream_sha256=hashlib.sha256(bitfile.read_bytes()).hexdigest(),
                  hwh_sha256=hashlib.sha256(hwh.read_bytes()).hexdigest())
    manifest.write_text(json.dumps(record))
    return bitfile, manifest


def make_mode_litex_artifacts(tmp_path, mode_name):
    import hashlib
    import json
    from hdmi_capture.modes import get_mode, mode_metadata
    mode = get_mode(mode_name)
    bitfile = tmp_path / "capture.bit"
    hwh = bitfile.with_suffix(".hwh")
    bitfile.write_bytes(b"synthetic-bitstream-fixture")
    hwh.write_text('<ROOT><MODULE FULLNAME="/video/hdmi_in/frontend/dvi2rgb_0">'
                   f'<PARAMETERS><PARAMETER NAME="kClkRange" VALUE="{mode.receiver_k_clk_range}"/>'
                   '</PARAMETERS></MODULE><MODULE FULLNAME="/video/capture_control">'
                   '<PARAMETERS><PARAMETER NAME="C_DOUT_DEFAULT" VALUE="0x00000000"/>'
                   '</PARAMETERS></MODULE></ROOT>')
    manifest = tmp_path / "build-manifest.json"
    record = dict(schema_version=1, **mode_metadata(mode), capture_enable_reset=0,
                  edid_sha256="f" * 64,
                  pynq_commit="93ddd21ab623883590a8c8b07f0b157b2855da4b",
                  bitstream_sha256=hashlib.sha256(bitfile.read_bytes()).hexdigest(),
                  hwh_sha256=hashlib.sha256(hwh.read_bytes()).hexdigest())
    manifest.write_text(json.dumps(record))
    return bitfile, manifest


def test_litex_rejects_old_receiver_even_with_matching_hashes(tmp_path):
    import hashlib
    import json
    from hdmi_capture.sources import verify_litex_artifacts
    bitfile, manifest = make_litex_artifacts(tmp_path)
    hwh = bitfile.with_suffix(".hwh")
    hwh.write_text(hwh.read_text().replace('VALUE="5"', 'VALUE="1"'))
    record = json.loads(manifest.read_text())
    record["hwh_sha256"] = hashlib.sha256(hwh.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(record))
    with pytest.raises(SourceError, match="clock range"):
        verify_litex_artifacts(bitfile, manifest)


def test_litex_manifest_hashes_fail_closed(tmp_path):
    import json
    from hdmi_capture.sources import verify_litex_artifacts
    bitfile, manifest = make_litex_artifacts(tmp_path)
    record = verify_litex_artifacts(bitfile, manifest)
    assert record["geometry"] == [640, 480]
    assert record["capture_mode"] == "vga"
    assert "capture_mode" not in json.loads(manifest.read_text())
    bitfile.write_bytes(b"modified")
    with pytest.raises(SourceError, match="hash mismatch"):
        verify_litex_artifacts(bitfile, manifest)


def test_litex_accepts_only_explicit_matching_1080p30_manifest(tmp_path):
    from hdmi_capture.sources import verify_litex_artifacts
    bitfile, manifest = make_mode_litex_artifacts(tmp_path, "1080p30")
    record = verify_litex_artifacts(bitfile, manifest, expected_mode="1080p30")
    assert record["capture_mode"] == "1080p30"
    assert record["geometry"] == [1920, 1080]
    assert record["pixel_clock_hz"] == 74_250_000
    with pytest.raises(SourceError, match="does not match requested mode"):
        verify_litex_artifacts(bitfile, manifest, expected_mode="vga")


@pytest.mark.parametrize("field,value", [
    ("geometry", [1920, 1081]),
    ("pixel_clock_hz", 74_250_001),
    ("receiver_k_clk_range", 5),
    ("timing", {}),
])
def test_litex_1080p30_manifest_profile_fields_fail_closed(tmp_path, field, value):
    import json
    from hdmi_capture.sources import verify_litex_artifacts
    bitfile, manifest = make_mode_litex_artifacts(tmp_path, "1080p30")
    record = json.loads(manifest.read_text())
    record[field] = value
    manifest.write_text(json.dumps(record))
    with pytest.raises(SourceError, match=f"manifest {field}"):
        verify_litex_artifacts(bitfile, manifest, expected_mode="1080p30")


def test_litex_1080p30_manifest_profile_fields_require_exact_json_types(tmp_path):
    import json
    from hdmi_capture.sources import verify_litex_artifacts
    bitfile, manifest = make_mode_litex_artifacts(tmp_path, "1080p30")
    record = json.loads(manifest.read_text())
    record["timing"]["h_sync_positive"] = 1
    manifest.write_text(json.dumps(record))
    with pytest.raises(SourceError, match="manifest timing"):
        verify_litex_artifacts(bitfile, manifest, expected_mode="1080p30")


def test_litex_profile_conflict_is_rejected_before_overlay_or_allocation(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace
    from hdmi_capture.sources import LiteXCreditSource
    bitfile, manifest = make_mode_litex_artifacts(tmp_path, "1080p30")
    allocations = []
    monkeypatch.setitem(sys.modules, "pynq", SimpleNamespace(
        allocate=lambda **kwargs: allocations.append(kwargs)))
    source = LiteXCreditSource(bitfile, manifest, capture_mode="vga")
    with pytest.raises(SourceError, match="does not match requested mode"):
        source.start()
    assert allocations == []


def test_litex_source_accepts_profile_geometry_and_rejects_shape_mismatch():
    from hdmi_capture.sources import LiteXSource
    source = LiteXSource("unused.bit", "unused.json", capture_mode="1080p30")
    hdmi = FakeHDMI(1920, 1080)
    source.hdmi, source.pixel_format = hdmi, "BGR"
    sample = asyncio.run(PynqSource.read(source))
    assert sample.pixels.shape == (1080, 1920, 3)
    sample.close()
    hdmi.buffer = np.zeros((480, 640, 3), dtype=np.uint8).view(Buffer)
    hdmi.buffer.freed = 0
    with pytest.raises(SourceError, match="shape"):
        asyncio.run(PynqSource.read(source))
    assert hdmi.buffer.freed == 1


def test_litex_counter_control_discovery_and_snapshot():
    from hdmi_capture.sources import LiteXControl
    descriptions = {"video/" + name: dict(type="xilinx.com:ip:axi_gpio:2.0",
                                         phys_addr=address, addr_range=4096)
                    for name, address in zip(("capture_control", "capture_counts", "capture_errors"), (101, 202, 303))}
    registers = {101: {0: 1, 8: 10}, 202: {0: 12, 8: 11}, 303: {0: 1, 8: 2}}
    class MMIO:
        def __init__(self, address, length):
            self.values = registers[address]
            assert length == 4096
        def read(self, offset):
            return self.values[offset]
        def write(self, offset, value):
            self.values[offset] = value
    control = LiteXControl(SimpleNamespace(ip_dict=descriptions), MMIO)
    assert control.snapshot()["observed_frames"] == 12
    assert control.snapshot()["invalid_frames"] == 2
    assert not control.snapshot()["snapshot_atomic"]
    control.enable(False)
    assert not control.snapshot()["enabled"]
    control.enable(True)
    assert control.snapshot()["enabled"]
    descriptions.pop("video/capture_errors")
    with pytest.raises(SourceError):
        LiteXControl(SimpleNamespace(ip_dict=descriptions), MMIO)


def test_litex_load_uses_generic_overlay_and_explicit_vdma(tmp_path, monkeypatch):
    import sys
    from types import ModuleType
    from hdmi_capture.sources import LiteXSource
    bitfile, manifest = make_litex_artifacts(tmp_path)
    calls = []
    hdmi = FakeHDMI()
    descriptions = {"video/" + name: dict(type="xilinx.com:ip:axi_gpio:2.0",
                                         phys_addr=i, addr_range=4096)
                    for i, name in enumerate(("capture_control", "capture_counts", "capture_errors"))}
    descriptions["video/axi_vdma"] = dict(type="xilinx.com:ip:axi_vdma:6.3",
                                          parameters=dict(C_INCLUDE_S2MM="1", C_INCLUDE_MM2S="0"))
    vdma = object()
    class Overlay:
        def __init__(self, path, download):
            calls.append((path, download))
            self.download = download
            self.ip_dict = descriptions
            self._video = SimpleNamespace(hdmi_in=SimpleNamespace(description="input-description"), axi_vdma=vdma)
        @property
        def video(self):
            if not self.download:
                pytest.fail("GPIO-only attach must never access or instantiate video drivers")
            return self._video
        def is_loaded(self):
            return True
    class MMIO:
        def __init__(self, address, length):
            self.value = 0
        def write(self, offset, value):
            self.value = value
        def read(self, offset):
            return self.value
    def video_in(description, dma):
        assert description == "input-description" and dma is vdma
        return hdmi
    pynq = ModuleType("pynq")
    pynq.__path__ = []
    pynq.__version__, pynq.Overlay, pynq.MMIO = "3.0.1", Overlay, MMIO
    lib = ModuleType("pynq.lib")
    lib.__path__ = []
    video = ModuleType("pynq.lib.video")
    video.__path__ = []
    video.PIXEL_BGR = "BGR"
    # Installed PYNQ3.0.1 exports pixel formats, but not VideoIn, at package root.
    hierarchies = ModuleType("pynq.lib.video.hierarchies")
    hierarchies.VideoIn = video_in
    for name, module in (("pynq", pynq), ("pynq.lib", lib), ("pynq.lib.video", video),
                         ("pynq.lib.video.hierarchies", hierarchies)):
        monkeypatch.setitem(sys.modules, name, module)
    source = LiteXSource(bitfile, manifest)
    source.start()
    assert calls == [(str(bitfile), True)]
    sample = asyncio.run(source.read())
    assert sample.extra_metadata["frame_source_id"] is None
    assert sample.extra_metadata["hardware_qualification"] == "unverified"
    assert not source.baseline_only
    sample.close()
    source.close()
    attached = LiteXSource(bitfile, manifest)
    attached.load_overlay(download=False)
    assert attached.hdmi is None
    assert attached.control.snapshot()["snapshot_atomic"] is False
    from hdmi_capture.sender import control_main
    control_main(["--bitfile", str(bitfile), "--manifest", str(manifest), "--enable", "0"])
    assert calls[-2:] == [(str(bitfile), False), (str(bitfile), False)]
    descriptions["video/axi_vdma"]["parameters"]["C_INCLUDE_MM2S"] = "1"
    with pytest.raises(SourceError, match="S2MM-only"):
        LiteXSource(bitfile, manifest).load_overlay(download=False)


def pinned_pynq_buffer():
    """Execute the exact inspected class with native release calls stubbed."""
    import ast
    import ctypes
    from pathlib import Path
    path = Path(__file__).parent / "fixtures/pynq_3_0_1_buffer.py"
    tree = ast.parse(path.read_text())
    node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "PynqBuffer")
    released = []
    namespace = dict(np=np, ctypes=ctypes,
                     libc=SimpleNamespace(munmap=lambda ptr, size: released.append(("unmap", size))),
                     xrt=SimpleNamespace(xclFreeBO=lambda handle, bo: released.append(("free", bo))))
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
    return namespace["PynqBuffer"], released


def test_pinned_pynq_double_free_regression_and_object_pool():
    from hdmi_capture.sources import PynqFramePool
    buffer_type, released = pinned_pynq_buffer()
    class CompatibleBuffer(buffer_type):
        # NumPy2 added a read-only ndarray.device; board NumPy1 predates it.
        @property
        def device(self):
            return self._test_device
        @device.setter
        def device(self, value):
            self._test_device = value
    class Cache:
        def __init__(self):
            self.returned = []
            self.allocated = 0
            self._cache = []
        def return_pointer(self, pointer):
            self.returned.append(pointer)
        def getframe(self):
            self.allocated += 1
            frame = CompatibleBuffer((2, 2, 3), dtype=np.uint8,
                                bo=self.allocated, device=SimpleNamespace(handle=7))
            frame.memory = True
            frame.pointer = (self.allocated, object(), 1234)
            frame.return_to = self
            return frame
    # Before adapter correction: first explicit release returns a live pointer,
    # then destructor releases that same allocation despite the cache reference.
    broken = Cache()
    frame = broken.getframe()
    frame.freebuffer()
    assert len(broken.returned) == 1 and released == []
    frame.__del__()
    assert released == [("unmap", 12), ("free", 1)]
    released.clear()
    cache = Cache()
    active = [cache.getframe() for _ in range(4)]
    channel = SimpleNamespace(_cache=cache, _frames=active)
    pool = PynqFramePool(channel)
    for _ in range(100):
        incoming = cache.getframe()
        captured = active.pop(0)
        active.append(incoming)
        pool.release(captured)
    assert cache.allocated == 5
    assert len(pool.owned) == 5
    assert cache.returned == [] and released == []
    # DMA ownership is relinquished before teardown; each BO is freed once.
    active.clear()
    pool.close()
    pool.close()
    assert [item for item in released if item[0] == "free"] == [("free", i) for i in range(1, 6)]


def test_stop_failure_retains_dma_buffers_and_success_frees_after_halt():
    from hdmi_capture.sources import PynqSource
    trace = []
    class MMIO:
        def read(self, offset):
            trace.append(("read", offset))
            return 1 if channel.running and offset == 0x30 else int(not channel.running)
    channel = SimpleNamespace(running=True, _mmio=MMIO())
    class Pool:
        owned = {1: object()}
        def close(self):
            assert not channel.running
            trace.append("pool_free")
    class HDMI:
        _vdma = SimpleNamespace(readchannel=channel)
        fail = True
        def close(self):
            trace.append("dma_stop")
            if self.fail:
                raise KeyboardInterrupt()
            channel.running = False
    hdmi = HDMI()
    stages = []
    source = PynqSource(hdmi=hdmi, progress=stages.append)
    source._started, source._pool = True, Pool()
    with pytest.raises(KeyboardInterrupt):
        source.close()
    assert source._started and source._pool is not None
    assert "pool_free" not in trace
    assert not any(isinstance(x, dict) and x["stage"] == "pool_free_begin" for x in stages)
    hdmi.fail = False
    source.close()
    assert trace.index("pool_free") > max(i for i, event in enumerate(trace) if event == "dma_stop")
    assert stages[-3] == "dma_stop_complete"
    assert stages[-2] == dict(stage="pool_free_begin", buffers=1)
    assert stages[-1] == "pool_free_complete"
    assert source._pool is None and not source._started


def test_nonhalting_stop_cannot_release_pool():
    trace = []
    channel = SimpleNamespace(running=True)
    hdmi = SimpleNamespace(_vdma=SimpleNamespace(readchannel=channel), close=lambda: trace.append("stop"))
    pool = SimpleNamespace(close=lambda: trace.append("free"))
    source = PynqSource(hdmi=hdmi)
    source._started, source._pool = True, pool
    with pytest.raises(SourceError, match="did not halt"):
        source.close()
    assert trace == ["stop"]
    assert source._pool is pool and source._started


def test_partial_native_start_failure_is_also_unsafe_until_halt():
    hdmi = FakeHDMI()
    def fail_start():
        raise RuntimeError("Interrupted partial DMA start")
    def fail_close():
        raise RuntimeError("DMA stop failed")
    hdmi.start, hdmi.close = fail_start, fail_close
    source = PynqSource(hdmi=hdmi, pixel_format="BGR")
    with pytest.raises(RuntimeError, match="DMA stop failed"):
        source.start()
    assert not source.dma_shutdown_safe
    assert not source._started


@pytest.mark.parametrize("field,initial,changed", [("invalid_frames", 0, 1),
                                                     ("frontend_overflow_episodes", 0, 1),
                                                     ("frontend_underflow_episodes", 0, 1),
                                                     ("invalid_frames", (1 << 32) - 1, 0),
                                                     ("native_vsync_edges", 12, 0),
                                                     ("native_vsync_edges", (1 << 32) - 1, 0)])
def test_litex_integrity_change_returns_buffer_before_error_and_safe_close(field, initial, changed):
    from hdmi_capture.sources import LiteXSource
    hdmi = FakeHDMI()
    counters = dict(invalid_frames=0, frontend_overflow_episodes=0, native_vsync_edges=12)
    counters[field] = initial
    class Control:
        def enable(self, enabled):
            pass
        def snapshot(self, sample_point=None):
            return dict(counters, enabled=False, selected_frames=0, sample_point=sample_point)
    class Source(LiteXSource):
        def load_overlay(self, download=True):
            self.hdmi, self.pixel_format = hdmi, "BGR"
            self.control = Control()
            self.manifest = dict(bitstream_sha256="f" * 64, capture_enable_reset=0)
    async def run():
        source = Source("unused.bit", "unused.json")
        source.start()
        counters[field] = changed
        with pytest.raises(SourceError, match="integrity counter changed"):
            await source.read()
        assert hdmi.buffer.freed == 1
        assert source.integrity_failure["frame_association"] == "unknown_session_stopped"
        assert source.integrity_baseline[field] == initial
        assert not source.dma_shutdown_safe
        source.close()
        assert source.dma_shutdown_safe and hdmi.closed
    asyncio.run(run())


def test_litex_startup_errors_are_retained_in_metadata():
    from hdmi_capture.sources import LiteXSource
    hdmi = FakeHDMI()
    class Control:
        def enable(self, enabled):
            pass
        def snapshot(self, sample_point=None):
            return dict(invalid_frames=2, frontend_overflow_episodes=3, native_vsync_edges=12,
                        enabled=False, selected_frames=0, sample_point=sample_point)
    class Source(LiteXSource):
        def load_overlay(self, download=True):
            self.hdmi, self.pixel_format = hdmi, "BGR"
            self.control = Control()
            self.manifest = dict(bitstream_sha256="f" * 64, capture_enable_reset=0)
    async def run():
        source = Source("unused.bit", "unused.json")
        source.start()
        sample = await source.read()
        assert sample.extra_metadata["litex_startup_counters"]["invalid_frames"] == 2
        assert sample.extra_metadata["litex_startup_counters"]["frontend_overflow_episodes"] == 3
        assert sample.extra_metadata["litex_counters"]["invalid_frames"] == 2
        sample.close()
        source.close()
    asyncio.run(run())


def test_litex_gate_only_enables_after_dma_start_and_pool_ready(monkeypatch):
    import hdmi_capture.sources as module
    from hdmi_capture.sources import LiteXSource
    trace = []
    hdmi = FakeHDMI()
    configure = hdmi.configure
    def configured(pixel_format):
        trace.append("configure")
        configure(pixel_format)
    hdmi.configure = configured
    channel = SimpleNamespace(running=False)
    hdmi._vdma = SimpleNamespace(readchannel=channel)
    def started():
        trace.append("dma_start")
        channel.running = True
    hdmi.start = started
    def stopped():
        channel.running = False
        hdmi.closed = True
    hdmi.close = stopped
    class Pool:
        owned = {}
        def __init__(self, active_channel):
            assert active_channel.running
            trace.append("pool_ready")
        def close(self):
            assert not channel.running
    monkeypatch.setattr(module, "PynqFramePool", Pool)
    class Control:
        def enable(self, enabled):
            trace.append(("enable", enabled))
        def snapshot(self, sample_point=None):
            trace.append("baseline")
            return dict(invalid_frames=0, frontend_overflow_episodes=0,
                        frontend_underflow_episodes=0, native_vsync_edges=2,
                        dropped_frames=12, enabled=False, selected_frames=0,
                        sample_point=sample_point)
    class Source(LiteXSource):
        def load_overlay(self, download=True):
            self.hdmi, self.pixel_format = hdmi, "BGR"
            self.control = Control()
            self.manifest = dict(bitstream_sha256="f" * 64, capture_enable_reset=0)
    source = Source("unused.bit", "unused.json")
    source.start()
    assert trace == [("enable", False), "configure", "dma_start", "pool_ready",
                     "baseline", ("enable", True)]
    assert source.integrity_baseline["dropped_frames"] == 12
    source.close()


@pytest.mark.parametrize("baseline", [dict(enabled=True, selected_frames=0),
                                      dict(enabled=False, selected_frames=1),
                                      dict(enabled=False, selected_frames=False), {}])
def test_litex_rejects_unproved_disabled_baseline_before_enabling(baseline):
    from hdmi_capture.sources import LiteXSource
    hdmi = FakeHDMI()
    enables = []
    class Control:
        def enable(self, enabled):
            enables.append(enabled)
        def snapshot(self, sample_point=None):
            return dict(baseline, invalid_frames=1, frontend_overflow_episodes=0,
                        frontend_underflow_episodes=0, native_vsync_edges=2,
                        sample_point=sample_point)
    class Source(LiteXSource):
        def load_overlay(self, download=True):
            self.hdmi, self.pixel_format = hdmi, "BGR"
            self.control = Control()
            self.manifest = dict(bitstream_sha256="f" * 64, capture_enable_reset=0)
    source = Source("unused.bit", "unused.json")
    with pytest.raises(SourceError, match="baseline requires disabled gate"):
        source.start()
    assert enables == [False]
    assert source.integrity_baseline["invalid_frames"] == 1
    assert hdmi.closed and source.dma_shutdown_safe


def test_manifest_and_paired_hwh_must_both_prove_disabled_reset(tmp_path):
    import hashlib
    import json
    from hdmi_capture.sources import verify_litex_artifacts
    bitfile, manifest = make_litex_artifacts(tmp_path)
    hwh = bitfile.with_suffix(".hwh")
    hwh.write_text(hwh.read_text().replace('NAME="C_DOUT_DEFAULT" VALUE="0x00000000"',
                                          'NAME="C_DOUT_DEFAULT" VALUE="0x00000001"'))
    record = json.loads(manifest.read_text())
    record["hwh_sha256"] = hashlib.sha256(hwh.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(record))
    with pytest.raises(SourceError, match="reset disabled"):
        verify_litex_artifacts(bitfile, manifest)
    record["capture_enable_reset"] = False
    manifest.write_text(json.dumps(record))
    with pytest.raises(SourceError, match="declare capture enable reset0"):
        verify_litex_artifacts(bitfile, manifest)


class CreditDMARegisters:
    def __init__(self):
        self.values = {0x34: 1, 0x28: 0}
        self.writes = []
    def read(self, offset):
        return self.values.get(offset, 0)
    def write(self, offset, value):
        self.writes.append((offset, value))
        if offset == 0x34:
            self.values[offset] &= ~value
        else:
            self.values[offset] = value
        if offset == 0xA0:
            self.values[0x34] = 0
    def complete(self):
        self.values[0x34] = 0x1001
        self.values[0x30] &= ~1


def test_oneframe_dma_start_irq_is_not_completion_and_stale_halt_rejected():
    from hdmi_capture.sources import OneFrameDMA
    registers = CreditDMARegisters()
    dma = OneFrameDMA(registers, SimpleNamespace(physical_address=0x100000, nbytes=640 * 480 * 3))
    dma.arm()
    registers.values[0x34] = 0x1000  # Frame-start IRQ, still running.
    assert dma.running_observed()
    assert dma.completed() is None
    registers.complete()
    assert dma.completed() == 0x1001
    dma.arm()
    registers.complete()  # Never observed running for this request.
    assert dma.completed() is None
    assert all(registers.read(0xAC + 4 * i) == 0x100000 for i in range(4))


def test_oneframe_dma_1080p30_programs_byte_stride_and_checks_full_buffer_span():
    from hdmi_capture.sources import OneFrameDMA
    width, height = 1920, 1080
    frame_bytes = width * height * 3
    maximum_start = 0xFFFFFFFF - frame_bytes + 1
    aligned_start = maximum_start - maximum_start % 64
    registers = CreditDMARegisters()
    dma = OneFrameDMA(registers, SimpleNamespace(physical_address=aligned_start,
                                                 nbytes=frame_bytes),
                      width=width, height=height)
    dma.arm()
    assert aligned_start + frame_bytes - 1 <= 0xFFFFFFFF
    assert registers.read(0xA8) == registers.read(0xA4) == width * 3 == 5760
    assert registers.read(0xA0) == height
    assert all(registers.read(0xAC + 4 * index) == aligned_start for index in range(4))
    with pytest.raises(SourceError, match="full frame"):
        OneFrameDMA(registers, SimpleNamespace(physical_address=aligned_start + 64,
                                               nbytes=frame_bytes),
                    width=width, height=height)
    with pytest.raises(SourceError, match="aligned"):
        OneFrameDMA(registers, SimpleNamespace(physical_address=aligned_start + 1,
                                               nbytes=frame_bytes),
                    width=width, height=height)


def test_oneframe_dma_rejects_unsupported_geometry_and_short_buffer():
    from hdmi_capture.sources import OneFrameDMA
    registers = CreditDMARegisters()
    with pytest.raises(SourceError, match="supported geometry"):
        OneFrameDMA(registers, SimpleNamespace(physical_address=0x100000,
                                               nbytes=1280 * 720 * 3),
                    width=1280, height=720)
    with pytest.raises(SourceError, match="full-size buffer"):
        OneFrameDMA(registers, SimpleNamespace(physical_address=0x100000,
                                               nbytes=640 * 480 * 3 - 1))


@pytest.mark.parametrize('error', [0x10, 0x20, 0x40, 0x80, 0x100, 0x800, 0x4000, 0x8000])
def test_oneframe_dma_errors_are_never_cleared_before_inspection(error):
    from hdmi_capture.sources import OneFrameDMA
    registers = CreditDMARegisters()
    registers.values[0x34] |= error
    dma = OneFrameDMA(registers, SimpleNamespace(physical_address=0x100000, nbytes=640 * 480 * 3))
    with pytest.raises(SourceError, match='Raw VDMA error'):
        dma.arm()
    assert registers.writes == []


def credit_reader_fixture(mode="vga"):
    from hdmi_capture.sources import LiteXCreditSource, OneFrameDMA
    source = LiteXCreditSource('unused.bit', 'unused.json', capture_mode=mode,
                               capture_fps=60, timeout=.03)
    registers = CreditDMARegisters()
    buffer = np.zeros((source.height, source.width, 3), np.uint8).view(FakeCreditBuffer)
    buffer.invalidations = 0
    source.native = OneFrameDMA(registers, buffer, width=source.width, height=source.height)
    source.hdmi = FakeHDMI()
    source.manifest = dict(bitstream_sha256='f' * 64)
    baseline = dict(enabled=False, selected_frames=0, invalid_frames=1,
                    frontend_overflow_episodes=0, frontend_underflow_episodes=0,
                    native_vsync_edges=100)
    source.integrity_baseline = source.integrity_previous = baseline
    class Control:
        command = 1
        next_native = 102
        next_sof = 22
        state = dict(credit_busy=False, credit_done=False, credit_failed=False,
                     request_seen=0, ack_seen=0, source_sequence_fault=False,
                     native_armed=True, selected_sof_id=0, selected_native_vsync_id=0,
                     selected_completed=0, command_errors=0, source_sequence_faults=0,
                     identity_snapshot_coherent=True)
        def identity(self):
            return dict(self.state)
        def snapshot(self):
            return dict(baseline)
        def request(self):
            assert source.native.seen_running
            self.command ^= 2
            self.state.update(credit_busy=True, credit_done=True,
                              request_seen=(self.command >> 1) & 1,
                              selected_sof_id=self.next_sof,
                              selected_native_vsync_id=self.next_native,
                              selected_completed=self.state['selected_completed'] + 1)
            registers.complete()
        def acknowledge(self):
            self.command ^= 4
            self.state.update(credit_busy=False, credit_done=False,
                              ack_seen=(self.command >> 2) & 1)
    source.control = Control()
    return source, registers


class FakeCreditBuffer(np.ndarray):
    physical_address = 0x100000
    def invalidate(self):
        self.invalidations += 1


def test_credit_identity_lease_and_exact_sampling_gaps():
    source, registers = credit_reader_fixture()
    async def run():
        first = await source.read()
        assert first.sequence == 102
        assert first.extra_metadata['frame_source_id'] == 22
        assert first.extra_metadata['source_accounting']['intentional_skips_since_previous'] is None
        with pytest.raises(SourceError, match='lease'):
            await source.read()
        rgb = first.copy_rgb()
        first.close()
        assert not source.control.state['credit_busy'] and not rgb.flags.writeable
        source.control.next_native, source.control.next_sof = 132, 52
        second = await source.read()
        accounting = second.extra_metadata['source_accounting']
        assert accounting['intentional_skips_since_previous'] == 29
        assert accounting['source_intentional_sampling_total'] == 29
        assert accounting['first_acquired_source_id'] == 102
        assert accounting['startup_intentional_accepted_sof_skips'] == 22
        assert accounting['acquired_frames_total'] == 2
        assert second.pixels.invalidations == 2
        second.close()
    asyncio.run(run())


@pytest.mark.parametrize('field,value', [('credit_failed', True), ('source_sequence_fault', True),
                                        ('command_errors', 1), ('source_sequence_faults', 1),
                                        ('native_armed', False)])
def test_credit_faults_prevent_request_or_delivery(field, value):
    source, registers = credit_reader_fixture()
    source.control.state[field] = value
    with pytest.raises(SourceError):
        asyncio.run(source.read())
    assert registers.writes == []
    assert not source.leased


@pytest.mark.parametrize('field', ['invalid_frames', 'frontend_overflow_episodes',
                                 'frontend_underflow_episodes'])
def test_credit_integrity_counter_change_rejects_before_dma_arm(field):
    source, registers = credit_reader_fixture()
    source.control.snapshot = lambda: dict(source.integrity_baseline,
        **{field: source.integrity_baseline[field] + 1})
    with pytest.raises(SourceError, match=field):
        asyncio.run(source.read())
    assert registers.writes == [] and source.acquired == 0
    assert source.integrity_failure['counter'] == field


def test_credit_identity_changed_during_copy_prevents_ack():
    source, _ = credit_reader_fixture()
    async def run():
        sample = await source.read()
        sample.copy_rgb()
        source.control.state['selected_sof_id'] += 1
        command = source.control.command
        with pytest.raises(SourceError, match='Identity changed'):
            sample.close()
        assert source.control.command == command and source.leased
    asyncio.run(run())


def test_credit_stale_halt_times_out_before_grant():
    source, registers = credit_reader_fixture()
    original = registers.write
    def write(offset, value):
        original(offset, value)
        if offset == 0xA0:
            registers.values[0x34] = 0x1001
    registers.write = write
    with pytest.raises(SourceError, match='timed out'):
        asyncio.run(source.read())
    assert source.control.command == 1
    assert source.dma_shutdown_safe is False


@pytest.mark.parametrize('native,sof', [(102, 22), (1, 1), (130, 51)])
def test_credit_repeated_reset_or_mismatched_ids_stop_session(native, sof):
    source, _ = credit_reader_fixture()
    async def run():
        sample = await source.read()
        sample.close()
        source.control.next_native, source.control.next_sof = native, sof
        with pytest.raises(SourceError, match='identity|identities'):
            await source.read()
        assert not source.leased
    asyncio.run(run())


def test_credit_halted_dma_waits_for_later_gate_closure():
    source, registers = credit_reader_fixture()
    original = source.control.request
    calls = 0
    identity = source.control.identity
    def request():
        original()
        source.control.state['credit_done'] = False
    def later():
        nonlocal calls
        calls += 1
        if calls >= 6:
            source.control.state['credit_done'] = True
        return identity()
    source.control.request, source.control.identity = request, later
    async def run():
        sample = await source.read()
        assert calls >= 6 and registers.read(0x34) == 0x1001
        sample.close()
    asyncio.run(run())


def test_credit_dma_error_after_grant_fails_before_buffer_invalidate():
    source, registers = credit_reader_fixture()
    original = source.control.request
    def request():
        original()
        registers.values[0x34] |= 0x10
    source.control.request = request
    with pytest.raises(SourceError, match='Raw VDMA error'):
        asyncio.run(source.read())
    assert source.native.buffer.invalidations == 0 and not source.leased


def test_credit_stop_mmio_failure_retains_owned_allocation():
    source, registers = credit_reader_fixture()
    source.control.command = 0
    source.control.enable = lambda enabled: None
    source.dma_shutdown_safe = False
    buffer = source.native.buffer
    def read(offset):
        raise OSError('MMIO inaccessible')
    registers.read = read
    with pytest.raises(OSError, match='inaccessible'):
        source.close()
    assert source.native.buffer is buffer and not source.dma_shutdown_safe


def test_legacy_litex_adapter_rejects_credit_manifest_before_overlay_import(monkeypatch, tmp_path):
    import hdmi_capture.sources as module
    bitfile, manifest = make_litex_artifacts(tmp_path)
    original = module.verify_litex_artifacts
    def credit_record(*args, **kwargs):
        return dict(original(*args, **kwargs), capture_interface='single_credit_parked_v1')
    monkeypatch.setattr(module, 'verify_litex_artifacts', credit_record)
    source = module.LiteXSource(bitfile, manifest)
    with pytest.raises(SourceError, match='ABI does not match'):
        source.load_overlay()


@pytest.mark.parametrize("capture_mode,width,height", [
    ("vga", 640, 480), ("1080p30", 1920, 1080),
])
def test_credit_startup_baseline_precedes_enable_without_stock_dma_start(
        monkeypatch, tmp_path, capture_mode, width, height):
    import sys
    import hdmi_capture.sources as module
    bitfile = tmp_path / 'capture.bit'
    bitfile.with_suffix('.hwh').write_text('''<ROOT><MODULE FULLNAME="/video/capture_control"><PARAMETERS>
        <PARAMETER NAME="C_GPIO_WIDTH" VALUE="32"/></PARAMETERS></MODULE>
        <MODULE FULLNAME="/video/axi_vdma"><PARAMETERS><PARAMETER NAME="C_ENABLE_DEBUG_INFO_15" VALUE="1"/>
        </PARAMETERS></MODULE></ROOT>''')
    record = dict(capture_interface=module.CREDIT_ABI, vdma_completion_mode='parked_frame_count_halt_v1',
                  vdma_frame_counter_enabled=True, vdma_fsync_mode='free_run', gate_completion_policy='next_sof_after_selected_output_drain_v1',
                  source_health_sha256='a'*64, capture_control_width=32, capture_control_reset=0,
                  source_identity_bits=32, source_identity_policy='native_delta_one_per_accepted_sof_with_watchdog',
                  receiver_reset_sync_sha256='a'*64, capture_lock_sync_sha256='b'*64, gateware_sha256='c'*64)
    monkeypatch.setattr(module, 'verify_litex_artifacts', lambda *args, **kwargs: record)
    trace = []
    template, registers = credit_reader_fixture()
    control = template.control
    def enable(enabled):
        trace.append(('enable', enabled))
        control.command = int(enabled)
    def snapshot(point=None):
        trace.append(('baseline', point))
        return dict(enabled=False, selected_frames=0, invalid_frames=1,
                    frontend_overflow_episodes=0, frontend_underflow_episodes=0, native_vsync_edges=100)
    control.enable, control.snapshot = enable, snapshot
    monkeypatch.setattr(module, 'CreditControl', lambda *args: control)
    hdmi = FakeHDMI(width, height)
    hdmi.start = lambda: pytest.fail('Stock DMA start must not be called')
    hdmi._vdma = SimpleNamespace(readchannel=SimpleNamespace(running=False, memory=object(), _mmio=registers), framecount=4)
    def allocate(**kwargs):
        assert kwargs['shape'] == (height, width, 3) and kwargs['cacheable'] is True
        trace.append('allocate')
        buffer = np.zeros(kwargs['shape'], dtype=np.uint8).view(FakeCreditBuffer)
        buffer.invalidations = 0
        return buffer
    monkeypatch.setitem(sys.modules, 'pynq', SimpleNamespace(allocate=allocate, MMIO=object()))
    class Source(module.LiteXCreditSource):
        def load_overlay(self, download=True):
            self.hdmi, self.pixel_format, self.manifest = hdmi, 'BGR', record
            self.overlay = SimpleNamespace(ip_dict={'video/axi_vdma': {'parameters': {'C_ENABLE_DEBUG_INFO_15': '1'}}})
    source = Source(bitfile, 'unused.json', capture_mode=capture_mode)
    source.start()
    assert trace == [('enable', False), ('baseline', 'before_first_credit_while_gate_disabled_dma_halted'),
                     'allocate', ('enable', True)]
    assert registers.writes == [] and source.integrity_baseline['invalid_frames'] == 1
    assert source.native.width == width
    assert source.native.height == height
    assert source.native.stride == width * 3


def test_credit_dma_halt_timeout_never_calls_vendor_close_or_frees_buffer():
    source, registers = credit_reader_fixture()
    source.control.command = 0
    source.control.enable = lambda enabled: None
    source._started = True
    registers.values[0x34] = 0
    buffer = source.native.buffer
    with pytest.raises(SourceError, match='halt timed out'):
        source.close()
    assert source.native.buffer is buffer
    assert source._started and not source.dma_shutdown_safe
    assert not source.hdmi.closed


def test_oneframe_dma_stop_waits_until_halted():
    from hdmi_capture.sources import OneFrameDMA
    registers = CreditDMARegisters()
    registers.values[0x34] = 0
    original = registers.read
    reads = 0
    def read(offset):
        nonlocal reads
        if offset == 0x34:
            reads += 1
            if reads >= 3:
                registers.values[offset] |= 1
        return original(offset)
    registers.read = read
    dma = OneFrameDMA(registers, SimpleNamespace(physical_address=0x100000, nbytes=640 * 480 * 3))
    dma.stop(.03)
    assert reads >= 3 and registers.read(0x34) & 1


def test_credit_close_checks_final_source_proof_then_halts_before_release_once():
    source, registers = credit_reader_fixture()
    source._started = True
    trace = []
    source.hdmi.frontend.stop = lambda: trace.append('frontend_stop')
    source.native.buffer.freebuffer = lambda: trace.append('free')
    source.control.enable = lambda enabled: trace.append(('enable', enabled))
    source._stage = lambda name, details=None: trace.append(name)
    count = 100
    baseline = source.control.snapshot()
    def snapshot():
        nonlocal count
        count += 1
        return dict(baseline, native_vsync_edges=count)
    source.control.snapshot = snapshot
    source.close()
    assert source.final_accounting['passed']
    assert source.final_accounting['native_edges_end'] - source.final_accounting['native_edges_begin'] >= 2
    assert trace.index('dma_stop_status_after') < trace.index('frontend_stop') < trace.index('free')
    assert source.native is None and source.dma_shutdown_safe
    source.close()
    assert trace.count('free') == 1


@pytest.mark.parametrize('mode,native_hz', [('vga', 60), ('vga', 59.94), ('1080p30', 30)])
@pytest.mark.parametrize('phase', [0, .49, .99])
@pytest.mark.parametrize('stopped', [False, True])
def test_credit_close_observes_slow_input_and_rejects_stopped_source(
        monkeypatch, mode, native_hz, phase, stopped):
    import math
    from hdmi_capture import sources as module
    source, _ = credit_reader_fixture(mode)
    source._started = True
    clock = [phase / native_hz]
    monkeypatch.setattr(module.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(module.time, 'sleep', lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    baseline = source.control.snapshot()
    source.control.snapshot = lambda: dict(baseline, native_vsync_edges=
        100 if stopped else 100 + math.floor(clock[0] * native_hz))
    trace = []
    source.control.enable = lambda enabled: setattr(source.control, 'command', int(enabled))
    source.native.buffer.freebuffer = lambda: trace.append('free')
    source.hdmi.frontend.stop = lambda: trace.append('frontend_stop')
    source._stage = lambda name, details=None: trace.append(name)

    if stopped:
        with pytest.raises(SourceError, match='Native source stopped'):
            source.close()
        assert source.final_accounting is None
    else:
        source.close()
        assert source.final_accounting['passed']
        assert source.final_accounting['native_edges_end'] - source.final_accounting['native_edges_begin'] >= 2
        assert source.final_accounting['interval_seconds'] > 2 / native_hz
        assert clock[0] - phase / native_hz >= source.final_accounting['interval_seconds']
    assert trace.index('dma_stop_status_after') < trace.index('frontend_stop') < trace.index('free')
    assert source.native is None and source.dma_shutdown_safe


@pytest.mark.parametrize('declared,s2mm,combined,accepted', [
    (None, '0', '0', False),
    ('tuser', '0', '0', False),
    ('free_run', '2', '1', False),
    ('free_run', '0', '1', True),
    ('free_run', '0', '0', True),
])
def test_credit_fsync_artifact_guard_before_programming(tmp_path, declared, s2mm, combined, accepted):
    import hashlib
    import json
    import xml.etree.ElementTree as ET
    from hdmi_capture.sources import verify_litex_artifacts
    bitfile, manifest = make_litex_artifacts(tmp_path)
    hwh = bitfile.with_suffix('.hwh')
    root = ET.parse(hwh).getroot()
    dma = ET.SubElement(root, 'MODULE', FULLNAME='/video/axi_vdma')
    parameters = ET.SubElement(dma, 'PARAMETERS')
    for name, value in [('C_USE_S2MM_FSYNC', s2mm), ('C_USE_FSYNC', combined),
                        ('C_ENABLE_DEBUG_INFO_15', '1')]:
        ET.SubElement(parameters, 'PARAMETER', NAME=name, VALUE=value)
    hwh.write_bytes(ET.tostring(root))
    record = json.loads(manifest.read_text())
    record.update(capture_interface='single_credit_parked_v1', vdma_fsync_mode=declared,
                  hwh_sha256=hashlib.sha256(hwh.read_bytes()).hexdigest())
    manifest.write_text(json.dumps(record))
    if accepted:
        assert verify_litex_artifacts(bitfile, manifest)['vdma_fsync_mode'] == 'free_run'
    else:
        with pytest.raises(SourceError, match='free-run|C_USE_'):
            verify_litex_artifacts(bitfile, manifest)


def test_credit_cleanup_retains_first_fault_snapshot_after_safe_release():
    source, _ = credit_reader_fixture()
    source.control.state['credit_failed'] = True
    source.control.snapshot = lambda: dict(source.integrity_baseline, invalid_frames=2)
    source.control.enable = lambda enabled: setattr(source.control, 'command', int(enabled))
    source.native.buffer.freebuffer = lambda: None
    with pytest.raises(SourceError):
        source._healthy()
    first = dict(source.integrity_failure)
    with pytest.raises(SourceError):
        source.close()
    assert source.integrity_failure['snapshot'] == first['snapshot']
    assert source.integrity_failure['snapshot']['invalid_frames'] == 2
    assert source.integrity_failure['error'] == first['error']
    assert 'final_accounting_error' in source.integrity_failure
    assert source.native is None and source.dma_shutdown_safe


@pytest.mark.parametrize('phase', ['idle', 'armed', 'complete', 'release', 'cleanup', 'timeout'])
def test_credit_input_clock_loss_never_reads_native_vtc(phase):
    source, registers = credit_reader_fixture()
    freed = []
    write = registers.write
    def stop_capable_write(offset, value):
        write(offset, value)
        if offset == 0x30 and not value & 1:
            registers.values[0x34] |= 1
    registers.write = stop_capable_write
    source.control.enable = lambda enabled: setattr(source.control, 'command', int(enabled))
    source.native.buffer.freebuffer = lambda: freed.append(registers.read(0x34) & 1)

    class ClocklessFrontend:
        @property
        def mode(self):
            raise AssertionError('VTC register access after input clock loss')

        def stop(self):
            pass  # PYNQ 3.0.1 HDMIInFrontend.stop is empty.

    def lose_clock(fault=True):
        source.hdmi.frontend = ClocklessFrontend()
        source.control.state.update(credit_failed=fault, source_sequence_fault=fault)

    async def run():
        if phase in ('release', 'cleanup'):
            sample = await source.read()
            lose_clock()
            if phase == 'release':
                with pytest.raises(SourceError, match='source-sequence fault'):
                    sample.close()
                assert source.leased and source.control.state['credit_done']
        else:
            if phase == 'idle':
                lose_clock()
            elif phase == 'timeout':
                lose_clock(fault=False)
                def request_without_input():
                    source.control.command ^= 2
                    source.control.state['credit_busy'] = True
                source.control.request = request_without_input
            elif phase == 'armed':
                original = source.native.arm
                def arm():
                    original()
                    lose_clock()
                source.native.arm = arm
            else:
                original = source.control.request
                def request():
                    original()
                    lose_clock()
                source.control.request = request
            with pytest.raises(SourceError, match='timed out' if phase == 'timeout' else 'source-sequence fault'):
                await source.read()
            assert not source.leased and source.native.buffer.invalidations == 0
        source._started = True
        with pytest.raises(SourceError, match='Native source stopped' if phase == 'timeout' else 'source-sequence fault'):
            source.close()
        assert source.native is None and source.dma_shutdown_safe
        assert not registers.read(0x30) & 1 and registers.read(0x34) & 1
        assert source.control.command & 1 == 0 and freed == [1]

    asyncio.run(run())
