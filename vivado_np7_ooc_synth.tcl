# NP7.7 共享突触执行单元 OOC 综合 + 实现（xc7z020clg400-1, 100 MHz）。
# 由 run_np7_vivado_ooc.py 调用；tclargs:
#   git_head wrapper_file top out_dir fmt lanes sw_build host
set git_head [lindex $argv 0]
set wrapper  [file normalize [lindex $argv 1]]
set top      [lindex $argv 2]
set out_dir  [file normalize [lindex $argv 3]]
set fmt      [lindex $argv 4]
set lanes    [lindex $argv 5]
set sw_build [lindex $argv 6]
set host     [lindex $argv 7]
if {$git_head eq {} } { set git_head UNKNOWN }
set part xc7z020clg400-1
file mkdir $out_dir
set rtl_root [file normalize [file dirname [file normalize [info script]]]]
foreach src {np7_weight_ram.sv np7_shared_synapse_lane.sv np7_exec_unit_dense.sv np7_exec_unit_sparse.sv} {
    read_verilog -sv [file join $rtl_root $src]
}
read_verilog -sv $wrapper
synth_design -top $top -part $part -mode out_of_context
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
set lut    [kv $util_text {Slice LUTs\s*\|\s*([0-9]+)}]
set ff     [kv $util_text {Slice Registers\s*\|\s*([0-9]+)}]
set bram36 [kv $util_text {Block RAM Tile\s*\|\s*([0-9.]+)}]
set bram18 [kv $util_text {RAMB18\s*\|\s*([0-9]+)}]
set dsp    [kv $util_text {DSPs\s*\|\s*([0-9]+)}]
set utram  [kv $util_text {URAM384W\s*\|\s*([0-9]+)}]
set timing_text [read [open [file join $out_dir timing_impl.rpt] r]]
set setup_re {Setup\s*:\s*([0-9]+)\s+Failing Endpoints,\s*Worst Slack\s+(-?[0-9.]+)ns,\s*Total Violation\s+(-?[0-9.]+)ns}
set hold_re {Hold\s*:\s*([0-9]+)\s+Failing Endpoints,\s*Worst Slack\s+(-?[0-9.]+)ns,\s*Total Violation\s+(-?[0-9.]+)ns}
set setup_fail NA; set wns NA; set tns NA
if {[regexp $setup_re $timing_text -> c s t]} { set setup_fail $c; set wns $s; set tns $t }
set hold_fail NA; set whs NA; set ths NA
if {[regexp $hold_re $timing_text -> c h th]} { set hold_fail $c; set whs $h; set ths $th }
set drc_text [read [open [file join $out_dir drc_impl.rpt] r]]
set drc_errors 0
foreach {- sev} [regexp -all -inline {\|\s*([A-Z][A-Z0-9-]+)\s*\|\s*(Error|Critical Warning|Warning|Info|Advisory)\s*\|} $drc_text] {
    if {$sev eq {Error}} { incr drc_errors }
}
set fh [open [file join $out_dir signoff_summary.txt] w]
puts $fh "RESULT=ROUTED"
puts $fh "VIVADO_VERSION=[version -short]"
puts $fh "VIVADO_BUILD=$sw_build"
puts $fh "EXECUTION_HOST=$host"
puts $fh "PART=$part"
puts $fh "TOP=$top"
puts $fh "FORMAT=$fmt"
puts $fh "LANES=$lanes"
puts $fh "CLOCK_MHZ=100.000"
puts $fh "GIT_HEAD=$git_head"
puts $fh "RUNNER=vivado_np7_ooc_synth.tcl"
puts $fh "WRAPPER=[file tail $wrapper]"
puts $fh "DRC_ERRORS=$drc_errors"
puts $fh "LUT=$lut"
puts $fh "FF=$ff"
puts $fh "BRAM36=$bram36"
puts $fh "BRAM18=$bram18"
puts $fh "URAM=$utram"
puts $fh "DSP=$dsp"
puts $fh "WNS_NS=$wns"
puts $fh "TNS_NS=$tns"
puts $fh "WHS_NS=$whs"
puts $fh "THS_NS=$ths"
puts $fh "SETUP_FAILING_ENDPOINTS=$setup_fail"
puts $fh "HOLD_FAILING_ENDPOINTS=$hold_fail"
puts $fh "NOTES=NP7.7 OOC synth+impl, xc7z020clg400-1, 100MHz, default strategies"
close $fh
puts "VIVADO_NP7_ROUTED top=$top fmt=$fmt lanes=$lanes lut=$lut ff=$ff bram36=$bram36 dsp=$dsp wns=$wns whs=$whs out_dir=$out_dir"
exit
