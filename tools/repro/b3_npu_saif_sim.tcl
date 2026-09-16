# 生成200 MHz QAT-v3 NPU dense/gated推理窗口SAIF。
# tclargs: mode out_dir model_mem samples_mem mask_mem post_route_netlist

set mode [lindex $argv 0]
set out_dir [file normalize [lindex $argv 1]]
set model_mem [file normalize [lindex $argv 2]]
set samples_mem [file normalize [lindex $argv 3]]
set mask_mem [file normalize [lindex $argv 4]]
set post_route_netlist [file normalize [lindex $argv 5]]
if {$mode ni {dense gated}} { error "mode must be dense or gated" }
foreach required [list $model_mem $samples_mem $mask_mem] {
    if {![file exists $required]} { error "missing simulation data: $required" }
}
if {![file exists $post_route_netlist]} { error "missing post-route functional netlist: $post_route_netlist" }

set root [file normalize [file join [file dirname [info script]] .. ..]]
file mkdir $out_dir
set part xc7z020clg484-2
set project_name b3_npu_saif_${mode}
set project_dir [file join $out_dir project]
set saif_path [file join $out_dir ${mode}.saif]

create_project -force $project_name $project_dir -part $part
set_property target_simulator XSim [current_project]
add_files -fileset sources_1 $post_route_netlist
add_files -fileset sim_1 [file join $root tb_b3_npu_saif_power.sv]
add_files -fileset sim_1 [list $model_mem $samples_mem $mask_mem]
set_property file_type SystemVerilog [get_files -of_objects [get_filesets sources_1]]
set_property file_type SystemVerilog [get_files -of_objects [get_filesets sim_1]]
set_property top tb_b3_npu_saif_power [get_filesets sim_1]
if {$mode eq "gated"} {
    set_property verilog_define {B3_SAIF_GATED} [get_filesets sim_1]
}
set plusargs [format {-testplusarg "MODEL=%s" -testplusarg "SAMPLES=%s" -testplusarg "MASK=%s"} \
    $model_mem $samples_mem $mask_mem]
set_property -dict [list xsim.simulate.xsim.more_options $plusargs xsim.simulate.runtime {}] [get_filesets sim_1]
update_compile_order -fileset sources_1
update_compile_order -fileset sim_1

launch_simulation -simset sim_1 -mode behavioral
set start_condition [add_condition -name saif_start {/tb_b3_npu_saif_power/saif_active == 1} {stop}]
run all
remove_condition $start_condition
if {[get_value /tb_b3_npu_saif_power/saif_active] ne "1"} {
    error "simulation ended before SAIF start"
}

open_saif $saif_path
set saved_scope [current_scope]
current_scope /tb_b3_npu_saif_power/dut
log_saif [get_objects -r *]
current_scope $saved_scope
set stop_condition [add_condition -name saif_stop {/tb_b3_npu_saif_power/saif_active == 0} {stop}]
run all
remove_condition $stop_condition
close_saif
run all
close_sim

if {![file exists $saif_path] || [file size $saif_path] == 0} {
    error "SAIF was not generated: $saif_path"
}
set sim_log [file join $project_dir ${project_name}.sim sim_1 behav xsim simulate.log]
if {![file exists $sim_log]} { error "missing XSim log: $sim_log" }
set fh [open $sim_log r]
set sim_text [read $fh]
close $fh
if {[string first "B3_NPU_SAIF_PASS mode=$mode" $sim_text] < 0} {
    error "XSim log has no B3_NPU_SAIF_PASS marker for $mode"
}
file copy -force $sim_log [file join $out_dir ${mode}_xsim.log]
puts "B3_NPU_SAIF_SIM_PASS mode=$mode saif=$saif_path"
close_project
exit
