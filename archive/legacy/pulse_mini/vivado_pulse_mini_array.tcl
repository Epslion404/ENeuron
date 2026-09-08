set root [file normalize [pwd]]
set out_root [file join $root vivado_pulse_mini_array_reports]
file mkdir $out_root
set part xc7z020clg400-1
foreach n {32 64 128} {
    set out_dir [file join $out_root "n$n"]
    file mkdir $out_dir
    read_verilog -sv [file join $root pulse_mini_core.sv]
    read_verilog -sv [file join $root pulse_mini_array.sv]
    synth_design -top pulse_mini_array -part $part -mode out_of_context -generic N_CORES=$n
    create_clock -name clk -period 10.000 [get_ports clk]
    opt_design
    place_design
    route_design
    report_utilization -file [file join $out_dir utilization_impl.rpt]
    report_timing_summary -delay_type min_max -max_paths 10 -file [file join $out_dir timing_impl.rpt]
    report_drc -file [file join $out_dir drc_impl.rpt]
    set util_text [read [open [file join $out_dir utilization_impl.rpt] r]]
    set lut 0
    set ff 0
    set bram 0
    set dsp 0
    if {[regexp {Slice LUTs\s*\|\s*([0-9]+)} $util_text -> value]} {set lut $value}
    if {[regexp {Slice Registers\s*\|\s*([0-9]+)} $util_text -> value]} {set ff $value}
    if {[regexp {Block RAM Tile\s*\|\s*([0-9]+)} $util_text -> value]} {set bram $value}
    if {[regexp {DSPs\s*\|\s*([0-9]+)} $util_text -> value]} {set dsp $value}
    set timing_text [read [open [file join $out_dir timing_impl.rpt] r]]
    set wns NA
    set tns NA
    if {[regexp {\n\s+(-?[0-9.]+)\s+(-?[0-9.]+)\s+[0-9]+\s+[0-9]+} $timing_text -> value_w value_t]} {
        set wns $value_w
        set tns $value_t
    }
    set fh [open [file join $out_dir summary.txt] w]
    puts $fh "N_CORES=$n"
    puts $fh "LUT=$lut"
    puts $fh "FF=$ff"
    puts $fh "BRAM=$bram"
    puts $fh "DSP=$dsp"
    puts $fh "WNS_NS=$wns"
    puts $fh "TNS_NS=$tns"
    puts $fh "CLOCK_MHZ=100.000"
    close $fh
    close_design
}
puts "PULSE_MINI_ARRAY_VIVADO_PASS"
exit
