if {$argc != 8} {
    error "usage: start_b3_power_window.tcl <bitstream> <ps7-init-tcl> <elf> <mode> <warmup-samples> <window-seconds> <start-delay-seconds> <minimum-valid-inferences>"
}

set bitstream [file normalize [lindex $argv 0]]
set ps7_init_script [file normalize [lindex $argv 1]]
set elf_file [file normalize [lindex $argv 2]]
set mode_name [lindex $argv 3]
set warmup_samples [lindex $argv 4]
set window_seconds [lindex $argv 5]
set start_delay_seconds [lindex $argv 6]
set minimum_valid_inferences [lindex $argv 7]

array set mode_ids {
    b3_idle 0
    b3_dense 1
    b3_static_mixed 2
    b3_live_eneuron 3
}
if {![info exists mode_ids($mode_name)]} {
    error "unsupported B3 power mode: $mode_name"
}
set mode_id $mode_ids($mode_name)

connect -url tcp:localhost:3121
puts "B3_POWER_TARGETS_BEGIN"
puts [targets]
puts "B3_POWER_TARGETS_END"
targets -set -nocase -filter {name =~ "APU*"}
rst -system
after 1000
targets -set -nocase -filter {name =~ "xc7z020*"}
fpga -file $bitstream
puts "B3_POWER_FPGA_PROGRAM_PASS"
targets -set -nocase -filter {name =~ "*Cortex-A9*#0*"}
source $ps7_init_script
ps7_init
ps7_post_config
rst -processor
dow $elf_file
puts "B3_POWER_ELF_DOWNLOAD_PASS"

# CPU 仍处于停止态，先写完整控制块，避免应用读到半写入配置。
mwr 0x01008500 0x33525750
mwr 0x01008504 1
mwr 0x01008508 $mode_id
mwr 0x0100850C $warmup_samples
mwr 0x01008510 $window_seconds
mwr 0x01008514 $start_delay_seconds
mwr 0x01008518 $minimum_valid_inferences
mwr 0x0100851C 0
for {set offset 0} {$offset <= 68} {incr offset 4} {
    mwr [expr {0x01008600 + $offset}] 0
}
puts "B3_POWER_CONTROL_WRITE_PASS"

con
puts "B3_POWER_CPU_RUN_PASS"
set ready_deadline [expr {[clock milliseconds] + 120000}]
set status 0
while {[clock milliseconds] < $ready_deadline} {
    set result_magic [mrd -value 0x01008600]
    set result_version [mrd -value 0x01008604]
    set status [mrd -value 0x01008608]
    if {$result_magic == 0x33534552 && $result_version == 1 && $status == 2} {
        break
    }
    if {$status == 5} {
        set error_code [mrd -value 0x01008644]
        error "B3 power benchmark failed before READY: error_code=$error_code"
    }
    after 100
}
if {$status != 2} {
    error "B3 power benchmark did not reach READY before timeout: status=$status"
}
puts "B3_POWER_READY_PASS"

mwr 0x0100851C 1
puts "B3_POWER_GO_WRITE_PASS"
puts "B3_POWER_GO_EPOCH_SECONDS=[clock seconds]"
disconnect
exit 0
