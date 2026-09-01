# NP6 4-pulse-mini-l2/pruned: pulse_mini_l2_prune_wrapper OOC synth+impl, frozen config
# (xc7z020clg400-1, 100 MHz). Constraint style aligned with vivado_pulse_mini_l2_synth.tcl:
# CLK_SRC + I/O false paths, measured scope = register-to-register.
set root [file normalize [pwd]]
set git_head [lindex $argv 0]
if {$git_head eq {}} { set git_head UNKNOWN }
set out_dir [file join $root vivado_np6_pulse_mini_l2_pruned_reports]
file mkdir $out_dir
set part xc7z020clg400-1
set top pulse_mini_l2_prune_wrapper
read_verilog -sv [file join $root pulse_mini_l2_prune_wrapper.sv]
read_verilog -sv [file join $root pulse_mini_l2_core.sv]
read_verilog -sv [file join $root pulse_mini_prune_bridge.sv]
read_verilog -sv [file join $root local_prune_gate_2of4.sv]
read_verilog -sv [file join $root local_prune_evidence_gain.sv]
synth_design -top $top -part $part -mode out_of_context
create_clock -name clk -period 10.000 [get_ports clk]
set_property HD.CLK_SRC BUFGCTRL_X0Y0 [get_ports clk]
set in_no_clk [get_ports -filter {NAME != clk}]
set_false_path -from $in_no_clk -to [all_registers]
set out_ports [get_ports -filter {DIRECTION == OUT}]
set_false_path -from [all_registers] -to $out_ports
report_utilization -file [file join $out_dir utilization_synth.rpt]
report_timing_summary -delay_type min_max -max_paths 20 -file [file join $out_dir timing_synth.rpt]
report_drc -file [file join $out_dir drc_synth.rpt]
opt_design
place_design
route_design
report_utilization -file [file join $out_dir utilization_impl.rpt]
report_timing_summary -delay_type min_max -max_paths 20 -file [file join $out_dir timing_impl.rpt]
report_drc -file [file join $out_dir drc_impl.rpt]
report_power -file [file join $out_dir power_impl.rpt]
write_checkpoint -force [file join $out_dir pulse_mini_l2_prune_wrapper_impl.dcp]

set util_text [read [open [file join $out_dir utilization_impl.rpt] r]]
set lut 0
set ff 0
set bram36 0
set bram18 0
set dsp 0
foreach {pattern var} {
    {Slice LUTs[[:space:]]*\|[[:space:]]*([0-9]+)} lut
    {Slice Registers[[:space:]]*\|[[:space:]]*([0-9]+)} ff
    {Block RAM Tile[[:space:]]*\|[[:space:]]*([0-9]+)} bram36
    {RAMB18[[:space:]]*\|[[:space:]]*([0-9]+)} bram18
    {DSPs[[:space:]]*\|[[:space:]]*([0-9]+)} dsp
} {
    if {[regexp $pattern $util_text -> value]} { set $var $value }
}
proc timing_metric {delay_type} {
    set paths [get_timing_paths -quiet -delay_type $delay_type -max_paths 1 -nworst 1]
    if {[llength $paths] == 0} { return NA }
    return [get_property SLACK [lindex $paths 0]]
}
proc sum_negative_slack {delay_type} {
    set total 0.0
    foreach path [get_timing_paths -quiet -delay_type $delay_type -nworst 10000] {
        set s [get_property SLACK $path]
        if {$s < 0.0} { set total [expr {$total + $s}] }
    }
    return $total
}
set wns [timing_metric max]
set whs [timing_metric min]
set tns [sum_negative_slack max]
set ths [sum_negative_slack min]
set summary_path [file join $out_dir signoff_summary.txt]
set fh [open $summary_path w]
puts $fh "RESULT=ROUTED"
puts $fh "VIVADO_VERSION=[version -short]"
puts $fh "PART=$part"
puts $fh "TOP=$top"
puts $fh "CLOCK_MHZ=100.000"
puts $fh "GIT_HEAD=$git_head"
puts $fh "RUNNER=vivado_np6_pulse_mini_l2_pruned_synth.tcl"
puts $fh "PAIR=4-pulse-mini-l2"
puts $fh "SIDE=pruned"
puts $fh "LUT=$lut"
puts $fh "FF=$ff"
puts $fh "BRAM36=$bram36"
puts $fh "BRAM18=$bram18"
puts $fh "DSP=$dsp"
puts $fh "WNS_NS=$wns"
puts $fh "TNS_NS=$tns"
puts $fh "WHS_NS=$whs"
puts $fh "THS_NS=$ths"
puts $fh "TIMING_SCOPE=REGISTER_TO_REGISTER_ONLY"
puts $fh "NOTES=NP6 frozen config xc7z020clg400-1 100MHz OOC; constraint style aligned with unpruned l2 runner"
close $fh
puts "VIVADO_NP6_ROUTED pair=4-pulse-mini-l2 side=pruned part=$part top=$top out_dir=$out_dir"
exit
