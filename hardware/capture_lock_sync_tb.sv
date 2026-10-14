`timescale 1ns/1ps
module capture_lock_sync_tb;
    reg pixel_clk = 0;
    reg locked_async = 0;
    wire locked_pixel;
    capture_lock_sync dut(pixel_clk, locked_async, locked_pixel);
    task pulse;
        #19 pixel_clk = 1;
        #1;
        #20 pixel_clk = 0;
    endtask
    task qualify;
        locked_async = 1;
        repeat (3) begin
            pulse();
            if (locked_pixel !== 0) $fatal(1, "Lock released before four edges");
        end
        pulse();
        if (locked_pixel !== 1) $fatal(1, "Lock did not release after four edges");
    endtask
    initial begin
        #200; // Allow vendor simulation global startup reset to finish.
        if (locked_pixel !== 0) $fatal(1, "No-input lock must stay reset");
        qualify();
        locked_async = 0;
        #1;
        if (locked_pixel !== 0) $fatal(1, "Loss of lock must assert without PixelClk");
        locked_async = 1;
        pulse(); pulse();
        if (locked_pixel !== 0) $fatal(1, "Transient lock must not release reset");
        locked_async = 0;
        #1;
        qualify();
        $display("capture_lock_sync: startup, qualification, stopped-clock loss, chatter PASS");
        $finish;
    end
endmodule
