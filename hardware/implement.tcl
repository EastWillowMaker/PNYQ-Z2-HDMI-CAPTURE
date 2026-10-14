# Called with the current project open and the isolated output variable set.
launch_runs impl_1 -to_step write_bitstream -jobs 2
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} {error "Implementation did not finish"}
open_run impl_1
report_timing_summary -file [file join $output timing.rpt]
report_drc -file [file join $output drc.rpt]
report_cdc -details -file [file join $output cdc.rpt]
report_clock_interaction -file [file join $output clocks.rpt]
report_utilization -file [file join $output utilization.rpt]
report_bus_skew -file [file join $output bus-skew.rpt]
set cdc_fd [open [file join $output cdc.rpt] r]
set cdc_text [read $cdc_fd]
close $cdc_fd
if {[regexp -line {^CDC-[0-9]+[ \t]+Critical[ \t]+[1-9]} $cdc_text]} {error "Critical CDC findings remain"}
set skew_fd [open [file join $output bus-skew.rpt] r]
set skew_text [read $skew_fd]
close $skew_fd
if {[string first "Slack (VIOLATED)" $skew_text] >= 0} {error "Bus skew constraints failed"}
foreach v [get_drc_violations] {
 set severity [get_property SEVERITY $v]
 if {$severity eq "Error" || [string match {*Critical*} $severity]} {error "Critical DRC finding: $v"}
}
foreach kind {max min} {
 set paths [get_timing_paths -delay_type $kind -max_paths 1]
 if {[llength $paths] == 0} {error "No $kind timing paths reported"}
 if {[get_property SLACK $paths] < 0} {error "Negative $kind timing slack"}
}
# Message counts in the parent Vivado process exclude launch_runs children.
# Inspect their preserved logs as well; do not publish a package on a critical.
foreach log_path [glob [file join $output vivado capture.runs * runme.log]] {
 set log_fd [open $log_path r]
 set log_text [read $log_fd]
 close $log_fd
 if {[regexp -line {^(ERROR:|CRITICAL WARNING:)} $log_text]} {error "Critical run diagnostic: $log_path"}
}
file copy [file join $output vivado capture.runs impl_1 capture_wrapper.bit] [file join $output capture.bit]
file copy [file join $output vivado capture.gen sources_1 bd capture hw_handoff capture.hwh] [file join $output capture.hwh]
exec python3 [file join [file dirname [info script]] .. scripts build_manifest.py] $output $gateware [version -short] [get_property SLACK [get_timing_paths -delay_type max -max_paths 1]] [get_property SLACK [get_timing_paths -delay_type min -max_paths 1]]
