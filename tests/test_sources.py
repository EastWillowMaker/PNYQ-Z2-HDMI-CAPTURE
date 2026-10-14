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


class Buffer(np.ndarray):
    def freebuffer(self):
        self.freed += 1
        self[:] = 0


class FakeHDMI:
    def __init__(self):
        self.mode = SimpleNamespace(width=640, height=480, bits_per_pixel=24)
        self.frontend = SimpleNamespace(mode=self.mode)
        self.buffer = np.zeros((480, 640, 3), dtype=np.uint8).view(Buffer)
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
    bitfile = tmp_path / "capture.bit"
    hwh = tmp_path / "capture.hwh"
    bitfile.write_bytes(b"synthetic-bitstream-fixture")
    hwh.write_text('<ROOT><MODULE FULLNAME="/video/hdmi_in/frontend/dvi2rgb_0">'
                   '<PARAMETERS><PARAMETER NAME="kClkRange" VALUE="5"/>'
                   '</PARAMETERS></MODULE><MODULE FULLNAME="/video/capture_control">'
                   '<PARAMETERS><PARAMETER NAME="C_DOUT_DEFAULT" VALUE="0x00000000"/>'
                   '</PARAMETERS></MODULE></ROOT>')
    manifest = tmp_path / "build-manifest.json"
    record = dict(schema_version=1, geometry=[640, 480], clock_hz=142857132,
                  capture_enable_reset=0,
                  pixel_clock_hz=25200000, supported_pixel_clocks_hz=[25175000, 25200000],
                  receiver_k_clk_range=5, edid_sha256="f" * 64,
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
    from hdmi_capture.sources import verify_litex_artifacts
    bitfile, manifest = make_litex_artifacts(tmp_path)
    assert verify_litex_artifacts(bitfile, manifest)["geometry"] == [640, 480]
    bitfile.write_bytes(b"modified")
    with pytest.raises(SourceError, match="hash mismatch"):
        verify_litex_artifacts(bitfile, manifest)


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
