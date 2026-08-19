# Vivado 2024.1 非工程 OOC 签核：Host CDC Bridge + Controller + 4->2->2 Tile。
set root [file normalize [file dirname [info script]]]
set out_dir [file join $root vivado_host_bridge_reports]
file mkdir $out_dir

set part xc7a35tcpg236-1
set top digital_snn_host_bridge_system
set host_period_ns 20.000
set tile_period_ns 10.000

proc write_text {path text} {
    set stream [open $path w]
    puts -nonewline $stream $text
    close $stream
}

proc clock_timing_metrics {clock_name delay_type} {
    set clock_object [get_clocks -quiet $clock_name]
    if {[llength $clock_object] != 1} {
        error "时钟不存在或不唯一：$clock_name"
    }

    set worst_paths [get_timing_paths -quiet -from $clock_object -to $clock_object \
        -delay_type $delay_type -max_paths 1 -nworst 1]
    if {[llength $worst_paths] == 0} {
        error "时钟域没有可签核的 $delay_type 路径：$clock_name"
    }
    set worst_slack [get_property SLACK [lindex $worst_paths 0]]

    set violating_paths [get_timing_paths -quiet -from $clock_object -to $clock_object \
        -delay_type $delay_type -slack_lesser_than 0.0 -max_paths 100000 -nworst 1]
    set total_negative_slack 0.0
    foreach path $violating_paths {
        set slack [get_property SLACK $path]
        if {$slack < 0.0} {
            set total_negative_slack [expr {$total_negative_slack + $slack}]
        }
    }
    return [list $worst_slack $total_negative_slack [llength $violating_paths]]
}

proc classify_cdc_report {report_path classification_path} {
    set stream [open $report_path r]
    set text [read $stream]
    close $stream

    set xpm_critical 0
    set xpm_warning 0
    set xpm_info 0
    set xpm_safe 0
    set xpm_unknown 0
    set external_critical 0
    set external_unsafe 0
    set external_warning 0
    set external_lines {}
    set classified_items {}

    foreach line [split $text "\n"] {
        set lower [string tolower $line]
        # 只解析详细表中的编号路径，跳过报告顶部的按 ID 汇总行。
        if {![regexp {^[[:space:]]*[0-9]+[[:space:]]+(cdc-[0-9]+)[[:space:]]+([^[:space:]]+)} \
            $lower -> cdc_id severity]} {
            continue
        }
        set is_xpm [expr {[string first "xpm_" $lower] >= 0 ||
            [string first "command_fifo" $lower] >= 0 ||
            [string first "response_fifo" $lower] >= 0}]
        set is_critical [expr {[string first "critical" $lower] >= 0}]
        set is_warning [expr {[string first "warning" $lower] >= 0}]
        set is_safe [expr {[string first "safe" $lower] >= 0 &&
            [string first "unsafe" $lower] < 0}]
        set is_unsafe [expr {[string first "unsafe" $lower] >= 0}]

        if {$is_xpm} {
            if {$is_critical} {incr xpm_critical}
            if {$is_warning} {incr xpm_warning}
            if {$severity eq "info"} {incr xpm_info}
            if {$is_safe} {incr xpm_safe}
            if {$cdc_id eq "cdc-6"} {
                set item_class "XPM_FIFO_GRAY_POINTER"
                set explanation "XPM async FIFO Gray pointer bus; two ASYNC_REG stages and one-bit Gray transitions make this recognized crossing acceptable."
            } elseif {$cdc_id eq "cdc-3"} {
                set item_class "XPM_FIFO_RESET_SYNC"
                set explanation "XPM async FIFO single-bit reset/reset-busy synchronizer; Vivado recognizes the two-stage ASYNC_REG chain."
            } else {
                set item_class "XPM_FIFO_OTHER"
                set explanation "Unrecognized XPM-internal CDC type; signoff must fail pending explicit review."
                incr xpm_unknown
            }
        } else {
            if {$is_critical} {incr external_critical}
            if {$is_unsafe} {incr external_unsafe}
            if {$is_warning} {incr external_warning}
            set item_class "EXTERNAL_CDC"
            set explanation "CDC outside the two XPM FIFOs; Critical or Unsafe findings fail signoff and all other findings require explicit review."
            if {$is_critical || $is_unsafe || $is_warning} {
                lappend external_lines [string trim $line]
            }
        }
        lappend classified_items [list $cdc_id $severity $item_class $explanation [string trim $line]]
    }

    set summary "CDC_CLASSIFICATION\n"
    append summary "XPM_SCOPE=host_bridge/command_fifo,host_bridge/response_fifo\n"
    append summary "XPM_POLICY=Vivado-recognized XPM FIFO internal CDC is accepted when no external endpoints are implicated.\n"
    append summary "XPM_CRITICAL_LINES=$xpm_critical\n"
    append summary "XPM_WARNING_LINES=$xpm_warning\n"
    append summary "XPM_INFO_LINES=$xpm_info\n"
    append summary "XPM_SAFE_LINES=$xpm_safe\n"
    append summary "XPM_UNKNOWN_LINES=$xpm_unknown\n"
    append summary "EXTERNAL_CRITICAL_LINES=$external_critical\n"
    append summary "EXTERNAL_UNSAFE_LINES=$external_unsafe\n"
    append summary "EXTERNAL_WARNING_LINES=$external_warning\n"
    if {[llength $external_lines] == 0} {
        append summary "EXTERNAL_FINDINGS=NONE\n"
    } else {
        append summary "EXTERNAL_FINDINGS_BEGIN\n"
        foreach line $external_lines {
            append summary "$line\n"
        }
        append summary "EXTERNAL_FINDINGS_END\n"
    }
    append summary "CLASSIFIED_ITEMS=[llength $classified_items]\n"
    set item_index 0
    foreach item $classified_items {
        incr item_index
        append summary "ITEM_${item_index}_ID=[lindex $item 0]\n"
        append summary "ITEM_${item_index}_SEVERITY=[lindex $item 1]\n"
        append summary "ITEM_${item_index}_CLASS=[lindex $item 2]\n"
        append summary "ITEM_${item_index}_EXPLANATION=[lindex $item 3]\n"
        append summary "ITEM_${item_index}_RAW=[lindex $item 4]\n"
    }
    write_text $classification_path $summary
    return [list $external_critical $external_unsafe $external_warning $xpm_critical $xpm_unknown]
}

puts "ENeuron Host Bridge System: 读取 RTL"
read_verilog -sv [list \
    [file join $root digital_lif_engine.sv] \
    [file join $root digital_snn_tile_4x2x2.sv] \
    [file join $root digital_snn_host_bridge_controller.sv] \
    [file join $root digital_snn_host_bridge.sv] \
    [file join $root digital_snn_host_bridge_system.sv]]

puts "ENeuron Host Bridge System: 综合 $top，器件 $part"
synth_design -top $top -part $part -mode out_of_context

create_clock -name host_clk -period $host_period_ns [get_ports host_clk]
create_clock -name tile_clk -period $tile_period_ns [get_ports tile_clk]
set_clock_groups -asynchronous \
    -group [get_clocks host_clk] \
    -group [get_clocks tile_clk]

# OOC 代理时钟位置只用于建立可重复的全局时钟延迟与偏斜估计。
set_property HD.CLK_SRC BUFGCTRL_X0Y0 [get_ports host_clk]
set_property HD.CLK_SRC BUFGCTRL_X0Y1 [get_ports tile_clk]

write_checkpoint -force [file join $out_dir digital_snn_host_bridge_system_synth.dcp]
report_timing_summary -delay_type min_max -max_paths 20 \
    -file [file join $out_dir timing_summary_synth.rpt]
report_utilization -hierarchical \
    -file [file join $out_dir utilization_hierarchical_synth.rpt]

puts "ENeuron Host Bridge System: opt/place/route"
opt_design
place_design
phys_opt_design
route_design

set timing_report [file join $out_dir timing_summary_impl.rpt]
set clock_report [file join $out_dir clock_interaction_impl.rpt]
set cdc_report [file join $out_dir cdc_impl.rpt]
set route_report [file join $out_dir route_status_impl.rpt]
set drc_report [file join $out_dir drc_impl.rpt]
set methodology_report [file join $out_dir methodology_impl.rpt]
set utilization_report [file join $out_dir utilization_hierarchical_impl.rpt]
set power_report [file join $out_dir power_impl.rpt]
set cdc_classification [file join $out_dir cdc_classification.txt]
set signoff_summary [file join $out_dir signoff_summary.txt]

report_timing_summary -delay_type min_max -max_paths 20 -file $timing_report
report_clock_interaction -delay_type min_max -file $clock_report
report_cdc -details -file $cdc_report
report_route_status -file $route_report
report_drc -file $drc_report
report_methodology -file $methodology_report
report_utilization -hierarchical -file $utilization_report
report_power -file $power_report
write_checkpoint -force [file join $out_dir digital_snn_host_bridge_system_impl.dcp]

set host_setup [clock_timing_metrics host_clk max]
set host_hold [clock_timing_metrics host_clk min]
set tile_setup [clock_timing_metrics tile_clk max]
set tile_hold [clock_timing_metrics tile_clk min]

set route_stream [open $route_report r]
set route_text [read $route_stream]
close $route_stream
if {![regexp -nocase {nets with routing errors[^0-9]*([0-9]+)} $route_text -> route_errors]} {
    error "无法从 route_status_impl.rpt 解析 routing errors"
}

set drc_error_count [llength [get_drc_violations -quiet -filter {SEVERITY == "Error"}]]
set drc_critical_count [llength [get_drc_violations -quiet -filter {SEVERITY == "Critical Warning"}]]
set cdc_counts [classify_cdc_report $cdc_report $cdc_classification]
set external_cdc_critical [lindex $cdc_counts 0]
set external_cdc_unsafe [lindex $cdc_counts 1]
set external_cdc_warning [lindex $cdc_counts 2]
set xpm_cdc_critical [lindex $cdc_counts 3]
set xpm_cdc_unknown [lindex $cdc_counts 4]

set summary "RESULT=PENDING\n"
append summary "PART=$part\n"
append summary "TOP=$top\n"
append summary "HOST_CLOCK_MHZ=50.000\n"
append summary "TILE_CLOCK_MHZ=100.000\n"
append summary "CLOCK_GROUPS=ASYNCHRONOUS\n"
append summary "HOST_WNS_NS=[lindex $host_setup 0]\n"
append summary "HOST_TNS_NS=[lindex $host_setup 1]\n"
append summary "HOST_SETUP_VIOLATIONS=[lindex $host_setup 2]\n"
append summary "HOST_WHS_NS=[lindex $host_hold 0]\n"
append summary "HOST_THS_NS=[lindex $host_hold 1]\n"
append summary "HOST_HOLD_VIOLATIONS=[lindex $host_hold 2]\n"
append summary "TILE_WNS_NS=[lindex $tile_setup 0]\n"
append summary "TILE_TNS_NS=[lindex $tile_setup 1]\n"
append summary "TILE_SETUP_VIOLATIONS=[lindex $tile_setup 2]\n"
append summary "TILE_WHS_NS=[lindex $tile_hold 0]\n"
append summary "TILE_THS_NS=[lindex $tile_hold 1]\n"
append summary "TILE_HOLD_VIOLATIONS=[lindex $tile_hold 2]\n"
append summary "ROUTE_ERRORS=$route_errors\n"
append summary "DRC_ERRORS=$drc_error_count\n"
append summary "DRC_CRITICAL_WARNINGS=$drc_critical_count\n"
append summary "EXTERNAL_CDC_CRITICAL_LINES=$external_cdc_critical\n"
append summary "EXTERNAL_CDC_UNSAFE_LINES=$external_cdc_unsafe\n"
append summary "EXTERNAL_CDC_WARNING_LINES=$external_cdc_warning\n"
append summary "XPM_CDC_CRITICAL_LINES=$xpm_cdc_critical\n"
append summary "XPM_CDC_UNKNOWN_LINES=$xpm_cdc_unknown\n"

set gate_failures {}
foreach item [list \
    [list HOST_WNS [lindex $host_setup 0]] \
    [list HOST_WHS [lindex $host_hold 0]] \
    [list TILE_WNS [lindex $tile_setup 0]] \
    [list TILE_WHS [lindex $tile_hold 0]]] {
    if {[lindex $item 1] < 0.0} {
        lappend gate_failures "[lindex $item 0]=[lindex $item 1]"
    }
}
foreach item [list \
    [list HOST_TNS [lindex $host_setup 1]] \
    [list HOST_THS [lindex $host_hold 1]] \
    [list TILE_TNS [lindex $tile_setup 1]] \
    [list TILE_THS [lindex $tile_hold 1]]] {
    if {[lindex $item 1] != 0.0} {
        lappend gate_failures "[lindex $item 0]=[lindex $item 1]"
    }
}
if {$route_errors != 0} {lappend gate_failures "ROUTE_ERRORS=$route_errors"}
if {$drc_error_count != 0} {lappend gate_failures "DRC_ERRORS=$drc_error_count"}
if {$drc_critical_count != 0} {lappend gate_failures "DRC_CRITICAL_WARNINGS=$drc_critical_count"}
if {$external_cdc_critical != 0} {lappend gate_failures "EXTERNAL_CDC_CRITICAL=$external_cdc_critical"}
if {$external_cdc_unsafe != 0} {lappend gate_failures "EXTERNAL_CDC_UNSAFE=$external_cdc_unsafe"}
if {$xpm_cdc_critical != 0} {lappend gate_failures "XPM_CDC_CRITICAL=$xpm_cdc_critical"}
if {$xpm_cdc_unknown != 0} {lappend gate_failures "XPM_CDC_UNKNOWN=$xpm_cdc_unknown"}

if {[llength $gate_failures] == 0} {
    regsub {RESULT=PENDING} $summary {RESULT=PASS} summary
    write_text $signoff_summary $summary
    puts "VIVADO_ENEURON_HOST_BRIDGE_SYSTEM_PASS out_dir=$out_dir"
    exit 0
}

append summary "FAILURES=[join $gate_failures {, }]\n"
regsub {RESULT=PENDING} $summary {RESULT=FAIL} summary
write_text $signoff_summary $summary
error "Host Bridge System OOC 硬门槛失败：[join $gate_failures {, }]"
