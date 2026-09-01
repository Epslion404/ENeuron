# Pulse-Mini-L2 XC7Z020 OOC 综合/布局布线与机器可读摘要。
set root [file normalize [pwd]]
set git_head [lindex $argv 0]
if {$git_head eq {}} { set git_head UNKNOWN }
set out_dir [file join $root vivado_pulse_mini_l2_reports]
file mkdir $out_dir
set part xc7z020clg400-1
set top pulse_mini_l2_core
read_verilog -sv [file join $root pulse_mini_l2_core.sv]
synth_design -top $top -part $part -mode out_of_context
create_clock -name clk -period 10.000 [get_ports clk]
set_property HD.CLK_SRC BUFGCTRL_X0Y0 [get_ports clk]
set_false_path -from [get_ports {rst cmd_valid cmd_opcode cmd_arg0 cmd_arg1 rsp_ready}] -to [all_registers]
set_false_path -from [all_registers] -to [get_ports {cmd_ready rsp_valid rsp_status rsp_data spike pending_valid protocol_error mode_state weight0 weight1 weight2 weight3 soma_state refractory_state leak_timer_state pre_age_flat post_age_state positive_evidence negative_evidence captured_direction_flat}]
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
write_checkpoint -force [file join $out_dir pulse_mini_l2_core_impl.dcp]

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
set wns [timing_metric max]
set whs [timing_metric min]
set summary_path [file join $out_dir signoff_summary.txt]
set fh [open $summary_path w]
puts $fh "RESULT=ROUTED"
puts $fh "VIVADO_VERSION=[version -short]"
puts $fh "PART=$part"
puts $fh "TOP=$top"
puts $fh "MODE=OUT_OF_CONTEXT"
puts $fh "CLOCK_MHZ=100.000"
puts $fh "GIT_HEAD=$git_head"
puts $fh "RUNNER=vivado_pulse_mini_l2_synth.tcl"
puts $fh "LUT=$lut"
puts $fh "FF=$ff"
puts $fh "BRAM36=$bram36"
puts $fh "BRAM18=$bram18"
puts $fh "DSP=$dsp"
puts $fh "WNS_NS=$wns"
puts $fh "WHS_NS=$whs"
puts $fh "TIMING_SCOPE=REGISTER_TO_REGISTER_ONLY"
puts $fh "NOTES=Pulse-Mini-L2 PN2 magnitude evidence; four-input fixed-width core; OOC with clock source and I/O false paths"
close $fh
puts "VIVADO_PULSE_MINI_L2_ROUTED part=$part top=$top out_dir=$out_dir"
exit
