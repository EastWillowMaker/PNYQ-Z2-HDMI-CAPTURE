`timescale 1ns/1ps

module lcd_demo #(
    parameter integer CLK_HZ = 142857132,
    parameter integer IN_WIDTH = 1920,
    parameter integer IN_HEIGHT = 1080,
    parameter integer PANEL_WIDTH = 480,
    parameter integer PANEL_HEIGHT = 320,
    parameter integer FIT_WIDTH = 480,
    parameter integer FIT_HEIGHT = 270,
    parameter integer SPI_HALF_PERIOD = 4,
    parameter integer RESET_HIGH_CYCLES = (CLK_HZ / 1000) * 10,
    parameter integer RESET_LOW_CYCLES = (CLK_HZ / 1000) * 20,
    parameter integer RESET_RELEASE_CYCLES = (CLK_HZ / 1000) * 150,
    parameter integer INIT_SLEEP_CYCLES = (CLK_HZ / 1000) * 255,
    parameter integer DISPLAY_WAKE_CYCLES = (CLK_HZ / 1000) * 100,
    parameter integer FRAME_TIMEOUT_CYCLES = (CLK_HZ / 30) * 2
) (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 clk CLK",
       X_INTERFACE_PARAMETER = "FREQ_HZ 142857132, ASSOCIATED_RESET rst" *)
    input wire clk,
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 rst RST",
       X_INTERFACE_PARAMETER = "POLARITY ACTIVE_HIGH" *)
    input wire rst,
    input wire [23:0] pixel_data,
    input wire pixel_valid,
    input wire pixel_ready,
    input wire pixel_sof,
    input wire pixel_eol,
    input wire receiver_reset,
    input wire fifo_fault,
    output reg lcd_sck,
    output reg lcd_mosi,
    output reg lcd_cs,
    output reg lcd_dc,
    output reg lcd_reset,
    output wire touch_cs,
    output wire [31:0] status,
    output reg [31:0] uploaded_frames
);
    localparam integer FIT_X_OFFSET = (PANEL_WIDTH - FIT_WIDTH) / 2;
    localparam integer FIT_Y_OFFSET = (PANEL_HEIGHT - FIT_HEIGHT) / 2;
    localparam [15:0] PANEL_X_END = PANEL_WIDTH - 1;
    localparam [15:0] PANEL_Y_END = PANEL_HEIGHT - 1;
    localparam integer FRAMEBUFFER_PIXELS = PANEL_WIDTH * PANEL_HEIGHT;
    localparam integer FRAMEBUFFER_ADDR_WIDTH =
        (FRAMEBUFFER_PIXELS <= 2) ? 1 : $clog2(FRAMEBUFFER_PIXELS);
    localparam integer X_DENOMINATOR = (FIT_WIDTH > 1) ? FIT_WIDTH - 1 : 1;
    localparam integer Y_DENOMINATOR = (FIT_HEIGHT > 1) ? FIT_HEIGHT - 1 : 1;
    localparam integer X_COORD_WIDTH = (IN_WIDTH <= 1) ? 1 : $clog2(IN_WIDTH + 1);
    localparam integer Y_COORD_WIDTH = (IN_HEIGHT <= 1) ? 1 : $clog2(IN_HEIGHT + 1);
    localparam integer X_INDEX_WIDTH = (FIT_WIDTH <= 2) ? 1 : $clog2(FIT_WIDTH);
    localparam integer X_ERROR_WIDTH =
        ($clog2(X_DENOMINATOR) < 1) ? 1 : $clog2(X_DENOMINATOR);
    localparam integer Y_ERROR_WIDTH =
        ($clog2(Y_DENOMINATOR) < 1) ? 1 : $clog2(Y_DENOMINATOR);
    localparam integer X_SPAN = IN_WIDTH - 1;
    localparam integer Y_SPAN = IN_HEIGHT - 1;
    localparam integer X_STEP = (FIT_WIDTH > 1) ? X_SPAN / X_DENOMINATOR : 0;
    localparam integer Y_STEP = (FIT_HEIGHT > 1) ? Y_SPAN / Y_DENOMINATOR : 0;
    localparam integer X_REMAINDER =
        (FIT_WIDTH > 1) ? X_SPAN % X_DENOMINATOR : 0;
    localparam integer Y_REMAINDER =
        (FIT_HEIGHT > 1) ? Y_SPAN % Y_DENOMINATOR : 0;
    localparam integer X_TARGET_FIRST = (FIT_WIDTH > 1) ? 0 : X_SPAN / 2;
    localparam integer Y_TARGET_FIRST = (FIT_HEIGHT > 1) ? 0 : Y_SPAN / 2;
    localparam integer X_ERROR_FIRST_VALUE = X_DENOMINATOR / 2;
    localparam integer Y_ERROR_FIRST_VALUE = Y_DENOMINATOR / 2;
    localparam integer X_ERROR_FIRST_SUM = X_ERROR_FIRST_VALUE + X_REMAINDER;
    localparam integer Y_ERROR_FIRST_SUM = Y_ERROR_FIRST_VALUE + Y_REMAINDER;
    localparam integer X_FIRST_CARRY = X_ERROR_FIRST_SUM >= X_DENOMINATOR;
    localparam integer Y_FIRST_CARRY = Y_ERROR_FIRST_SUM >= Y_DENOMINATOR;
    localparam integer X_TARGET_SECOND =
        X_TARGET_FIRST + X_STEP + X_FIRST_CARRY;
    localparam integer Y_TARGET_SECOND =
        Y_TARGET_FIRST + Y_STEP + Y_FIRST_CARRY;
    localparam integer X_ERROR_SECOND_VALUE = X_FIRST_CARRY ?
        X_ERROR_FIRST_SUM - X_DENOMINATOR : X_ERROR_FIRST_SUM;
    localparam integer Y_ERROR_SECOND_VALUE = Y_FIRST_CARRY ?
        Y_ERROR_FIRST_SUM - Y_DENOMINATOR : Y_ERROR_FIRST_SUM;
    localparam [X_COORD_WIDTH-1:0] IN_WIDTH_LAST = IN_WIDTH - 1;
    localparam [Y_COORD_WIDTH-1:0] IN_HEIGHT_LAST = IN_HEIGHT - 1;
    localparam [X_COORD_WIDTH-1:0] X_TARGET_FIRST_N = X_TARGET_FIRST;
    localparam [Y_COORD_WIDTH-1:0] Y_TARGET_FIRST_N = Y_TARGET_FIRST;
    localparam [X_COORD_WIDTH-1:0] X_TARGET_SECOND_N = X_TARGET_SECOND;
    localparam [Y_COORD_WIDTH-1:0] Y_TARGET_SECOND_N = Y_TARGET_SECOND;
    localparam [X_ERROR_WIDTH-1:0] X_ERROR_FIRST = X_ERROR_FIRST_VALUE;
    localparam [Y_ERROR_WIDTH-1:0] Y_ERROR_FIRST = Y_ERROR_FIRST_VALUE;
    localparam [X_ERROR_WIDTH-1:0] X_REMAINDER_N = X_REMAINDER;
    localparam [Y_ERROR_WIDTH-1:0] Y_REMAINDER_N = Y_REMAINDER;
    localparam [X_ERROR_WIDTH:0] X_DENOMINATOR_EXT = X_DENOMINATOR;
    localparam [Y_ERROR_WIDTH:0] Y_DENOMINATOR_EXT = Y_DENOMINATOR;
    localparam [X_ERROR_WIDTH-1:0] X_ERROR_SECOND = X_ERROR_SECOND_VALUE;
    localparam [Y_ERROR_WIDTH-1:0] Y_ERROR_SECOND = Y_ERROR_SECOND_VALUE;
    localparam [X_COORD_WIDTH-1:0] X_STEP_N = X_STEP;
    localparam [Y_COORD_WIDTH-1:0] Y_STEP_N = Y_STEP;
    localparam integer INIT_WORD_COUNT = 71;
    localparam integer DIAGNOSTIC_BORDER =
        ((FIT_WIDTH >= 8) && (FIT_HEIGHT >= 8)) ? 3 : 1;

    localparam [4:0] ST_FRAMEBUFFER_INIT = 5'd0;
    localparam [4:0] ST_POWERUP_WAIT = 5'd1;
    localparam [4:0] ST_RESET_LOW_WAIT = 5'd2;
    localparam [4:0] ST_RESET_RELEASE_WAIT = 5'd3;
    localparam [4:0] ST_INIT_LAUNCH = 5'd4;
    localparam [4:0] ST_INIT_WAIT = 5'd5;
    localparam [4:0] ST_INIT_SLEEP_WAIT = 5'd6;
    localparam [4:0] ST_DISPLAY_ON_LAUNCH = 5'd7;
    localparam [4:0] ST_DISPLAY_ON_WAIT = 5'd8;
    localparam [4:0] ST_DISPLAY_WAKE_WAIT = 5'd9;
    localparam [4:0] ST_WAIT_FRAME = 5'd10;
    localparam [4:0] ST_WINDOW_LAUNCH = 5'd11;
    localparam [4:0] ST_WINDOW_WAIT = 5'd12;
    localparam [4:0] ST_PIXEL_SETUP = 5'd13;
    localparam [4:0] ST_PIXEL_READ = 5'd14;
    localparam [4:0] ST_PIXEL_LAUNCH = 5'd15;
    localparam [4:0] ST_PIXEL_WAIT = 5'd16;

    reg [4:0] state;
    reg [31:0] delay_count;
    reg [6:0] init_word_index;
    reg [3:0] window_word_index;
    reg [FRAMEBUFFER_ADDR_WIDTH-1:0] framebuffer_init_addr;
    reg [15:0] framebuffer_init_x;
    reg [15:0] framebuffer_init_y;
    reg [FRAMEBUFFER_ADDR_WIDTH-1:0] pixel_address;
    reg [15:0] framebuffer_read_data;
    reg [X_COORD_WIDTH-1:0] source_x;
    reg [Y_COORD_WIDTH-1:0] source_y;
    reg [X_COORD_WIDTH-1:0] x_target;
    reg [Y_COORD_WIDTH-1:0] y_target;
    reg [X_ERROR_WIDTH-1:0] x_error;
    reg [Y_ERROR_WIDTH-1:0] y_error;
    reg [X_INDEX_WIDTH-1:0] scaled_x;
    reg [FRAMEBUFFER_ADDR_WIDTH-1:0] capture_row_base;
    reg capture_active;
    reg candidate_bad;
    reg frame_pending;
    reg pending_live;
    reg upload_live;
    reg memory_initialized;
    reg panel_ready;
    reg [7:0] fifo_fault_count;
    reg [7:0] rejected_frame_count;
    reg previous_fifo_fault;
    reg [31:0] frame_idle_count;
    reg await_boundary;

    reg spi_busy;
    reg spi_done;
    reg spi_start;
    reg [15:0] spi_tx_word;
    reg [15:0] spi_shift_word;
    reg [4:0] spi_bits_remaining;
    reg [2:0] spi_divider;

    (* ram_style = "block" *) reg [15:0] framebuffer [0:FRAMEBUFFER_PIXELS-1];

    wire stream_fire = pixel_valid && pixel_ready;
    wire capture_enabled = (state == ST_WAIT_FRAME) && !frame_pending;
    wire frame_pixel = capture_enabled && stream_fire && !receiver_reset &&
                       (pixel_sof || capture_active);
    wire [X_COORD_WIDTH-1:0] current_source_x = pixel_sof ?
        {X_COORD_WIDTH{1'b0}} : source_x;
    wire [Y_COORD_WIDTH-1:0] current_source_y = pixel_sof ?
        {Y_COORD_WIDTH{1'b0}} : source_y;
    wire [X_INDEX_WIDTH-1:0] current_scaled_x = pixel_sof ?
        {X_INDEX_WIDTH{1'b0}} : scaled_x;
    wire [FRAMEBUFFER_ADDR_WIDTH-1:0] current_row_base = pixel_sof ?
        ((FIT_Y_OFFSET * PANEL_WIDTH) + FIT_X_OFFSET) : capture_row_base;
    wire current_row_selected = pixel_sof ? (Y_TARGET_FIRST == 0) :
                                (source_y == y_target);
    wire [X_ERROR_WIDTH:0] x_error_sum =
        {1'b0, x_error} + {1'b0, X_REMAINDER_N};
    wire [Y_ERROR_WIDTH:0] y_error_sum =
        {1'b0, y_error} + {1'b0, Y_REMAINDER_N};
    wire x_carry = x_error_sum >= X_DENOMINATOR_EXT;
    wire y_carry = y_error_sum >= Y_DENOMINATOR_EXT;
    wire [X_COORD_WIDTH-1:0] x_target_after_sample = x_target + X_STEP_N + x_carry;
    wire [Y_COORD_WIDTH-1:0] y_target_after_sample = y_target + Y_STEP_N + y_carry;
    wire [X_ERROR_WIDTH-1:0] x_error_after_sample =
        x_carry ? x_error_sum - X_DENOMINATOR_EXT :
                  x_error_sum[X_ERROR_WIDTH-1:0];
    wire [Y_ERROR_WIDTH-1:0] y_error_after_sample =
        y_carry ? y_error_sum - Y_DENOMINATOR_EXT :
                  y_error_sum[Y_ERROR_WIDTH-1:0];
    wire x_sample = pixel_sof ? (X_TARGET_FIRST == 0) : (source_x == x_target);
    wire [Y_COORD_WIDTH-1:0] source_y_after_line = current_source_y + 1'b1;
    wire eol_matches = (current_source_x < IN_WIDTH) &&
                       (pixel_eol == (current_source_x == IN_WIDTH_LAST));
    wire [FRAMEBUFFER_ADDR_WIDTH-1:0] sample_address =
        current_row_base + current_scaled_x;
    wire sample_write = frame_pixel &&
        (pixel_sof || !candidate_bad) && !fifo_fault && eol_matches &&
        current_row_selected && x_sample && !await_boundary;
    wire [15:0] rgb565_pixel =
        {pixel_data[23:19], pixel_data[15:10], pixel_data[7:3]};
    wire framebuffer_init_write = state == ST_FRAMEBUFFER_INIT;
    wire framebuffer_write_enable = !rst &&
        (framebuffer_init_write || sample_write);
    wire [FRAMEBUFFER_ADDR_WIDTH-1:0] framebuffer_write_address =
        framebuffer_init_write ? framebuffer_init_addr : sample_address;
    wire [15:0] framebuffer_write_data = framebuffer_init_write ?
        diagnostic_pixel(framebuffer_init_x, framebuffer_init_y) : rgb565_pixel;
    wire [16:0] init_item = init_word(init_word_index);
    wire [16:0] window_item = window_word(window_word_index);

    assign touch_cs = 1'b1;
    assign status[4:0] = state;
    assign status[5] = memory_initialized;
    assign status[6] = panel_ready;
    assign status[7] = capture_active;
    assign status[8] = candidate_bad;
    assign status[9] = frame_pending && pending_live;
    assign status[10] = receiver_reset;
    assign status[11] = spi_busy;
    assign status[12] = lcd_reset;
    assign status[13] = await_boundary;
    assign status[15:14] = 2'b00;
    assign status[23:16] = rejected_frame_count;
    assign status[31:24] = fifo_fault_count;

    function [16:0] init_word(input [6:0] index);
        begin
            init_word = {1'b0, 16'h0000};
            case (index)
                0:  init_word = {1'b0, 16'h00f1};
                1:  init_word = {1'b1, 16'h0036};
                2:  init_word = {1'b1, 16'h0004};
                3:  init_word = {1'b1, 16'h0000};
                4:  init_word = {1'b1, 16'h003c};
                5:  init_word = {1'b1, 16'h000f};
                6:  init_word = {1'b1, 16'h008f};
                7:  init_word = {1'b0, 16'h00f2};
                8:  init_word = {1'b1, 16'h0018};
                9:  init_word = {1'b1, 16'h00a3};
                10: init_word = {1'b1, 16'h0012};
                11: init_word = {1'b1, 16'h0002};
                12: init_word = {1'b1, 16'h00b2};
                13: init_word = {1'b1, 16'h0012};
                14: init_word = {1'b1, 16'h00ff};
                15: init_word = {1'b1, 16'h0010};
                16: init_word = {1'b1, 16'h0000};
                17: init_word = {1'b0, 16'h00f8};
                18: init_word = {1'b1, 16'h0021};
                19: init_word = {1'b1, 16'h0004};
                20: init_word = {1'b0, 16'h00f9};
                21: init_word = {1'b1, 16'h0000};
                22: init_word = {1'b1, 16'h0008};
                23: init_word = {1'b0, 16'h0036};
                24: init_word = {1'b1, 16'h0008};
                25: init_word = {1'b0, 16'h00b4};
                26: init_word = {1'b1, 16'h0000};
                27: init_word = {1'b0, 16'h00c1};
                28: init_word = {1'b1, 16'h0041};
                29: init_word = {1'b0, 16'h00c5};
                30: init_word = {1'b1, 16'h0000};
                31: init_word = {1'b1, 16'h0091};
                32: init_word = {1'b1, 16'h0080};
                33: init_word = {1'b1, 16'h0000};
                34: init_word = {1'b0, 16'h00e0};
                35: init_word = {1'b1, 16'h000f};
                36: init_word = {1'b1, 16'h001f};
                37: init_word = {1'b1, 16'h001c};
                38: init_word = {1'b1, 16'h000c};
                39: init_word = {1'b1, 16'h000f};
                40: init_word = {1'b1, 16'h0008};
                41: init_word = {1'b1, 16'h0048};
                42: init_word = {1'b1, 16'h0098};
                43: init_word = {1'b1, 16'h0037};
                44: init_word = {1'b1, 16'h000a};
                45: init_word = {1'b1, 16'h0013};
                46: init_word = {1'b1, 16'h0004};
                47: init_word = {1'b1, 16'h0011};
                48: init_word = {1'b1, 16'h000d};
                49: init_word = {1'b1, 16'h0000};
                50: init_word = {1'b0, 16'h00e1};
                51: init_word = {1'b1, 16'h000f};
                52: init_word = {1'b1, 16'h0032};
                53: init_word = {1'b1, 16'h002e};
                54: init_word = {1'b1, 16'h000b};
                55: init_word = {1'b1, 16'h000d};
                56: init_word = {1'b1, 16'h0005};
                57: init_word = {1'b1, 16'h0047};
                58: init_word = {1'b1, 16'h0075};
                59: init_word = {1'b1, 16'h0037};
                60: init_word = {1'b1, 16'h0006};
                61: init_word = {1'b1, 16'h0010};
                62: init_word = {1'b1, 16'h0003};
                63: init_word = {1'b1, 16'h0024};
                64: init_word = {1'b1, 16'h0020};
                65: init_word = {1'b1, 16'h0000};
                66: init_word = {1'b0, 16'h003a};
                67: init_word = {1'b1, 16'h0055};
                68: init_word = {1'b0, 16'h0011};
                69: init_word = {1'b0, 16'h0036};
                70: init_word = {1'b1, 16'h0028};
                default: init_word = {1'b0, 16'h0000};
            endcase
        end
    endfunction

    function [16:0] window_word(input [3:0] index);
        begin
            case (index)
                0:  window_word = {1'b0, 16'h002a};
                1:  window_word = {1'b1, 16'h0000};
                2:  window_word = {1'b1, 16'h0000};
                3:  window_word = {1'b1, 8'd0, PANEL_X_END[15:8]};
                4:  window_word = {1'b1, 8'd0, PANEL_X_END[7:0]};
                5:  window_word = {1'b0, 16'h002b};
                6:  window_word = {1'b1, 16'h0000};
                7:  window_word = {1'b1, 16'h0000};
                8:  window_word = {1'b1, 8'd0, PANEL_Y_END[15:8]};
                9:  window_word = {1'b1, 8'd0, PANEL_Y_END[7:0]};
                10: window_word = {1'b0, 16'h002c};
                default: window_word = {1'b0, 16'h0000};
            endcase
        end
    endfunction

    function [15:0] diagnostic_pixel(input [15:0] x, input [15:0] y);
        reg [15:0] fit_x;
        reg [15:0] fit_y;
        begin
            fit_x = x - FIT_X_OFFSET;
            fit_y = y - FIT_Y_OFFSET;
            if ((x < FIT_X_OFFSET) || (x >= FIT_X_OFFSET + FIT_WIDTH) ||
                (y < FIT_Y_OFFSET) || (y >= FIT_Y_OFFSET + FIT_HEIGHT))
                diagnostic_pixel = 16'h0000;
            else if ((fit_x < DIAGNOSTIC_BORDER) ||
                     (fit_x >= FIT_WIDTH - DIAGNOSTIC_BORDER) ||
                     (fit_y < DIAGNOSTIC_BORDER) ||
                     (fit_y >= FIT_HEIGHT - DIAGNOSTIC_BORDER) ||
                     ((FIT_WIDTH >= 32) && (FIT_HEIGHT >= 32) &&
                      (fit_x >= 8) && (fit_x < 32) &&
                      (fit_y >= 8) && (fit_y < 32)))
                diagnostic_pixel = 16'hffff;
            else if (fit_x < (FIT_WIDTH * 1) / 8)
                diagnostic_pixel = 16'hf800;
            else if (fit_x < (FIT_WIDTH * 2) / 8)
                diagnostic_pixel = 16'h07e0;
            else if (fit_x < (FIT_WIDTH * 3) / 8)
                diagnostic_pixel = 16'h001f;
            else if (fit_x < (FIT_WIDTH * 4) / 8)
                diagnostic_pixel = 16'hffff;
            else if (fit_x < (FIT_WIDTH * 5) / 8)
                diagnostic_pixel = 16'h0000;
            else if (fit_x < (FIT_WIDTH * 6) / 8)
                diagnostic_pixel = 16'hffe0;
            else if (fit_x < (FIT_WIDTH * 7) / 8)
                diagnostic_pixel = 16'h07ff;
            else
                diagnostic_pixel = 16'hf81f;
        end
    endfunction

    always @(posedge clk) begin
        if (rst) begin
            state <= ST_FRAMEBUFFER_INIT;
            delay_count <= 32'd0;
            init_word_index <= 7'd0;
            window_word_index <= 4'd0;
            framebuffer_init_addr <= {FRAMEBUFFER_ADDR_WIDTH{1'b0}};
            framebuffer_init_x <= 16'd0;
            framebuffer_init_y <= 16'd0;
            pixel_address <= {FRAMEBUFFER_ADDR_WIDTH{1'b0}};
            source_x <= {X_COORD_WIDTH{1'b0}};
            source_y <= {Y_COORD_WIDTH{1'b0}};
            x_target <= X_TARGET_FIRST_N;
            y_target <= Y_TARGET_FIRST_N;
            x_error <= X_ERROR_FIRST;
            y_error <= Y_ERROR_FIRST;
            scaled_x <= {X_INDEX_WIDTH{1'b0}};
            capture_row_base <= {FRAMEBUFFER_ADDR_WIDTH{1'b0}};
            capture_active <= 1'b0;
            candidate_bad <= 1'b0;
            frame_pending <= 1'b0;
            pending_live <= 1'b0;
            upload_live <= 1'b0;
            memory_initialized <= 1'b0;
            panel_ready <= 1'b0;
            fifo_fault_count <= 8'd0;
            rejected_frame_count <= 8'd0;
            previous_fifo_fault <= 1'b0;
            frame_idle_count <= 32'd0;
            await_boundary <= 1'b0;
            uploaded_frames <= 32'd0;
            spi_start <= 1'b0;
            spi_tx_word <= 16'd0;
            lcd_cs <= 1'b1;
            lcd_dc <= 1'b1;
            lcd_reset <= 1'b0;
        end else begin
            spi_start <= 1'b0;

            if (fifo_fault && !previous_fifo_fault &&
                fifo_fault_count != 8'hff)
                fifo_fault_count <= fifo_fault_count + 8'd1;
            previous_fifo_fault <= fifo_fault;

            if (fifo_fault && capture_active && !pixel_sof)
                candidate_bad <= 1'b1;

            if (receiver_reset || !capture_active || state != ST_WAIT_FRAME) begin
                frame_idle_count <= 32'd0;
            end else if (frame_pixel) begin
                frame_idle_count <= 32'd0;
            end else if (frame_idle_count + 1 >= FRAME_TIMEOUT_CYCLES) begin
                capture_active <= 1'b0;
                candidate_bad <= 1'b0;
                await_boundary <= 1'b0;
                frame_idle_count <= 32'd0;
                if (rejected_frame_count != 8'hff)
                    rejected_frame_count <= rejected_frame_count + 8'd1;
            end else begin
                frame_idle_count <= frame_idle_count + 1'b1;
            end

            if (receiver_reset) begin
                if (capture_active && rejected_frame_count != 8'hff)
                    rejected_frame_count <= rejected_frame_count + 8'd1;
                capture_active <= 1'b0;
                candidate_bad <= 1'b0;
                await_boundary <= 1'b0;
                source_x <= {X_COORD_WIDTH{1'b0}};
                source_y <= {Y_COORD_WIDTH{1'b0}};
                x_target <= X_TARGET_FIRST_N;
                y_target <= Y_TARGET_FIRST_N;
                x_error <= X_ERROR_FIRST;
                y_error <= Y_ERROR_FIRST;
                scaled_x <= {X_INDEX_WIDTH{1'b0}};
            end

            case (state)
                ST_FRAMEBUFFER_INIT: begin
                    if (framebuffer_init_addr == FRAMEBUFFER_PIXELS - 1) begin
                        framebuffer_init_addr <= {FRAMEBUFFER_ADDR_WIDTH{1'b0}};
                        framebuffer_init_x <= 16'd0;
                        framebuffer_init_y <= 16'd0;
                        memory_initialized <= 1'b1;
                        frame_pending <= 1'b1;
                        pending_live <= 1'b0;
                        lcd_reset <= 1'b1;
                        delay_count <= 32'd0;
                        state <= ST_POWERUP_WAIT;
                    end else begin
                        framebuffer_init_addr <= framebuffer_init_addr + 1'b1;
                        if (framebuffer_init_x == PANEL_WIDTH - 1) begin
                            framebuffer_init_x <= 16'd0;
                            framebuffer_init_y <= framebuffer_init_y + 1'b1;
                        end else begin
                            framebuffer_init_x <= framebuffer_init_x + 1'b1;
                        end
                    end
                end

                ST_POWERUP_WAIT: begin
                    if (delay_count + 1 >= RESET_HIGH_CYCLES) begin
                        delay_count <= 32'd0;
                        lcd_reset <= 1'b0;
                        state <= ST_RESET_LOW_WAIT;
                    end else begin
                        delay_count <= delay_count + 1'b1;
                    end
                end

                ST_RESET_LOW_WAIT: begin
                    if (delay_count + 1 >= RESET_LOW_CYCLES) begin
                        delay_count <= 32'd0;
                        lcd_reset <= 1'b1;
                        state <= ST_RESET_RELEASE_WAIT;
                    end else begin
                        delay_count <= delay_count + 1'b1;
                    end
                end

                ST_RESET_RELEASE_WAIT: begin
                    if (delay_count + 1 >= RESET_RELEASE_CYCLES) begin
                        delay_count <= 32'd0;
                        init_word_index <= 7'd0;
                        state <= ST_INIT_LAUNCH;
                    end else begin
                        delay_count <= delay_count + 1'b1;
                    end
                end

                ST_INIT_LAUNCH: begin
                    lcd_dc <= init_item[16];
                    lcd_cs <= 1'b0;
                    spi_tx_word <= init_item[15:0];
                    spi_start <= 1'b1;
                    state <= ST_INIT_WAIT;
                end

                ST_INIT_WAIT: begin
                    if (spi_done) begin
                        lcd_cs <= 1'b1;
                        if (init_word_index == INIT_WORD_COUNT - 1) begin
                            delay_count <= 32'd0;
                            state <= ST_INIT_SLEEP_WAIT;
                        end else begin
                            init_word_index <= init_word_index + 1'b1;
                            state <= ST_INIT_LAUNCH;
                        end
                    end
                end

                ST_INIT_SLEEP_WAIT: begin
                    if (delay_count + 1 >= INIT_SLEEP_CYCLES) begin
                        delay_count <= 32'd0;
                        state <= ST_DISPLAY_ON_LAUNCH;
                    end else begin
                        delay_count <= delay_count + 1'b1;
                    end
                end

                ST_DISPLAY_ON_LAUNCH: begin
                    lcd_dc <= 1'b0;
                    lcd_cs <= 1'b0;
                    spi_tx_word <= 16'h0029;
                    spi_start <= 1'b1;
                    state <= ST_DISPLAY_ON_WAIT;
                end

                ST_DISPLAY_ON_WAIT: begin
                    if (spi_done) begin
                        lcd_cs <= 1'b1;
                        delay_count <= 32'd0;
                        state <= ST_DISPLAY_WAKE_WAIT;
                    end
                end

                ST_DISPLAY_WAKE_WAIT: begin
                    if (delay_count + 1 >= DISPLAY_WAKE_CYCLES) begin
                        delay_count <= 32'd0;
                        panel_ready <= 1'b1;
                        state <= ST_WAIT_FRAME;
                    end else begin
                        delay_count <= delay_count + 1'b1;
                    end
                end

                ST_WAIT_FRAME: begin
                    if (frame_pending) begin
                        frame_pending <= 1'b0;
                        upload_live <= pending_live;
                        window_word_index <= 4'd0;
                        state <= ST_WINDOW_LAUNCH;
                    end
                end

                ST_WINDOW_LAUNCH: begin
                    lcd_dc <= window_item[16];
                    lcd_cs <= 1'b0;
                    spi_tx_word <= window_item[15:0];
                    spi_start <= 1'b1;
                    state <= ST_WINDOW_WAIT;
                end

                ST_WINDOW_WAIT: begin
                    if (spi_done) begin
                        lcd_cs <= 1'b1;
                        if (window_word_index == 4'd10) begin
                            pixel_address <= {FRAMEBUFFER_ADDR_WIDTH{1'b0}};
                            state <= ST_PIXEL_SETUP;
                        end else begin
                            window_word_index <= window_word_index + 1'b1;
                            state <= ST_WINDOW_LAUNCH;
                        end
                    end
                end

                ST_PIXEL_SETUP: begin
                    lcd_dc <= 1'b1;
                    lcd_cs <= 1'b0;
                    state <= ST_PIXEL_READ;
                end

                ST_PIXEL_READ: begin
                    state <= ST_PIXEL_LAUNCH;
                end

                ST_PIXEL_LAUNCH: begin
                    spi_tx_word <= framebuffer_read_data;
                    spi_start <= 1'b1;
                    state <= ST_PIXEL_WAIT;
                end

                ST_PIXEL_WAIT: begin
                    if (spi_done) begin
                        if (pixel_address == FRAMEBUFFER_PIXELS - 1) begin
                            lcd_cs <= 1'b1;
                            if (upload_live)
                                uploaded_frames <= uploaded_frames + 32'd1;
                            state <= ST_WAIT_FRAME;
                        end else begin
                            pixel_address <= pixel_address + 1'b1;
                            state <= ST_PIXEL_READ;
                        end
                    end
                end

                default: begin
                    state <= ST_FRAMEBUFFER_INIT;
                    lcd_cs <= 1'b1;
                end
            endcase

            if (receiver_reset && state == ST_WAIT_FRAME) begin
                capture_active <= 1'b0;
                candidate_bad <= 1'b0;
                await_boundary <= 1'b0;
            end else if (frame_pixel) begin
                frame_idle_count <= 32'd0;
                if (await_boundary) begin
                    capture_active <= 1'b0;
                    await_boundary <= 1'b0;
                    if (pixel_sof) begin
                        if (!candidate_bad) begin
                            frame_pending <= 1'b1;
                            pending_live <= 1'b1;
                        end else if (rejected_frame_count != 8'hff) begin
                            rejected_frame_count <= rejected_frame_count + 8'd1;
                        end
                        candidate_bad <= 1'b0;
                    end else begin
                        candidate_bad <= 1'b1;
                        if (rejected_frame_count != 8'hff)
                            rejected_frame_count <= rejected_frame_count + 8'd1;
                    end
                end else begin
                    if (pixel_sof) begin
                        if (capture_active && rejected_frame_count != 8'hff)
                            rejected_frame_count <= rejected_frame_count + 8'd1;
                        candidate_bad <= fifo_fault;
                        capture_active <= 1'b1;
                    end else if (fifo_fault) begin
                        candidate_bad <= 1'b1;
                    end

                    if (!eol_matches) begin
                        candidate_bad <= 1'b1;
                        capture_active <= 1'b0;
                        await_boundary <= 1'b0;
                        if (rejected_frame_count != 8'hff)
                            rejected_frame_count <= rejected_frame_count + 8'd1;
                    end else begin
                        if (x_sample) begin
                            scaled_x <= current_scaled_x + 1'b1;
                            if (FIT_WIDTH > 1) begin
                                if (pixel_sof) begin
                                    x_target <= X_TARGET_SECOND_N;
                                    x_error <= X_ERROR_SECOND;
                                end else begin
                                    x_target <= x_target_after_sample;
                                    x_error <= x_error_after_sample;
                                end
                            end
                        end

                        if (pixel_eol) begin
                            source_x <= {X_COORD_WIDTH{1'b0}};
                            x_target <= X_TARGET_FIRST_N;
                            x_error <= X_ERROR_FIRST;
                            scaled_x <= {X_INDEX_WIDTH{1'b0}};
                            if (current_source_y == IN_HEIGHT_LAST) begin
                                capture_active <= 1'b1;
                                await_boundary <= 1'b1;
                            end else begin
                                source_y <= source_y_after_line;
                                if (current_row_selected && FIT_HEIGHT > 1) begin
                                    if (pixel_sof) begin
                                        y_target <= Y_TARGET_SECOND_N;
                                        y_error <= Y_ERROR_SECOND;
                                    end else begin
                                        y_target <= y_target_after_sample;
                                        y_error <= y_error_after_sample;
                                    end
                                    capture_row_base <=
                                        current_row_base + PANEL_WIDTH;
                                end
                            end
                        end else begin
                            source_x <= current_source_x + 1'b1;
                        end

                        if (pixel_sof) begin
                            source_y <= {Y_COORD_WIDTH{1'b0}};
                            y_target <= Y_TARGET_FIRST_N;
                            y_error <= Y_ERROR_FIRST;
                            capture_row_base <=
                                (FIT_Y_OFFSET * PANEL_WIDTH) + FIT_X_OFFSET;
                        end
                    end
                end
            end
        end
    end

    always @(posedge clk) begin
        if (framebuffer_write_enable)
            framebuffer[framebuffer_write_address] <= framebuffer_write_data;
    end

    always @(posedge clk) begin
        if (!rst && state == ST_PIXEL_READ)
            framebuffer_read_data <= framebuffer[pixel_address];
    end

    always @(posedge clk) begin
        if (rst) begin
            spi_busy <= 1'b0;
            spi_done <= 1'b0;
            spi_shift_word <= 16'd0;
            spi_bits_remaining <= 5'd0;
            spi_divider <= 3'd0;
            lcd_sck <= 1'b0;
            lcd_mosi <= 1'b0;
        end else begin
            spi_done <= 1'b0;
            if (spi_start && !spi_busy) begin
                spi_busy <= 1'b1;
                spi_shift_word <= spi_tx_word;
                spi_bits_remaining <= 5'd16;
                spi_divider <= 3'd0;
                lcd_sck <= 1'b0;
                lcd_mosi <= spi_tx_word[15];
            end else if (spi_busy) begin
                if (spi_divider == SPI_HALF_PERIOD - 1) begin
                    spi_divider <= 3'd0;
                    if (!lcd_sck) begin
                        lcd_sck <= 1'b1;
                    end else begin
                        lcd_sck <= 1'b0;
                        spi_shift_word <= {spi_shift_word[14:0], 1'b0};
                        if (spi_bits_remaining == 1) begin
                            spi_bits_remaining <= 5'd0;
                            spi_busy <= 1'b0;
                            spi_done <= 1'b1;
                        end else begin
                            spi_bits_remaining <= spi_bits_remaining - 1'b1;
                            lcd_mosi <= spi_shift_word[14];
                        end
                    end
                end else begin
                    spi_divider <= spi_divider + 1'b1;
                end
            end else begin
                lcd_sck <= 1'b0;
                lcd_mosi <= 1'b0;
            end
        end
    end
endmodule
