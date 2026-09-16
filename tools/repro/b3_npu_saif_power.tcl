# 同一xc7z020clg484-2/200 MHz routed OOC DCP上的dense/gated SAIF功耗分析。
# tclargs: action git_head out_dir dense_saif gated_saif

set action [lindex $argv 0]
set git_head [lindex $argv 1]
set out_dir [file normalize [lindex $argv 2]]
set dense_saif [file normalize [lindex $argv 3]]
set gated_saif [file normalize [lindex $argv 4]]
set root [file normalize [file join [file dirname [info script]] .. ..]]
set part xc7z020clg484-2
set top npu_eneuron_single_clock_skeleton
set dcp [file join $out_dir ${top}_200mhz_routed.dcp]
file mkdir $out_dir

if {$action eq "implement"} {
    read_verilog -sv [file join $root npu_eneuron_single_clock_skeleton.sv]
    synth_design -top $top -part $part -mode out_of_context -flatten_hierarchy rebuilt
    create_clock -name clk -period 5.000 [get_ports clk]
    set_property HD.CLK_SRC BUFGCTRL_X0Y0 [get_ports clk]
    report_utilization -file [file join $out_dir utilization_synth.rpt]
    report_timing_summary -delay_type min_max -max_paths 20 -file [file join $out_dir timing_synth.rpt]

    opt_design
    place_design
    phys_opt_design
    route_design
    report_route_status -file [file join $out_dir route_status_post_route.rpt]
    report_utilization -file [file join $out_dir utilization_post_route.rpt]
    report_timing_summary -delay_type min_max -max_paths 20 -file [file join $out_dir timing_post_route.rpt]
    report_drc -file [file join $out_dir drc_post_route.rpt]
    write_checkpoint -force $dcp
    write_verilog -force -mode funcsim [file join $out_dir ${top}_200mhz_post_route_funcsim.v]

    set summary [open [file join $out_dir implementation_summary.txt] w]
    puts $summary "RESULT=ROUTED_FUNCTIONAL_NETLIST_GENERATED"
    puts $summary "VIVADO_VERSION=[version -short]"
    puts $summary "PART=$part"
    puts $summary "TOP=$top"
    puts $summary "CLOCK_MHZ=200.000"
    puts $summary "CLOCK_PERIOD_NS=5.000"
    puts $summary "GIT_HEAD=$git_head"
    puts $summary "DCP=$dcp"
    puts $summary "BOUNDARY=OOC NPU core only; device static is whole-device baseline; no PS, DMA, board I/O or external rails"
    close $summary
    puts "B3_NPU_POST_ROUTE_IMPL_DONE part=$part dcp=$dcp"
} elseif {$action eq "report"} {
    foreach mode {dense gated} saif [list $dense_saif $gated_saif] {
        open_checkpoint $dcp
        if {![file exists $saif]} { error "missing SAIF for $mode: $saif" }
        set unmatched [file join $out_dir ${mode}_saif_unmatched.rpt]
        read_saif -verbose -strip_path tb_b3_npu_saif_power/dut -out_file $unmatched $saif
        report_power -hier all -hierarchical_depth 0 -advisory \
            -file [file join $out_dir ${mode}_power_post_route.rpt]
        close_design
    }
    puts "B3_NPU_POST_ROUTE_SAIF_REPORTS_DONE part=$part dcp=$dcp"
} else {
    error "action must be implement or report"
}
exit
