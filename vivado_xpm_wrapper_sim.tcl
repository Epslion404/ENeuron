# Vivado 2024.1 project-mode xsim using AMD's real XPM FIFO library.
set root [file normalize [pwd]]
set out_dir [file join $root vivado_xpm_wrapper_sim]
set project_dir [file join $out_dir project]
file mkdir $out_dir

set part xc7a35tcpg236-1
set project_name ene_xpm_wrapper
set sim_top tb_vivado_xpm_wrapper
set synth_top digital_snn_host_bridge

create_project -force $project_name $project_dir -part $part
set_property target_simulator XSim [current_project]
set_property XPM_LIBRARIES {XPM_FIFO} [current_project]

add_files -fileset sources_1 [file join $root digital_snn_host_bridge.sv]
add_files -fileset sim_1 [file join $root tb_vivado_xpm_wrapper.sv]
set_property file_type SystemVerilog [get_files [file join $root digital_snn_host_bridge.sv]]
set_property file_type SystemVerilog [get_files [file join $root tb_vivado_xpm_wrapper.sv]]
set_property top $synth_top [get_filesets sources_1]
set_property top $sim_top [get_filesets sim_1]
update_compile_order -fileset sources_1
update_compile_order -fileset sim_1

puts "ENeuron XPM wrapper: launch real XPM behavioral simulation"
launch_simulation -simset sim_1 -mode behavioral
run all
set pass_objects [get_objects -quiet /${sim_top}/test_passed]
if {[llength $pass_objects] != 1} {
    error "Cannot inspect ${sim_top}.test_passed"
}
set pass_value [get_value -radix unsigned [lindex $pass_objects 0]]
if {$pass_value ne "1"} {
    error "Real XPM simulation did not reach pass state: test_passed=$pass_value"
}
close_sim

# Xsim can return control after $fatal/$finish and a later run can continue.
# Therefore the persistent simulator log is part of the pass criterion.
set sim_log [file join $project_dir ${project_name}.sim sim_1 behav xsim simulate.log]
if {![file exists $sim_log]} {
    error "Missing Xsim log: $sim_log"
}
set sim_log_file [open $sim_log r]
set sim_log_text [read $sim_log_file]
close $sim_log_file
foreach forbidden_text {"Fatal:" "RESET_REENTRY_ERROR" "XPM_FIFO 20-"} {
    if {[string first $forbidden_text $sim_log_text] >= 0} {
        error "Real XPM simulation log contains forbidden text: $forbidden_text"
    }
}
if {[string first "VIVADO_XPM_WRAPPER_PASS" $sim_log_text] < 0} {
    error "Real XPM simulation log has no pass marker"
}

# Synthesis defines SYNTHESIS, so the simulation-only reset report must vanish.
puts "ENeuron XPM wrapper: synthesize and audit simulation-only reset assertion"
synth_design -top $synth_top -part $part
set synth_status "synth_design complete"
create_clock -name host_clk -period 20.000 [get_ports host_clk]
create_clock -name tile_clk -period 14.000 [get_ports tile_clk]
set_clock_groups -asynchronous -group [get_clocks host_clk] -group [get_clocks tile_clk]

set forbidden_cells [get_cells -hier -quiet -filter {NAME =~ *reset_cycle_active*}]
set forbidden_nets [get_nets -hier -quiet -filter {NAME =~ *reset_cycle_active*}]
if {[llength $forbidden_cells] != 0 || [llength $forbidden_nets] != 0} {
    error "Simulation-only reset_cycle_active reached synthesized netlist"
}
report_cdc -details -file [file join $out_dir cdc_post_synth.rpt]
report_utilization -file [file join $out_dir utilization_post_synth.rpt]

set summary [open [file join $out_dir vivado_xpm_wrapper_summary.txt] w]
puts $summary "VIVADO_XPM_WRAPPER_PASS"
puts $summary "vivado_version=[version -short]"
puts $summary "part=$part"
puts $summary "xpm_libraries=[get_property XPM_LIBRARIES [current_project]]"
puts $summary "simulation_top=$sim_top"
puts $summary "synthesis_top=$synth_top"
puts $summary "synthesis_status=$synth_status"
puts $summary "reset_reentry_assertion_in_netlist=0"
puts $summary "cdc_report=[file join $out_dir cdc_post_synth.rpt]"
close $summary

puts "VIVADO_XPM_WRAPPER_SIGNOFF_PASS out_dir=$out_dir"
close_project
exit
