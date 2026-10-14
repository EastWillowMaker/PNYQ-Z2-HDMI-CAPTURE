`timescale 1ns/1ps
module source_health_tb;
    reg pixel_clk = 0;
    reg pixel_run = 1;
    reg sys_clk = 0;
    reg pixel_reset = 1;
    reg sys_reset = 1;
    reg vsync = 1;
    reg overflow = 1;
    reg underflow = 1;
    wire [31:0] overflow_episodes, native_vsync_edges, underflow_episodes;
    reg monitor = 0;
    reg [31:0] last_overflow = 0, last_vsync = 0;
    integer i;

    always #20 if (pixel_run) pixel_clk = ~pixel_clk;
    always #3.5 sys_clk = ~sys_clk;
    source_health dut(.*);

    // Observe the actual XPM destination registers, including binary carry
    // transitions. With slower source clocks there can be at most one new
    // event per destination sample. No destination reset is applied here.
    always @(posedge sys_clk) begin
        #0.1;
        if (monitor) begin
            if (^overflow_episodes === 1'bx || ^native_vsync_edges === 1'bx)
                $fatal(1, "Unknown CDC output");
            if (overflow_episodes < last_overflow ||
                overflow_episodes > last_overflow + 1 ||
                native_vsync_edges < last_vsync ||
                native_vsync_edges > last_vsync + 1)
                $fatal(1, "CDC counter incoherent or nonmonotonic");
            if (overflow_episodes > dut.overflow_native ||
                native_vsync_edges > dut.vsync_native)
                $fatal(1, "CDC count exceeded native count");
        end
        last_overflow = overflow_episodes;
        last_vsync = native_vsync_edges;
    end

    task settle;
        repeat (12) @(posedge sys_clk);
        #1;
    endtask

    task check;
        input [31:0] wanted_overflow, wanted_vsync, wanted_underflow;
        begin
            settle();
            if (overflow_episodes !== wanted_overflow ||
                native_vsync_edges !== wanted_vsync ||
                underflow_episodes !== wanted_underflow)
                $fatal(1, "Counts overflow=%0d/%0d vsync=%0d/%0d underflow=%0d/%0d",
                       overflow_episodes, wanted_overflow,
                       native_vsync_edges, wanted_vsync,
                       underflow_episodes, wanted_underflow);
        end
    endtask

    initial begin
        // Keep all vendor assertions active, including startup. XSIM 2025.2
        // reports one S-2 first-history diagnostic per Gray instance at 20ns
        // for initialized counters that remain zero. Preserve and classify
        // those diagnostics in the run result; any later diagnostic fails
        // qualification. Procedural startup counts are checked independently.
        #220; // Vendor global startup reset has completed.
        check(0, 0, 0);
        monitor = 1;
        @(negedge pixel_clk); pixel_reset = 0;
        @(negedge sys_clk); sys_reset = 0;
        repeat (4) @(negedge pixel_clk);
        // HIGH startup faults count once; HIGH startup VSYNC is baseline only.
        check(1, 0, 1);
        repeat (8) @(negedge pixel_clk);
        check(1, 0, 1); // Episodes, not HIGH cycles.
        overflow = 0; vsync = 0;
        @(negedge sys_clk); underflow = 0;
        repeat (3) @(negedge pixel_clk);
        // Exercise 255->256 and 511->512 multi-bit binary carries in actual XPM.
        for (i = 0; i < 512; i = i + 1) begin
            overflow = 1; vsync = 1;
            repeat (3) @(negedge pixel_clk);
            overflow = 0; vsync = 0;
            repeat (2) @(negedge pixel_clk);
        end
        @(negedge sys_clk); underflow = 1;
        check(513, 512, 2);

        // Loss of lock while PixelClk is stopped must preserve binary counts
        // and destination snapshots. Restart with reset asserted first.
        @(negedge pixel_clk); pixel_run = 0;
        pixel_reset = 1; vsync = 1; overflow = 1;
        @(negedge sys_clk); sys_reset = 1;
        #300;
        check(513, 512, 2);
        pixel_run = 1;
        repeat (3) @(negedge pixel_clk);
        check(513, 512, 2);
        pixel_reset = 0;
        @(negedge sys_clk); sys_reset = 0;
        repeat (4) @(negedge pixel_clk);
        // Faults still HIGH on rearm count episodes; VSYNC remains a baseline.
        check(514, 512, 3);
        repeat (8) @(negedge pixel_clk);
        check(514, 512, 3);
        overflow = 0; vsync = 0;
        repeat (2) @(negedge pixel_clk);
        vsync = 1;
        repeat (2) @(negedge pixel_clk);
        check(514, 513, 3);
        $display("source_health PASS: episodes, startup HIGH, native VSYNC rearm, lifetime counters, stopped PixelClk, actual XPM coherent carries");
        $finish;
    end
    initial begin #1000000; $fatal(1, "source_health timeout"); end
endmodule
