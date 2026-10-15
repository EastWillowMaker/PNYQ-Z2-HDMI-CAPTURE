"""Bounded single-client RGB TCP sender; acquisition never awaits the network."""

import argparse
import asyncio
from contextlib import suppress
import json
import math
import signal
import sys
import time
import uuid

from .protocol import Frame, encode_frame
from .sources import LiteXCreditSource, LiteXSource, PynqSource, SyntheticSource


class Sender:
    def __init__(self, source, *, fps=1, read_timeout=3, send_timeout=5):
        if not math.isfinite(fps) or fps <= 0 or fps > 240:
            raise ValueError("fps must be finite and in (0, 240]")
        if any(not math.isfinite(x) or x <= 0 for x in (read_timeout, send_timeout)):
            raise ValueError("Timeouts must be finite and positive")
        self.source, self.fps = source, fps
        self.read_timeout, self.send_timeout = read_timeout, send_timeout
        self.session_id = str(uuid.uuid4())
        self.counters = dict(acquired=0, startup_discarded=0,
                             intentional_sampling_drops=0,
                             network_backpressure_drops=0,
                             client_discarded=0, transport_enqueued=0,
                             source_errors=0, network_errors=0)
        # PYNQ's driver does not provide reliable hardware sequence/error counts.
        self.counters.update(source_skips=None, source_overruns=None,
                             source_invalid_frames=None)
        self.ready = None
        self._ready_event = asyncio.Event()
        self._client = None
        self._client_tasks = set()
        self._capture_task = None
        self._server = None
        self._closed = False

    def _metadata(self, sample, acquisition_id):
        accounting = (sample.extra_metadata or {}).get("source_accounting")
        if accounting is not None:
            self.counters.update(source_skips=accounting["source_intentional_sampling_total"],
                                 source_overruns=0, source_invalid_frames=0)
        metadata = dict(width=self.source.width, height=self.source.height,
                    pixel_format="RGB888", stride=self.source.width * 3,
                    frame_id=acquisition_id, acquisition_id=acquisition_id,
                    session_id=self.session_id, source_sequence=sample.sequence,
                    timestamp_ns=sample.timestamp_ns,
                    timestamp_clock="board_monotonic" if self.source.origin == "hdmi"
                    else "sender_monotonic",
                    timestamp_sample_point="after_dma_read_complete" if
                    self.source.origin == "hdmi" else "after_pattern_generation",
                    flags=["baseline_only"] if self.source.baseline_only else
                    (["synthetic"] if self.source.origin == "synthetic" else ["litex_capture"]),
                    source_origin=self.source.origin,
                    source_color_format=self.source.color_format,
                    source_quantization_range=self.source.quantization_range,
                    baseline_only=self.source.baseline_only,
                    source_fps=None if self.source.origin == "hdmi" else self.source.input_fps,
                    source_progressive=None if self.source.origin == "hdmi" else True,
                    counters=dict(self.counters))
        if sample.extra_metadata is not None:
            metadata.update(sample.extra_metadata)
        return metadata

    async def _capture(self):
        next_sample = 0
        paced = getattr(self.source, "paces_capture", False)
        prime = self.source.origin == "hdmi" and not paced
        try:
            while True:
                sample = await asyncio.wait_for(self.source.read(), self.read_timeout)
                self.counters["acquired"] += 1
                acquisition_id = self.counters["acquired"]
                try:
                    if prime:
                        prime = False
                        self.counters["startup_discarded"] += 1
                        continue
                    now = time.monotonic()
                    if not paced and now < next_sample:
                        self.counters["intentional_sampling_drops"] += 1
                        continue
                    period = 1 / self.fps
                    next_sample = (now + period if next_sample == 0 else
                                   next_sample + (math.floor((now - next_sample) / period) + 1) * period)
                    if sample.pixels.shape != (self.source.height, self.source.width, 3):
                        raise ValueError("Source sample dimensions do not match configured mode")
                    frame = Frame(sample.copy_rgb(), self._metadata(sample, acquisition_id))
                    if self.ready is not None:
                        self.counters["network_backpressure_drops"] += 1
                    self.ready = frame
                    self._ready_event.set()
                finally:
                    sample.close()
                    # Yield on skipped frames too: PYNQ interrupts can be pre-signaled.
                    await asyncio.sleep(0)
        except asyncio.CancelledError:
            raise
        except BaseException:
            self.counters["source_errors"] += 1
            self.ready = None
            if self._server is not None:
                self._server.close()
            if self._client is not None:
                self._abort_writer(self._client)
                self._client.close()
            self._ready_event.set()
            raise

    async def _serve_client(self, reader, writer):
        if self._client is not None:
            writer.close()
            await writer.wait_closed()
            return
        self._client = writer
        task = asyncio.current_task()
        self._client_tasks.add(task)
        # Never present a preconnection ready frame as fresh acquisition.
        if self.ready is not None:
            self.counters["client_discarded"] += 1
            self.ready = None
            self._ready_event.clear()
        try:
            while not self._closed:
                await self._ready_event.wait()
                if self._capture_task.done():
                    self._capture_task.result()
                frame, self.ready = self.ready, None
                self._ready_event.clear()
                if frame is None:
                    continue
                # This local immutable frame is distinct from the ready slot.
                wire = encode_frame(frame.rgb, frame.metadata)
                writer.write(wire)
                await asyncio.wait_for(writer.drain(), self.send_timeout)
                self.counters["transport_enqueued"] += 1  # Not host acknowledgement.
        except (ConnectionError, OSError, asyncio.TimeoutError):
            self.counters["network_errors"] += 1
            self._abort_writer(writer)
        finally:
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), self.send_timeout)
            except (ConnectionError, OSError, asyncio.TimeoutError, asyncio.CancelledError):
                self._abort_writer(writer)
            if self._client is writer:
                self._client = None
            self._client_tasks.discard(task)

    @staticmethod
    def _abort_writer(writer):
        transport = getattr(writer, "transport", None)
        if transport is not None:
            transport.abort()

    async def start(self, host="0.0.0.0", port=9020):
        self.source.start()
        try:
            self._server = await asyncio.start_server(self._serve_client, host, port)
        except BaseException:
            self.source.close()
            raise
        self._capture_task = asyncio.create_task(self._capture())
        return self._server.sockets[0].getsockname()

    async def run(self, host="0.0.0.0", port=9020, duration=None):
        address = await self.start(host, port)
        print(json.dumps(dict(listening=address, source=self.source.origin,
                              session_id=self.session_id)), flush=True)
        try:
            if duration is None:
                await self._capture_task
            else:
                done, _ = await asyncio.wait([self._capture_task], timeout=duration)
                if done:
                    self._capture_task.result()
        finally:
            try:
                await self.close()
            finally:
                status = dict(session_id=self.session_id, counters=self.counters,
                              dma_shutdown_safe=getattr(self.source, "dma_shutdown_safe", None))
                if getattr(self.source, "integrity_baseline", None) is not None:
                    status["source_integrity"] = dict(
                        startup=self.source.integrity_baseline,
                        last=self.source.integrity_previous,
                        failure=self.source.integrity_failure)
                if getattr(self.source, "final_accounting", None) is not None:
                    status["final_source_accounting"] = self.source.final_accounting
                print(json.dumps(status), flush=True)

    async def close(self):
        if self._closed:
            return
        self._closed = True
        if self._server is not None:
            self._server.close()
        try:
            if self._capture_task is not None:
                self._capture_task.cancel()
                with suppress(asyncio.CancelledError):
                    await self._capture_task
        finally:
            if self._client is not None:
                self._abort_writer(self._client)
                self._client.close()
            tasks = list(self._client_tasks)
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            if self._server is not None:
                await self._server.wait_closed()
            self.ready = None
            self._ready_event.set()
            self.source.close()


def _hold_unsafe_dma(source, error, wait=None):
    """Retain source/BO references until an authorized external hardware reset.

    A CLI must not exit merely because native DMA stop failed: process teardown
    may free its XRT buffers while the DMA still writes. `wait` is a test seam;
    production holds with signal.pause(), without deadlines or hardware access.
    """
    def report(event):
        try:
            print(json.dumps(dict(event=event, error_type=type(error).__name__,
                                  error=str(error), dma_shutdown_safe=False,
                                  action="Keep process alive; reset board or verify PL/DMA reset before termination")),
                  file=sys.stderr, flush=True)
        except BaseException:
            # A failed diagnostic must not unwind and release live DMA memory.
            pass

    if wait is not None:
        report("fatal_dma_shutdown_unverified")
        while True:
            wait(source, error)
    # Only the standalone CLI installs these handlers; library close still raises.
    def keep_alive(signum, frame):
        report("dma_shutdown_hold_signal_ignored")
    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT):
        signal.signal(signum, keep_alive)
    report("fatal_dma_shutdown_unverified")
    while True:
        signal.pause()
        # `source` remains a strong local reference across every wait.
        if source.dma_shutdown_safe:
            # No reset is inferred from a software flag or an elapsed deadline.
            report("dma_shutdown_hold_requires_external_confirmation")


def main(argv=None, *, unsafe_hold=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "control":
        return control_main(argv[1:])
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, choices=("pynq", "synthetic", "litex", "litex-credit"))
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=9020)
    parser.add_argument("--fps", type=float, default=1)
    parser.add_argument("--input-fps", type=float, default=60)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--bitfile", default="base.bit")
    parser.add_argument("--manifest", help="Required build-manifest.json for the LiteX source")
    parser.add_argument("--read-timeout", type=float, default=3)
    parser.add_argument("--send-timeout", type=float, default=5)
    parser.add_argument("--duration", type=float)
    parser.add_argument("--startup-diagnostics", action="store_true",
                        help="Emit JSON startup and DMA cleanup stages to stderr")
    args = parser.parse_args(argv)
    if args.duration is not None and (not math.isfinite(args.duration) or args.duration <= 0):
        parser.error("duration must be finite and positive")
    if args.source in ("pynq", "litex", "litex-credit"):
        if (args.width, args.height, args.input_fps) != (640, 480, 60):
            parser.error("Hardware sources require the configured 640x480p60 contract")
        def progress(stage):
            details = stage if isinstance(stage, dict) else dict(stage=stage)
            cleanup = details["stage"].startswith(("dma_stop", "pool_free"))
            print(json.dumps(dict(event="source_cleanup" if cleanup else "source_startup",
                                  timestamp_ns=time.monotonic_ns(), **details)),
                  file=sys.stderr, flush=True)
        if args.source in ("litex", "litex-credit"):
            if args.manifest is None or args.bitfile == "base.bit":
                parser.error("LiteX source requires explicit --bitfile and --manifest")
            options = dict(progress=progress if args.startup_diagnostics else None)
            if args.source == "litex-credit":
                options.update(capture_fps=args.fps, timeout=args.read_timeout)
            source_class = LiteXCreditSource if args.source == "litex-credit" else LiteXSource
            source = source_class(args.bitfile, args.manifest, **options)
        else:
            source = PynqSource(args.bitfile,
                                progress=progress if args.startup_diagnostics else None)
    else:
        source = SyntheticSource(args.width, args.height, args.input_fps)
    sender = Sender(source, fps=args.fps, read_timeout=args.read_timeout,
                    send_timeout=args.send_timeout)
    previous_handlers = {}
    if args.source in ("pynq", "litex", "litex-credit"):
        def request_cleanup(signum, frame):
            raise KeyboardInterrupt()
        for signum in (signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT):
            previous_handlers[signum] = signal.signal(signum, request_cleanup)
    try:
        asyncio.run(sender.run(args.host, args.port, args.duration))
    except BaseException as error:
        if not getattr(source, "dma_shutdown_safe", True):
            _hold_unsafe_dma(source, error, wait=unsafe_hold)
        if isinstance(error, KeyboardInterrupt):
            return
        raise
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)


def control_main(argv):
    parser = argparse.ArgumentParser(description="Attach to the loaded LiteX capture gate")
    parser.add_argument("--bitfile", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--enable", type=int, choices=(0, 1))
    args = parser.parse_args(argv)
    source = LiteXSource(args.bitfile, args.manifest)
    source.load_overlay(download=False)
    if args.enable is not None:
        source.control.enable(bool(args.enable))
    print(json.dumps(source.control.snapshot(sample_point="standalone_sequential_gpio_reads")), flush=True)


if __name__ == "__main__":
    main()
