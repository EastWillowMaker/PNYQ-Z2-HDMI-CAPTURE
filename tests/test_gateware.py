"""Handshake-level Migen tests; do not qualify HDMI, DDR, or board timing."""

import random
import shutil
import subprocess
import sys

import pytest
pytest.importorskip("migen", reason="gateware tests require the pinned Migen environment")
pytest.importorskip("litex", reason="gateware tests require the pinned LiteX environment")
from migen.sim import passive, run_simulation

from gateware.capture import LegacyVideoCapture, VideoCapture


def frame(width, height, base=0):
    return [(base + y * width + x, x == 0 and y == 0, x == width - 1)
            for y in range(height) for x in range(width)]


def simulate(beats, width=3, height=2, enables=None, stalls=False):
    dut = LegacyVideoCapture(width, height)
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
    assert stats["invalid_frames"] == 2  # orphan episode plus aborted frame
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


class CreditDriver:
    def __init__(self, dut):
        self.dut = dut
        self.native = 0

    def wait(self, cycles=3):
        for _ in range(cycles):
            yield

    def request(self):
        yield self.dut.enable.eq(1)
        yield self.dut.request_toggle.eq(1 - (yield self.dut.request_toggle))
        yield from self.wait()

    def ack(self):
        yield self.dut.ack_toggle.eq(1 - (yield self.dut.ack_toggle))
        yield from self.wait()

    def send(self, beats, *, native_delta=1):
        for data, sof, eol in beats:
            if sof:
                self.native = (self.native + native_delta) & 0xffffffff
                yield self.dut.native_vsync_edges.eq(self.native)
            yield self.dut.sink.valid.eq(1)
            yield self.dut.sink.data.eq(data)
            yield self.dut.sink.first.eq(sof)
            yield self.dut.sink.last.eq(eol)
            yield
            while not (yield self.dut.sink.ready):
                yield
        yield self.dut.sink.valid.eq(0)
        yield self.dut.sink.first.eq(0)
        yield from self.wait()


def credit_sim(exercise, *, width=3, height=2, seed=None):
    dut = VideoCapture(width, height)
    if seed is not None:
        dut.observer._next_id.reset = seed
    output = []

    @passive
    def monitor():
        while True:
            if (yield dut.source.valid) and (yield dut.source.ready):
                output.append(((yield dut.source.data), (yield dut.source.first),
                               (yield dut.source.last), (yield dut.output_frame_id)))
            yield

    def drive():
        yield dut.source.ready.eq(1)
        driver = CreditDriver(dut)
        yield from driver.wait()
        yield from exercise(dut, driver, output)
        yield from driver.wait()

    run_simulation(dut, [drive(), monitor()])


def test_credit_default_disabled_exact_sampling_counts_and_immutable_identity():
    def exercise(dut, driver, output):
        yield from driver.send(frame(3, 2))
        assert output == []
        assert (yield dut.credit_status) == 64  # paired, idle, disabled
        yield from driver.request()
        assert (yield dut.busy) == 1
        good = frame(3, 2, 100)
        yield from driver.send(good)
        assert output == [(*b, 1) for b in good]
        assert (yield dut.done) == 0  # complete tail awaits next SOF closure
        assert (yield dut.selected_completed) == 0
        assert (yield dut.selected_source_id) == 1
        assert (yield dut.selected_native_vsync_id) == 2
        yield from driver.send(frame(3, 2, 200))
        assert (yield dut.done) == (yield dut.selected_completed) == 1
        assert (yield dut.selected_source_id) == 1
        assert (yield dut.selected_native_vsync_id) == 2
        assert len(output) == 6
        assert (yield dut.observed_frames) == (yield dut.completed_frames) == 3
        assert (yield dut.selected_frames) == 1
        assert (yield dut.dropped_frames) == 2
        yield from driver.ack()
        assert (yield dut.busy) == (yield dut.done) == 0
        yield from driver.request()
        yield from driver.send(frame(3, 2, 300))
        assert (yield dut.selected_source_id) == 3
        assert (yield dut.selected_native_vsync_id) == 4
        assert (yield dut.selected_completed) == 1
        yield from driver.send(frame(3, 2, 400))
        assert (yield dut.selected_completed) == 2
        yield from driver.send(frame(3, 2, 500))
        assert (yield dut.selected_completed) == 2  # only one closure per credit
        assert (yield dut.failed) == 0
    credit_sim(exercise)


@pytest.mark.parametrize("command", ["request_busy", "ack_before_done", "ack_and_request"])
def test_credit_forbidden_commands_fail_stop(command):
    def exercise(dut, driver, output):
        yield from driver.send(frame(3, 2))
        yield from driver.request()
        if command == "request_busy":
            yield from driver.request()
        elif command == "ack_before_done":
            yield from driver.ack()
        else:
            yield from driver.send(frame(3, 2))
            yield from driver.send(frame(3, 2))
            yield dut.ack_toggle.eq(1)
            yield dut.request_toggle.eq(0)
            yield from driver.wait()
        assert (yield dut.failed) == 1
        assert (yield dut.command_errors) == 1
        count = len(output)
        yield from driver.send(frame(3, 2, 100))
        assert len(output) == count
    credit_sim(exercise)


@pytest.mark.parametrize("offset", range(6))
def test_credit_malformed_selected_frame_never_reports_done(offset):
    def exercise(dut, driver, output):
        yield from driver.send(frame(3, 2))
        yield from driver.request()
        bad = frame(3, 2, 100)
        data, sof, eol = bad[offset]
        bad[offset] = data, sof, not eol
        yield from driver.send(bad)
        assert [b[:3] for b in output] == bad  # cannot retract emitted bad pixels
        assert (yield dut.failed) == 1
        assert (yield dut.done) == (yield dut.selected_completed) == 0
        assert (yield dut.invalid_frames) == 1
    credit_sim(exercise)


def test_credit_early_sof_aborts_selected_frame_without_reselecting():
    def exercise(dut, driver, output):
        yield from driver.send(frame(3, 2))
        yield from driver.request()
        yield from driver.send(frame(3, 2, 100)[:2])
        yield from driver.send(frame(3, 2, 200))
        assert len(output) == 2
        assert (yield dut.failed) == 1
        assert (yield dut.done) == (yield dut.selected_completed) == 0
        assert (yield dut.selected_frames) == 1
    credit_sim(exercise)


@pytest.mark.parametrize("native_delta", [0, 2])
def test_credit_missing_or_repeated_native_sequence_fails(native_delta):
    def exercise(dut, driver, output):
        yield from driver.send(frame(3, 2))
        yield from driver.request()
        yield from driver.send(frame(3, 2, 100), native_delta=native_delta)
        assert output == []
        assert (yield dut.source_sequence_fault) == (yield dut.failed) == 1
        assert (yield dut.source_sequence_faults) == 1
    credit_sim(exercise)


def test_credit_trailing_missing_sof_watchdog_and_receiver_reset_pulse():
    def exercise(dut, driver, output):
        yield dut.receiver_reset.eq(1)
        yield from driver.wait()
        assert (yield dut.failed) == (yield dut.native_armed) == 0
        yield dut.receiver_reset.eq(0)
        yield from driver.send(frame(3, 2))
        yield dut.enable.eq(1)
        yield dut.native_vsync_edges.eq(driver.native + 1)
        yield from driver.wait()
        assert (yield dut.failed) == 0  # next native frame may await its SOF
        yield dut.native_vsync_edges.eq(driver.native + 2)
        yield from driver.wait()
        assert (yield dut.source_sequence_fault) == (yield dut.failed) == 1
        assert (yield dut.source_sequence_faults) == 1
    credit_sim(exercise)


@pytest.mark.parametrize("during_frame,clear_enable", [(False, False), (True, False), (True, True)])
def test_credit_receiver_reset_enabled_is_sticky_failure(during_frame, clear_enable):
    def exercise(dut, driver, output):
        yield from driver.send(frame(3, 2))
        if during_frame:
            yield from driver.request()
            yield from driver.send(frame(3, 2, 100)[:2])
        else:
            yield dut.enable.eq(1)
        if clear_enable:
            yield dut.enable.eq(0)
        yield dut.receiver_reset.eq(1)
        yield from driver.wait(1)
        yield dut.receiver_reset.eq(0)
        yield from driver.wait()
        assert (yield dut.source_sequence_fault) == (yield dut.failed) == 1
        assert (yield dut.source_sequence_faults) == 1
    credit_sim(exercise)


def test_credit_request_while_disabled_is_forbidden():
    def exercise(dut, driver, output):
        yield dut.request_toggle.eq(1)
        yield from driver.wait()
        assert (yield dut.failed) == (yield dut.command_errors) == 1
        assert (yield dut.busy) == 0
        yield from driver.send(frame(3, 2))
        assert output == []
    credit_sim(exercise)


@pytest.mark.parametrize("seed", [0xfffffffd, 0xfffffffe])
def test_credit_sof_ids_and_native_proof_wrap_modulo_32(seed):
    def exercise(dut, driver, output):
        driver.native = (seed - 1) & 0xffffffff
        for i in range(3):
            expected_id = expected_native = (seed + 2 * i) & 0xffffffff
            yield from driver.request()
            yield from driver.send(frame(3, 2))
            assert (yield dut.selected_source_id) == expected_id
            assert (yield dut.selected_native_vsync_id) == expected_native
            assert (yield dut.done) == 0
            yield from driver.send(frame(3, 2))
            assert (yield dut.done) == 1
            assert (yield dut.failed) == 0
            yield from driver.ack()
    credit_sim(exercise, seed=seed)


def test_credit_done_waits_for_stalled_final_output_transfer():
    def exercise(dut, driver, output):
        yield from driver.send(frame(3, 2))
        yield from driver.request()
        good = frame(3, 2, 100)
        yield from driver.send(good[:-1])
        yield dut.source.ready.eq(0)
        yield from driver.send(good[-1:])
        before = ((yield dut.source.data), (yield dut.source.last),
                  (yield dut.output_frame_id))
        for _ in range(7):
            assert (yield dut.source.valid) == 1
            assert ((yield dut.source.data), (yield dut.source.last),
                    (yield dut.output_frame_id)) == before
            assert (yield dut.done) == (yield dut.selected_completed) == 0
            yield
        yield dut.source.ready.eq(1)
        yield from driver.wait()
        assert output == [(*b, 1) for b in good]
        assert (yield dut.done) == (yield dut.selected_completed) == 0
        yield from driver.send(frame(3, 2, 200))
        assert (yield dut.done) == (yield dut.selected_completed) == 1
    credit_sim(exercise)


def test_credit_request_and_sof_same_cycle_drops_that_frame():
    def exercise(dut, driver, output):
        yield from driver.send(frame(3, 2))
        yield dut.enable.eq(1)
        yield dut.request_toggle.eq(1)
        yield from driver.send(frame(3, 2, 100))
        assert output == []
        assert (yield dut.busy) == 1
        yield from driver.send(frame(3, 2, 200))
        assert output == [(*b, 2) for b in frame(3, 2, 200)]
        assert (yield dut.selected_frames) == 1
        assert (yield dut.dropped_frames) == 2
    credit_sim(exercise)


@pytest.mark.parametrize("phase", ["waiting", "tail_before_closure", "done_before_ack", "after_ack"])
def test_credit_enabled_orphan_is_an_exported_sticky_source_fault(phase):
    def exercise(dut, driver, output):
        # Orphans during disabled startup remain reported by the observer,
        # without contaminating the later enabled session's sticky fault.
        yield from driver.send([(99, 0, 0)])
        assert (yield dut.source_sequence_fault) == 0
        yield from driver.send(frame(3, 2))
        invalid_baseline = (yield dut.invalid_frames)
        yield from driver.request()
        if phase != "waiting":
            yield from driver.send(frame(3, 2, 100))
            assert (yield dut.done) == 0
            yield from driver.wait(200)  # never assume CPU is slower than extra pixels
            assert (yield dut.done) == 0
            if phase != "tail_before_closure":
                yield from driver.send(frame(3, 2, 200))
                assert (yield dut.done) == 1
            if phase == "after_ack":
                yield from driver.ack()
        frozen = ((yield dut.selected_source_id), (yield dut.selected_native_vsync_id))
        count = len(output)
        yield from driver.send([(777, 0, 1)])
        assert (yield dut.source_sequence_fault) == (yield dut.failed) == 1
        assert (yield dut.source_sequence_faults) == 1
        assert (yield dut.invalid_frames) == invalid_baseline + 1
        yield from driver.send([(778, 0, 0), (779, 0, 1)])
        assert (yield dut.invalid_frames) == invalid_baseline + 1
        assert (yield dut.done) == 0
        assert len(output) == count
        assert ((yield dut.selected_source_id), (yield dut.selected_native_vsync_id)) == frozen
        yield from driver.send(frame(3, 2, 200))
        assert len(output) == count
    credit_sim(exercise)


@pytest.mark.parametrize("premature_ack", [False, True])
def test_credit_simultaneous_tail_transfer_and_next_sof_closure(premature_ack):
    def exercise(dut, driver, output):
        yield from driver.send(frame(3, 2))
        yield from driver.request()
        good = frame(3, 2, 100)
        yield from driver.send(good[:-1])
        yield dut.source.ready.eq(0)
        yield from driver.send(good[-1:])
        driver.native += 1
        yield dut.native_vsync_edges.eq(driver.native)
        yield dut.sink.valid.eq(1)
        yield dut.sink.first.eq(1)
        yield dut.sink.last.eq(0)
        yield dut.sink.data.eq(200)
        yield from driver.wait()
        assert (yield dut.sink.ready) == (yield dut.done) == 0
        if premature_ack:
            yield dut.ack_toggle.eq(1)
        yield dut.source.ready.eq(1)
        yield
        yield dut.sink.valid.eq(0)
        yield dut.sink.first.eq(0)
        yield from driver.wait()
        assert output == [(*b, 1) for b in good]
        assert (yield dut.selected_source_id) == 1
        if premature_ack:
            assert (yield dut.failed) == (yield dut.command_errors) == 1
            assert (yield dut.done) == (yield dut.selected_completed) == 0
        else:
            assert (yield dut.done) == (yield dut.selected_completed) == 1
            assert (yield dut.failed) == 0
    credit_sim(exercise)


def test_generated_640x480_rtl_reset_stalls_and_frame_selection(tmp_path):
    if shutil.which("iverilog") is None or shutil.which("vvp") is None:
        pytest.skip("compiled RTL verification requires iverilog and vvp")
    rtl = tmp_path / "litex_capture.v"
    subprocess.run([sys.executable, "-m", "gateware.generate", "--output", str(rtl)],
                   check=True, capture_output=True, text=True)
    bench = tmp_path / "bench.v"
    bench.write_text(r'''
module bench;
reg clk=0, rst=1, enable=0, req=0, ack=0, sv=0, su=0, sl=0;
reg [31:0] native_count=0;
reg [23:0] sd=0;
wire sr, mv, mu, ml;
wire [23:0] md;
wire [31:0] id, observed, selected, dropped, completed, valid_frames, invalid_frames;
wire [2:0] errors;
wire [31:0] credit_status, selected_completed, command_errors, selected_id, selected_native_id;
reg mr=0;
integer cycles=0, count=0, f,p;
always #5 clk=~clk;
litex_capture dut(.sys_clk(clk), .sys_rst(rst), .enable(enable),
 .request_toggle(req), .ack_toggle(ack), .native_vsync_edges(native_count),
 .receiver_reset(1'b0), .credit_status(credit_status),
 .selected_completed(selected_completed), .command_errors(command_errors),
 .selected_source_id(selected_id), .selected_native_vsync_id(selected_native_id),
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
  if(pixel==0) native_count=native_count+1;
  @(posedge clk);
  while(!sr) @(posedge clk);
 end
endtask
initial begin
 repeat(3) @(negedge clk);
 rst=0;
 enable=1; req=1;
 repeat(4) @(negedge clk);
 // Reset during an incomplete selected frame flushes its pending output.
 for(p=0;p<100;p=p+1) send_pixel(p);
 @(negedge clk); rst=1; sv=0; enable=0; req=0; ack=0;
 repeat(3) @(negedge clk);
 if(mv !== 0 || observed !== 0 || errors !== 0) $fatal(1,"reset failed");
 rst=0;
 for(f=0;f<4;f=f+1) begin
  if(f==0 || f==2) begin
   enable=1; req=~req;
   repeat(4) @(negedge clk);
  end
  for(p=0;p<307200;p=p+1) send_pixel(p);
  @(negedge clk); sv=0;
  repeat(12) @(negedge clk);
  if(f==0 || f==2) begin
   if(credit_status[1] !== 0) $fatal(1,"DONE before next-SOF closure");
  end
  if(f==1) begin
   if(credit_status[1] !== 1 || selected_id !== 0) $fatal(1,"first credit incomplete");
   ack=~ack;
   repeat(4) @(negedge clk);
   if(credit_status[0] !== 0) $fatal(1,"credit did not release");
  end
 end
 @(negedge clk); sv=0;
 repeat(10) @(negedge clk);
 if(count !== 614400 || observed !== 4 || selected !== 2 || dropped !== 2 ||
    completed !== 4 || valid_frames !== 4 || invalid_frames !== 0 || errors !== 0 ||
    selected_completed !== 2 || command_errors !== 0 || selected_id !== 2 ||
    selected_native_id !== 4 || credit_status[5:0] !== 6'b010011)
  $fatal(1,"bad final counts output=%0d observed=%0d valid=%0d",count,observed,valid_frames);
 $display("PASS 4 observed 640x480 frames; 2 selected; next-SOF closure; synchronous mid-frame reset; stalls");
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
    assert "PASS 4 observed" in result.stdout
