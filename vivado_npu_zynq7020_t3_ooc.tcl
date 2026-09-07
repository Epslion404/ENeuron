# Vivado 2024.1 XC7Z020 T3 OOC：核心 + T1 wrapper + 四条 XPM FIFO。
set script_dir [file normalize [file dirname [info script]]]
set git_head [lindex $argv 0]
set out_dir [file normalize [lindex $argv 1]]
if {$git_head eq {}} { set git_head UNKNOWN }
if {$out_dir eq {}} { set out_dir [file join $script_dir vivado_npu_zynq7020_t3_ooc_reports] }
file mkdir $out_dir

set part xc7z020clg400-1
set top npu_zynq7020_t1_wrapper
set host_period 10.000
set npu_period 10.000

read_verilog -sv [list \
    [file join $script_dir npu_eneuron_single_clock_skeleton.sv] \
    [file join $script_dir npu_zynq7020_t1_wrapper.sv]]
synth_design -top $top -part $part -mode out_of_context -flatten_hierarchy rebuilt
create_clock -name host_clk -period $host_period [get_ports host_clk]
create_clock -name npu_clk -period $npu_period [get_ports npu_clk]
set_clock_groups -asynchronous -group [get_clocks host_clk] -group [get_clocks npu_clk]
set_property HD.CLK_SRC BUFGCTRL_X0Y0 [get_ports host_clk]
set_property HD.CLK_SRC BUFGCTRL_X0Y1 [get_ports npu_clk]

report_utilization -hierarchical -file [file join $out_dir utilization_synth_hierarchical.rpt]
report_timing_summary -delay_type min_max -max_paths 20 -file [file join $out_dir timing_synth.rpt]
report_cdc -details -file [file join $out_dir cdc_synth.rpt]

opt_design
place_design
phys_opt_design
route_design

set timing_report [file join $out_dir timing_impl.rpt]
set utilization_report [file join $out_dir utilization_impl_hierarchical.rpt]
set cdc_report [file join $out_dir cdc_impl.rpt]
set route_report [file join $out_dir route_status_impl.rpt]
set drc_report [file join $out_dir drc_impl.rpt]
report_timing_summary -delay_type min_max -max_paths 20 -file $timing_report
report_utilization -hierarchical -file $utilization_report
report_cdc -details -file $cdc_report
report_route_status -file $route_report
report_drc -file $drc_report
write_checkpoint -force [file join $out_dir ${top}_impl.dcp]

proc clock_metrics {clock_name delay_type} {
    set clock [get_clocks -quiet $clock_name]
    if {[llength $clock] != 1} { error "时钟不存在或不唯一: $clock_name" }
    set worst [get_timing_paths -quiet -from $clock -to $clock -delay_type $delay_type -max_paths 1 -nworst 1]
    if {[llength $worst] == 0} { return [list NA NA 0] }
    set worst_slack [get_property SLACK [lindex $worst 0]]
    set violating [get_timing_paths -quiet -from $clock -to $clock -delay_type $delay_type \
        -slack_lesser_than 0.0 -max_paths 100000 -nworst 1]
    set total 0.0
    foreach path $violating {
        set slack [get_property SLACK $path]
        if {$slack < 0.0} { set total [expr {$total + $slack}] }
    }
    return [list $worst_slack $total [llength $violating]]
}

proc report_value {path pattern} {
    set fh [open $path r]
    set text [read $fh]
    close $fh
    if {[regexp -nocase $pattern $text -> value]} { return $value }
    return NA
}

proc classify_cdc {path} {
    set fh [open $path r]
    set text [read $fh]
    close $fh
    set external_critical 0
    set external_warning 0
    set xpm_critical 0
    set xpm_warning 0
    foreach line [split $text "\n"] {
        if {![regexp {^[[:space:]]*[0-9]+[[:space:]]+CDC-[0-9]+[[:space:]]+(Critical|Warning)} $line -> severity]} {
            continue
        }
        set is_xpm [expr {[string first "gnuram_async_fifo.xpm_fifo_base_inst" $line] >= 0}]
        if {$is_xpm} {
            if {$severity eq "Critical"} { incr xpm_critical } else { incr xpm_warning }
        } else {
            if {$severity eq "Critical"} { incr external_critical } else { incr external_warning }
        }
    }
    return [list $external_critical $external_warning $xpm_critical $xpm_warning]
}

set host_setup [clock_metrics host_clk max]
set host_hold [clock_metrics host_clk min]
set npu_setup [clock_metrics npu_clk max]
set npu_hold [clock_metrics npu_clk min]
set route_errors [report_value $route_report {nets with routing errors[^0-9]*([0-9]+)}]
set drc_errors [llength [get_drc_violations -quiet -filter {SEVERITY == "Error"}]]
set drc_critical [llength [get_drc_violations -quiet -filter {SEVERITY == "Critical Warning"}]]
set cdc_counts [classify_cdc $cdc_report]
set external_cdc_critical [lindex $cdc_counts 0]
set external_cdc_warning [lindex $cdc_counts 1]
set xpm_cdc_critical [lindex $cdc_counts 2]
set xpm_cdc_warning [lindex $cdc_counts 3]
set dsp_cells [get_cells -hierarchical -filter {REF_NAME == DSP48E1}]
set dsp_count [llength $dsp_cells]
set dsp_fh [open [file join $out_dir dsp48e1_cells.txt] w]
foreach cell [lsort $dsp_cells] { puts $dsp_fh "CELL=$cell LOC=[get_property LOC $cell]" }
close $dsp_fh

set setup_fail [expr {[lindex $host_setup 2] + [lindex $npu_setup 2]}]
set hold_fail [expr {[lindex $host_hold 2] + [lindex $npu_hold 2]}]
set physical_gate NOT_PROVEN
if {$dsp_count == 4 && $setup_fail == 0 && $hold_fail == 0 && $route_errors eq "0" &&
    $drc_errors == 0 && $drc_critical == 0 && $external_cdc_critical == 0 &&
    $external_cdc_warning == 0 && [lindex $host_setup 0] >= 0.0 &&
    [lindex $host_hold 0] >= 0.0 && [lindex $npu_setup 0] >= 0.0 && [lindex $npu_hold 0] >= 0.0} {
    set physical_gate PASS
}

set summary [open [file join $out_dir signoff_summary.txt] w]
puts $summary "RESULT=ROUTED"
puts $summary "PHYSICAL_GATE=$physical_gate"
puts $summary "VIVADO_VERSION=[version -short]"
puts $summary "PART=$part"
puts $summary "TOP=$top"
puts $summary "GIT_HEAD=$git_head"
puts $summary "HOST_CLOCK_MHZ=100.000"
puts $summary "NPU_CLOCK_MHZ=100.000"
puts $summary "CLOCK_GROUPS=ASYNCHRONOUS"
puts $summary "DSP48E1_COUNT=$dsp_count"
puts $summary "EXPECTED_DSP48E1_COUNT=4"
puts $summary "HOST_WNS_NS=[lindex $host_setup 0]"
puts $summary "HOST_TNS_NS=[lindex $host_setup 1]"
puts $summary "HOST_SETUP_FAILING_ENDPOINTS=[lindex $host_setup 2]"
puts $summary "HOST_WHS_NS=[lindex $host_hold 0]"
puts $summary "HOST_THS_NS=[lindex $host_hold 1]"
puts $summary "HOST_HOLD_FAILING_ENDPOINTS=[lindex $host_hold 2]"
puts $summary "NPU_WNS_NS=[lindex $npu_setup 0]"
puts $summary "NPU_TNS_NS=[lindex $npu_setup 1]"
puts $summary "NPU_SETUP_FAILING_ENDPOINTS=[lindex $npu_setup 2]"
puts $summary "NPU_WHS_NS=[lindex $npu_hold 0]"
puts $summary "NPU_THS_NS=[lindex $npu_hold 1]"
puts $summary "NPU_HOLD_FAILING_ENDPOINTS=[lindex $npu_hold 2]"
puts $summary "ROUTE_ERRORS=$route_errors"
puts $summary "DRC_ERRORS=$drc_errors"
puts $summary "DRC_CRITICAL_WARNINGS=$drc_critical"
puts $summary "EXTERNAL_CDC_CRITICAL=$external_cdc_critical"
puts $summary "EXTERNAL_CDC_WARNING=$external_cdc_warning"
puts $summary "XPM_INTERNAL_CDC_CRITICAL=$xpm_cdc_critical"
puts $summary "XPM_INTERNAL_CDC_WARNING=$xpm_cdc_warning"
puts $summary "UTILIZATION_REPORT=$utilization_report"
puts $summary "CDC_REPORT=$cdc_report"
puts $summary "NOTES=Vivado 2024.1 post-route; T1 wrapper with four real XPM async FIFOs; no AXI/DMA/PS/Ethernet/board I/O"
close $summary
puts "T3_XC7Z020_OOC_DONE part=$part top=$top dsp48e1_count=$dsp_count physical_gate=$physical_gate out_dir=$out_dir"
exit
