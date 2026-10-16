# Fast reset and clock metadata check for the optional HDMI output fixture.
# Run Vivado with staged build root and a fresh project directory as arguments.
if {$argc != 2} {
    error "Expected staged_build_root fresh_project_directory"
}
lassign $argv staged_build_root project_dir
set staged_build_root [file normalize $staged_build_root]
set project_dir [file normalize $project_dir]
set rx_ip_repo [file join $staged_build_root rx_ip]
set tx_ip_repo [file join $staged_build_root tx_ip]

foreach path [list \
    [file join $staged_build_root tx hdmi_test_clock.v] \
    [file join $staged_build_root tx hdmi_test_pattern.v] \
    [file join $tx_ip_repo rgb2dvi_v1_2 component.xml]] {
    if {![file isfile $path]} {
        error "Missing staged HDMI output input: $path"
    }
}
foreach path [list $rx_ip_repo $tx_ip_repo] {
    if {![file isdirectory $path]} {
        error "Missing staged HDMI IP repository: $path"
    }
}
if {[file exists $project_dir]} {
    error "Project directory already exists: $project_dir"
}

create_project hdmi_output_check $project_dir -part xc7z020clg400-1
set_property ip_repo_paths [list $rx_ip_repo $tx_ip_repo] [current_project]
update_ip_catalog
if {[llength [get_ipdefs -all digilentinc.com:ip:rgb2dvi:1.2]] != 1} {
    error "Pinned rgb2dvi IP is missing or ambiguous"
}
add_files [file join $staged_build_root tx hdmi_test_clock.v]
add_files [file join $staged_build_root tx hdmi_test_pattern.v]

create_bd_design hdmi_output_check
create_bd_port -dir I -type clk -freq_hz 100000000 ref_clk_100
create_bd_port -dir I -from 0 -to 0 resetn
create_bd_intf_port -mode Master \
    -vlnv digilentinc.com:interface:tmds_rtl:1.0 hdmi_out

create_bd_cell -type module -reference hdmi_test_clock tx_clock
create_bd_cell -type module -reference hdmi_test_pattern tx_pattern
create_bd_cell -type ip -vlnv digilentinc.com:ip:rgb2dvi:1.2 tx_encoder
set_property -dict [list \
    CONFIG.kClkRange {2} \
    CONFIG.kGenerateSerialClk {false} \
    CONFIG.kRstActiveHigh {true}] [get_bd_cells tx_encoder]

connect_bd_net [get_bd_ports ref_clk_100] [get_bd_pins tx_clock/ref_clk_100]
connect_bd_net [get_bd_ports resetn] [get_bd_pins tx_clock/resetn]
connect_bd_net [get_bd_pins tx_clock/pixel_clk] \
    [get_bd_pins tx_pattern/pixel_clk] [get_bd_pins tx_encoder/PixelClk]
connect_bd_net [get_bd_pins tx_clock/serial_clk] \
    [get_bd_pins tx_encoder/SerialClk]
connect_bd_net [get_bd_pins tx_clock/tx_reset] \
    [get_bd_pins tx_pattern/async_reset] [get_bd_pins tx_encoder/aRst]
connect_bd_net [get_bd_pins tx_pattern/vid_pData] \
    [get_bd_pins tx_encoder/vid_pData]
connect_bd_net [get_bd_pins tx_pattern/vid_pVDE] \
    [get_bd_pins tx_encoder/vid_pVDE]
connect_bd_net [get_bd_pins tx_pattern/vid_pHSync] \
    [get_bd_pins tx_encoder/vid_pHSync]
connect_bd_net [get_bd_pins tx_pattern/vid_pVSync] \
    [get_bd_pins tx_encoder/vid_pVSync]
connect_bd_intf_net [get_bd_intf_ports hdmi_out] \
    [get_bd_intf_pins tx_encoder/TMDS]

validate_bd_design
set critical_count [get_msg_config -count -severity {CRITICAL WARNING}]
puts "HDMI_OUTPUT_BD_CRITICAL_COUNT $critical_count"
if {$critical_count > 0} {
    error "HDMI output clock/reset block design has critical warnings"
}
save_bd_design
puts "HDMI_OUTPUT_BD_PASS"
