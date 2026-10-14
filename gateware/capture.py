"""AXI4-Stream Video frame selection and geometry observation."""

from migen import If, Signal
from litex.gen import LiteXModule
from litex.soc.interconnect import stream


class VideoCapture(LiteXModule):
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
