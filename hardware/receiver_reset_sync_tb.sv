`timescale 1ns/1ps
module receiver_reset_sync_tb;
    reg sys_clk = 0;
    reg clock_running = 1;
    reg receiver_reset_async = 0;
    wire receiver_reset;
    reg enable = 0;
    wire [31:0] credit_status;
    wire unused_ready;
    always #3.5 if (clock_running) sys_clk = ~sys_clk;
    receiver_reset_sync bridge(.*);
    litex_capture capture(.sys_clk(sys_clk), .sys_rst(1'b0), .enable(enable),
        .request_toggle(1'b0), .ack_toggle(1'b0), .native_vsync_edges(32'd0),
        .receiver_reset(receiver_reset), .credit_status(credit_status),
        .s_axis_tvalid(1'b0), .s_axis_tdata(24'd0), .s_axis_tuser(1'b0),
        .s_axis_tlast(1'b0), .s_axis_tready(unused_ready), .m_axis_tready(1'b1));
    task release_check;
        @(posedge sys_clk); #0.1;
        if (receiver_reset !== 0) $fatal(1,"Gate reset data changed before two-stage observation");
        repeat (4) begin
            @(posedge sys_clk); #0.1;
            if (receiver_reset !== 1) $fatal(1,"Reset observation did not retain the stretched pulse");
        end
        @(posedge sys_clk); #0.1;
        if (receiver_reset !== 0) $fatal(1,"Reset data did not release on sixth AXIS edge");
    endtask
    initial begin
        #220;
        if (receiver_reset !== 0 || credit_status[5] !== 0)
            $fatal(1,"Disabled startup must release without source fault");
        @(negedge sys_clk); enable = 1;
        // Assert while the stable AXIS clock is paused: the reset bridge must
        // capture the source pulse, then hold it until synchronized release.
        @(negedge sys_clk); clock_running = 0;
        #1 receiver_reset_async = 1;
        #0.1;
        if (bridge.stretched_reset !== 1) $fatal(1,"Pulse stretcher assertion was not asynchronous");
        #40 receiver_reset_async = 0;
        #30;
        if (bridge.stretched_reset !== 1) $fatal(1,"Stopped clock lost receiver reset pulse");
        clock_running = 1;
        release_check();
        @(posedge sys_clk); #0.1;
        if (credit_status[5] !== 1 || credit_status[2] !== 1)
            $fatal(1,"Enabled idle reset must be a sticky gate source fault");
        repeat (8) @(posedge sys_clk);
        if (credit_status[5] !== 1) $fatal(1,"Source reset fault was not sticky");
        $display("receiver_reset_sync PASS: async pulse retention, two-stage data observation, six-edge release, real gate sticky fault");
        $finish;
    end
    initial begin #2000; $fatal(1,"receiver_reset_sync timeout"); end
endmodule
