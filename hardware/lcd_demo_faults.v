`timescale 1ns/1ps
module lcd_demo_faults (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 clk CLK",
       X_INTERFACE_PARAMETER = "FREQ_HZ 142857132, ASSOCIATED_RESET rst" *)
    input wire clk,
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 rst RST",
       X_INTERFACE_PARAMETER = "POLARITY ACTIVE_HIGH" *)
    input wire rst,
    input wire [31:0] overflow_count,
    input wire [31:0] underflow_count,
    output wire fault
);
    reg [31:0] previous_overflow;
    reg [31:0] previous_underflow;
    assign fault = !rst && ((overflow_count != previous_overflow) ||
                           (underflow_count != previous_underflow));
    always @(posedge clk) begin
        previous_overflow <= overflow_count;
        previous_underflow <= underflow_count;
    end
endmodule
