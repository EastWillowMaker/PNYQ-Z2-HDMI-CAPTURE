`timescale 1ns/1ps
// Receiver lock is registered in the independent 200 MHz RefClk domain.
// Assert loss of lock asynchronously, then qualify lock on four PixelClk edges
// before the pixel-domain reset controller may release the video pipeline.
module capture_lock_sync (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 pixel_clk CLK" *)
    input wire pixel_clk,
    input wire locked_async,
    output wire locked_pixel
);
    xpm_cdc_async_rst #(
        .DEST_SYNC_FF(4),
        .INIT_SYNC_FF(1),
        .RST_ACTIVE_HIGH(0)
    ) receiver_lock_bridge (
        .src_arst(locked_async),
        .dest_clk(pixel_clk),
        .dest_arst(locked_pixel)
    );
endmodule
