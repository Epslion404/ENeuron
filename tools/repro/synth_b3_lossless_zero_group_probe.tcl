# QAT 无损零激活/零权重组跳过的目标器件 200 MHz OOC 探测。
# tclargs: out_dir git_head

set root [file normalize [file join [file dirname [info script]] .. ..]]
set out_dir [file normalize [lindex $argv 0]]
set git_head [lindex $argv 1]
set part xc7z020clg484-2
set top npu_eneuron_single_clock_skeleton
file mkdir $out_dir

read_verilog -sv [file join $root npu_eneuron_single_clock_skeleton.sv]
set_property verilog_define {LOSSLESS_ZERO_GROUP_SKIP B3_USE_XPM} [current_fileset]
synth_design -top $top -part $part -mode out_of_context -flatten_hierarchy rebuilt
create_clock -name clk -period 5.000 [get_ports clk]
set_property HD.CLK_SRC BUFGCTRL_X0Y0 [get_ports clk]
report_utilization -hierarchical -file [file join $out_dir utilization_synth.rpt]
report_timing_summary -delay_type min_max -max_paths 20 -file [file join $out_dir timing_synth.rpt]

opt_design
place_design
phys_opt_design
route_design
report_route_status -file [file join $out_dir route_status_post_route.rpt]
report_utilization -hierarchical -file [file join $out_dir utilization_post_route.rpt]
report_timing_summary -delay_type min_max -max_paths 20 -file [file join $out_dir timing_post_route.rpt]
report_drc -file [file join $out_dir drc_post_route.rpt]
write_checkpoint -force [file join $out_dir ${top}_lossless_zero_group_200mhz_routed.dcp]

set setup_path [get_timing_paths -delay_type max -max_paths 1]
set hold_path [get_timing_paths -delay_type min -max_paths 1]
set wns [expr {[llength $setup_path] ? [get_property SLACK $setup_path] : "N/A"}]
set whs [expr {[llength $hold_path] ? [get_property SLACK $hold_path] : "N/A"}]
set summary [open [file join $out_dir implementation_summary.txt] w]
puts $summary "RESULT=ROUTED_OOC_COMPLETE"
puts $summary "VIVADO_VERSION=[version -short]"
puts $summary "PART=$part"
puts $summary "TOP=$top"
puts $summary "DEFINE=LOSSLESS_ZERO_GROUP_SKIP,B3_USE_XPM"
puts $summary "CLOCK_MHZ=200.000"
puts $summary "CLOCK_PERIOD_NS=5.000"
puts $summary "WNS_NS=$wns"
puts $summary "WHS_NS=$whs"
puts $summary "GIT_HEAD=$git_head"
puts $summary "BOUNDARY=OOC NPU core only; no PS, DMA, board I/O or external rails"
close $summary
puts "B3_LOSSLESS_ZERO_GROUP_OOC_COMPLETE part=$part wns=$wns whs=$whs"
exit
