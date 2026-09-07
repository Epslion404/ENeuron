set bitstream_path [file normalize [lindex $argv 0]]
set result_path [file normalize [lindex $argv 1]]
if {![file exists $bitstream_path]} { error "Bitstream not found: $bitstream_path" }

open_hw_manager
connect_hw_server -url localhost:3121 -allow_non_jtag

set targets [get_hw_targets -quiet]
if {[llength $targets] != 1} { error "Expected one hardware target, found [llength $targets]" }
set target [lindex $targets 0]
open_hw_target $target

set devices [get_hw_devices -quiet xc7z020*]
if {[llength $devices] != 1} { error "Expected one XC7Z020 device, found [llength $devices]" }
set device [lindex $devices 0]

refresh_hw_device -update_hw_probes false $device
set pre_status [get_property REGISTER.CONFIG_STATUS $device]
set pre_program_file [get_property PROGRAM.FILE $device]

set_property PROGRAM.FILE $bitstream_path $device
program_hw_devices $device
refresh_hw_device -update_hw_probes false $device

set post_status [get_property REGISTER.CONFIG_STATUS $device]
set post_program_file [get_property PROGRAM.FILE $device]
if {[file normalize $post_program_file] ne $bitstream_path} {
    error "Hardware Manager PROGRAM.FILE does not match the requested bitstream"
}
set done_internal [get_property REGISTER.CONFIG_STATUS.BIT13_DONE_INTERNAL_SIGNAL_STATUS $device]
set done_pin [get_property REGISTER.CONFIG_STATUS.BIT14_DONE_PIN $device]
set isc_done [get_property REGISTER.IR.BIT2_ISC_DONE $device]
if {$done_internal != 1 || $done_pin != 1 || $isc_done != 1} {
    error "B0 configuration did not reach DONE"
}

set result [open $result_path w]
puts $result "B0_PROGRAM_TIME_UTC=[clock format [clock seconds] -gmt true -format {%Y-%m-%dT%H:%M:%SZ}]"
puts $result "B0_HW_TARGET=$target"
puts $result "B0_HW_DEVICE=$device"
puts $result "B0_PRE_CONFIG_STATUS=$pre_status"
puts $result "B0_PRE_PROGRAM_FILE=$pre_program_file"
puts $result "B0_POST_CONFIG_STATUS=$post_status"
puts $result "B0_POST_PROGRAM_FILE=$post_program_file"
puts $result "B0_POST_DONE_INTERNAL=$done_internal"
puts $result "B0_POST_DONE_PIN=$done_pin"
puts $result "B0_POST_ISC_DONE=$isc_done"
puts $result "B0_PROGRAM_COMMAND=PASS"
foreach property_name [lsort [list_property $device]] {
    if {[regexp -nocase {DONE|CONFIG_STATUS|IR_STATUS|PROGRAM} $property_name]} {
        if {![catch {set property_value [get_property $property_name $device]}]} {
            puts $result "B0_HW_PROPERTY:$property_name=$property_value"
        }
    }
}
close $result

puts "B0_PROGRAM_PASS"
puts "B0_PROGRAM_RESULT=$result_path"

close_hw_target
disconnect_hw_server
close_hw_manager
