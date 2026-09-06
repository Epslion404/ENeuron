set script_dir [file normalize [file dirname [info script]]]
set git_head [lindex $argv 0]
set out_dir [file normalize [lindex $argv 1]]
if {$git_head eq {}} { set git_head UNKNOWN }
if {$out_dir eq {}} { set out_dir [file join $script_dir build] }
file mkdir $out_dir

set part xc7z020clg484-2
set project_dir [file join $out_dir project]
set project_name hello_zynq_b1a

create_project -force $project_name $project_dir -part $part
source [file join $script_dir create_b1a_bd.tcl]
make_wrapper -files [get_files */design_1.bd] -top
add_files -norecurse [file join $project_dir ${project_name}.gen sources_1 bd design_1 hdl design_1_wrapper.v]
set board_xdc [file join $script_dir hello_zynq_b1a.xdc]
set tx_xdc [file join $script_dir hello_zynq_b1a_rgmii_tx.xdc]
add_files -fileset constrs_1 -norecurse [list $board_xdc $tx_xdc]
set_property PROCESSING_ORDER LATE [get_files $tx_xdc]
set_property top design_1_wrapper [current_fileset]
update_compile_order -fileset sources_1

validate_bd_design
generate_target all [get_files */design_1.bd]
export_ip_user_files -of_objects [get_files */design_1.bd] -no_script -sync -force -quiet

launch_runs impl_1 -to_step write_bitstream -jobs 8
wait_on_run impl_1
set run_status [get_property STATUS [get_runs impl_1]]
if {![string match {write_bitstream Complete!} $run_status]} {
    error "B1A implementation failed: $run_status"
}

open_run impl_1
set utilization_report [file join $out_dir utilization_impl.rpt]
set timing_report [file join $out_dir timing_impl.rpt]
set methodology_report [file join $out_dir methodology_impl.rpt]
set route_report [file join $out_dir route_status_impl.rpt]
set drc_report [file join $out_dir drc_impl.rpt]
set bitstream_path [file join $out_dir hello_zynq_b1a.bit]
set xsa_path [file join $out_dir hello_zynq_b1a.xsa]

report_utilization -file $utilization_report
report_timing_summary -delay_type min_max -max_paths 20 -file $timing_report
report_methodology -file $methodology_report
report_route_status -file $route_report
report_drc -file $drc_report
write_bitstream -force $bitstream_path
write_hw_platform -fixed -include_bit -force -file $xsa_path

proc timing_metrics {delay_type} {
    set worst [get_timing_paths -quiet -delay_type $delay_type -max_paths 1 -nworst 1]
    if {[llength $worst] == 0} { return [list NA 0.0 0] }
    set worst_slack [get_property SLACK [lindex $worst 0]]
    set violating [get_timing_paths -quiet -delay_type $delay_type -slack_lesser_than 0.0 -max_paths 100000 -nworst 1]
    set total 0.0
    foreach path $violating {
        set slack [get_property SLACK $path]
        if {$slack < 0.0} { set total [expr {$total + $slack}] }
    }
    return [list $worst_slack $total [llength $violating]]
}

proc report_value {path pattern} {
    set fh [open $path r]
    set report_text [read $fh]
    close $fh
    if {[regexp -nocase $pattern $report_text -> value]} { return $value }
    return NA
}

set setup [timing_metrics max]
set hold [timing_metrics min]
set route_errors [report_value $route_report {nets with routing errors[^0-9]*([0-9]+)}]
set drc_errors [llength [get_drc_violations -quiet -filter {SEVERITY == "Error"}]]
set drc_critical [llength [get_drc_violations -quiet -filter {SEVERITY == "Critical Warning"}]]
set drc_warnings [llength [get_drc_violations -quiet -filter {SEVERITY == "Warning"}]]
set methodology_fh [open $methodology_report r]
set methodology_text [read $methodology_fh]
close $methodology_fh
set rgmii_tx_missing_delays [regexp -all {An output delay is missing on RGMII_0_} $methodology_text]
set mdio_missing_input_delays [regexp -all {An input delay is missing on MDIO_PHY_0_mdio_io} $methodology_text]

set summary_path [file join $out_dir signoff_summary.txt]
set summary [open $summary_path w]
puts $summary "B1A_BUILD_HEAD=$git_head"
puts $summary "B1A_PART=$part"
puts $summary "B1A_TOP=design_1_wrapper"
puts $summary "B1A_DDR_PART=MT41K256M16_RE-125"
puts $summary "B1A_DDR_WIDTH_BITS=16"
puts $summary "B1A_DDR_FREQ_MHZ=533.333333"
puts $summary "B1A_GMII_TO_RGMII_PHYADDR=8"
puts $summary "B1A_PHYSICAL_PHY_ADDRESS=RUNTIME_MDIO_DISCOVERY_REQUIRED"
puts $summary "B1A_PHY_HARD_RESET=UNAVAILABLE_R46_NC"
puts $summary "B1A_SETUP_WNS=[lindex $setup 0]"
puts $summary "B1A_SETUP_TNS=[lindex $setup 1]"
puts $summary "B1A_SETUP_FAIL_ENDPOINTS=[lindex $setup 2]"
puts $summary "B1A_HOLD_WHS=[lindex $hold 0]"
puts $summary "B1A_HOLD_THS=[lindex $hold 1]"
puts $summary "B1A_HOLD_FAIL_ENDPOINTS=[lindex $hold 2]"
puts $summary "B1A_ROUTE_ERRORS=$route_errors"
puts $summary "B1A_DRC_ERRORS=$drc_errors"
puts $summary "B1A_DRC_CRITICAL_WARNINGS=$drc_critical"
puts $summary "B1A_DRC_WARNINGS=$drc_warnings"
puts $summary "B1A_RGMII_TX_MISSING_OUTPUT_DELAYS=$rgmii_tx_missing_delays"
puts $summary "B1A_MDIO_MISSING_INPUT_DELAYS=$mdio_missing_input_delays"
puts $summary "B1A_BITSTREAM=$bitstream_path"
puts $summary "B1A_XSA=$xsa_path"
close $summary

if {[lindex $setup 0] eq "NA" || [lindex $setup 0] < 0.0 || [lindex $setup 2] != 0} { error "B1A setup timing failed" }
if {[lindex $hold 0] eq "NA" || [lindex $hold 0] < 0.0 || [lindex $hold 2] != 0} { error "B1A hold timing failed" }
if {$route_errors eq "NA" || $route_errors != 0} { error "B1A route status failed" }
if {$drc_errors != 0 || $drc_critical != 0} { error "B1A DRC failed or has critical warnings" }
if {$rgmii_tx_missing_delays != 0} { error "B1A RGMII TX output delay constraints are incomplete" }

puts "B1A_BUILD_PASS"
puts "B1A_BUILD_SUMMARY=$summary_path"
puts "B1A_BITSTREAM=$bitstream_path"
puts "B1A_XSA=$xsa_path"
close_project
