# Optional fixed 1080p30 pattern source for a board-side HDMI OUT -> HDMI IN
# loop.  This file is sourced only when hdmi_output=1 on a 1080p30 build.
if {![info exists hdmi_output] || !$hdmi_output} {
    return
}
if {![info exists mode] || $mode ne "1080p30"} {
    error "HDMI test output requires the 1080p30 profile"
}
if {![info exists ps7_0]} {
    error "HDMI test output requires the configured PS7 block"
}

# The build stages these project-owned sources before sourcing this file.
foreach source_file [list \
    [file join $output tx hdmi_test_clock.v] \
    [file join $output tx hdmi_test_pattern.v]] {
    if {![file isfile $source_file]} {
        error "Missing staged HDMI output RTL: $source_file"
    }
}

set tx_clock [create_bd_cell -type module -reference hdmi_test_clock hdmi_test_clock]
set tx_pattern [create_bd_cell -type module -reference hdmi_test_pattern hdmi_test_pattern]
set tx_encoder [create_bd_cell -type ip -vlnv digilentinc.com:ip:rgb2dvi:1.2 hdmi_out_tx]
set_property -dict [list \
    CONFIG.kClkRange {2} \
    CONFIG.kGenerateSerialClk {false} \
    CONFIG.kRstActiveHigh {true}] $tx_encoder

# FCLK0 is the independent 100 MHz output reference.  The TX serializer uses
# the clock module's MMCM -> BUFIO and BUFR /5 pair; it does not use RX PixelClk
# or the 142.857 MHz video/DMA clock.
connect_bd_net [get_bd_pins $ps7_0/FCLK_CLK0] \
    [get_bd_pins hdmi_test_clock/ref_clk_100]
connect_bd_net [get_bd_pins $ps7_0/FCLK_RESET0_N] \
    [get_bd_pins hdmi_test_clock/resetn]
connect_bd_net [get_bd_pins hdmi_test_clock/pixel_clk] \
    [get_bd_pins hdmi_test_pattern/pixel_clk] \
    [get_bd_pins hdmi_out_tx/PixelClk]
connect_bd_net [get_bd_pins hdmi_test_clock/serial_clk] \
    [get_bd_pins hdmi_out_tx/SerialClk]
connect_bd_net [get_bd_pins hdmi_test_clock/serializer_reset] \
    [get_bd_pins hdmi_test_pattern/arst] \
    [get_bd_pins hdmi_out_tx/aRst]
connect_bd_net [get_bd_pins hdmi_test_pattern/vid_pData] \
    [get_bd_pins hdmi_out_tx/vid_pData]
connect_bd_net [get_bd_pins hdmi_test_pattern/vid_pVDE] \
    [get_bd_pins hdmi_out_tx/vid_pVDE]
connect_bd_net [get_bd_pins hdmi_test_pattern/vid_pHSync] \
    [get_bd_pins hdmi_out_tx/vid_pHSync]
connect_bd_net [get_bd_pins hdmi_test_pattern/vid_pVSync] \
    [get_bd_pins hdmi_out_tx/vid_pVSync]

# Use the pinned board interface type so its DATA_P/N and CLK_P/N mappings
# resolve to the existing HDMI TX XDC names.
create_bd_intf_port -mode Master \
    -vlnv digilentinc.com:interface:tmds_rtl:1.0 hdmi_out
connect_bd_intf_net [get_bd_intf_ports hdmi_out] \
    [get_bd_intf_pins hdmi_out_tx/TMDS]

# TUL names R19 HDMI_TX_HPDN; the manual describes it as an inverted HPD input.
# Keep the constrained input visible, but this fixed-mode transmitter does not
# read EDID or stop on unplug.  The pinned upstream BD instead drives this pin,
# so avoid applying that conflicting direction here.
create_bd_port -dir I -from 0 -to 0 hdmi_out_hpd
