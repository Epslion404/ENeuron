# 当前传统 NPU + ENeuron 单时钟 RTL 的 Vivado 2024.1 OOC 综合与布局布线。
# tclargs: git_head out_dir

set git_head [lindex $argv 0]
set out_dir [file normalize [lindex $argv 1]]
if {$git_head eq {}} { set git_head UNKNOWN }
if {$out_dir eq {}} { set out_dir [file join [file normalize [pwd]] vivado_npu_single_clock_ooc_reports] }
file mkdir $out_dir

set root [file normalize [file dirname [file normalize [info script]]]]
set part xc7z020clg400-1
set top npu_eneuron_single_clock_skeleton
set rtl [file join $root npu_eneuron_single_clock_skeleton.sv]

read_verilog -sv $rtl
synth_design -top $top -part $part -mode out_of_context -flatten_hierarchy rebuilt
create_clock -name clk -period 10.000 [get_ports clk]

report_utilization -file [file join $out_dir utilization_synth.rpt]
report_timing_summary -delay_type min_max -max_paths 20 -file [file join $out_dir timing_synth.rpt]
report_drc -file [file join $out_dir drc_synth.rpt]

opt_design
place_design
route_design

report_route_status -file [file join $out_dir route_status_impl.rpt]
report_utilization -file [file join $out_dir utilization_impl.rpt]
report_timing_summary -delay_type min_max -max_paths 20 -file [file join $out_dir timing_impl.rpt]
report_drc -file [file join $out_dir drc_impl.rpt]
report_power -file [file join $out_dir power_impl.rpt]
write_checkpoint -force [file join $out_dir ${top}_impl.dcp]

proc kv {text pattern} {
    if {[regexp $pattern $text -> value]} { return $value }
    return NA
}

set util_text [read [open [file join $out_dir utilization_impl.rpt] r]]
set lut [kv $util_text {Slice LUTs\s*\|\s*([0-9]+)}]
set ff [kv $util_text {Slice Registers\s*\|\s*([0-9]+)}]
set bram36 [kv $util_text {Block RAM Tile\s*\|\s*([0-9.]+)}]
set bram18 [kv $util_text {RAMB18\s*\|\s*([0-9]+)}]
set dsp [kv $util_text {DSPs\s*\|\s*([0-9]+)}]
set timing_text [read [open [file join $out_dir timing_impl.rpt] r]]
set setup_fail [kv $timing_text {Setup\s*:\s*([0-9]+)\s+Failing Endpoints,\s*Worst Slack\s+(-?[0-9.]+)ns,\s*Total Violation\s+(-?[0-9.]+)ns}]
set wns [kv $timing_text {Setup\s*:\s*[0-9]+\s+Failing Endpoints,\s*Worst Slack\s+(-?[0-9.]+)ns}]
set tns [kv $timing_text {Setup\s*:\s*[0-9]+\s+Failing Endpoints,\s*Worst Slack\s+-?[0-9.]+ns,\s*Total Violation\s+(-?[0-9.]+)ns}]
set hold_fail [kv $timing_text {Hold\s*:\s*([0-9]+)\s+Failing Endpoints,\s*Worst Slack\s+(-?[0-9.]+)ns,\s*Total Violation\s+(-?[0-9.]+)ns}]
set whs [kv $timing_text {Hold\s*:\s*[0-9]+\s+Failing Endpoints,\s*Worst Slack\s+(-?[0-9.]+)ns}]
set ths [kv $timing_text {Hold\s*:\s*[0-9]+\s+Failing Endpoints,\s*Worst Slack\s+-?[0-9.]+ns,\s*Total Violation\s+(-?[0-9.]+)ns}]

set drc_text [read [open [file join $out_dir drc_impl.rpt] r]]
set drc_errors [regexp -all -line {^\|[^|]+\|\s*Error\s*\|} $drc_text]
set route_text [read [open [file join $out_dir route_status_impl.rpt] r]]
set route_errors [kv $route_text {nets with routing errors\.+\s*:\s*([0-9]+)}]

set physical_gate NOT_PROVEN
if {$setup_fail ne {NA} && $hold_fail ne {NA} && $drc_errors ne {NA} && $route_errors ne {NA} &&
    [string is integer -strict $setup_fail] && [string is integer -strict $hold_fail] &&
    [string is integer -strict $drc_errors] && [string is integer -strict $route_errors] &&
    $setup_fail == 0 && $hold_fail == 0 && $drc_errors == 0 && $route_errors == 0} {
    if {[string is double -strict $wns] && [string is double -strict $whs] && $wns >= 0.0 && $whs >= 0.0} {
        set physical_gate PASS
    }
}

set summary_path [file join $out_dir signoff_summary.txt]
set fh [open $summary_path w]
puts $fh "RESULT=ROUTED"
puts $fh "PHYSICAL_GATE=$physical_gate"
puts $fh "VIVADO_VERSION=[version -short]"
puts $fh "PART=$part"
puts $fh "TOP=$top"
puts $fh "CLOCK_MHZ=100.000"
puts $fh "GIT_HEAD=$git_head"
puts $fh "RUNNER=vivado_npu_single_clock_ooc.tcl"
puts $fh "RTL=npu_eneuron_single_clock_skeleton.sv"
puts $fh "LUT=$lut"
puts $fh "FF=$ff"
puts $fh "BRAM36=$bram36"
puts $fh "BRAM18=$bram18"
puts $fh "DSP=$dsp"
puts $fh "WNS_NS=$wns"
puts $fh "TNS_NS=$tns"
puts $fh "WHS_NS=$whs"
puts $fh "THS_NS=$ths"
puts $fh "SETUP_FAILING_ENDPOINTS=$setup_fail"
puts $fh "HOLD_FAILING_ENDPOINTS=$hold_fail"
puts $fh "DRC_ERRORS=$drc_errors"
puts $fh "ROUTE_ERRORS=$route_errors"
puts $fh "NOTES=Vivado 2024.1 OOC post-route; xc7z020clg400-1; 100MHz; no board I/O, DMA, PS, Ethernet or SAIF activity"
close $fh
puts "NPU_SINGLE_CLOCK_OOC_ROUTED part=$part top=$top physical_gate=$physical_gate out_dir=$out_dir"
exit
