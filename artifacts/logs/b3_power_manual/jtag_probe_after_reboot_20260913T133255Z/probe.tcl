connect -url tcp:localhost:3121
puts "TARGETS_BEGIN"
puts [targets]
puts "TARGETS_END"
disconnect
exit 0
