"""AXI4-Stream Video frame selection and geometry observation."""

from migen import If, Signal
from litex.gen import LiteXModule
from litex.soc.interconnect import stream


class LegacyVideoCapture(LiteXModule):
    """One clock domain, one beat elastic buffer, fixed 24-bit pixel geometry.

    Endpoint first/last map to AXIS TUSER[0]/TLAST: SOF/EOL, respectively.
    Counters wrap modulo 2**32 and clear on synchronous sys reset.
    """

    def __init__(self, width=640, height=480):
        if not (1 <= width <= 65535 and 1 <= height <= 65535):
            raise ValueError("width and height must be in 1..65535")
        self.sink = stream.Endpoint([("data", 24)])
        self.source = stream.Endpoint([("data", 24)])
        self.enable = Signal(reset=1)
        self.active = Signal()
        self.frame_id = Signal(32)
        self.output_frame_id = Signal(32)
        names = ("observed_frames", "selected_frames", "dropped_frames",
                 "completed_frames", "valid_frames", "invalid_frames",
                 "orphan_pixels", "stall_cycles")
        for name in names:
            setattr(self, name, Signal(32, name=name))
        # Sticky errors: orphan=1, unexpected SOF=2, bad EOL=4.
        self.errors = Signal(3)
        selected = Signal()
        bad = Signal()
        x = Signal(max=max(2, width))
        y = Signal(max=max(2, height))
        next_id = Signal(32)
        choose = Signal()
        beat_x = Signal.like(x)
        beat_y = Signal.like(y)
        eol_error = Signal()
        end_frame = Signal()
        accepted = Signal()
        self._next_id = next_id
        self._choose = choose
        self._accepted = accepted
        self._eol_error = eol_error
        self._end_frame = end_frame
        self.comb += [
            self.sink.ready.eq(~self.source.valid | self.source.ready),
            accepted.eq(self.sink.valid & self.sink.ready),
            choose.eq(self.sink.first & self.enable |
                      ~self.sink.first & self.active & selected),
            beat_x.eq(x), beat_y.eq(y),
            If(self.sink.first, beat_x.eq(0), beat_y.eq(0)),
            eol_error.eq(self.sink.last != (beat_x == width - 1)),
            end_frame.eq((beat_x == width - 1) & (beat_y == height - 1)),
        ]
        self.sync += [
            If(self.source.valid & ~self.source.ready,
               self.stall_cycles.eq(self.stall_cycles + 1)),
            If(self.sink.ready,
               self.source.valid.eq(self.sink.valid & choose)),
            If(accepted,
               If(choose,
                  self.source.data.eq(self.sink.data),
                  self.source.first.eq(self.sink.first),
                  self.source.last.eq(self.sink.last),
                  self.output_frame_id.eq(self.frame_id),
                  If(self.sink.first, self.output_frame_id.eq(next_id))),
               If(self.sink.first,
                  self.frame_id.eq(next_id), next_id.eq(next_id + 1),
                  self.observed_frames.eq(self.observed_frames + 1),
                  selected.eq(self.enable), self.active.eq(1), bad.eq(0),
                  If(self.enable,
                     self.selected_frames.eq(self.selected_frames + 1)
                  ).Else(self.dropped_frames.eq(self.dropped_frames + 1)),
                  If(self.active,
                     self.errors.eq(self.errors | 2),
                     If(~bad, self.invalid_frames.eq(self.invalid_frames + 1)))),
               If(self.active | self.sink.first,
                  If(eol_error,
                     self.errors.eq(self.errors | 4 |
                                    (self.sink.first & self.active) * 2),
                     bad.eq(1),
                     If(self.sink.first | ~bad,
                        self.invalid_frames.eq(self.invalid_frames + 1 +
                                               (self.sink.first & self.active & ~bad)))),
                  If(beat_x == width - 1,
                     x.eq(0), y.eq(beat_y + 1)
                  ).Else(x.eq(beat_x + 1), y.eq(beat_y)),
                  If(end_frame,
                     self.active.eq(0),
                     self.completed_frames.eq(self.completed_frames + 1),
                     If(~eol_error & (self.sink.first | ~bad),
                        self.valid_frames.eq(self.valid_frames + 1)))
               ).Else(
                   self.errors.eq(self.errors | 1),
                   If(~bad, self.invalid_frames.eq(self.invalid_frames + 1)),
                   bad.eq(1),
                   self.orphan_pixels.eq(self.orphan_pixels + 1))),
        ]

    def ports(self):
        """Explicit RTL ports; clock/reset are added by Migen conversion."""
        return {self.sink.data, self.sink.valid, self.sink.ready,
                self.sink.first, self.sink.last, self.source.data,
                self.source.valid, self.source.ready, self.source.first,
                self.source.last, self.enable, self.active, self.frame_id,
                self.output_frame_id, self.errors, self.observed_frames,
                self.selected_frames, self.dropped_frames,
                self.completed_frames, self.valid_frames,
                self.invalid_frames, self.orphan_pixels, self.stall_cycles}


class VideoCapture(LiteXModule):
    """Single-credit capture with immutable identity until software release.

    GPIO ABI single_credit_parked_v1. DONE requires the final selected AXIS
    transfer AND its following unselected SOF, never DDR completion.
    Software additionally requires VDMA frame-count halt.
    All control and native-count inputs must already be in the sys clock domain.
    """

    def __init__(self, width=640, height=480):
        self.submodules.observer = observer = LegacyVideoCapture(width, height)
        self.sink, self.source = observer.sink, observer.source
        for name in ("active", "frame_id", "output_frame_id", "observed_frames",
                     "selected_frames", "dropped_frames", "completed_frames",
                     "valid_frames", "invalid_frames", "orphan_pixels",
                     "stall_cycles", "errors"):
            setattr(self, name, getattr(observer, name))
        self.enable = Signal()
        self.request_toggle = Signal()
        self.ack_toggle = Signal()
        self.native_vsync_edges = Signal(32)
        self.receiver_reset = Signal()
        self.busy = Signal()
        self.done = Signal()
        self.failed = Signal()
        self.request_seen = Signal()
        self.ack_seen = Signal()
        self.source_sequence_fault = Signal()
        self.native_armed = Signal()
        self.credit_status = Signal(32)
        self.selected_source_id = Signal(32)
        self.selected_native_vsync_id = Signal(32)
        self.selected_completed = Signal(32)
        self.command_errors = Signal(32)
        self.source_sequence_faults = Signal(32)
        waiting = Signal()
        capturing = Signal()
        output_end = Signal()
        output_end_pending = Signal()
        tail_transfer = Signal()
        previous_native = Signal(32)
        native_delta = Signal(32)
        request_edge = Signal()
        ack_edge = Signal()
        command_fault = Signal()
        source_fault = Signal()
        select_sof = Signal()
        selected_bad = Signal()
        self.comb += [
            request_edge.eq(self.request_toggle != self.request_seen),
            ack_edge.eq(self.ack_toggle != self.ack_seen),
            command_fault.eq(request_edge & (~self.enable | self.busy | self.failed) |
                             ack_edge & (~self.busy | ~self.done | self.failed)),
            native_delta.eq(self.native_vsync_edges - previous_native),
            source_fault.eq((self.enable | self.busy) & (
                self.receiver_reset |
                (observer._accepted & ~observer.active & ~self.sink.first) |
                (self.native_armed & (native_delta > 1)) |
                (self.native_armed & observer._accepted & self.sink.first & (native_delta != 1)))),
            observer.enable.eq(waiting & self.enable & ~self.failed &
                               ~command_fault & ~source_fault),
            select_sof.eq(observer._accepted & self.sink.first & observer.enable),
            selected_bad.eq(observer._accepted & (
                (observer._choose & observer._eol_error) |
                (capturing & self.sink.first))),
            tail_transfer.eq(self.source.valid & self.source.ready & output_end),
            self.credit_status.eq(self.busy | (self.done << 1) | (self.failed << 2) |
                                  (self.request_seen << 3) | (self.ack_seen << 4) |
                                  (self.source_sequence_fault << 5) |
                                  (self.native_armed << 6)),
        ]
        self.sync += [
            If(request_edge, self.request_seen.eq(self.request_toggle)),
            If(ack_edge, self.ack_seen.eq(self.ack_toggle)),
            If(request_edge & ~command_fault & ~source_fault,
               self.busy.eq(1), waiting.eq(1), self.done.eq(0)),
            If(ack_edge & ~command_fault & ~source_fault,
               self.busy.eq(0), self.done.eq(0), waiting.eq(0)),
            If(observer.sink.ready,
               output_end.eq(observer.sink.valid & observer._choose & observer._end_frame)),
            If(select_sof,
               self.selected_source_id.eq(observer._next_id),
               self.selected_native_vsync_id.eq(self.native_vsync_edges),
               waiting.eq(0), capturing.eq(~observer._end_frame)),
            If(observer._accepted & capturing & observer._end_frame, capturing.eq(0)),
            If(tail_transfer, output_end_pending.eq(1)),
            If(self.busy & ~self.done & ~capturing &
               observer._accepted & self.sink.first &
               (output_end_pending | tail_transfer) &
               ~self.failed & ~command_fault & ~source_fault & ~selected_bad,
               self.done.eq(1), output_end_pending.eq(0),
               self.selected_completed.eq(self.selected_completed + 1)),
            If(self.receiver_reset & ~self.enable & ~self.busy,
               self.native_armed.eq(0)
            ).Elif(observer._accepted & self.sink.first,
                   previous_native.eq(self.native_vsync_edges), self.native_armed.eq(1)),
            If(command_fault,
               self.command_errors.eq(self.command_errors + 1)),
            If(source_fault & ~self.source_sequence_fault,
               self.source_sequence_faults.eq(self.source_sequence_faults + 1),
               self.source_sequence_fault.eq(1)),
            If(command_fault | source_fault | selected_bad,
               self.failed.eq(1), self.done.eq(0), waiting.eq(0)),
        ]

    def ports(self):
        return (self.observer.ports() - {self.observer.enable}) | {
            self.enable, self.request_toggle, self.ack_toggle,
            self.native_vsync_edges, self.receiver_reset, self.credit_status,
            self.selected_source_id, self.selected_native_vsync_id,
            self.selected_completed, self.command_errors, self.source_sequence_faults}
