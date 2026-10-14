"""Handshake-level Migen tests; do not qualify HDMI, DDR, or board timing."""

import random
import shutil
import subprocess
import sys

import pytest
pytest.importorskip("migen", reason="gateware tests require the pinned Migen environment")
pytest.importorskip("litex", reason="gateware tests require the pinned LiteX environment")
from migen.sim import run_simulation

from gateware.capture import VideoCapture


def frame(width, height, base=0):
    return [(base + y * width + x, x == 0 and y == 0, x == width - 1)
            for y in range(height) for x in range(width)]


def simulate(beats, width=3, height=2, enables=None, stalls=False):
    dut = VideoCapture(width, height)
    output, stats = [], {}
    rng = random.Random(721)

    def process():
        yield dut.source.ready.eq(0)
        yield
        prior = None
        for index, beat in enumerate(beats):
            yield dut.enable.eq(1 if enables is None else enables[index])
            yield dut.sink.valid.eq(1)
            yield dut.sink.data.eq(beat[0])
            yield dut.sink.first.eq(beat[1])
            yield dut.sink.last.eq(beat[2])
            for _ in range(200):
                ready = rng.randrange(2) if stalls else 1
                yield dut.source.ready.eq(ready)
                yield
                valid = (yield dut.source.valid)
                current = ((yield dut.source.data), (yield dut.source.first),
                           (yield dut.source.last), (yield dut.output_frame_id))
                if prior is not None:
                    assert valid and current == prior, "AXIS changed stalled output"
                prior = current if valid and not ready else None
                if valid and ready:
                    output.append(current)
                if (yield dut.sink.ready):
                    break
            else:
                raise AssertionError("input deadlocked")
        yield dut.sink.valid.eq(0)
        yield dut.source.ready.eq(1)
        yield
        if (yield dut.source.valid):
            output.append(((yield dut.source.data), (yield dut.source.first),
                           (yield dut.source.last), (yield dut.output_frame_id)))
        yield
        for name in ("observed_frames", "selected_frames", "dropped_frames",
                     "completed_frames", "valid_frames", "invalid_frames",
                     "orphan_pixels", "stall_cycles", "errors", "active"):
            stats[name] = (yield getattr(dut, name))

    run_simulation(dut, process())
    return output, stats


def test_frames_preserve_pixels_sof_eol_and_ids_under_stalls():
    beats = frame(3, 2) + frame(3, 2, 100) + frame(3, 2, 200)
    output, stats = simulate(beats, stalls=True)
    assert output == [(*b, i // 6) for i, b in enumerate(beats)]
    assert stats["observed_frames"] == stats["valid_frames"] == 3
    assert stats["completed_frames"] == 3
    assert stats["invalid_frames"] == stats["errors"] == stats["active"] == 0
    assert stats["stall_cycles"] > 0


def test_enable_changes_only_at_sof_drop_whole_frames():
    beats = frame(3, 2) + frame(3, 2, 100) + frame(3, 2, 200)
    enables = [1, 0, 0, 0, 0, 0] + [0, 1, 1, 1, 1, 1] + [1] * 6
    output, stats = simulate(beats, enables=enables, stalls=True)
    assert output == [(*b, 0) for b in beats[:6]] + [(*b, 2) for b in beats[12:]]
    assert stats["selected_frames"] == 2
    assert stats["dropped_frames"] == 1
    assert stats["valid_frames"] == 3  # observations include skipped frames


@pytest.mark.parametrize("offset", [0, 1, 2, 3, 4, 5])
def test_bad_eol_marks_frame_once_and_next_frame_recovers(offset):
    broken = frame(3, 2)
    data, sof, eol = broken[offset]
    broken[offset] = (data, sof, not eol)
    good = frame(3, 2, 100)
    output, stats = simulate(broken + good)
    assert [b[:3] for b in output] == broken + good
    assert stats["invalid_frames"] == 1
    assert stats["valid_frames"] == 1
    assert stats["completed_frames"] == 2
    assert stats["errors"] == 4


def test_orphans_are_not_forwarded_and_unexpected_sof_aborts():
    beats = [(99, 0, 1)] + frame(3, 2)[:2] + frame(3, 2, 100)
    output, stats = simulate(beats)
    assert [b[:3] for b in output] == beats[1:]
    assert stats["orphan_pixels"] == 1
    assert stats["invalid_frames"] == 1
    assert stats["completed_frames"] == stats["valid_frames"] == 1
    assert stats["errors"] == 3


def test_bad_aborted_frame_counted_once_and_bad_restart_counted_separately():
    beats = [(1, 1, 1), (2, 0, 0), (3, 1, 1)] + frame(3, 2, 100)[1:]
    _, stats = simulate(beats)
    assert stats["invalid_frames"] == 2
    assert stats["errors"] == 6
    assert stats["valid_frames"] == 0


@pytest.mark.parametrize("startup", [
    [(99, 1, 1)] + frame(3, 2)[1:],  # wrong EOL in a completed dropped frame
    frame(3, 2)[:2] + frame(3, 2, 100),  # early SOF aborts a dropped frame
])
def test_invalid_disabled_startup_is_counted_without_forwarding(startup):
    # Establish the baseline with enable HELD LOW for the complete observation.
    baseline_output, baseline = simulate(startup, enables=[0] * len(startup))
    assert baseline_output == []
    assert baseline["selected_frames"] == 0
    assert baseline["invalid_frames"] == 1
    assert baseline["completed_frames"] == 1  # includes an unselected frame
    assert baseline["dropped_frames"] == baseline["observed_frames"]
    # Replay the same startup followed by a valid selected frame, without any
    # reset or counter clearing. The sticky startup error remains visible.
    good = frame(3, 2, 200)
    output, final = simulate(startup + good,
                             enables=[0] * len(startup) + [1] * len(good),
                             stalls=True)
    assert output == [(*b, baseline["observed_frames"]) for b in good]
    assert final["selected_frames"] == 1
    assert final["invalid_frames"] == baseline["invalid_frames"] == 1
    assert final["errors"] == baseline["errors"]
    assert final["completed_frames"] == baseline["completed_frames"] + 1


def test_single_pixel_frames():
    output, stats = simulate(frame(1, 1) + frame(1, 1, 10), width=1, height=1)
    assert output == [(0, 1, 1, 0), (10, 1, 1, 1)]
    assert stats["valid_frames"] == 2
    assert stats["active"] == 0


@pytest.mark.parametrize("width,height", [(0, 1), (1, 0), (65536, 480)])
def test_forbidden_geometry(width, height):
    with pytest.raises(ValueError):
        VideoCapture(width, height)


def test_generated_640x480_rtl_reset_stalls_and_frame_selection(tmp_path):
    if shutil.which("iverilog") is None or shutil.which("vvp") is None:
        pytest.skip("compiled RTL verification requires iverilog and vvp")
    rtl = tmp_path / "litex_capture.v"
    subprocess.run([sys.executable, "-m", "gateware.generate", "--output", str(rtl)],
                   check=True, capture_output=True, text=True)
    bench = tmp_path / "bench.v"
    bench.write_text(r'''
module bench;
reg clk=0, rst=1, enable=1, sv=0, su=0, sl=0;
reg [23:0] sd=0;
wire sr, mv, mu, ml;
wire [23:0] md;
wire [31:0] id, observed, selected, dropped, completed, valid_frames, invalid_frames;
wire [2:0] errors;
reg mr=0;
integer cycles=0, count=0, f,p;
always #5 clk=~clk;
litex_capture dut(.sys_clk(clk), .sys_rst(rst), .enable(enable),
 .s_axis_tdata(sd), .s_axis_tvalid(sv), .s_axis_tready(sr),
 .s_axis_tuser(su), .s_axis_tlast(sl), .m_axis_tdata(md),
 .m_axis_tvalid(mv), .m_axis_tready(mr), .m_axis_tuser(mu),
 .m_axis_tlast(ml), .output_frame_id(id), .observed_frames(observed),
 .selected_frames(selected), .dropped_frames(dropped),
 .completed_frames(completed), .valid_frames(valid_frames),
 .invalid_frames(invalid_frames), .errors(errors));
always @(negedge clk) begin
 cycles=cycles+1;
 mr=(cycles%7 != 0 && cycles%7 != 1);
end
always @(posedge clk) begin
 if (rst) count=0;
 else if(mv && mr) begin
  if(md !== count%307200 || mu !== (count%307200==0) ||
     ml !== (count%640==639) || id !== (count/307200)*2)
   $fatal(1,"corrupt output count=%0d data=%0d id=%0d",count,md,id);
  count=count+1;
 end
end
task send_pixel;
 input integer pixel;
 begin
  @(negedge clk); sd=pixel; sv=1; su=(pixel==0); sl=(pixel%640==639);
  @(posedge clk);
  while(!sr) @(posedge clk);
 end
endtask
initial begin
 repeat(3) @(negedge clk);
 rst=0;
 // Reset during an incomplete selected frame flushes its pending output.
 for(p=0;p<100;p=p+1) send_pixel(p);
 @(negedge clk); rst=1; sv=0;
 repeat(3) @(negedge clk);
 if(mv !== 0 || observed !== 0 || errors !== 0) $fatal(1,"reset failed");
 rst=0;
 for(f=0;f<3;f=f+1) begin
  enable=(f!=1);
  for(p=0;p<307200;p=p+1) send_pixel(p);
 end
 @(negedge clk); sv=0;
 repeat(10) @(negedge clk);
 if(count !== 614400 || observed !== 3 || selected !== 2 || dropped !== 1 ||
    completed !== 3 || valid_frames !== 3 || invalid_frames !== 0 || errors !== 0)
  $fatal(1,"bad final counts output=%0d observed=%0d valid=%0d",count,observed,valid_frames);
 $display("PASS 3 observed 640x480 frames; 2 selected; synchronous mid-frame reset; stalls");
 $finish;
end
initial begin #20000000; $fatal(1,"timeout"); end
endmodule
''')
    binary = tmp_path / "bench"
    subprocess.run(["iverilog", "-g2012", "-s", "bench", "-o", str(binary),
                    str(rtl), str(bench)], check=True, capture_output=True, text=True)
    result = subprocess.run(["vvp", str(binary)], check=True,
                            capture_output=True, text=True, timeout=30)
    assert "PASS 3 observed" in result.stdout
