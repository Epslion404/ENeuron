connect -url tcp:localhost:3121
targets -set -nocase -filter {name =~ "*Cortex-A9*#0*"}

set uart_base 0xE0000000
set mr_addr [expr {$uart_base + 0x04}]
set sr_addr [expr {$uart_base + 0x2C}]
set fifo_addr [expr {$uart_base + 0x30}]
set original_mr [mrd -force -value $mr_addr]
set loopback_mr [expr {$original_mr | 0x00000200}]
mwr $mr_addr $loopback_mr

after 1500
set bytes 0
set first_byte -1
set last_byte -1
set sample_bytes {}
set sr [mrd -force -value $sr_addr]
while {(($sr & 0x2) == 0) && ($bytes < 64)} {
    set value [mrd -force -value $fifo_addr]
    if {$bytes == 0} { set first_byte [expr {$value & 0xFF}] }
    set last_byte [expr {$value & 0xFF}]
    if {$bytes < 8} { lappend sample_bytes [expr {$value & 0xFF}] }
    incr bytes
    set sr [mrd -force -value $sr_addr]
}
mwr $mr_addr $original_mr

puts [format "B2_UART_LOOPBACK_ORIGINAL_MR=0x%08X" $original_mr]
puts [format "B2_UART_LOOPBACK_FINAL_MR=0x%08X" [mrd -force -value $mr_addr]]
puts [format "B2_UART_LOOPBACK_SR=0x%08X" $sr]
puts "B2_UART_LOOPBACK_BYTES=$bytes"
puts "B2_UART_LOOPBACK_FIRST_BYTE=$first_byte"
puts "B2_UART_LOOPBACK_LAST_BYTE=$last_byte"
puts "B2_UART_LOOPBACK_SAMPLE_BYTES=$sample_bytes"
disconnect
