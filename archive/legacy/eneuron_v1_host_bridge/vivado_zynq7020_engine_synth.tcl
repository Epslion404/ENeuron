# XC7Z020 capacity probe for the current multi-cycle neuron engine.
# This is an out-of-context measurement; it does not include PS-PL or board I/O.

set root [file normalize [pwd]]
set part xc7z020clg400-1
set top digital_lif_engine

if {[info exists ::env(ENEURON_N_INPUTS)]} {
    set n_inputs $::env(ENEURON_N_INPUTS)
} else {
    set n_inputs 4
}

set out_dir [file join $root "vivado_zynq7020_engine_n${n_inputs}_reports"]
file mkdir $out_dir

puts "ENEURON_ZYNQ_PROBE_START part=$part n_inputs=$n_inputs"
read_verilog -sv [file join $root digital_lif_engine.sv]
synth_design -top $top -part $part -mode out_of_context -generic N_INPUTS=$n_inputs
create_clock -name clk -period 10.000 [get_ports clk]
# Give the OOC clock a reproducible global-buffer location so clock delay and
# skew are included in the post-route timing estimate.
set_property HD.CLK_SRC BUFGCTRL_X0Y0 [get_ports clk]

opt_design
place_design
route_design

report_utilization -file [file join $out_dir utilization_impl.rpt]
report_timing_summary -delay_type min_max -max_paths 10 \
    -file [file join $out_dir timing_impl.rpt]
report_route_status -file [file join $out_dir route_status_impl.rpt]
report_drc -file [file join $out_dir drc_impl.rpt]
write_checkpoint -force [file join $out_dir "digital_lif_engine_n${n_inputs}_impl.dcp"]

set timing_paths [get_timing_paths -delay_type max -max_paths 1]
if {[llength $timing_paths] == 0} {
    set worst_slack "NA"
} else {
    set worst_slack [get_property SLACK [lindex $timing_paths 0]]
}

puts "ENEURON_ZYNQ_PROBE_PASS part=$part n_inputs=$n_inputs worst_slack=$worst_slack out_dir=$out_dir"
exit
