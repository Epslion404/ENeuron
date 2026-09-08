if {$argc != 1} {
    error "usage: arm_b1b_high_diag.tcl <output-file>"
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
set magic [mrd -value 0x0002F000]
set status [mrd -value 0x0002F008]
set phase [mrd -value 0x0002F00C]
set execution_address [mrd -value 0x0002F030]
emit $channel "B1B_HIGH_PREFLIGHT_MAGIC" $magic
emit $channel "B1B_HIGH_PREFLIGHT_STATUS" $status
emit $channel "B1B_HIGH_PREFLIGHT_PHASE" $phase
emit $channel "B1B_HIGH_PREFLIGHT_EXECUTION_ADDRESS" $execution_address
emit $channel "B1B_HIGH_PREFLIGHT_PC" [rrd pc]
emit $channel "B1B_HIGH_PREFLIGHT_SP" [rrd sp]
emit $channel "B1B_HIGH_PREFLIGHT_CPSR" [rrd cpsr]

if {$magic != 0x42314844} {
    error "unexpected high diagnostic magic: $magic"
}
if {$status != 4} {
    error "high diagnostic is not READY: $status"
}
if {$phase != 1} {
    error "high diagnostic is not in OCM_READY phase: $phase"
}
if {$execution_address >= 0x0002F000} {
    error "high diagnostic execution address is outside OCM app range: $execution_address"
}

mwr 0x0002F02C 0x474F4444
emit $channel "B1B_HIGH_GO_WRITE_PASS" 1
close $channel
con
disconnect
