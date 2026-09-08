# Vivado 2024.1 非工程 OOC 签核：固定 4->2->2 数字 SNN Tile。
set root [file normalize [file dirname [info script]]]
set out_dir [file join $root vivado_tile_reports]
file mkdir $out_dir

set part xc7a35tcpg236-1
set top digital_snn_tile_4x2x2
set clock_period_ns 10.000
set lut_budget 3200
set ff_budget 2000

proc write_text {path content} {
    set stream [open $path w]
    puts -nonewline $stream $content
    close $stream
}

proc read_text {path} {
    set stream [open $path r]
    set content [read $stream]
    close $stream
    return $content
}

proc timing_metrics {delay_type} {
    set worst_paths [get_timing_paths -quiet -delay_type $delay_type -max_paths 1 -nworst 1]
    if {[llength $worst_paths] == 0} {
        error "Tile 没有可签核的 $delay_type 路径"
    }
    set worst_slack [get_property SLACK [lindex $worst_paths 0]]
    set violating_paths [get_timing_paths -quiet -delay_type $delay_type \
        -slack_lesser_than 0.0 -max_paths 100000 -nworst 1]
    set total_negative_slack 0.0
    foreach path $violating_paths {
        set slack [get_property SLACK $path]
        if {$slack < 0.0} {
            set total_negative_slack [expr {$total_negative_slack + $slack}]
        }
    }
    return [list $worst_slack $total_negative_slack [llength $violating_paths]]
}

proc report_rule_counts {report_text report_name} {
    set error_count 0
    set critical_count 0
    set warning_count 0
    set rules {}
    foreach line [split $report_text "\n"] {
        if {![regexp {^\|[[:space:]]*([^|]+?)[[:space:]]*\|[[:space:]]*(Error|Critical Warning|Warning)[[:space:]]*\|.*\|[[:space:]]*([0-9]+)[[:space:]]*\|$} \
            $line -> rule severity count]} {
            continue
        }
        set rule [string trim $rule]
        lappend rules [list $rule $severity $count]
        if {$severity eq "Error"} {
            incr error_count $count
        } elseif {$severity eq "Critical Warning"} {
            incr critical_count $count
        } else {
            incr warning_count $count
        }
    }
    if {[llength $rules] == 0} {
        error "无法从 $report_name 解析规则汇总"
    }
    return [list $error_count $critical_count $warning_count $rules]
}

proc only_allowed_warning {rules allowed_rule allowed_count} {
    if {[llength $rules] != 1} {
        return 0
    }
    set item [lindex $rules 0]
    return [expr {
        [lindex $item 0] eq $allowed_rule &&
        [lindex $item 1] eq "Warning" &&
        [lindex $item 2] == $allowed_count
    }]
}

puts "ENeuron Tile: 读取 RTL"
read_verilog -sv [list \
    [file join $root digital_lif_engine.sv] \
    [file join $root digital_snn_tile_4x2x2.sv]]

puts "ENeuron Tile: 综合 $top，器件 $part"
synth_design -top $top -part $part -mode out_of_context
create_clock -name clk -period $clock_period_ns [get_ports clk]
# OOC 代理位置只用于建立可重复的全局时钟延迟和偏斜估计。
set_property HD.CLK_SRC BUFGCTRL_X0Y0 [get_ports clk]

report_utilization -file [file join $out_dir utilization_synth.rpt]
report_timing_summary -delay_type min_max -max_paths 10 \
    -file [file join $out_dir timing_synth.rpt]
report_drc -file [file join $out_dir drc_synth.rpt]
write_checkpoint -force [file join $out_dir digital_snn_tile_4x2x2_synth.dcp]

puts "ENeuron Tile: opt/place/route"
opt_design
place_design
route_design

set utilization_report [file join $out_dir utilization_impl.rpt]
set route_report [file join $out_dir route_status_impl.rpt]
set timing_report [file join $out_dir timing_impl.rpt]
set methodology_report [file join $out_dir methodology_impl.rpt]
set drc_report [file join $out_dir drc_impl.rpt]
set power_report [file join $out_dir power_impl.rpt]
set signoff_summary [file join $out_dir signoff_summary.txt]

report_utilization -file $utilization_report
report_route_status -file $route_report
report_timing_summary -delay_type min_max -max_paths 10 -file $timing_report
report_methodology -file $methodology_report
report_drc -file $drc_report
report_power -file $power_report
write_checkpoint -force [file join $out_dir digital_snn_tile_4x2x2_impl.dcp]

set setup [timing_metrics max]
set hold [timing_metrics min]

set route_text [read_text $route_report]
if {![regexp -nocase {# of fully routed nets[^0-9]*([0-9]+)} $route_text -> fully_routed_nets]} {
    error "无法从 route_status_impl.rpt 解析 fully routed nets"
}
if {![regexp -nocase {# of nets with routing errors[^0-9]*([0-9]+)} $route_text -> route_errors]} {
    error "无法从 route_status_impl.rpt 解析 routing errors"
}

set utilization_text [read_text $utilization_report]
foreach item [list \
    [list lut {\| Slice LUTs[[:space:]]*\|[[:space:]]*([0-9]+)}] \
    [list ff {\| Slice Registers[[:space:]]*\|[[:space:]]*([0-9]+)}] \
    [list bram36 {\|[[:space:]]*RAMB36/FIFO\*[[:space:]]*\|[[:space:]]*([0-9]+)}] \
    [list bram18 {\|[[:space:]]*RAMB18[[:space:]]*\|[[:space:]]*([0-9]+)}] \
    [list dsp {\| DSPs[[:space:]]*\|[[:space:]]*([0-9]+)}]] {
    if {![regexp [lindex $item 1] $utilization_text -> value]} {
        error "无法从 utilization_impl.rpt 解析 [lindex $item 0]"
    }
    set [lindex $item 0] $value
}

set drc_counts [report_rule_counts [read_text $drc_report] drc_impl.rpt]
set methodology_counts [report_rule_counts [read_text $methodology_report] methodology_impl.rpt]
set drc_errors [lindex $drc_counts 0]
set drc_critical [lindex $drc_counts 1]
set drc_warnings [lindex $drc_counts 2]
set methodology_errors [lindex $methodology_counts 0]
set methodology_critical [lindex $methodology_counts 1]
set methodology_warnings [lindex $methodology_counts 2]
set drc_allowlist_ok [only_allowed_warning [lindex $drc_counts 3] CFGBVS-1 1]
set methodology_allowlist_ok [only_allowed_warning [lindex $methodology_counts 3] TIMING-18 180]

set power_text [read_text $power_report]
if {![regexp {\| Total On-Chip Power \(W\)[[:space:]]*\|[[:space:]]*([0-9]+\.[0-9]+)} \
    $power_text -> power_w]} {
    error "无法从 power_impl.rpt 解析总功耗"
}
if {![regexp {\| Confidence Level[[:space:]]*\|[[:space:]]*([^|]+?)[[:space:]]*\|} \
    $power_text -> power_confidence]} {
    error "无法从 power_impl.rpt 解析功耗置信度"
}
set power_confidence [string trim $power_confidence]
if {![regexp {\| Simulation Activity File[[:space:]]*\|[[:space:]]*---[[:space:]]*\|} $power_text]} {
    error "功耗报告不再是冻结的 vector-less 条件"
}

set vivado_version [version -short]
set summary "RESULT=PENDING\n"
append summary "VIVADO_VERSION=$vivado_version\n"
append summary "PART=$part\n"
append summary "TOP=$top\n"
append summary "MODE=OUT_OF_CONTEXT\n"
append summary "CLOCK_MHZ=100.000\n"
append summary "WNS_NS=[lindex $setup 0]\n"
append summary "TNS_NS=[lindex $setup 1]\n"
append summary "SETUP_VIOLATIONS=[lindex $setup 2]\n"
append summary "WHS_NS=[lindex $hold 0]\n"
append summary "THS_NS=[lindex $hold 1]\n"
append summary "HOLD_VIOLATIONS=[lindex $hold 2]\n"
append summary "ROUTE_ERRORS=$route_errors\n"
append summary "FULLY_ROUTED_NETS=$fully_routed_nets\n"
append summary "DRC_ERRORS=$drc_errors\n"
append summary "DRC_CRITICAL_WARNINGS=$drc_critical\n"
append summary "DRC_WARNINGS=$drc_warnings\n"
append summary "DRC_CFGBVS1_WARNINGS=1\n"
append summary "METHODOLOGY_ERRORS=$methodology_errors\n"
append summary "METHODOLOGY_CRITICAL_WARNINGS=$methodology_critical\n"
append summary "METHODOLOGY_WARNINGS=$methodology_warnings\n"
append summary "METHODOLOGY_TIMING18_WARNINGS=180\n"
append summary "LUT=$lut\n"
append summary "FF=$ff\n"
append summary "BRAM36=$bram36\n"
append summary "BRAM18=$bram18\n"
append summary "DSP=$dsp\n"
append summary "LUT_BUDGET=$lut_budget\n"
append summary "FF_BUDGET=$ff_budget\n"
append summary "POWER_W=$power_w\n"
append summary "POWER_CONFIDENCE=$power_confidence\n"
append summary "POWER_ACTIVITY_FILE=NONE\n"

set gate_failures {}
foreach item [list \
    [list WNS [lindex $setup 0]] \
    [list WHS [lindex $hold 0]]] {
    if {[lindex $item 1] < 0.0} {
        lappend gate_failures "[lindex $item 0]=[lindex $item 1]"
    }
}
foreach item [list \
    [list TNS [lindex $setup 1]] \
    [list THS [lindex $hold 1]] \
    [list SETUP_VIOLATIONS [lindex $setup 2]] \
    [list HOLD_VIOLATIONS [lindex $hold 2]] \
    [list ROUTE_ERRORS $route_errors] \
    [list DRC_ERRORS $drc_errors] \
    [list DRC_CRITICAL_WARNINGS $drc_critical] \
    [list METHODOLOGY_ERRORS $methodology_errors] \
    [list METHODOLOGY_CRITICAL_WARNINGS $methodology_critical] \
    [list BRAM36 $bram36] \
    [list BRAM18 $bram18] \
    [list DSP $dsp]] {
    if {[lindex $item 1] != 0} {
        lappend gate_failures "[lindex $item 0]=[lindex $item 1]"
    }
}
if {$fully_routed_nets == 0} {lappend gate_failures "FULLY_ROUTED_NETS=0"}
if {!$drc_allowlist_ok} {lappend gate_failures "DRC_WARNING_SET_CHANGED"}
if {!$methodology_allowlist_ok} {lappend gate_failures "METHODOLOGY_WARNING_SET_CHANGED"}
if {$lut > $lut_budget} {lappend gate_failures "LUT=$lut>$lut_budget"}
if {$ff > $ff_budget} {lappend gate_failures "FF=$ff>$ff_budget"}
if {$power_confidence ne "Medium"} {lappend gate_failures "POWER_CONFIDENCE=$power_confidence"}

if {[llength $gate_failures] == 0} {
    regsub {RESULT=PENDING} $summary {RESULT=PASS} summary
    write_text $signoff_summary $summary
    puts "VIVADO_ENEURON_TILE_PASS out_dir=$out_dir"
    exit 0
}

append summary "FAILURES=[join $gate_failures {, }]\n"
regsub {RESULT=PENDING} $summary {RESULT=FAIL} summary
write_text $signoff_summary $summary
error "Tile OOC 硬门槛失败：[join $gate_failures {, }]"
