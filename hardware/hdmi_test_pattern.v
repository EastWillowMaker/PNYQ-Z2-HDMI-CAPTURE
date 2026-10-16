// Fixed 1920x1080p30 analytic pattern for the optional HDMI OUT loop test.
// vid_pData uses the pinned rgb2dvi IP's documented RBG byte order.
module hdmi_test_pattern (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 pixel_clk CLK",
       X_INTERFACE_PARAMETER = "XIL_INTERFACENAME pixel_clk, FREQ_HZ 74250000, ASSOCIATED_ASYNC_RESET async_reset" *)
    input  wire        pixel_clk,
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 async_reset RST",
       X_INTERFACE_PARAMETER = "XIL_INTERFACENAME async_reset, POLARITY ACTIVE_HIGH" *)
    input  wire        async_reset,
    output reg  [23:0] vid_pData,
    output reg         vid_pVDE,
    output reg         vid_pHSync,
    output reg         vid_pVSync
);
    reg [11:0] h_count;
    reg [10:0] v_count;
    reg [31:0] frame_id;
    (* ASYNC_REG = "TRUE" *) reg [1:0] reset_pipe;

    reg [31:0] red_sum;
    reg [31:0] green_sum;
    reg [7:0] red;
    reg [7:0] green;
    reg [7:0] blue;
    reg marker_bit;
    reg [7:0] marker_value;

    wire pixel_reset = reset_pipe[1];

    // Asynchronous assertion with two pixel-clock stages before release.
    always @(posedge pixel_clk or posedge async_reset) begin
        if (async_reset)
            reset_pipe <= 2'b11;
        else
            reset_pipe <= {reset_pipe[0], 1'b0};
    end

    always @(posedge pixel_clk or posedge pixel_reset) begin
        if (pixel_reset) begin
            h_count <= 12'd0;
            v_count <= 11'd0;
            frame_id <= 32'd1;
        end else if (h_count == 12'd2199) begin
            h_count <= 12'd0;
            if (v_count == 11'd1124) begin
                v_count <= 11'd0;
                frame_id <= frame_id + 32'd1;
            end else begin
                v_count <= v_count + 11'd1;
            end
        end else begin
            h_count <= h_count + 12'd1;
        end
    end

    always @* begin
        vid_pHSync = (h_count >= 12'd2008) && (h_count < 12'd2052);
        vid_pVSync = (v_count >= 11'd1084) && (v_count < 11'd1089);
        vid_pVDE = !async_reset && !pixel_reset &&
                   (h_count < 12'd1920) && (v_count < 11'd1080);
        vid_pData = 24'd0;

        red_sum = {20'd0, h_count} +
                  ({21'd0, v_count} * 32'd3) + {24'd0, frame_id[7:0]};
        green_sum = ({20'd0, h_count} * 32'd5) +
                    {21'd0, v_count} + {24'd0, frame_id[15:8]};
        red = red_sum[7:0];
        green = green_sum[7:0];
        blue = h_count[7:0] ^ v_count[7:0] ^ frame_id[23:16];
        marker_bit = frame_id[h_count[5:1]];
        marker_value = marker_bit ? 8'hff : 8'h00;

        if (vid_pVDE) begin
            if (h_count < 12'd128) begin
                if (h_count >= 12'd64)
                    marker_value = ~marker_value;
                vid_pData = {marker_value, marker_value, marker_value};
            end else if (h_count == 12'd128) begin
                vid_pData = {8'hff, 8'h00, 8'h00};
            end else if (h_count == 12'd129) begin
                vid_pData = {8'h00, 8'h00, 8'hff};
            end else if (h_count == 12'd130) begin
                vid_pData = {8'h00, 8'hff, 8'h00};
            end else if (h_count == 12'd131) begin
                vid_pData = 24'h000000;
            end else if (h_count == 12'd132) begin
                vid_pData = 24'hffffff;
            end else if ((v_count >= 11'd16) && (v_count < 11'd32) &&
                         (h_count >= 12'd160) && (h_count < 12'd416)) begin
                vid_pData = {h_count[7:0] - 8'd160, 16'h0000};
            end else if ((v_count >= 11'd32) && (v_count < 11'd48) &&
                         (h_count >= 12'd160) && (h_count < 12'd416)) begin
                vid_pData = {8'h00, 8'h00, h_count[7:0] - 8'd160};
            end else if ((v_count >= 11'd48) && (v_count < 11'd64) &&
                         (h_count >= 12'd160) && (h_count < 12'd416)) begin
                vid_pData = {8'h00, h_count[7:0] - 8'd160, 8'h00};
            end else begin
                vid_pData = {red, blue, green};
            end
        end
    end
endmodule
