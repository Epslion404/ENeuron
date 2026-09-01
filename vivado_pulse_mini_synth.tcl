# Pulse-Mini XC7Z020 OOC 综合/布局布线与机器可读摘要。
set root [file normalize [pwd]]
set git_head [lindex $argv 0]
if {$git_head eq {}} { set git_head UNKNOWN }
set out_dir [file join $root vivado_pulse_mini_reports]
file mkdir $out_dir
set part xc7z020clg400-1
set top pulse_mini_core
read_verilog -sv [file join $root pulse_mini_core.sv]
synth_design -top $top -part $part -mode out_of_context
create_clock -name clk -period 10.000 [get_ports clk]
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
write_checkpoint -force [file join $out_dir pulse_mini_core_impl.dcp]

set util_text [read [open [file join $out_dir utilization_impl.rpt] r]]
set lut 0
set ff 0
set bram36 0
set bram18 0
set dsp 0
if {[regexp {Slice LUTs\s*\|\s*([0-9]+)} $util_text -> value]} {set lut $value}
if {[regexp {Slice Registers\s*\|\s*([0-9]+)} $util_text -> value]} {set ff $value}
if {[regexp {Block RAM Tile\s*\|\s*([0-9]+)} $util_text -> value]} {set bram36 $value}
if {[regexp {DSPs\s*\|\s*([0-9]+)} $util_text -> value]} {set dsp $value}
set timing_text [read [open [file join $out_dir timing_impl.rpt] r]]
set wns NA
set whs NA
set tns NA
set ths NA
if {[regexp {\n\s+(-?[0-9.]+)\s+(-?[0-9.]+)\s+[0-9]+\s+[0-9]+\s+(-?[0-9.]+)\s+(-?[0-9.]+)} $timing_text -> value_w value_t value_wh value_th]} {
    set wns $value_w
    set tns $value_t
    set whs $value_wh
    set ths $value_th
}
set summary_path [file join $out_dir signoff_summary.txt]
set fh [open $summary_path w]
puts $fh "RESULT=ROUTED"
puts $fh "VIVADO_VERSION=[version -short]"
puts $fh "PART=$part"
puts $fh "TOP=$top"
puts $fh "CLOCK_MHZ=100.000"
puts $fh "GIT_HEAD=$git_head"
puts $fh "RUNNER=vivado_pulse_mini_synth.tcl"
puts $fh "LUT=$lut"
puts $fh "FF=$ff"
puts $fh "BRAM36=$bram36"
puts $fh "BRAM18=$bram18"
puts $fh "DSP=$dsp"
puts $fh "WNS_NS=$wns"
puts $fh "TNS_NS=$tns"
puts $fh "WHS_NS=$whs"
puts $fh "THS_NS=$ths"
puts $fh "NOTES=Pulse-Mini four-input fixed-width core; OOC no I/O delays"
close $fh
puts "VIVADO_PULSE_MINI_ROUTED part=$part top=$top out_dir=$out_dir"
exit
