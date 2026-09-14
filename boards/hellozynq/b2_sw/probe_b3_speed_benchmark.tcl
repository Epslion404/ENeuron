if {$argc < 1 || $argc > 2} {
    error "usage: probe_b3_speed_benchmark.tcl SAMPLE_COUNT [capture_logits]"
}
set sample_count [lindex $argv 0]
if {$sample_count < 1 || $sample_count > 64} {
    error "sample count must be in 1..64"
}
set capture_logits 0
if {$argc == 2} {
    if {[lindex $argv 1] ne "capture_logits"} {
        error "second argument must be capture_logits"
    }
    set capture_logits 1
}

set base 0x01009000
set rx_base 0x01007000
connect -url tcp:localhost:3121
targets -set -nocase -filter {name =~ "*Cortex-A9*#0*"}

puts [format "B3_SPEED_MAGIC=0x%08X" [mrd -force -value $base]]
puts [format "B3_SPEED_STATUS=%u" [mrd -force -value [expr {$base + 4}]]]
puts [format "B3_SPEED_MODE_ID=%u" [mrd -force -value [expr {$base + 8}]]]
puts [format "B3_SPEED_SAMPLE_COUNT=%u" [mrd -force -value [expr {$base + 12}]]]
puts [format "B3_SPEED_SETUP_US=%u" [mrd -force -value [expr {$base + 16}]]]
puts [format "B3_SPEED_MASK_US=%u" [mrd -force -value [expr {$base + 20}]]]
puts [format "B3_SPEED_FENCE_US=%u" [mrd -force -value [expr {$base + 24}]]]
puts [format "B3_SPEED_TOTAL_MIN_US=%u" [mrd -force -value [expr {$base + 28}]]]
puts [format "B3_SPEED_TOTAL_MAX_US=%u" [mrd -force -value [expr {$base + 32}]]]
puts [format "B3_SPEED_TOTAL_SUM_LO=%u" [mrd -force -value [expr {$base + 36}]]]
puts [format "B3_SPEED_TOTAL_SUM_HI=%u" [mrd -force -value [expr {$base + 40}]]]
puts [format "B3_SPEED_DMA_MIN_US=%u" [mrd -force -value [expr {$base + 44}]]]
puts [format "B3_SPEED_DMA_MAX_US=%u" [mrd -force -value [expr {$base + 48}]]]
puts [format "B3_SPEED_DMA_SUM_LO=%u" [mrd -force -value [expr {$base + 52}]]]
puts [format "B3_SPEED_DMA_SUM_HI=%u" [mrd -force -value [expr {$base + 56}]]]
puts [format "B3_SPEED_PS_MIN_US=%u" [mrd -force -value [expr {$base + 60}]]]
puts [format "B3_SPEED_PS_MAX_US=%u" [mrd -force -value [expr {$base + 64}]]]
puts [format "B3_SPEED_PS_SUM_LO=%u" [mrd -force -value [expr {$base + 68}]]]
puts [format "B3_SPEED_PS_SUM_HI=%u" [mrd -force -value [expr {$base + 72}]]]
puts [format "B3_SPEED_RESULT_FAILURES=%u" [mrd -force -value [expr {$base + 76}]]]
puts [format "B3_SPEED_FAILURE_STAGE=%u" [mrd -force -value [expr {$base + 80}]]]
puts [format "B3_SPEED_FAILURE_SAMPLE_INDEX=%u" [mrd -force -value [expr {$base + 84}]]]
puts [format "B3_SPEED_FAILURE_CHECK_MASK=%u" [mrd -force -value [expr {$base + 88}]]]
puts [format "B3_SPEED_FAILURE_RESPONSE_WORDS=%u" [mrd -force -value [expr {$base + 92}]]]
puts [format "B3_SPEED_FAILURE_RESPONSE_SEQUENCE=%u" [mrd -force -value [expr {$base + 96}]]]
puts [format "B3_SPEED_MASK_COMPUTE_US=%u" [mrd -force -value [expr {$base + 100}]]]
puts [format "B3_SPEED_MASK_SUBMIT_US=%u" [mrd -force -value [expr {$base + 104}]]]
for {set index 8} {$index < 13} {incr index} {
    puts [format "B3_SPEED_FAILURE_RX_WORD_%02d=0x%08X" $index [mrd -force -value [expr {$rx_base + ($index * 4)}]]]
}

set sample_base [expr {$base + 108}]
for {set index 0} {$index < $sample_count} {incr index} {
    set offset [expr {$sample_base + ($index * 60)}]
    puts [format "B3_SPEED_SAMPLE_%02d_SEQUENCE=%u" $index [mrd -force -value $offset]]
    puts [format "B3_SPEED_SAMPLE_%02d_ID=0x%08X" $index [mrd -force -value [expr {$offset + 4}]]]
    puts [format "B3_SPEED_SAMPLE_%02d_MASK_EPOCH=%u" $index [mrd -force -value [expr {$offset + 8}]]]
    puts [format "B3_SPEED_SAMPLE_%02d_INPUT_CRC=0x%08X" $index [mrd -force -value [expr {$offset + 12}]]]
    puts [format "B3_SPEED_SAMPLE_%02d_STATUS=%u" $index [mrd -force -value [expr {$offset + 16}]]]
    puts [format "B3_SPEED_SAMPLE_%02d_PS_US=%u" $index [mrd -force -value [expr {$offset + 20}]]]
    puts [format "B3_SPEED_SAMPLE_%02d_DMA_US=%u" $index [mrd -force -value [expr {$offset + 24}]]]
    puts [format "B3_SPEED_SAMPLE_%02d_RESULT_US=%u" $index [mrd -force -value [expr {$offset + 28}]]]
    puts [format "B3_SPEED_SAMPLE_%02d_TOTAL_US=%u" $index [mrd -force -value [expr {$offset + 32}]]]
    puts [format "B3_SPEED_SAMPLE_%02d_NPU_CYCLES=%u" $index [mrd -force -value [expr {$offset + 36}]]]
    puts [format "B3_SPEED_SAMPLE_%02d_EXECUTE_GROUPS=%u" $index [mrd -force -value [expr {$offset + 40}]]]
    puts [format "B3_SPEED_SAMPLE_%02d_SKIP_GROUPS=%u" $index [mrd -force -value [expr {$offset + 44}]]]
    puts [format "B3_SPEED_SAMPLE_%02d_PROTOCOL_ERRORS=%u" $index [mrd -force -value [expr {$offset + 48}]]]
    puts [format "B3_SPEED_SAMPLE_%02d_RESULT_CRC=0x%08X" $index [mrd -force -value [expr {$offset + 52}]]]
    set mask_split [mrd -force -value [expr {$offset + 56}]]
    puts [format "B3_SPEED_SAMPLE_%02d_MASK_COMPUTE_US=%u" $index [expr {$mask_split & 0xFFFF}]]
    puts [format "B3_SPEED_SAMPLE_%02d_MASK_SUBMIT_US=%u" $index [expr {($mask_split >> 16) & 0xFFFF}]]
}

if {$capture_logits} {
    set accuracy_base 0x0100A000
    puts [format "B3_ACCURACY_MAGIC=0x%08X" [mrd -force -value $accuracy_base]]
    puts [format "B3_ACCURACY_STATUS=%u" [mrd -force -value [expr {$accuracy_base + 4}]]]
    puts [format "B3_ACCURACY_MODE_ID=%u" [mrd -force -value [expr {$accuracy_base + 8}]]]
    puts [format "B3_ACCURACY_SAMPLE_COUNT=%u" [mrd -force -value [expr {$accuracy_base + 12}]]]
    puts [format "B3_ACCURACY_RESULT_FAILURES=%u" [mrd -force -value [expr {$accuracy_base + 16}]]]
    puts [format "B3_ACCURACY_FAILURE_STAGE=%u" [mrd -force -value [expr {$accuracy_base + 20}]]]
    puts [format "B3_ACCURACY_FAILURE_SAMPLE_INDEX=%u" [mrd -force -value [expr {$accuracy_base + 24}]]]
    set accuracy_sample_base [expr {$accuracy_base + 28}]
    for {set index 0} {$index < $sample_count} {incr index} {
        set offset [expr {$accuracy_sample_base + ($index * 56)}]
        puts [format "B3_ACCURACY_SAMPLE_%02d_MASK_EPOCH=%u" $index [mrd -force -value $offset]]
        puts [format "B3_ACCURACY_SAMPLE_%02d_INPUT_CRC=0x%08X" $index [mrd -force -value [expr {$offset + 4}]]]
        puts [format "B3_ACCURACY_SAMPLE_%02d_STATUS=%u" $index [mrd -force -value [expr {$offset + 8}]]]
        puts [format "B3_ACCURACY_SAMPLE_%02d_RESULT_CRC=0x%08X" $index [mrd -force -value [expr {$offset + 12}]]]
        for {set logit 0} {$logit < 10} {incr logit} {
            puts [format "B3_ACCURACY_SAMPLE_%02d_LOGIT_%02d=0x%08X" $index $logit [mrd -force -value [expr {$offset + 16 + ($logit * 4)}]]]
        }
    }
}
disconnect
exit 0
