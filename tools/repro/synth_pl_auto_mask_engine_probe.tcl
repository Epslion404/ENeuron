set repo_root [file normalize [file join [file dirname [info script]] .. ..]]
set out_arg [lindex $argv 0]
set out_dir [file normalize [expr {$out_arg eq {} ? [file join $repo_root artifacts tmp_pl_auto_mask_engine_probe] : $out_arg}]]
file mkdir $out_dir
read_verilog -sv [file join $repo_root eneuron_pl_auto_mask_engine.sv]
synth_design -top eneuron_pl_auto_mask_engine -part xc7z020clg484-2 -mode out_of_context
report_utilization -hierarchical -file [file join $out_dir "eneuron_pl_auto_mask_engine_utilization.rpt"]
write_checkpoint -force [file join $out_dir "eneuron_pl_auto_mask_engine.dcp"]
puts "PL_AUTO_MASK_ENGINE_OOC_PASS"
