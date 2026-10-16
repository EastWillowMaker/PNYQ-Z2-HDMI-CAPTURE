# PYNQ-Z2 video-only PS7 capture with a LiteX-generated stream gate.
# Run through scripts/build_capture.py; no board access or existing-image writes.
if {$argc != 6} {error "Expected vendor output gateware stage mode hdmi_output"}
lassign $argv vendor output gateware stage mode hdmi_output
switch -- $mode {
    vga {set receiver_k_clk_range 5}
    1080p30 {set receiver_k_clk_range 2}
    default {error "Unsupported capture mode: $mode"}
}
if {$hdmi_output ni {0 1}} {error "hdmi_output must be 0 or 1"}
if {$hdmi_output && $mode ne "1080p30"} {
    error "HDMI test output requires the 1080p30 capture mode"
}
create_project capture [file join $output vivado] -part xc7z020clg400-1
set ip_repos [list [file join $output rx_ip] [file join $output hls]]
if {$hdmi_output} {lappend ip_repos [file join $output tx_ip]}
set_property ip_repo_paths $ip_repos [current_project]
update_ip_catalog
set required_ip {digilentinc.com:ip:dvi2rgb:1.7 xilinx.com:ip:v_vid_in_axi4s:5.0 xilinx.com:ip:v_tc:6.2 xilinx.com:ip:axi_vdma:6.3 xilinx.com:ip:axi_intc:4.1 xilinx.com:ip:processing_system7:5.5 xilinx.com:hls:pixel_pack:1.0 xilinx.com:hls:color_convert:1.0}
if {$hdmi_output} {lappend required_ip digilentinc.com:ip:rgb2dvi:1.2}
foreach vlnv $required_ip {
    if {[llength [get_ipdefs -all $vlnv]] != 1} {error "Missing or ambiguous IP: $vlnv"}
}
add_files $gateware
add_files [file join $output capture_lock_sync.v]
add_files [file join $output source_health.v]
add_files [file join $output receiver_reset_sync.v]
if {$hdmi_output} {
    add_files -fileset constrs_1 [file join $output hdmi_tx.xdc]
}
if {$hdmi_output} {
    add_files [file join $output tx hdmi_test_pattern.v]
    add_files [file join $output tx hdmi_test_clock.v]
}
add_files -fileset constrs_1 [file join $output hdmi_rx.xdc]
create_bd_design capture
# Defines only the two upstream receiver procedures, then applies its exact
# board-specific PS7 configuration. The full base design is never evaluated.
source [file join $output pynq_rx.tcl]
set_property -dict [list CONFIG.PCW_USE_S_AXI_HP0 {1} CONFIG.PCW_USE_S_AXI_HP2 {0} CONFIG.PCW_EN_CLK3_PORT {0} CONFIG.PCW_USE_M_AXI_GP1 {0} CONFIG.PCW_USE_S_AXI_GP0 {0}] $ps7_0
make_bd_intf_pins_external [get_bd_intf_pins ps7_0/DDR]
make_bd_intf_pins_external [get_bd_intf_pins ps7_0/FIXED_IO]
create_bd_cell -type ip -vlnv xilinx.com:ip:axi_intc:4.1 system_interrupts
# Select and synchronize edge inputs explicitly. The upstream base source
# establishes IRQ topology but not this mask; inferred level IRQ metadata still
# requires driver/runtime qualification with the retained edge-input policy.
set_property -dict [list CONFIG.C_KIND_OF_INTR {0xFFFFFFFF} CONFIG.C_ASYNC_INTR {0xFFFFFFFF} CONFIG.C_NUM_SYNC_FF {2}] [get_bd_cells system_interrupts]
create_bd_cell -type hier video
create_hier_cell_hdmi_in /video hdmi_in
set video /video
if {$hdmi_output} {
    source [file join $output tx hdmi_output.tcl]
    set tx_generate_serial_clock [string tolower \
        [get_property CONFIG.kGenerateSerialClk [get_bd_cells hdmi_out_tx]]]
    if {$tx_generate_serial_clock ni {false 0}} {
        error "HDMI output fixture requires an external SerialClk source"
    }
}
# Select the receiver PLL range for the selected input pixel clock. The
# upstream base kClkRange=1 is for >=120 MHz and supports neither profile.
set_property CONFIG.kClkRange $receiver_k_clk_range [get_bd_cells video/hdmi_in/frontend/dvi2rgb_0]
create_bd_intf_port -mode Slave -vlnv digilentinc.com:interface:tmds_rtl:1.0 hdmi_in
connect_bd_intf_net [get_bd_intf_ports hdmi_in] [get_bd_intf_pins video/hdmi_in/TMDS_in]
create_bd_intf_port -mode Master -vlnv xilinx.com:interface:iic_rtl:1.0 hdmi_in_ddc
connect_bd_intf_net [get_bd_intf_ports hdmi_in_ddc] [get_bd_intf_pins video/hdmi_in/DDC]
create_bd_port -dir O -from 0 -to 0 hdmi_in_hpd
connect_bd_net [get_bd_ports hdmi_in_hpd] [get_bd_pins video/hdmi_in/hdmi_in_hpd]
create_bd_cell -type ip -vlnv xilinx.com:ip:axi_vdma:6.3 video/axi_vdma
set_property -dict [list CONFIG.c_include_mm2s {0} CONFIG.c_include_sg {0} CONFIG.c_use_s2mm_fsync {0} CONFIG.c_m_axi_s2mm_data_width {32} CONFIG.c_num_fstores {4} CONFIG.c_s2mm_genlock_mode {0} CONFIG.c_s2mm_linebuffer_depth {4096} CONFIG.c_s2mm_max_burst_length {32}] [get_bd_cells video/axi_vdma]
create_bd_cell -type module -reference litex_capture video/litex_capture
create_bd_cell -type module -reference source_health video/source_monitor
connect_bd_net [get_bd_pins video/hdmi_in/PixelClk] [get_bd_pins video/source_monitor/pixel_clk]
connect_bd_net [get_bd_pins video/hdmi_in/frontend/dvi2rgb_0/vid_pVSync] [get_bd_pins video/hdmi_in/frontend/color_swap_0/vsync_in] [get_bd_pins video/source_monitor/vsync]
connect_bd_net [get_bd_pins video/hdmi_in/frontend/v_vid_in_axi4s_0/overflow] [get_bd_pins video/source_monitor/overflow]
connect_bd_net [get_bd_pins video/hdmi_in/frontend/v_vid_in_axi4s_0/underflow] [get_bd_pins video/source_monitor/underflow]
create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio:2.0 video/source_health
set_property -dict [list CONFIG.C_IS_DUAL {1} CONFIG.C_ALL_INPUTS {1} CONFIG.C_GPIO_WIDTH {32} CONFIG.C_ALL_INPUTS_2 {1} CONFIG.C_GPIO2_WIDTH {32}] [get_bd_cells video/source_health]
create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio:2.0 video/source_faults
set_property -dict [list CONFIG.C_ALL_INPUTS {1} CONFIG.C_GPIO_WIDTH {32}] [get_bd_cells video/source_faults]
connect_bd_net [get_bd_pins video/source_monitor/overflow_episodes] [get_bd_pins video/source_health/gpio_io_i]
connect_bd_net [get_bd_pins video/source_monitor/native_vsync_edges] [get_bd_pins video/source_health/gpio2_io_i] [get_bd_pins video/litex_capture/native_vsync_edges]
connect_bd_net [get_bd_pins video/source_monitor/underflow_episodes] [get_bd_pins video/source_faults/gpio_io_i]
# Insert into the unpacked 24-bit AXIS pixel stream, preserving SOF and EOL.
set oldnet [get_bd_intf_nets -of_objects [get_bd_intf_pins video/hdmi_in/frontend/video_out]]
delete_bd_objs $oldnet
# Generated module has inferred AXIS interfaces (Vivado standard pin names).
connect_bd_intf_net [get_bd_intf_pins video/hdmi_in/frontend/video_out] [get_bd_intf_pins video/litex_capture/s_axis]
connect_bd_intf_net [get_bd_intf_pins video/litex_capture/m_axis] [get_bd_intf_pins video/hdmi_in/color_convert/stream_in_24]
connect_bd_intf_net [get_bd_intf_pins video/hdmi_in/out_stream] [get_bd_intf_pins video/axi_vdma/S_AXIS_S2MM]
create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio:2.0 video/capture_control
set_property -dict [list CONFIG.C_IS_DUAL {1} CONFIG.C_ALL_OUTPUTS {1} CONFIG.C_GPIO_WIDTH {32} CONFIG.C_DOUT_DEFAULT {0x00000000} CONFIG.C_ALL_INPUTS_2 {1} CONFIG.C_GPIO2_WIDTH {32}] [get_bd_cells video/capture_control]
foreach {field bit} {enable 0 request_toggle 1 ack_toggle 2} {
 create_bd_cell -type ip -vlnv xilinx.com:ip:xlslice:1.0 video/control_$field
 set_property -dict [list CONFIG.DIN_WIDTH {32} CONFIG.DIN_FROM $bit CONFIG.DIN_TO $bit CONFIG.DOUT_WIDTH {1}] [get_bd_cells video/control_$field]
 connect_bd_net [get_bd_pins video/capture_control/gpio_io_o] [get_bd_pins video/control_$field/Din]
 connect_bd_net [get_bd_pins video/control_$field/Dout] [get_bd_pins video/litex_capture/$field]
}
connect_bd_net [get_bd_pins video/litex_capture/completed_frames] [get_bd_pins video/capture_control/gpio2_io_i]
foreach {name counter0 counter1} {capture_counts observed_frames selected_frames capture_errors dropped_frames invalid_frames capture_credit credit_status selected_source_id capture_completion selected_completed command_errors capture_sequence selected_native_vsync_id source_sequence_faults} {
 create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio:2.0 video/$name
 set_property -dict [list CONFIG.C_IS_DUAL {1} CONFIG.C_ALL_INPUTS {1} CONFIG.C_GPIO_WIDTH {32} CONFIG.C_ALL_INPUTS_2 {1} CONFIG.C_GPIO2_WIDTH {32}] [get_bd_cells video/$name]
 connect_bd_net [get_bd_pins video/litex_capture/$counter0] [get_bd_pins video/$name/gpio_io_i]
 connect_bd_net [get_bd_pins video/litex_capture/$counter1] [get_bd_pins video/$name/gpio2_io_i]
 connect_bd_net [get_bd_pins ps7_0/FCLK_CLK1] [get_bd_pins video/$name/s_axi_aclk]
}
# Domain resets retain the upstream PS FCLK/receiver PixelClk clock plan.
foreach {name clk} {rst100 ps7_0/FCLK_CLK0 rst142 ps7_0/FCLK_CLK1 rstpixel video/hdmi_in/PixelClk} {
 create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 $name
 connect_bd_net [get_bd_pins $clk] [get_bd_pins $name/slowest_sync_clk]
 connect_bd_net [get_bd_pins ps7_0/FCLK_RESET0_N] [get_bd_pins $name/ext_reset_in]
}
create_bd_cell -type module -reference capture_lock_sync receiver_lock_sync
connect_bd_net [get_bd_pins video/hdmi_in/PixelClk] [get_bd_pins receiver_lock_sync/pixel_clk]
connect_bd_net [get_bd_pins video/hdmi_in/aPixelClkLckd] [get_bd_pins receiver_lock_sync/locked_async]
connect_bd_net [get_bd_pins receiver_lock_sync/locked_pixel] [get_bd_pins rstpixel/dcm_locked]
create_bd_cell -type module -reference receiver_reset_sync video/receiver_reset_monitor
connect_bd_net [get_bd_pins ps7_0/FCLK_CLK1] [get_bd_pins video/receiver_reset_monitor/sys_clk]
connect_bd_net [get_bd_pins rstpixel/peripheral_reset] [get_bd_pins video/receiver_reset_monitor/receiver_reset_async]
connect_bd_net [get_bd_pins video/receiver_reset_monitor/receiver_reset] [get_bd_pins video/litex_capture/receiver_reset]
create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 locked
set_property CONFIG.CONST_VAL {1} [get_bd_cells locked]
connect_bd_net [get_bd_pins locked/dout] [get_bd_pins rst100/dcm_locked] [get_bd_pins rst142/dcm_locked]
connect_bd_net [get_bd_pins ps7_0/FCLK_CLK0] [get_bd_pins video/hdmi_in/clk_100M] [get_bd_pins video/axi_vdma/s_axi_lite_aclk] [get_bd_pins ps7_0/M_AXI_GP0_ACLK] [get_bd_pins system_interrupts/s_axi_aclk]
connect_bd_net [get_bd_pins ps7_0/FCLK_CLK1] [get_bd_pins video/hdmi_in/clk_142M] [get_bd_pins video/axi_vdma/m_axi_s2mm_aclk] [get_bd_pins video/axi_vdma/s_axis_s2mm_aclk] [get_bd_pins ps7_0/S_AXI_HP0_ACLK] [get_bd_pins video/litex_capture/sys_clk] [get_bd_pins video/capture_control/s_axi_aclk] [get_bd_pins video/source_monitor/sys_clk] [get_bd_pins video/source_health/s_axi_aclk] [get_bd_pins video/source_faults/s_axi_aclk]
connect_bd_net [get_bd_pins ps7_0/FCLK_CLK2] [get_bd_pins video/hdmi_in/clk_200M]
connect_bd_net [get_bd_pins rst100/peripheral_aresetn] [get_bd_pins video/hdmi_in/periph_resetn_clk100M] [get_bd_pins video/axi_vdma/axi_resetn] [get_bd_pins system_interrupts/s_axi_aresetn]
connect_bd_net [get_bd_pins rst142/peripheral_aresetn] [get_bd_pins video/hdmi_in/periph_resetn_clk142M] [get_bd_pins video/capture_control/s_axi_aresetn] [get_bd_pins video/capture_counts/s_axi_aresetn] [get_bd_pins video/capture_errors/s_axi_aresetn] [get_bd_pins video/capture_credit/s_axi_aresetn] [get_bd_pins video/capture_completion/s_axi_aresetn] [get_bd_pins video/capture_sequence/s_axi_aresetn] [get_bd_pins video/source_health/s_axi_aresetn] [get_bd_pins video/source_faults/s_axi_aresetn]
connect_bd_net [get_bd_pins rst142/peripheral_reset] [get_bd_pins video/litex_capture/sys_rst] [get_bd_pins video/source_monitor/sys_reset]
connect_bd_net [get_bd_pins rstpixel/peripheral_aresetn] [get_bd_pins video/hdmi_in/resetn]
connect_bd_net [get_bd_pins rstpixel/peripheral_reset] [get_bd_pins video/hdmi_in/vid_io_in_reset] [get_bd_pins video/source_monitor/pixel_reset]
# Automation creates AXI protocol/clock conversion with explicit endpoint clocks.
foreach slave {system_interrupts/s_axi video/axi_vdma/S_AXI_LITE video/hdmi_in/S00_AXILite video/hdmi_in/S01_AXILite video/hdmi_in/S02_AXILite video/hdmi_in/S03_AXILite video/capture_control/S_AXI video/capture_counts/S_AXI video/capture_errors/S_AXI video/capture_credit/S_AXI video/capture_completion/S_AXI video/capture_sequence/S_AXI video/source_health/S_AXI video/source_faults/S_AXI} {
 apply_bd_automation -rule xilinx.com:bd_rule:axi4 -config {Master "/ps7_0/M_AXI_GP0" Clk_master "/ps7_0/FCLK_CLK0" Clk_slave "Auto" Clk_xbar "/ps7_0/FCLK_CLK0"} [get_bd_intf_pins $slave]
}
apply_bd_automation -rule xilinx.com:bd_rule:axi4 -config {Master "/video/axi_vdma/M_AXI_S2MM" Slave "/ps7_0/S_AXI_HP0" Clk_master "/ps7_0/FCLK_CLK1" Clk_slave "/ps7_0/FCLK_CLK1" Clk_xbar "/ps7_0/FCLK_CLK1"} [get_bd_intf_pins ps7_0/S_AXI_HP0]
create_bd_cell -type ip -vlnv xilinx.com:ip:xlconcat:2.1 irq
set_property CONFIG.NUM_PORTS {3} [get_bd_cells irq]
connect_bd_net [get_bd_pins video/axi_vdma/s2mm_introut] [get_bd_pins irq/In0]
connect_bd_net [get_bd_pins video/hdmi_in/hdmi_in_hpd_irq] [get_bd_pins irq/In1]
connect_bd_net [get_bd_pins video/hdmi_in/vtc_in_irq] [get_bd_pins irq/In2]
connect_bd_net [get_bd_pins irq/dout] [get_bd_pins system_interrupts/intr]
connect_bd_net [get_bd_pins system_interrupts/irq] [get_bd_pins ps7_0/IRQ_F2P]
assign_bd_address
validate_bd_design
set bd_criticals [get_msg_config -count -severity {CRITICAL WARNING}]
puts "CAPTURE_BD_CRITICAL_COUNT $bd_criticals"
if {$bd_criticals > 0} {error "Critical block-design warnings remain"}
save_bd_design
report_ip_status -file [file join $output ip-status.rpt]
write_bd_tcl [file join $output capture-export.tcl]
generate_target all [get_files capture.bd]
if {[get_msg_config -count -severity {CRITICAL WARNING}] > 0} {error "Critical IP-generation warnings remain"}
make_wrapper -files [get_files capture.bd] -top
add_files [file join $output vivado capture.srcs sources_1 bd capture hdl capture_wrapper.v]
set_property top capture_wrapper [current_fileset]
update_compile_order -fileset sources_1
if {$stage eq "bitstream"} {
 source [file join [file dirname [info script]] implement.tcl]
}
exit
