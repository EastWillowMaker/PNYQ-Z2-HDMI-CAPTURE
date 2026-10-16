`timescale 1ns/1ps

module bench;
    reg pixel_clk = 1'b0;
    reg async_reset = 1'b1;
    wire [23:0] vid_pData;
    wire vid_pVDE;
    wire vid_pHSync;
    wire vid_pVSync;
    integer image_file;
    integer active_pixels = 0;
    integer x;
    integer y;
    integer frame;
    integer expected_vde;
    integer expected_hsync;
    integer expected_vsync;
    reg [1023:0] output_path;

    always #1 pixel_clk = ~pixel_clk;

    hdmi_test_pattern dut (
        .pixel_clk(pixel_clk),
        .async_reset(async_reset),
        .vid_pData(vid_pData),
        .vid_pVDE(vid_pVDE),
        .vid_pHSync(vid_pHSync),
        .vid_pVSync(vid_pVSync)
    );

    initial begin
        if (!$value$plusargs("OUT=%s", output_path))
            $fatal(1, "pass +OUT=<RGB byte file>");
        image_file = $fopen(output_path, "wb");
        if (image_file == 0)
            $fatal(1, "cannot open output image stream");

        repeat (4) @(negedge pixel_clk);
        async_reset = 1'b0;
        @(posedge vid_pVDE);

        for (frame = 0; frame < 2; frame = frame + 1) begin
            for (y = 0; y < 1125; y = y + 1) begin
                for (x = 0; x < 2200; x = x + 1) begin
                    @(negedge pixel_clk);
                    #0.1;
                    expected_vde = (x < 1920) && (y < 1080);
                    expected_hsync = (x >= 2008) && (x < 2052);
                    expected_vsync = (y >= 1084) && (y < 1089);
                    if (vid_pVDE !== expected_vde[0] ||
                        vid_pHSync !== expected_hsync[0] ||
                        vid_pVSync !== expected_vsync[0])
                        $fatal(1, "timing mismatch frame=%0d x=%0d y=%0d vde=%b hs=%b vs=%b",
                               frame, x, y, vid_pVDE, vid_pHSync, vid_pVSync);
                    if (expected_vde) begin
                        // Convert the serializer's RBG input bytes back to RGB.
                        $fwrite(image_file, "%c%c%c",
                                vid_pData[23:16], vid_pData[7:0], vid_pData[15:8]);
                        active_pixels = active_pixels + 1;
                    end else if (vid_pData !== 24'd0) begin
                        $fatal(1, "nonzero blanking data frame=%0d x=%0d y=%0d",
                               frame, x, y);
                    end
                end
            end
        end
        $fclose(image_file);
        if (active_pixels != 2 * 1920 * 1080)
            $fatal(1, "wrong active pixel count: %0d", active_pixels);

        // Reassert reset during active video, then check the first pixel after
        // the two-stage synchronous release starts a fresh frame.
        repeat (10) @(posedge pixel_clk);
        @(negedge pixel_clk);
        async_reset = 1'b1;
        #0.1;
        if (vid_pVDE !== 1'b0)
            $fatal(1, "active video remained enabled during reset assertion");
        repeat (4) @(negedge pixel_clk);
        async_reset = 1'b0;
        @(posedge vid_pVDE);
        #0.1;
        if (vid_pData !== 24'hffffff)
            $fatal(1, "reset release did not restart frame ID and pixel origin");
        $display("PASS 2 full 2200x1125 frames; timing, blanking, and active pixels checked");
        $finish;
    end

    initial begin
        #20000000;
        $fatal(1, "timeout");
    end
endmodule
