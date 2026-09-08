if {$argc != 1} {
    error "usage: probe_b1b_high_diag.tcl <output-file>"
}

set output_file [file normalize [lindex $argv 0]]
set channel [open $output_file w]

proc emit {channel key value} {
    puts $channel "$key=$value"
    puts "$key=$value"
}

connect -url tcp:localhost:3121
targets -set -nocase -filter {name =~ "*Cortex-A9*#0*"}
catch {stop}
emit $channel "B1B_HIGH_CPU_STATE" [state]
emit $channel "B1B_HIGH_CPU_PC" [rrd pc]
emit $channel "B1B_HIGH_CPU_SP" [rrd sp]
emit $channel "B1B_HIGH_CPU_CPSR" [rrd cpsr]
emit $channel "B1B_HIGH_MAGIC" [mrd -value 0x0002F000]
emit $channel "B1B_HIGH_VERSION" [mrd -value 0x0002F004]
emit $channel "B1B_HIGH_STATUS" [mrd -value 0x0002F008]
emit $channel "B1B_HIGH_PHASE" [mrd -value 0x0002F00C]
emit $channel "B1B_HIGH_WINDOW_BASE" [mrd -value 0x0002F010]
emit $channel "B1B_HIGH_ADDRESS" [mrd -value 0x0002F014]
emit $channel "B1B_HIGH_OPERATION" [mrd -value 0x0002F018]
emit $channel "B1B_HIGH_ACCESS_WIDTH" [mrd -value 0x0002F01C]
emit $channel "B1B_HIGH_EXPECTED" [mrd -value 0x0002F020]
emit $channel "B1B_HIGH_ACTUAL" [mrd -value 0x0002F024]
emit $channel "B1B_HIGH_COMPLETED_ACCESSES" [mrd -value 0x0002F028]
emit $channel "B1B_HIGH_COMMAND" [mrd -value 0x0002F02C]
emit $channel "B1B_HIGH_EXECUTION_ADDRESS" [mrd -value 0x0002F030]
close $channel
disconnect
