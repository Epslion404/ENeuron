set script_dir [file normalize [file dirname [info script]]]
set git_head [lindex $argv 0]
set out_dir [file normalize [lindex $argv 1]]
set npu_mode [lindex $argv 2]
if {$git_head eq {}} { set git_head UNKNOWN }
if {$out_dir eq {}} { set out_dir [file join $script_dir build] }
if {$npu_mode eq {}} { set npu_mode dense }
if {$npu_mode ni {dense lossless_zero_group_skip dense_pl_replay lossless_zero_group_skip_pl_replay}} {
    error "Unsupported B2_NPU_MODE=$npu_mode"
}
file mkdir $out_dir

set verilog_defines {}
if {[string match {lossless_zero_group_skip*} $npu_mode]} {
    lappend verilog_defines LOSSLESS_ZERO_GROUP_SKIP
    lappend verilog_defines B3_USE_XPM
}
if {[string match {*_pl_replay} $npu_mode]} {
    lappend verilog_defines B3_PL_REPLAY_BENCHMARK
    lappend verilog_defines B3_PL_REPLAY_WARMUP_SAMPLES=1000
    lappend verilog_defines B3_PL_REPLAY_MEASURE_SAMPLES=10000
}

set part xc7z020clg484-2
set project_dir [file join $out_dir project]
set project_name hello_zynq_b2
set repo_root [file normalize [file join $script_dir .. .. ..]]

create_project -force $project_name $project_dir -part $part
add_files -norecurse [list \
    [file join $script_dir axis_stream_probe.v] \
    [file join $script_dir b2_npu_status_probe.v] \
    [file join $script_dir b2_npu_axis_top.v] \
    [file join $repo_root b2_npu_packet_adapter.sv] \
    [file join $repo_root b2_packet_ingress.sv] \
    [file join $repo_root b2_packet_bram.sv] \
    [file join $repo_root b2_packet_egress.sv] \
    [file join $repo_root b3_pl_replay_shim.sv] \
    [file join $repo_root npu_zynq7020_t1_wrapper.sv] \
    [file join $repo_root npu_eneuron_single_clock_skeleton.sv] \
]
set_property verilog_define $verilog_defines [current_fileset]
source [file join $script_dir create_b2_bd.tcl]
make_wrapper -files [get_files */design_1.bd] -top
add_files -norecurse [file join $project_dir ${project_name}.gen sources_1 bd design_1 hdl design_1_wrapper.v]
set board_xdc [file normalize [file join $script_dir .. b1a_hw hello_zynq_b1a.xdc]]
set tx_xdc [file normalize [file join $script_dir .. b1a_hw hello_zynq_b1a_rgmii_tx.xdc]]
add_files -fileset constrs_1 -norecurse [list $board_xdc $tx_xdc]
set_property PROCESSING_ORDER LATE [get_files $tx_xdc]
set_property top design_1_wrapper [current_fileset]
update_compile_order -fileset sources_1

validate_bd_design
generate_target all [get_files */design_1.bd]
export_ip_user_files -of_objects [get_files */design_1.bd] -no_script -sync -force -quiet

set_property strategy Performance_ExploreWithRemap [get_runs impl_1]
set_property STEPS.PHYS_OPT_DESIGN.ARGS.DIRECTIVE AggressiveExplore [get_runs impl_1]
set_property STEPS.ROUTE_DESIGN.ARGS.DIRECTIVE Explore [get_runs impl_1]
set_property STEPS.POST_ROUTE_PHYS_OPT_DESIGN.IS_ENABLED true [get_runs impl_1]
set_property STEPS.POST_ROUTE_PHYS_OPT_DESIGN.ARGS.DIRECTIVE AggressiveExplore [get_runs impl_1]
launch_runs impl_1 -to_step write_bitstream -jobs 8
wait_on_run impl_1
set run_status [get_property STATUS [get_runs impl_1]]
if {![string match {write_bitstream Complete!} $run_status]} {
    error "B2 implementation failed: $run_status"
}

open_run impl_1
set bitstream_path [file join $out_dir hello_zynq_b2.bit]
set xsa_path [file join $out_dir hello_zynq_b2.xsa]
set utilization_report [file join $out_dir utilization_impl.rpt]
set timing_report [file join $out_dir timing_impl.rpt]
set route_report [file join $out_dir route_status_impl.rpt]
set drc_report [file join $out_dir drc_impl.rpt]
report_utilization -file $utilization_report
report_timing_summary -delay_type min_max -max_paths 20 -file $timing_report
report_route_status -file $route_report
report_drc -file $drc_report
write_bitstream -force $bitstream_path
write_hw_platform -fixed -include_bit -force -file $xsa_path

set summary_path [file join $out_dir signoff_summary.txt]
set summary [open $summary_path w]
puts $summary "B2_BUILD_HEAD=$git_head"
puts $summary "B2_NPU_MODE=$npu_mode"
puts $summary "B2_VERILOG_DEFINE=[join $verilog_defines ,]"
puts $summary "B2_PART=$part"
puts $summary "B2_TOP=design_1_wrapper"
puts $summary "B2_DMA_MODE=SIMPLE_POLLING"
puts $summary "B2_DMA_SG=0"
puts $summary "B2_DMA_STREAM_WIDTH=32"
puts $summary "B2_DMA_MEMORY_WIDTH=64"
puts $summary "B2_DMA_LOOPBACK=MM2S_PACKET_NPU_S2MM"
puts $summary "B2_NPU_CLOCK_HZ=200000000"
puts $summary "B2_NPU_DSP_EXPECTED=4"
set dsp48_cells [get_cells -hierarchical -filter {REF_NAME == DSP48E1}]
set dsp48_count [llength $dsp48_cells]
puts $summary "B2_NPU_DSP48E1_COUNT=$dsp48_count"
puts $summary "B2_BITSTREAM=$bitstream_path"
puts $summary "B2_XSA=$xsa_path"
close $summary
puts "B2_BUILD_PASS"
puts "B2_BUILD_SUMMARY=$summary_path"
puts "B2_BITSTREAM=$bitstream_path"
puts "B2_XSA=$xsa_path"
close_project
