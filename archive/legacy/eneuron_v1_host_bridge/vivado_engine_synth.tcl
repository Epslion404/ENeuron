# Vivado 2024.1 非工程批处理：多周期数字 LIF 引擎综合与实现。
# xc7a35tcpg236-1 是可重复的 OOC 代理目标，不代表最终开发板器件。

set root [file normalize [pwd]]
set out_dir [file join $root vivado_engine_reports]
file mkdir $out_dir

set part xc7a35tcpg236-1
set top digital_lif_engine

read_verilog -sv [file join $root digital_lif_engine.sv]
synth_design -top $top -part $part -mode out_of_context
create_clock -name clk -period 10.000 [get_ports clk]

report_utilization -file [file join $out_dir utilization_synth.rpt]
report_timing_summary -delay_type min_max -max_paths 10 -file [file join $out_dir timing_synth.rpt]
report_drc -file [file join $out_dir drc_synth.rpt]
write_checkpoint -force [file join $out_dir digital_lif_engine_synth.dcp]

# OOC 布局布线用于评估核心数据通路，不包含板级 I/O 与完整时钟约束。
opt_design
place_design
route_design
report_utilization -file [file join $out_dir utilization_impl.rpt]
report_timing_summary -delay_type min_max -max_paths 10 -file [file join $out_dir timing_impl.rpt]
report_drc -file [file join $out_dir drc_impl.rpt]
report_power -file [file join $out_dir power_impl.rpt]
write_checkpoint -force [file join $out_dir digital_lif_engine_impl.dcp]

set timing_paths [get_timing_paths -delay_type max -max_paths 1]
if {[llength $timing_paths] == 0} {
    set worst_slack "NA"
} else {
    set worst_slack [get_property SLACK [lindex $timing_paths 0]]
}
puts "VIVADO_ENEURON_ENGINE_PASS part=$part top=$top worst_slack=$worst_slack out_dir=$out_dir"
exit
