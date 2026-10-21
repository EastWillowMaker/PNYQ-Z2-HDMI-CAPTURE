`timescale 1ns/1ps

module lcd_demo_tb #(
    parameter integer SOURCE_WIDTH = 32,
    parameter integer SOURCE_HEIGHT = 16,
    parameter integer PANEL_WIDTH = 32,
    parameter integer PANEL_HEIGHT = 20,
    parameter integer FIT_WIDTH = 8,
    parameter integer FIT_HEIGHT = 4
);
    localparam integer FIT_X_OFFSET = (PANEL_WIDTH - FIT_WIDTH) / 2;
    localparam integer FIT_Y_OFFSET = (PANEL_HEIGHT - FIT_HEIGHT) / 2;
    localparam integer DIAGNOSTIC_BORDER =
        ((FIT_WIDTH >= 8) && (FIT_HEIGHT >= 8)) ? 3 : 1;
    localparam integer PANEL_PIXELS = PANEL_WIDTH * PANEL_HEIGHT;

    reg clk = 1'b0;
    reg rst = 1'b1;
    reg [23:0] pixel_data = 24'd0;
    reg pixel_valid = 1'b0;
    reg pixel_ready = 1'b1;
    reg pixel_sof = 1'b0;
    reg pixel_eol = 1'b0;
    reg receiver_reset = 1'b0;
    reg fifo_fault = 1'b0;
    wire lcd_sck;
    wire lcd_mosi;
    wire lcd_cs;
    wire lcd_dc;
    wire lcd_reset;
    wire touch_cs;
    wire [31:0] status;
    wire [31:0] uploaded_frames;

    integer decoded_words = 0;
    integer pixel_bursts = 0;
    integer payload_count = 0;
    integer window_stage = 0;
    integer window_word_index = 0;
    integer bit_count = 0;
    reg [15:0] shift_word = 16'd0;
    reg [15:0] last_command = 16'd0;
    reg [15:0] x_window [0:3];
    reg [15:0] y_window [0:3];
    reg [15:0] payload [0:PANEL_PIXELS-1];
    reg collecting_pixels = 1'b0;
    reg saw_init_f1 = 1'b0;
    reg saw_init_first_parameter = 1'b0;
    reg saw_correct_window = 1'b0;
    reg init_drain_checked = 1'b0;
    integer i;

    always #5 clk = ~clk;

    lcd_demo #(
        .IN_WIDTH(SOURCE_WIDTH),
        .IN_HEIGHT(SOURCE_HEIGHT),
        .PANEL_WIDTH(PANEL_WIDTH),
        .PANEL_HEIGHT(PANEL_HEIGHT),
        .FIT_WIDTH(FIT_WIDTH),
        .FIT_HEIGHT(FIT_HEIGHT),
        .RESET_HIGH_CYCLES(2),
        .RESET_LOW_CYCLES(2),
        .RESET_RELEASE_CYCLES(2),
        .INIT_SLEEP_CYCLES(2),
        .DISPLAY_WAKE_CYCLES(2)
    ) dut (
        .clk(clk),
        .rst(rst),
        .pixel_data(pixel_data),
        .pixel_valid(pixel_valid),
        .pixel_ready(pixel_ready),
        .pixel_sof(pixel_sof),
        .pixel_eol(pixel_eol),
        .receiver_reset(receiver_reset),
        .fifo_fault(fifo_fault),
        .lcd_sck(lcd_sck),
        .lcd_mosi(lcd_mosi),
        .lcd_cs(lcd_cs),
        .lcd_dc(lcd_dc),
        .lcd_reset(lcd_reset),
        .touch_cs(touch_cs),
        .status(status),
        .uploaded_frames(uploaded_frames)
    );

    always @(posedge lcd_sck) begin
        if (!lcd_cs) begin
            if (bit_count == 15) begin
                shift_word = {shift_word[14:0], lcd_mosi};
                bit_count = 0;
                decoded_words = decoded_words + 1;

                if (!lcd_dc) begin
                    last_command = shift_word;
                    if (shift_word == 16'h00f1)
                        saw_init_f1 = 1'b1;
                    if (saw_init_f1 && shift_word == 16'h0036)
                        saw_init_first_parameter = 1'b1;

                    if (shift_word == 16'h002a) begin
                        window_stage = 1;
                        window_word_index = 0;
                        collecting_pixels = 1'b0;
                    end else if (shift_word == 16'h002b) begin
                        window_stage = 2;
                        window_word_index = 0;
                    end else if (shift_word == 16'h002c) begin
                        if (window_stage != 2 ||
                            x_window[0] != 16'd0 || x_window[1] != 16'd0 ||
                            x_window[2] != ((PANEL_WIDTH - 1) >> 8) ||
                            x_window[3] != ((PANEL_WIDTH - 1) & 16'h00ff) ||
                            y_window[0] != 16'd0 || y_window[1] != 16'd0 ||
                            y_window[2] != ((PANEL_HEIGHT - 1) >> 8) ||
                            y_window[3] != ((PANEL_HEIGHT - 1) & 16'h00ff))
                            $fatal(1, "LCD window command did not cover the panel");
                        saw_correct_window = 1'b1;
                        collecting_pixels = 1'b1;
                        payload_count = 0;
                    end
                end else if (window_stage == 1 && window_word_index < 4) begin
                    x_window[window_word_index] = shift_word;
                    window_word_index = window_word_index + 1;
                end else if (window_stage == 2 && window_word_index < 4) begin
                    y_window[window_word_index] = shift_word;
                    window_word_index = window_word_index + 1;
                end else if (collecting_pixels) begin
                    if (payload_count < PANEL_PIXELS)
                        payload[payload_count] = shift_word;
                    payload_count = payload_count + 1;
                    if (payload_count == PANEL_PIXELS) begin
                        pixel_bursts = pixel_bursts + 1;
                        collecting_pixels = 1'b0;
                    end
                end
                shift_word = 16'd0;
            end else begin
                shift_word = {shift_word[14:0], lcd_mosi};
                bit_count = bit_count + 1;
            end
        end
    end

    always @(negedge lcd_cs) begin
        if (lcd_sck !== 1'b0)
            $fatal(1, "LCD chip select fell while SCK was high");
    end

    always @(posedge clk) begin
        if (touch_cs !== 1'b1)
            $fatal(1, "Touch chip select must remain inactive");
    end

    always @(posedge clk) begin
        if (rst) begin
            init_drain_checked = 1'b0;
        end else begin
            if (dut.state >= 5'd11 && dut.state <= 5'd16 &&
                dut.framebuffer_write_enable_q)
                $fatal(1, "Framebuffer write command overlapped LCD upload");

            if (!init_drain_checked && dut.memory_initialized) begin
                if (dut.framebuffer_write_enable_q)
                    $fatal(1, "Framebuffer init completed with a write pending");
                if (dut.framebuffer[PANEL_PIXELS - 1] !==
                    expected_diagnostic_pixel(PANEL_WIDTH - 1,
                                              PANEL_HEIGHT - 1))
                    $fatal(1, "Final diagnostic framebuffer write did not drain");
                init_drain_checked = 1'b1;
            end
        end
    end

    function [23:0] source_pixel(input integer x, input integer y);
        reg [7:0] red;
        reg [7:0] green;
        reg [7:0] blue;
        begin
            red = x * 17;
            green = y * 31;
            blue = x * 7 + y * 11;
            source_pixel = {red, green, blue};
        end
    endfunction

    function [15:0] expected_pixel(input integer x, input integer y);
        reg [23:0] rgb;
        begin
            rgb = source_pixel(x, y);
            expected_pixel = {rgb[23:19], rgb[15:10], rgb[7:3]};
        end
    endfunction

    function integer expected_source_x(input integer x);
        begin
            if (FIT_WIDTH > 1)
                expected_source_x =
                    (x * (SOURCE_WIDTH - 1) + (FIT_WIDTH - 1) / 2) /
                    (FIT_WIDTH - 1);
            else
                expected_source_x = (SOURCE_WIDTH - 1) / 2;
        end
    endfunction

    function integer expected_source_y(input integer y);
        begin
            if (FIT_HEIGHT > 1)
                expected_source_y =
                    (y * (SOURCE_HEIGHT - 1) + (FIT_HEIGHT - 1) / 2) /
                    (FIT_HEIGHT - 1);
            else
                expected_source_y = (SOURCE_HEIGHT - 1) / 2;
        end
    endfunction

    function [15:0] expected_diagnostic_pixel(
        input integer panel_x,
        input integer panel_y
    );
        integer fit_x;
        integer fit_y;
        begin
            if ((panel_x < FIT_X_OFFSET) ||
                (panel_x >= FIT_X_OFFSET + FIT_WIDTH) ||
                (panel_y < FIT_Y_OFFSET) ||
                (panel_y >= FIT_Y_OFFSET + FIT_HEIGHT)) begin
                expected_diagnostic_pixel = 16'h0000;
            end else begin
                fit_x = panel_x - FIT_X_OFFSET;
                fit_y = panel_y - FIT_Y_OFFSET;
                if ((fit_x < DIAGNOSTIC_BORDER) ||
                    (fit_x >= FIT_WIDTH - DIAGNOSTIC_BORDER) ||
                    (fit_y < DIAGNOSTIC_BORDER) ||
                    (fit_y >= FIT_HEIGHT - DIAGNOSTIC_BORDER) ||
                    ((FIT_WIDTH >= 32) && (FIT_HEIGHT >= 32) &&
                     (fit_x >= 8) && (fit_x < 32) &&
                     (fit_y >= 8) && (fit_y < 32)))
                    expected_diagnostic_pixel = 16'hffff;
                else if (fit_x < (FIT_WIDTH * 1) / 8)
                    expected_diagnostic_pixel = 16'hf800;
                else if (fit_x < (FIT_WIDTH * 2) / 8)
                    expected_diagnostic_pixel = 16'h07e0;
                else if (fit_x < (FIT_WIDTH * 3) / 8)
                    expected_diagnostic_pixel = 16'h001f;
                else if (fit_x < (FIT_WIDTH * 4) / 8)
                    expected_diagnostic_pixel = 16'hffff;
                else if (fit_x < (FIT_WIDTH * 5) / 8)
                    expected_diagnostic_pixel = 16'h0000;
                else if (fit_x < (FIT_WIDTH * 6) / 8)
                    expected_diagnostic_pixel = 16'hffe0;
                else if (fit_x < (FIT_WIDTH * 7) / 8)
                    expected_diagnostic_pixel = 16'h07ff;
                else
                    expected_diagnostic_pixel = 16'hf81f;
            end
        end
    endfunction

    task send_transfer(
        input [23:0] data,
        input sof,
        input eol,
        input fault
    );
        begin
            @(negedge clk);
            pixel_data = data;
            pixel_sof = sof;
            pixel_eol = eol;
            fifo_fault = fault;
            pixel_valid = 1'b1;
            @(negedge clk);
            pixel_valid = 1'b0;
            pixel_sof = 1'b0;
            pixel_eol = 1'b0;
            fifo_fault = 1'b0;
        end
    endtask

    task send_good_frame;
        integer x;
        integer y;
        begin
            for (y = 0; y < SOURCE_HEIGHT; y = y + 1) begin
                for (x = 0; x < SOURCE_WIDTH; x = x + 1) begin
                    send_transfer(source_pixel(x, y), (x == 0 && y == 0),
                                  (x == SOURCE_WIDTH - 1), 1'b0);
                end
            end
        end
    endtask

    task send_fault_frame;
        integer x;
        integer y;
        begin
            for (y = 0; y < SOURCE_HEIGHT; y = y + 1) begin
                for (x = 0; x < SOURCE_WIDTH; x = x + 1) begin
                    send_transfer(source_pixel(x, y), (x == 0 && y == 0),
                                  (x == SOURCE_WIDTH - 1),
                                  (x == 0 && y == 0));
                end
            end
        end
    endtask

    task check_ready_handshake;
        begin
            @(negedge clk);
            pixel_data = source_pixel(0, 0);
            pixel_sof = 1'b1;
            pixel_eol = 1'b0;
            pixel_valid = 1'b1;
            pixel_ready = 1'b0;
            @(negedge clk);
            pixel_valid = 1'b0;
            pixel_sof = 1'b0;
            pixel_ready = 1'b1;
            repeat (3) @(posedge clk);
            if (status[7])
                $fatal(1, "A stalled SOF was captured without a handshake");

            @(negedge clk);
            pixel_data = source_pixel(0, 0);
            pixel_sof = 1'b1;
            pixel_eol = 1'b0;
            pixel_valid = 1'b1;
            pixel_ready = 1'b0;
            @(negedge clk);
            pixel_ready = 1'b1;
            @(negedge clk);
            pixel_valid = 1'b0;
            pixel_sof = 1'b0;
            repeat (3) @(posedge clk);
            if (!status[7])
                $fatal(1, "SOF was not captured when ready accepted it");

            @(negedge clk);
            receiver_reset = 1'b1;
            repeat (2) @(negedge clk);
            receiver_reset = 1'b0;
            repeat (3) @(posedge clk);
            if (status[7])
                $fatal(1, "Receiver reset did not flush the partial frame");
        end
    endtask

    task wait_for_live_upload(input [31:0] expected_count);
        integer timeout;
        begin
            timeout = 0;
            while (uploaded_frames < expected_count && timeout < 500000) begin
                @(posedge clk);
                timeout = timeout + 1;
            end
            if (uploaded_frames != expected_count)
                $fatal(1, "Timed out waiting for live upload %0d", expected_count);
            repeat (4) @(posedge clk);
        end
    endtask

    task wait_lcd_idle;
        integer timeout;
        begin
            timeout = 0;
            while ((lcd_cs !== 1'b1 || lcd_sck !== 1'b0) && timeout < 1000) begin
                @(posedge clk);
                timeout = timeout + 1;
            end
            if (lcd_cs !== 1'b1 || lcd_sck !== 1'b0)
                $fatal(1, "LCD pins did not return to idle");
            repeat (2) @(posedge clk);
        end
    endtask

    initial begin
        repeat (3) @(posedge clk);
        rst = 1'b0;

        wait_for_live_upload(32'd0);
        begin : wait_fallback
            integer timeout;
            timeout = 0;
            while (pixel_bursts < 1 && timeout < 500000) begin
                @(posedge clk);
                timeout = timeout + 1;
            end
            if (pixel_bursts != 1) begin
                $display("state=%0d init=%0d ready=%0d pending=%0d spi_busy=%0d spi_done=%0d spi_start=%0d bits=%0d div=%0d cs=%0d sck=%0d payload=%0d",
                         dut.state, dut.memory_initialized, dut.panel_ready,
                         dut.frame_pending, dut.spi_busy, dut.spi_done,
                         dut.spi_start, dut.spi_bits_remaining, dut.spi_divider,
                         lcd_cs, lcd_sck, payload_count);
                $fatal(1, "Fallback framebuffer did not reach the LCD");
            end
        end
        wait_lcd_idle();

        if (!saw_init_f1 || !saw_init_first_parameter)
            $fatal(1, "LCD init command and parameter were not decoded");
        if (!saw_correct_window)
            $fatal(1, "LCD address window was not decoded");
        for (i = 0; i < PANEL_PIXELS; i = i + 1) begin
            if (payload[i] != expected_diagnostic_pixel(i % PANEL_WIDTH,
                                                        i / PANEL_WIDTH))
                $fatal(1, "Fallback pattern mismatch at panel x=%0d y=%0d",
                       i % PANEL_WIDTH, i / PANEL_WIDTH);
        end
        if (lcd_sck !== 1'b0 || lcd_cs !== 1'b1 || lcd_mosi !== 1'b0 ||
            lcd_reset !== 1'b1) begin
            $display("idle pins: cs=%b sck=%b mosi=%b reset=%b",
                     lcd_cs, lcd_sck, lcd_mosi, lcd_reset);
            $fatal(1, "LCD pins did not return to their idle levels");
        end

        check_ready_handshake();

        send_transfer(24'hffffff, 1'b1, 1'b1, 1'b0);
        repeat (100) @(posedge clk);
        if (uploaded_frames != 32'd0 || pixel_bursts != 1)
            $fatal(1, "Malformed frame was uploaded");

        send_good_frame();
        repeat (100) @(posedge clk);
        if (uploaded_frames != 32'd0 || pixel_bursts != 1)
            $fatal(1, "Frame published before the next SOF boundary");
        send_transfer(24'h123456, 1'b0, 1'b0, 1'b0);
        repeat (100) @(posedge clk);
        if (uploaded_frames != 32'd0 || pixel_bursts != 1)
            $fatal(1, "Overlong frame was uploaded");

        send_good_frame();
        send_transfer(source_pixel(0, 0), 1'b1, 1'b0, 1'b0);
        wait_for_live_upload(32'd1);
        if (pixel_bursts != 2)
            $fatal(1, "Complete source frame was not uploaded exactly once");

        for (i = 0; i < PANEL_PIXELS; i = i + 1) begin
            if (i / PANEL_WIDTH < FIT_Y_OFFSET ||
                i / PANEL_WIDTH >= FIT_Y_OFFSET + FIT_HEIGHT ||
                i % PANEL_WIDTH < FIT_X_OFFSET ||
                i % PANEL_WIDTH >= FIT_X_OFFSET + FIT_WIDTH) begin
                if (payload[i] != 16'h0000)
                    $fatal(1, "Live upload border pixel %0d was not black", i);
            end else if (payload[i] != expected_pixel(
                           expected_source_x(i % PANEL_WIDTH - FIT_X_OFFSET),
                           expected_source_y(i / PANEL_WIDTH - FIT_Y_OFFSET))) begin
                $fatal(1, "RGB565 pixel mismatch at panel x=%0d y=%0d: %h",
                       i % PANEL_WIDTH, i / PANEL_WIDTH, payload[i]);
            end
        end

        send_fault_frame();
        repeat (100) @(posedge clk);
        if (uploaded_frames != 32'd1 || pixel_bursts != 2)
            $fatal(1, "FIFO-faulted frame was uploaded");
        send_transfer(source_pixel(0, 0), 1'b1, 1'b0, 1'b0);
        repeat (100) @(posedge clk);
        if (uploaded_frames != 32'd1 || pixel_bursts != 2)
            $fatal(1, "FIFO-faulted frame was published at its boundary");
        if (status[31:24] != 8'd1 || status[23:16] < 8'd3)
            $fatal(1, "Fault and rejected-frame counters were not updated");

        send_good_frame();
        send_transfer(source_pixel(0, 0), 1'b1, 1'b0, 1'b0);
        wait_for_live_upload(32'd2);
        if (pixel_bursts != 3)
            $fatal(1, "A valid frame did not recover after the FIFO fault");

        send_transfer(source_pixel(0, 0), 1'b1, 1'b0, 1'b0);
        @(negedge clk);
        receiver_reset = 1'b1;
        repeat (2) @(negedge clk);
        receiver_reset = 1'b0;
        send_good_frame();
        send_transfer(source_pixel(0, 0), 1'b1, 1'b0, 1'b0);
        wait_for_live_upload(32'd3);
        if (pixel_bursts != 4)
            $fatal(1, "A valid frame did not recover after receiver reset");

        $display("PASS: SPI init/window/pixels, atomic frames, RGB565, recovery");
        $finish;
    end

    initial begin
        #500000000;
        $fatal(1, "lcd_demo_tb timed out");
    end
endmodule
