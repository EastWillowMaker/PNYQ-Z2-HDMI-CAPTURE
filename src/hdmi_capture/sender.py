"""Bounded single-client RGB TCP sender; acquisition never awaits the network."""

import argparse
import asyncio
from contextlib import suppress
import json
import math
from pathlib import Path
import signal
import sys
import time
import uuid

from .modes import CAPTURE_MODES, get_mode
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
                             source_errors=0, source_cleanup_errors=0, network_errors=0)
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
        capture_mode = getattr(self.source, "capture_mode_name", None)
        if capture_mode is not None:
            metadata["capture_mode"] = capture_mode
        if sample.extra_metadata is not None:
            metadata.update(sample.extra_metadata)
        return metadata

    def _failed_source_counters(self):
        if not isinstance(self.source, LiteXCreditSource):
            return
        # Zero overruns was conditional on a clean source monitor. A failed
        # session cannot infer physical loss counts from the previous good frame.
        self.counters["source_overruns"] = None
        baseline = self.source.integrity_baseline or {}
        current = self.source.integrity_previous or {}
        initial, invalid = baseline.get("invalid_frames"), current.get("invalid_frames")
        self.counters["source_invalid_frames"] = (
            invalid-initial if type(initial) is int and type(invalid) is int
            and 0 <= initial <= invalid < 2**32 else None)

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
            self._failed_source_counters()
            self.ready = None
            if self._server is not None:
                self._server.close()
            if self._client is not None:
                self._abort_writer(self._client)
                self._client.close()
            self._ready_event.set()
            raise

    async def _watch_disconnect(self, reader, writer, client_task):
        try:
            # Clients send no requests. Bound ignored input while waiting for
            # EOF, independently of the next source frame or socket write.
            while await reader.read(1024):
                pass
        except (ConnectionError, OSError):
            self.counters["network_errors"] += 1
        self._abort_writer(writer)
        client_task.cancel()

    async def _serve_client(self, reader, writer):
        if self._client is not None:
            writer.close()
            await writer.wait_closed()
            return
        self._client = writer
        task = asyncio.current_task()
        self._client_tasks.add(task)
        disconnect = (asyncio.create_task(self._watch_disconnect(reader, writer, task))
                      if reader is not None else None)
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
            if disconnect is not None:
                disconnect.cancel()
                await asyncio.gather(disconnect, return_exceptions=True)
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
            try:
                self.source.close()
            except BaseException:
                self.counters["source_cleanup_errors"] += 1
                raise
            finally:
                if self.counters["source_errors"] or self.counters["source_cleanup_errors"]:
                    self._failed_source_counters()
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
            try:
                self.source.close()
            except BaseException:
                self.counters["source_cleanup_errors"] += 1
                raise
            finally:
                if self.counters["source_errors"] or self.counters["source_cleanup_errors"]:
                    self._failed_source_counters()


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
    if argv and argv[0] == "prepare":
        return prepare_main(argv[1:])
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, choices=("pynq", "synthetic", "litex", "litex-credit"))
    parser.add_argument("--mode", choices=tuple(CAPTURE_MODES), default="vga",
                        help="Expected LiteX input timing profile (default: vga)")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=9020)
    parser.add_argument("--fps", type=float, default=1)
    parser.add_argument("--input-fps", type=float,
                        help="Expected hardware refresh or synthetic input rate")
    parser.add_argument("--width", type=int, help="Synthetic width or expected hardware width")
    parser.add_argument("--height", type=int, help="Synthetic height or expected hardware height")
    parser.add_argument("--bitfile", default="base.bit")
    parser.add_argument("--manifest", help="Required build-manifest.json for the LiteX source")
    parser.add_argument("--prepared-receipt", help="Attach a prepared litex-credit receiver without reloading")
    parser.add_argument("--wait-ready-file", help="Wait for a new source-ready marker before prepared attach")
    parser.add_argument("--ready-timeout", type=float,
                        help="Bound source-ready wait to (0, 900] seconds (default: 120)")
    parser.add_argument("--read-timeout", type=float, default=3)
    parser.add_argument("--send-timeout", type=float, default=5)
    parser.add_argument("--duration", type=float)
    parser.add_argument("--startup-diagnostics", action="store_true",
                        help="Emit JSON startup and DMA cleanup stages to stderr")
    args = parser.parse_args(argv)
    if args.prepared_receipt is not None and args.source != "litex-credit":
        parser.error("--prepared-receipt requires --source litex-credit")
    if args.wait_ready_file is not None and (args.source != "litex-credit" or args.prepared_receipt is None):
        parser.error("--wait-ready-file requires litex-credit and --prepared-receipt")
    if args.ready_timeout is not None and args.wait_ready_file is None:
        parser.error("--ready-timeout requires --wait-ready-file")
    if args.ready_timeout is not None and (not math.isfinite(args.ready_timeout) or
                                           not 0 < args.ready_timeout <= 900):
        parser.error("ready timeout must be finite and in (0, 900]")
    if args.duration is not None and (not math.isfinite(args.duration) or args.duration <= 0):
        parser.error("duration must be finite and positive")
    mode = get_mode(args.mode)
    if args.source in ("pynq", "litex", "litex-credit"):
        if args.source == "pynq" and mode.name != "vga":
            parser.error("The baseline PYNQ source supports only --mode vga")
        if ((args.width is not None and args.width != mode.width) or
                (args.height is not None and args.height != mode.height)):
            parser.error(f"Hardware dimensions must match --mode {mode.name}")
        if (args.input_fps is not None and
                not math.isclose(args.input_fps, mode.refresh_hz, rel_tol=0, abs_tol=0.01)):
            parser.error(f"--input-fps must match the nominal --mode {mode.name} refresh")
        def progress(stage):
            details = stage if isinstance(stage, dict) else dict(stage=stage)
            cleanup = details["stage"].startswith(("dma_stop", "pool_free"))
            print(json.dumps(dict(event="source_cleanup" if cleanup else "source_startup",
                                  timestamp_ns=time.monotonic_ns(), **details)),
                  file=sys.stderr, flush=True)
        if args.source in ("litex", "litex-credit"):
            if args.manifest is None or args.bitfile == "base.bit":
                parser.error("LiteX source requires explicit --bitfile and --manifest")
            options = dict(capture_mode=mode.name,
                           progress=progress if args.startup_diagnostics else None)
            if args.source == "litex-credit":
                options.update(capture_fps=args.fps, timeout=args.read_timeout)
                if args.prepared_receipt is not None:
                    options["prepared_receipt"] = args.prepared_receipt
            if args.wait_ready_file is not None:
                from .prepared import wait_ready_file
                timeout = 120 if args.ready_timeout is None else args.ready_timeout
                print(json.dumps(dict(event="waiting_for_source", ready_file=args.wait_ready_file,
                                      timeout_seconds=timeout)), file=sys.stderr, flush=True)
                wait_ready_file(args.wait_ready_file, timeout)
            source_class = LiteXCreditSource if args.source == "litex-credit" else LiteXSource
            source = source_class(args.bitfile, args.manifest, **options)
        else:
            source = PynqSource(args.bitfile,
                                progress=progress if args.startup_diagnostics else None)
    else:
        if mode.name != "vga":
            parser.error("--mode applies only to hardware sources; set synthetic dimensions directly")
        source = SyntheticSource(640 if args.width is None else args.width,
                                 480 if args.height is None else args.height,
                                 60 if args.input_fps is None else args.input_fps)
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


def prepare_main(argv):
    from .prepared import prepare
    parser = argparse.ArgumentParser(description="Prepare the credit receiver before starting HDMI input")
    parser.add_argument("--bitfile", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--mode", choices=tuple(CAPTURE_MODES), default="vga")
    parser.add_argument("--after-reset", action="store_true",
                        help="Assert board or PL reset and no active DMA; does not reset hardware")
    args = parser.parse_args(argv)
    source = LiteXCreditSource(args.bitfile, args.manifest, capture_mode=args.mode)
    receipt = prepare(source, args.receipt, after_reset=args.after_reset)
    print(json.dumps(dict(event="receiver_prepared", capture_mode=args.mode,
                          receipt=str(Path(args.receipt).resolve()),
                          preparation=receipt["preparation"], input_mode_verified=False)), flush=True)


def control_main(argv):
    parser = argparse.ArgumentParser(description="Attach to the loaded LiteX capture gate")
    parser.add_argument("--bitfile", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--mode", choices=tuple(CAPTURE_MODES), default="vga")
    parser.add_argument("--enable", type=int, choices=(0, 1))
    args = parser.parse_args(argv)
    source = LiteXSource(args.bitfile, args.manifest, capture_mode=args.mode)
    source.load_overlay(download=False)
    if args.enable is not None:
        source.control.enable(bool(args.enable))
    print(json.dumps(source.control.snapshot(sample_point="standalone_sequential_gpio_reads")), flush=True)


if __name__ == "__main__":
    main()
