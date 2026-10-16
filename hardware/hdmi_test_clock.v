// Fixed 1080p30 TMDS clocks for the optional PYNQ-Z2 output fixture.
// The clock pair follows PYNQ's pinned axi_dynclk MMCM -> BUFIO/BUFR path.
module hdmi_test_clock (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 ref_clk_100 CLK",
       X_INTERFACE_PARAMETER = "XIL_INTERFACENAME ref_clk_100, FREQ_HZ 100000000" *)
    input  wire ref_clk_100,
    // This resets only the MMCM primitive; serializer_reset resets the clock
    // consumers after lock and owns their pixel/serial clock association.
    (* X_INTERFACE_IGNORE = "true" *)
    input  wire resetn,
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 pixel_clk CLK",
       X_INTERFACE_PARAMETER = "XIL_INTERFACENAME pixel_clk, FREQ_HZ 74250000, ASSOCIATED_RESET serializer_reset" *)
    output wire pixel_clk,
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 serial_clk CLK",
       X_INTERFACE_PARAMETER = "XIL_INTERFACENAME serial_clk, FREQ_HZ 371250000, ASSOCIATED_RESET serializer_reset" *)
    output wire serial_clk,
    output wire locked,
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 serializer_reset RST",
       X_INTERFACE_PARAMETER = "XIL_INTERFACENAME serializer_reset, POLARITY ACTIVE_HIGH" *)
    output wire serializer_reset
);
    // 100 MHz * 37.125 / 5 = 742.5 MHz VCO.  CLKOUT0 / 2 is
    // 371.25 MHz; the BUFR then divides it by five for 74.25 MHz pixels.
    wire mmcm_clk;
    wire mmcm_fb_raw;
    wire mmcm_fb;
    wire mmcm_locked;

    MMCME2_ADV #(
        .BANDWIDTH("OPTIMIZED"),
        .CLKFBOUT_MULT_F(37.125),
        .CLKFBOUT_PHASE(0.0),
        .CLKIN1_PERIOD(10.000),
        .CLKOUT0_DIVIDE_F(2.000),
        .CLKOUT0_DUTY_CYCLE(0.5),
        .CLKOUT0_PHASE(0.0),
        .DIVCLK_DIVIDE(5),
        .STARTUP_WAIT("FALSE")
    ) mmcm (
        .CLKFBOUT(mmcm_fb_raw),
        .CLKFBOUTB(),
        .CLKOUT0(mmcm_clk),
        .CLKOUT0B(),
        .CLKOUT1(),
        .CLKOUT1B(),
        .CLKOUT2(),
        .CLKOUT2B(),
        .CLKOUT3(),
        .CLKOUT3B(),
        .CLKOUT4(),
        .CLKOUT5(),
        .CLKOUT6(),
        .CLKFBIN(mmcm_fb),
        .CLKIN1(ref_clk_100),
        .CLKIN2(1'b0),
        .CLKINSEL(1'b1),
        .DADDR(7'b0),
        .DCLK(ref_clk_100),
        .DEN(1'b0),
        .DI(16'b0),
        .DWE(1'b0),
        .DO(),
        .DRDY(),
        .LOCKED(mmcm_locked),
        .PSCLK(1'b0),
        .PSEN(1'b0),
        .PSINCDEC(1'b0),
        .PSDONE(),
        .PWRDWN(1'b0),
        .RST(~resetn),
        .CLKINSTOPPED(),
        .CLKFBSTOPPED()
    );

    BUFG feedback_buffer (
        .I(mmcm_fb_raw),
        .O(mmcm_fb)
    );

    // OSERDESE2 requires a local I/O clock and a matching /5 CLKDIV clock.
    BUFIO serial_buffer (
        .I(mmcm_clk),
        .O(serial_clk)
    );

    BUFR #(
        .BUFR_DIVIDE("5"),
        .SIM_DEVICE("7SERIES")
    ) pixel_buffer (
        .I(mmcm_clk),
        .CE(1'b1),
        .CLR(~mmcm_locked),
        .O(pixel_clk)
    );

    assign locked = mmcm_locked;
    // Assert reset when PS clock reset is active or the MMCM loses lock.
    assign serializer_reset = ~(resetn & mmcm_locked);
endmodule
