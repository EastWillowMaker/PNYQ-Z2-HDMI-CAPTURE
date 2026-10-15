`timescale 1ns/1ps
// Preserve short receiver-reset assertions when observing them in the stable
// AXIS domain. No edge/event data CDC is inferred from this reset synchronizer.
module receiver_reset_sync (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 sys_clk CLK",
       X_INTERFACE_PARAMETER = "FREQ_HZ 142857132" *)
    input wire sys_clk,
    input wire receiver_reset_async,
    output wire receiver_reset
);
    wire stretched_reset;
    xpm_cdc_async_rst #(
        .DEST_SYNC_FF(4), .INIT_SYNC_FF(1), .RST_ACTIVE_HIGH(1)
    ) receiver_reset_bridge (
        .src_arst(receiver_reset_async), .dest_clk(sys_clk),
        .dest_arst(stretched_reset)
    );
    // The gate observes reset as DATA, not as an asynchronous reset pin.
    // Retain a recognized two-stage ASYNC_REG chain for that observation;
    // do not replace it with an unmarked single FF or waive the CDC path.
    xpm_cdc_single #(
        .DEST_SYNC_FF(2), .INIT_SYNC_FF(1), .SRC_INPUT_REG(0),
        .SIM_ASSERT_CHK(1)
    ) receiver_reset_data_bridge (
        .src_clk(sys_clk), .src_in(stretched_reset),
        .dest_clk(sys_clk), .dest_out(receiver_reset)
    );
endmodule
