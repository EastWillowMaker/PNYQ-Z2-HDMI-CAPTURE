import asyncio
import socket

import pytest

from hdmi_capture.protocol import read_frame
from hdmi_capture.sender import Sender
from hdmi_capture.sources import SyntheticSource


def test_bounded_ready_slot_and_sampling():
    async def run():
        source = SyntheticSource(20, 10, input_fps=200)
        sender = Sender(source, fps=100)
        await sender.start("127.0.0.1", 0)
        await asyncio.sleep(0.12)
        assert sender.counters["acquired"] >= 10
        assert sender.counters["intentional_sampling_drops"] > 0
        assert sender.counters["network_backpressure_drops"] > 0
        assert sender.ready.metadata["frame_id"] > 1
        assert not sender.ready.rgb.flags.writeable
        assert sender.ready.metadata["source_origin"] == "synthetic"
        assert sender.ready.metadata["source_quantization_range"] == "full"
        await sender.close()
    asyncio.run(run())


def test_actual_socket_reconnect_fresh_ids_and_single_client():
    async def run():
        sender = Sender(SyntheticSource(20, 10, 100), fps=50)
        address = await sender.start("127.0.0.1", 0)
        def connect():
            sock = socket.create_connection(address, timeout=1)
            return sock
        first = await asyncio.to_thread(connect)
        frame1 = await asyncio.to_thread(read_frame, first)
        second = await asyncio.to_thread(connect)
        assert await asyncio.to_thread(second.recv, 1) == b""
        second.close()
        first.close()
        for _ in range(100):
            if sender._client is None:
                break
            await asyncio.sleep(0.01)
        assert sender._client is None
        third = await asyncio.to_thread(connect)
        frame2 = await asyncio.to_thread(read_frame, third)
        third.close()
        assert frame2.metadata["frame_id"] > frame1.metadata["frame_id"]
        assert frame2.metadata["session_id"] == frame1.metadata["session_id"]
        assert frame2.metadata["source_sequence"] > frame1.metadata["source_sequence"]
        await sender.close()
    asyncio.run(run())


@pytest.mark.parametrize("peer_data", [b"", b"unsupported-request"])
def test_disconnected_client_releases_slot_while_source_is_waiting(peer_data):
    class PausedSource(SyntheticSource):
        def __init__(self):
            super().__init__(20, 10, 100)
            self.first_frame = asyncio.Event()
            self.waiting = asyncio.Event()
            self.resume = asyncio.Event()

        async def read(self):
            await self.first_frame.wait()
            if self.sequence:
                self.waiting.set()
                await self.resume.wait()
            return await super().read()

    async def run():
        source = PausedSource()
        sender = Sender(source, fps=100)
        address = await sender.start("127.0.0.1", 0)
        first = await asyncio.to_thread(socket.create_connection, address, 1)
        second = None
        try:
            for _ in range(100):
                if sender._client is not None:
                    break
                await asyncio.sleep(0.005)
            assert sender._client is not None
            source.first_frame.set()
            frame1 = await asyncio.to_thread(read_frame, first)
            await source.waiting.wait()
            if peer_data:
                first.sendall(peer_data)
            first.close()
            for _ in range(100):
                if sender._client is None:
                    break
                await asyncio.sleep(0.005)
            assert sender._client is None
            assert not sender._closed
            assert not sender._capture_task.done()
            second = await asyncio.to_thread(socket.create_connection, address, 1)
            source.resume.set()
            frame2 = await asyncio.to_thread(read_frame, second)
            assert frame2.metadata["frame_id"] > frame1.metadata["frame_id"]
            assert frame2.metadata["session_id"] == frame1.metadata["session_id"]
            assert sender.counters["network_errors"] == 0
        finally:
            first.close()
            if second is not None:
                second.close()
            await sender.close()
        assert not sender._client_tasks

    asyncio.run(run())


def test_slow_network_keeps_acquiring_and_sending_copy_stable():
    class SlowWriter:
        def __init__(self):
            self.started = asyncio.Event()
            self.finish = asyncio.Event()
            self.wire = None
        def write(self, wire):
            self.wire = wire
            self.started.set()
        async def drain(self):
            await self.finish.wait()
        def close(self):
            self.finish.set()
        async def wait_closed(self):
            pass
    async def run():
        sender = Sender(SyntheticSource(20, 10, 100), fps=100)
        await sender.start("127.0.0.1", 0)
        writer = SlowWriter()
        client = asyncio.create_task(sender._serve_client(None, writer))
        await writer.started.wait()
        sending = writer.wire
        acquired = sender.counters["acquired"]
        await asyncio.sleep(0.08)
        assert sender.counters["acquired"] > acquired + 2
        assert sender.counters["network_backpressure_drops"] > 0
        assert writer.wire == sending
        assert sender.ready is not None
        await sender.close()
        with pytest.raises(asyncio.CancelledError):
            await client
    asyncio.run(run())


def test_source_timeout_propagates_and_cleans_up():
    class NoSignal(SyntheticSource):
        async def read(self):
            await asyncio.Event().wait()
        def close(self):
            self.closed = True
    async def run():
        source = NoSignal(20, 10)
        sender = Sender(source, read_timeout=0.01)
        await sender.start("127.0.0.1", 0)
        await asyncio.sleep(0.03)
        with pytest.raises(asyncio.TimeoutError):
            await sender.close()
        assert source.closed
        assert sender.counters["source_errors"] == 1
    asyncio.run(run())


@pytest.mark.parametrize("fps", [0, -1, float("nan"), float("inf"), 241])
def test_sampling_rejects_invalid_rates(fps):
    with pytest.raises(ValueError):
        Sender(SyntheticSource(), fps=fps)


def test_hdmi_startup_discards_and_releases_before_copy():
    from hdmi_capture.sources import Sample
    import numpy as np
    class OwnedSource(SyntheticSource):
        origin = "hdmi"
        baseline_only = True
        color_format = "unknown"
        quantization_range = "unknown"
        def __init__(self):
            super().__init__(20, 10, 100)
            self.released = []
        async def read(self):
            original = await super().read()
            seq = original.sequence
            pixels = original.pixels
            def release():
                self.released.append(seq)
                pixels[:] = 0
            return Sample(pixels, original.timestamp_ns, release=release)
    async def run():
        source = OwnedSource()
        sender = Sender(source, fps=100)
        await sender.start("127.0.0.1", 0)
        await asyncio.sleep(0.06)
        assert sender.counters["startup_discarded"] == 1
        assert len(source.released) == sender.counters["acquired"]
        assert sender.ready.metadata["source_sequence"] is None
        assert sender.ready.metadata["frame_id"] > 1
        assert sender.ready.rgb[0, 0].tolist() == [255, 0, 0]
        assert sender.ready.metadata["baseline_only"]
        assert sender.ready.metadata["source_quantization_range"] == "unknown"
        await sender.close()
    asyncio.run(run())


def test_send_timeout_disconnects_while_capture_continues():
    class StalledWriter:
        def write(self, wire):
            pass
        async def drain(self):
            await asyncio.Event().wait()
        def close(self):
            self.closed = True
        async def wait_closed(self):
            pass
    async def run():
        sender = Sender(SyntheticSource(20, 10, 100), fps=100, send_timeout=0.01)
        await sender.start("127.0.0.1", 0)
        writer = StalledWriter()
        await sender._serve_client(None, writer)
        assert writer.closed
        assert sender._client is None
        assert sender.counters["network_errors"] == 1
        before = sender.counters["acquired"]
        await asyncio.sleep(0.04)
        assert sender.counters["acquired"] > before
        await sender.close()
    asyncio.run(run())


def test_real_stalled_clients_abort_buffers_and_shutdown_promptly():
    async def run():
        sender = Sender(SyntheticSource(1920, 1080, 30), fps=30, send_timeout=0.05)
        address = await sender.start("127.0.0.1", 0)
        def connect():
            sock = socket.socket()
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024)
            sock.settimeout(1)
            sock.connect(address)
            return sock
        try:
            for _ in range(3):
                sock = await asyncio.to_thread(connect)
                for _ in range(100):
                    writer = sender._client
                    if writer is not None:
                        break
                    await asyncio.sleep(0.001)
                assert writer is not None
                for _ in range(200):
                    if sender._client is None:
                        break
                    await asyncio.sleep(0.001)
                assert sender._client is None
                assert writer.transport.is_closing()
                assert writer.transport.get_write_buffer_size() == 0
                sock.close()
            # Shutdown while another stalled connection is still live.
            sock = await asyncio.to_thread(connect)
            await asyncio.sleep(0.02)
            await asyncio.wait_for(sender.close(), 0.3)
            sock.close()
        finally:
            await sender.close()
        assert sender.counters["network_errors"] >= 3
    asyncio.run(run())


def test_cli_stop_failure_holds_source_instead_of_normal_exit(monkeypatch):
    import hdmi_capture.sender as module
    from types import SimpleNamespace
    class EnteredHold(BaseException):
        pass
    class UnsafeSource(SyntheticSource):
        origin = "hdmi"
        baseline_only = True
        dma_shutdown_safe = True
        _pool = SimpleNamespace(owned={1: object()})
        def start(self):
            self.dma_shutdown_safe = False
            super().start()
        def close(self):
            raise RuntimeError("Native DMA stop failed")
    source = UnsafeSource(20, 10, 100)
    monkeypatch.setattr(module, "PynqSource", lambda *args, **kwargs: source)
    def hold(held_source, error):
        assert held_source is source
        assert len(held_source._pool.owned) == 1
        assert str(error) == "Native DMA stop failed"
        raise EnteredHold()
    with pytest.raises(EnteredHold):
        module.main(["--source", "pynq", "--host", "127.0.0.1",
                     "--port", "0", "--duration", "0.02"], unsafe_hold=hold)
    assert source._pool.owned


def test_cli_safe_failure_does_not_hold(monkeypatch):
    import hdmi_capture.sender as module
    from types import SimpleNamespace
    source = SimpleNamespace(dma_shutdown_safe=True)
    monkeypatch.setattr(module, "PynqSource", lambda *args, **kwargs: source)
    def failed_run(coroutine):
        coroutine.close()
        raise RuntimeError("Safe non-DMA failure")
    monkeypatch.setattr(module.asyncio, "run", failed_run)
    def hold(source, error):
        pytest.fail("Safe failure must not enter DMA hold")
    with pytest.raises(RuntimeError, match="Safe non-DMA failure"):
        module.main(["--source", "pynq"], unsafe_hold=hold)


def test_integrity_failure_never_becomes_ready_and_reports_baseline(capsys):
    import json
    import numpy as np
    from types import SimpleNamespace
    from hdmi_capture.sources import LiteXSource, SourceError
    class Buffer(np.ndarray):
        def freebuffer(self):
            self.released += 1
    pixels = np.zeros((480, 640, 3), dtype=np.uint8).view(Buffer)
    pixels.released = 0
    mode = SimpleNamespace(width=640, height=480, bits_per_pixel=24)
    count = dict(invalid_frames=0, frontend_overflow_episodes=0, native_vsync_edges=10)
    class HDMI:
        frontend = SimpleNamespace(mode=mode)
        def configure(self, pixel_format):
            pass
        def start(self):
            pass
        def close(self):
            self.closed = True
        async def readframe_async(self):
            count["invalid_frames"] += 1
            return pixels
    hdmi = HDMI()
    hdmi.mode = mode
    class Control:
        def enable(self, enabled):
            pass
        def snapshot(self, sample_point=None):
            return dict(count, enabled=False, selected_frames=0, sample_point=sample_point)
    class Source(LiteXSource):
        def load_overlay(self, download=True):
            self.hdmi, self.pixel_format = hdmi, "BGR"
            self.control = Control()
            self.manifest = dict(bitstream_sha256="f" * 64, capture_enable_reset=0)
    async def run():
        source = Source("unused.bit", "unused.json")
        sender = Sender(source)
        with pytest.raises(SourceError, match="integrity counter changed"):
            await sender.run("127.0.0.1", 0, duration=0.1)
        assert sender.ready is None and sender.counters["transport_enqueued"] == 0
        assert pixels.released == 1 and source.dma_shutdown_safe
        assert hdmi.closed
    asyncio.run(run())
    report = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert report["source_integrity"]["startup"]["invalid_frames"] == 0
    assert report["source_integrity"]["failure"]["snapshot"]["invalid_frames"] == 1
    assert report["dma_shutdown_safe"]


def test_paced_credit_source_keeps_first_and_all_acquisitions():
    import numpy as np
    from hdmi_capture.sources import Sample
    class Source(SyntheticSource):
        origin = 'hdmi'
        paces_capture = True
        async def read(self):
            await asyncio.sleep(.002)
            self.sequence += 1
            return Sample(np.zeros((10, 20, 3), np.uint8), self.sequence,
                          self.sequence, extra_metadata=dict(source_accounting=dict(
                              source_intentional_sampling_total=29 * (self.sequence - 1))))
    async def run():
        source = Source(20, 10, 100)
        sender = Sender(source, fps=1)
        await sender.start('127.0.0.1', 0)
        await asyncio.sleep(.025)
        assert sender.counters['acquired'] >= 3
        assert sender.counters['startup_discarded'] == 0
        assert sender.counters['intentional_sampling_drops'] == 0
        assert sender.ready.metadata['counters']['source_skips'] == 29 * (sender.ready.metadata['acquisition_id'] - 1)
        assert sender.ready.metadata['counters']['source_overruns'] == 0
        assert sender.ready.metadata['counters']['source_invalid_frames'] == 0
        await sender.close()
    asyncio.run(run())


@pytest.mark.parametrize('mode_fault', [False, True])
def test_credit_failure_reports_observed_invalid_geometry(mode_fault):
    from types import SimpleNamespace
    from test_sources import credit_reader_fixture
    from hdmi_capture.sources import SourceError
    source, registers = credit_reader_fixture()
    source.control.snapshot = lambda: dict(source.integrity_baseline, invalid_frames=2)
    if mode_fault:
        source.hdmi.frontend.mode = SimpleNamespace(width=1280, height=720, bits_per_pixel=24)
    else:
        source.control.state['credit_failed'] = True
    sender = Sender(source)
    with pytest.raises(SourceError):
        asyncio.run(sender._capture())
    assert sender.counters['source_errors'] == 1
    assert sender.counters['source_invalid_frames'] == 1
    assert sender.counters['source_overruns'] is None
    assert source.integrity_failure['snapshot']['invalid_frames'] == 2
    assert registers.writes == [] and sender.ready is None


def test_credit_failure_does_not_reuse_stale_zero_when_counters_unavailable():
    from test_sources import credit_reader_fixture
    source, _ = credit_reader_fixture()
    def unavailable():
        raise OSError('GPIO is unavailable')
    source.control.snapshot = unavailable
    sender = Sender(source)
    sender.counters.update(source_invalid_frames=0, source_overruns=0)
    with pytest.raises(OSError):
        asyncio.run(sender._capture())
    assert sender.counters['source_invalid_frames'] is None
    assert sender.counters['source_overruns'] is None


def test_credit_cleanup_failure_reports_latest_diagnostic_without_hiding_acquisition_error():
    from test_sources import credit_reader_fixture
    from hdmi_capture.sources import SourceError
    source, _ = credit_reader_fixture()
    sender = Sender(source)
    sender.counters.update(source_errors=1, source_invalid_frames=1)
    def cleanup():
        source.integrity_previous = dict(source.integrity_baseline, invalid_frames=4)
        raise SourceError('Final source proof failed')
    source.close = cleanup
    with pytest.raises(SourceError):
        asyncio.run(sender.close())
    assert sender.counters['source_errors'] == 1
    assert sender.counters['source_cleanup_errors'] == 1
    assert sender.counters['source_invalid_frames'] == 3
    assert sender.counters['source_overruns'] is None
