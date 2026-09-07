# Vivado 2024.1 真实 AMD XPM/xsim：复用 T1 协议 testbench。
set root [file normalize [pwd]]
set git_head [lindex $argv 0]
set out_dir [file normalize [lindex $argv 1]]
if {$git_head eq {}} { set git_head UNKNOWN }
if {$out_dir eq {}} { set out_dir [file join $root vivado_npu_zynq7020_t3_xsim] }
file mkdir $out_dir

set part xc7z020clg400-1
set project_dir [file join $out_dir project]
set project_name ene_npu_t3_xsim
set sim_top tb_npu_zynq7020_t1_wrapper

create_project -force $project_name $project_dir -part $part
set_property target_simulator XSim [current_project]
set_property XPM_LIBRARIES {XPM_FIFO} [current_project]

add_files -fileset sources_1 [list \
    [file join $root npu_eneuron_single_clock_skeleton.sv] \
    [file join $root npu_zynq7020_t1_wrapper.sv]]
add_files -fileset sim_1 [file join $root tb_npu_zynq7020_t1_wrapper.sv]
set_property file_type SystemVerilog [get_files -of_objects [get_filesets sources_1]]
set_property file_type SystemVerilog [get_files -of_objects [get_filesets sim_1]]
set_property top $sim_top [get_filesets sim_1]
update_compile_order -fileset sources_1
update_compile_order -fileset sim_1

puts "ENeuron T3: launch Vivado 2024.1 XSim with real AMD XPM_FIFO"
launch_simulation -simset sim_1 -mode behavioral
run all
close_sim

set sim_log [file join $project_dir ${project_name}.sim sim_1 behav xsim simulate.log]
if {![file exists $sim_log]} { error "Missing XSim log: $sim_log" }
set fh [open $sim_log r]
set sim_text [read $fh]
close $fh
foreach forbidden_text {"Fatal:" "ERROR:" "XPM_FIFO 20-" "T1 ready leaked"} {
    if {[string first $forbidden_text $sim_text] >= 0} {
        error "Real XPM/xsim log contains forbidden text: $forbidden_text"
    }
}
if {[string first "T1_PROTOCOL_SKELETON_PASS" $sim_text] < 0} {
    error "Real XPM/xsim log has no T1_PROTOCOL_SKELETON_PASS marker"
}

set summary [open [file join $out_dir xsim_signoff_summary.txt] w]
puts $summary "RESULT=PASS"
puts $summary "VIVADO_VERSION=[version -short]"
puts $summary "PART=$part"
puts $summary "GIT_HEAD=$git_head"
puts $summary "SIM_TOP=$sim_top"
puts $summary "XPM_LIBRARIES=[get_property XPM_LIBRARIES [current_project]]"
puts $summary "REAL_XPM_MODEL=AMD_XPM_FIFO"
puts $summary "T1_MARKER=T1_PROTOCOL_SKELETON_PASS"
puts $summary "SIM_LOG=$sim_log"
close $summary
puts "T3_REAL_XPM_XSIM_PASS part=$part sim_top=$sim_top out_dir=$out_dir"
close_project
exit
