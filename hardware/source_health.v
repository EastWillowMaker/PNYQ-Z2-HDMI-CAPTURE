`timescale 1ns/1ps
// Event counters persist for the lifetime of the loaded FPGA configuration.
// Domain resets rearm edge detection only: resetting a live binary counter
// would violate the incremental-input contract of the Gray CDC primitive.
module source_health (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 pixel_clk CLK",
       X_INTERFACE_PARAMETER = "FREQ_HZ 25200000, ASSOCIATED_RESET pixel_reset" *)
    input wire pixel_clk,
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 pixel_reset RST",
       X_INTERFACE_PARAMETER = "POLARITY ACTIVE_HIGH" *)
    input wire pixel_reset,
    input wire vsync,
    input wire overflow,
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 sys_clk CLK",
       X_INTERFACE_PARAMETER = "FREQ_HZ 142857132, ASSOCIATED_RESET sys_reset" *)
    input wire sys_clk,
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 sys_reset RST",
       X_INTERFACE_PARAMETER = "POLARITY ACTIVE_HIGH" *)
    input wire sys_reset,
    input wire underflow,
    output wire [31:0] overflow_episodes,
    output wire [31:0] native_vsync_edges,
    output reg [31:0] underflow_episodes = 32'd0
);
    reg [31:0] overflow_native = 32'd0;
    reg [31:0] vsync_native = 32'd0;
    reg prev_overflow = 1'b0;
    reg prev_vsync = 1'b0;
    reg vsync_armed = 1'b0;
    reg prev_underflow = 1'b0;

    always @(posedge pixel_clk) begin
        if (pixel_reset) begin
            prev_overflow <= 1'b0;
            prev_vsync <= vsync;
            vsync_armed <= 1'b0;
        end else begin
            // A high overflow on first qualified edge counts one episode.
            if (overflow && !prev_overflow)
                overflow_native <= overflow_native + 32'd1;
            prev_overflow <= overflow;
            // Establish a baseline after reset; do not invent a VSYNC edge.
            if (vsync_armed && vsync && !prev_vsync)
                vsync_native <= vsync_native + 32'd1;
            prev_vsync <= vsync;
            vsync_armed <= 1'b1;
        end
    end

    always @(posedge sys_clk) begin
        if (sys_reset)
            prev_underflow <= 1'b0;
        else begin
            if (underflow && !prev_underflow)
                underflow_episodes <= underflow_episodes + 32'd1;
            prev_underflow <= underflow;
        end
    end

    xpm_cdc_gray #(
        .DEST_SYNC_FF(4), .INIT_SYNC_FF(1), .REG_OUTPUT(1),
        .WIDTH(32), .SIM_ASSERT_CHK(1)
    ) overflow_bridge (
        .src_clk(pixel_clk), .src_in_bin(overflow_native),
        .dest_clk(sys_clk), .dest_out_bin(overflow_episodes)
    );
    xpm_cdc_gray #(
        .DEST_SYNC_FF(4), .INIT_SYNC_FF(1), .REG_OUTPUT(1),
        .WIDTH(32), .SIM_ASSERT_CHK(1)
    ) vsync_bridge (
        .src_clk(pixel_clk), .src_in_bin(vsync_native),
        .dest_clk(sys_clk), .dest_out_bin(native_vsync_edges)
    );
endmodule
