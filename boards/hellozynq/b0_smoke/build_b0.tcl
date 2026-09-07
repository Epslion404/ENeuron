set script_dir [file normalize [file dirname [info script]]]
set git_head [lindex $argv 0]
set out_dir [file normalize [lindex $argv 1]]
if {$git_head eq {}} { set git_head UNKNOWN }
if {$out_dir eq {}} { set out_dir [file join $script_dir build] }
file mkdir $out_dir

set part xc7z020clg484-2
set top hello_zynq_b0_smoke
set clock_name sys_clk_50m
set clock_period 20.000

read_verilog -sv [file join $script_dir hello_zynq_b0_smoke.sv]
read_xdc [file join $script_dir hello_zynq_b0_smoke.xdc]
synth_design -top $top -part $part -flatten_hierarchy rebuilt

report_utilization -file [file join $out_dir utilization_synth.rpt]
report_timing_summary -delay_type min_max -max_paths 20 -file [file join $out_dir timing_synth.rpt]

opt_design
place_design
phys_opt_design
route_design

set utilization_report [file join $out_dir utilization_impl.rpt]
set timing_report [file join $out_dir timing_impl.rpt]
set route_report [file join $out_dir route_status_impl.rpt]
set drc_report [file join $out_dir drc_impl.rpt]
set checkpoint_path [file join $out_dir ${top}_impl.dcp]
set bitstream_path [file join $out_dir ${top}.bit]

report_utilization -file $utilization_report
report_timing_summary -delay_type min_max -max_paths 20 -file $timing_report
report_route_status -file $route_report
report_drc -file $drc_report
write_checkpoint -force $checkpoint_path
write_bitstream -force $bitstream_path

proc timing_metrics {delay_type} {
    set worst [get_timing_paths -quiet -delay_type $delay_type -max_paths 1 -nworst 1]
    if {[llength $worst] == 0} { return [list NA 0.0 0] }
    set worst_slack [get_property SLACK [lindex $worst 0]]
    set violating [get_timing_paths -quiet -delay_type $delay_type \
        -slack_lesser_than 0.0 -max_paths 100000 -nworst 1]
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

set summary_path [file join $out_dir signoff_summary.txt]
set summary [open $summary_path w]
puts $summary "B0_BUILD_HEAD=$git_head"
puts $summary "B0_PART=$part"
puts $summary "B0_TOP=$top"
puts $summary "B0_CLOCK_NAME=$clock_name"
puts $summary "B0_CLOCK_PERIOD_NS=$clock_period"
puts $summary "B0_SETUP_WNS=[lindex $setup 0]"
puts $summary "B0_SETUP_TNS=[lindex $setup 1]"
puts $summary "B0_SETUP_FAIL_ENDPOINTS=[lindex $setup 2]"
puts $summary "B0_HOLD_WHS=[lindex $hold 0]"
puts $summary "B0_HOLD_THS=[lindex $hold 1]"
puts $summary "B0_HOLD_FAIL_ENDPOINTS=[lindex $hold 2]"
puts $summary "B0_ROUTE_ERRORS=$route_errors"
puts $summary "B0_DRC_ERRORS=$drc_errors"
puts $summary "B0_DRC_CRITICAL_WARNINGS=$drc_critical"
puts $summary "B0_DRC_WARNINGS=$drc_warnings"
puts $summary "B0_BITSTREAM=$bitstream_path"
close $summary

if {[lindex $setup 0] eq "NA" || [lindex $setup 0] < 0.0 || [lindex $setup 2] != 0} {
    error "B0 setup timing failed"
}
if {[lindex $hold 0] eq "NA" || [lindex $hold 0] < 0.0 || [lindex $hold 2] != 0} {
    error "B0 hold timing failed"
}
if {$route_errors eq "NA" || $route_errors != 0} {
    error "B0 route status failed"
}
if {$drc_errors != 0 || $drc_critical != 0} {
    error "B0 DRC failed or has critical warnings"
}

puts "B0_BUILD_PASS"
puts "B0_BUILD_SUMMARY=$summary_path"
puts "B0_BITSTREAM=$bitstream_path"
