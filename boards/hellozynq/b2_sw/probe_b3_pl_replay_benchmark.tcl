connect -url tcp:localhost:3121
targets -set -nocase -filter {name =~ "*Cortex-A9*#0*"}
set base 0x40430000
puts [format "B3_PL_REPLAY_STATUS=%u" [mrd -force -value [expr {$base + 0x64}]]]
puts [format "B3_PL_REPLAY_COMPLETED=%u" [mrd -force -value [expr {$base + 0x68}]]]
puts [format "B3_PL_REPLAY_CYCLES=%u" [mrd -force -value [expr {$base + 0x6C}]]]
puts [format "B3_PL_REPLAY_EXECUTE_GROUPS=%u" [mrd -force -value [expr {$base + 0x48}]]]
puts [format "B3_PL_REPLAY_SKIP_GROUPS=%u" [mrd -force -value [expr {$base + 0x4C}]]]
puts [format "B3_PL_REPLAY_LAST_COMPUTE_CYCLES=%u" [mrd -force -value [expr {$base + 0x5C}]]]
puts [format "B3_PL_REPLAY_PROTOCOL_ERRORS=%u" [mrd -force -value [expr {$base + 0x60}]]]
disconnect
exit 0
