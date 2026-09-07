if {$argc != 2} {
    error "usage: probe_b0_power_off.tcl <expected_target> <result_path>"
}

set expected_target [lindex $argv 0]
set result_path [file normalize [lindex $argv 1]]

open_hw_manager
connect_hw_server -url localhost:3121 -allow_non_jtag
refresh_hw_server

set targets [get_hw_targets -quiet $expected_target]
if {[llength $targets] != 1} {
    error "Expected exactly one matching JTAG cable target, got [llength $targets]"
}

set target [lindex $targets 0]
set target_opened 0
set target_open_error ""
set devices {}
if {[catch {open_hw_target $target} target_open_error]} {
    set target_opened 0
} else {
    set target_opened 1
    set devices [get_hw_devices -quiet]
    close_hw_target $target
}

set result [open $result_path w]
puts $result "B0_POWER_OFF_PROBE_TIME_UTC=[clock format [clock seconds] -gmt true -format {%Y-%m-%dT%H:%M:%SZ}]"
puts $result "B0_POWER_OFF_EXPECTED_TARGET=$expected_target"
puts $result "B0_POWER_OFF_MATCHING_TARGET_COUNT=[llength $targets]"
puts $result "B0_POWER_OFF_TARGET=$target"
puts $result "B0_POWER_OFF_TARGET_OPENED=$target_opened"
puts $result "B0_POWER_OFF_TARGET_OPEN_ERROR=$target_open_error"
puts $result "B0_POWER_OFF_ACCESSIBLE_DEVICE_COUNT=[llength $devices]"
foreach device $devices {
    puts $result "B0_POWER_OFF_ACCESSIBLE_DEVICE=$device"
}

if {[llength $devices] == 0} {
    puts $result "B0_COMPLETE_POWER_OFF_JTAG_INACCESSIBLE=PASS"
} else {
    puts $result "B0_COMPLETE_POWER_OFF_JTAG_INACCESSIBLE=FAIL"
}
close $result

disconnect_hw_server
close_hw_manager

if {[llength $devices] != 0} {
    error "An FPGA device remains accessible; complete power-off is not proven"
}

puts "B0_COMPLETE_POWER_OFF_JTAG_INACCESSIBLE=PASS"
puts "B0_POWER_OFF_RESULT=$result_path"
