connect -url tcp:localhost:3121
targets -set -nocase -filter {name =~ "*Cortex-A9*#0*"}
catch {stop}
puts "B3_POWER_CPU_STOP_REQUESTED"
disconnect
exit 0
