# CP8 功耗四态独立 probe：只读/单次写 0x74，不 reset、不停 CPU、不结束功耗窗口。
# 用法: xsct probe_b3_cp8_power_state.tcl idle|full
if {[llength $argv] < 1} {
    puts "B3_CP8_POWER_PROBE_ERROR=missing_state"
    exit 1
}
set state [lindex $argv 0]
if {$state ne "idle" && $state ne "full"} {
    puts "B3_CP8_POWER_PROBE_ERROR=invalid_state:$state"
    exit 1
}

set base 0x40430000
set control_addr [expr {$base + 0x74}]
set status_addr [expr {$base + 0x64}]
set completed_addr [expr {$base + 0x68}]
set cycles_addr [expr {$base + 0x6C}]
set capture_addr [expr {$base + 0x70}]
set protocol_addr [expr {$base + 0x60}]

set READY 0x43503849
set START 0x43503853
set RUNNING 0x43503852
set STATUS_CAPTURE 1
set STATUS_MEASURE 3
set STATUS_FAIL 5
set EXPECTED_CAPTURE 397
set POLL_MS 50
set TIMEOUT_MS 30000

proc read32 {addr} {
    return [expr {[mrd -force -value $addr] & 0xFFFFFFFF}]
}

proc wait_ready_capture {control_addr status_addr capture_addr completed_addr protocol_addr ready status_capture status_fail poll_ms timeout_ms} {
    set elapsed 0
    while {$elapsed < $timeout_ms} {
        set control [read32 $control_addr]
        set status [read32 $status_addr]
        set capture [read32 $capture_addr]
        set completed [read32 $completed_addr]
        set protocol [read32 $protocol_addr]
        if {$status == $status_fail || $protocol != 0} {
            error "idle_status status=$status protocol=$protocol"
        }
        if {$control == $ready && $status == $status_capture && $capture == 0 && $completed == 0 && $protocol == 0} {
            return
        }
        after $poll_ms
        incr elapsed $poll_ms
    }
    error "timeout_ready"
}

proc wait_measure_running {control_addr status_addr capture_addr protocol_addr running status_measure status_fail expected_capture poll_ms timeout_ms} {
    set elapsed 0
    while {$elapsed < $timeout_ms} {
        set control [read32 $control_addr]
        set status [read32 $status_addr]
        set capture [read32 $capture_addr]
        set protocol [read32 $protocol_addr]
        if {$status == $status_fail || $protocol != 0} {
            error "measure_status status=$status protocol=$protocol"
        }
        if {$control == $running && $status == $status_measure && $capture == $expected_capture && $protocol == 0} {
            return
        }
        after $poll_ms
        incr elapsed $poll_ms
    }
    error "timeout_measure"
}

if {[catch {
    connect -url tcp:localhost:3121
    targets -set -nocase -filter {name =~ "*Cortex-A9*#0*"}

    wait_ready_capture $control_addr $status_addr $capture_addr $completed_addr $protocol_addr \
        $READY $STATUS_CAPTURE $STATUS_FAIL $POLL_MS $TIMEOUT_MS

    if {$state eq "full"} {
        mwr -force $control_addr $START
        wait_measure_running $control_addr $status_addr $capture_addr $protocol_addr \
            $RUNNING $STATUS_MEASURE $STATUS_FAIL $EXPECTED_CAPTURE $POLL_MS $TIMEOUT_MS
        set completed_first [read32 $completed_addr]
        after 150
        set completed_second [read32 $completed_addr]
        if {$completed_second == $completed_first} {
            error "completed_stalled first=$completed_first second=$completed_second"
        }
    } else {
        set completed_first [read32 $completed_addr]
        set completed_second $completed_first
    }

    set control [read32 $control_addr]
    set status [read32 $status_addr]
    set capture [read32 $capture_addr]
    set completed [read32 $completed_addr]
    set cycles [read32 $cycles_addr]
    set protocol [read32 $protocol_addr]
} err]} {
    puts "B3_CP8_POWER_PROBE_ERROR=$err"
    catch {disconnect}
    exit 1
}

puts "B3_CP8_POWER_STATE=$state"
puts [format "B3_CP8_POWER_CONTROL=%u" $control]
puts [format "B3_CP8_POWER_REPLAY_STATUS=%u" $status]
puts [format "B3_CP8_POWER_CAPTURE=%u" $capture]
puts [format "B3_CP8_POWER_COMPLETED=%u" $completed]
puts [format "B3_CP8_POWER_CYCLES=%u" $cycles]
puts [format "B3_CP8_POWER_PROTOCOL=%u" $protocol]
puts [format "B3_CP8_POWER_COMPLETED_FIRST=%u" $completed_first]
puts [format "B3_CP8_POWER_COMPLETED_SECOND=%u" $completed_second]
puts "B3_CP8_POWER_PROBE_PASS=1"
disconnect
exit 0
