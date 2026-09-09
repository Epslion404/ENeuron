set repo_root [file normalize [file join [file dirname [info script]] .. ..]]
set out_arg [lindex $argv 0]
set out_dir [file normalize [expr {$out_arg eq {} ? [file join $repo_root artifacts tmp_b2_packet_memory_probe] : $out_arg}]]
file mkdir $out_dir
read_verilog -sv [file join $repo_root b2_packet_ingress.sv]
read_verilog -sv [file join $repo_root b2_packet_bram.sv]
read_verilog -sv [file join $repo_root b2_packet_egress.sv]

foreach top {b2_packet_ingress b2_packet_egress} {
    synth_design -top $top -part xc7z020clg484-2 -mode out_of_context
    report_utilization -hierarchical -file [file join $out_dir "${top}_utilization.rpt"]
    write_checkpoint -force [file join $out_dir "${top}.dcp"]
    close_design
}
puts "B2_PACKET_MEMORY_OOC_PASS"
