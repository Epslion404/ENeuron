connect -url tcp:localhost:3121
targets -set -nocase -filter {name =~ "*Cortex-A9*#0*"}
stop
puts "B1B_CPU_STATE=[state]"
puts "B1B_CPU_PC=[rrd pc]"
puts "B1B_CPU_SP=[rrd sp]"
puts "B1B_CPU_CPSR=[rrd cpsr]"
puts "B1B_UART_CR=[mrd -value 0xE0000000]"
puts "B1B_UART_MR=[mrd -value 0xE0000004]"
puts "B1B_UART_BAUDGEN=[mrd -value 0xE0000018]"
puts "B1B_UART_SR=[mrd -value 0xE000002C]"
puts "B1B_UART_BAUDDIV=[mrd -value 0xE0000034]"
puts "B1B_RESULT_MAGIC=[mrd -value 0x0002F000]"
puts "B1B_RESULT_STATUS=[mrd -value 0x0002F004]"
puts "B1B_RESULT_PHASE=[mrd -value 0x0002F008]"
puts "B1B_RESULT_FAIL_ADDRESS=[mrd -value 0x0002F00C]"
puts "B1B_RESULT_EXPECTED=[mrd -value 0x0002F010]"
puts "B1B_RESULT_ACTUAL=[mrd -value 0x0002F014]"
con
disconnect
