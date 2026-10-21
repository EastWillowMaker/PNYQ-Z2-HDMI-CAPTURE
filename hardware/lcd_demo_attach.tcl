# Optional bring-up branch; capture.tcl sources this before address assignment.
set demo_dir [file dirname [info script]]
add_files [file join $demo_dir lcd_demo.v]
add_files [file join $demo_dir lcd_demo_faults.v]
add_files -fileset constrs_1 [file join $demo_dir lcd_demo.xdc]
update_compile_order -fileset sources_1
create_bd_cell -type module -reference lcd_demo video/lcd_demo_0
create_bd_cell -type module -reference lcd_demo_faults video/lcd_faults
if {$mode eq "1080p30"} {
    set_property -dict [list CONFIG.IN_WIDTH {1920} CONFIG.IN_HEIGHT {1080} CONFIG.FIT_WIDTH {480} CONFIG.FIT_HEIGHT {270}] [get_bd_cells video/lcd_demo_0]
} elseif {$mode eq "vga"} {
    set_property -dict [list CONFIG.IN_WIDTH {640} CONFIG.IN_HEIGHT {480} CONFIG.FIT_WIDTH {427} CONFIG.FIT_HEIGHT {320}] [get_bd_cells video/lcd_demo_0]
} else {
    error "LCD demo supports only VGA and 1080p30 profiles"
}
connect_bd_net [get_bd_pins ps7_0/FCLK_CLK1] [get_bd_pins video/lcd_demo_0/clk] [get_bd_pins video/lcd_faults/clk]
connect_bd_net [get_bd_pins rst142/peripheral_reset] [get_bd_pins video/lcd_demo_0/rst] [get_bd_pins video/lcd_faults/rst]
foreach {source sink} {tdata pixel_data tvalid pixel_valid tready pixel_ready tuser pixel_sof tlast pixel_eol} {
    connect_bd_net [get_bd_pins video/hdmi_in/frontend/v_vid_in_axi4s_0/m_axis_video_$source] [get_bd_pins video/litex_capture/s_axis_$source] [get_bd_pins video/lcd_demo_0/$sink]
}
connect_bd_net [get_bd_pins video/receiver_reset_monitor/receiver_reset] [get_bd_pins video/lcd_demo_0/receiver_reset]
connect_bd_net [get_bd_pins video/source_monitor/overflow_episodes] [get_bd_pins video/lcd_faults/overflow_count]
connect_bd_net [get_bd_pins video/source_monitor/underflow_episodes] [get_bd_pins video/lcd_faults/underflow_count]
connect_bd_net [get_bd_pins video/lcd_faults/fault] [get_bd_pins video/lcd_demo_0/fifo_fault]
foreach name {lcd_sck lcd_mosi lcd_cs lcd_dc lcd_reset touch_cs} {
    create_bd_port -dir O $name
    connect_bd_net [get_bd_pins video/lcd_demo_0/$name] [get_bd_ports $name]
}
create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio:2.0 video/lcd_status
set_property -dict [list CONFIG.C_IS_DUAL {1} CONFIG.C_ALL_INPUTS {1} CONFIG.C_GPIO_WIDTH {32} CONFIG.C_ALL_INPUTS_2 {1} CONFIG.C_GPIO2_WIDTH {32}] [get_bd_cells video/lcd_status]
connect_bd_net [get_bd_pins video/lcd_demo_0/status] [get_bd_pins video/lcd_status/gpio_io_i]
connect_bd_net [get_bd_pins video/lcd_demo_0/uploaded_frames] [get_bd_pins video/lcd_status/gpio2_io_i]
connect_bd_net [get_bd_pins ps7_0/FCLK_CLK1] [get_bd_pins video/lcd_status/s_axi_aclk]
connect_bd_net [get_bd_pins rst142/peripheral_aresetn] [get_bd_pins video/lcd_status/s_axi_aresetn]
apply_bd_automation -rule xilinx.com:bd_rule:axi4 -config {Master "/ps7_0/M_AXI_GP0" Clk_master "/ps7_0/FCLK_CLK0" Clk_slave "Auto" Clk_xbar "/ps7_0/FCLK_CLK0"} [get_bd_intf_pins video/lcd_status/S_AXI]
