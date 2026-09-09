connect -url tcp:localhost:3121
targets -set -nocase -filter {name =~ "*Cortex-A9*#0*"}
catch {stop}
puts "B2_CPU_STATE=[state]"
puts "B2_CPU_PC=[rrd pc]"
puts "B2_CPU_SP=[rrd sp]"
puts "B2_CPU_CPSR=[rrd cpsr]"
puts "B2_UART_CR=[mrd -force -value 0xE0000000]"
puts "B2_UART_MR=[mrd -force -value 0xE0000004]"
puts "B2_UART_BAUDGEN=[mrd -force -value 0xE0000018]"
puts "B2_UART_SR=[mrd -force -value 0xE000002C]"
puts "B2_UART_BAUDDIV=[mrd -force -value 0xE0000034]"
puts "B2_STATUS_MAGIC=[mrd -value 0x01008000]"
puts "B2_STATUS_STATUS=[mrd -value 0x01008004]"
puts "B2_STATUS_SEQUENCE=[mrd -value 0x01008008]"
puts "B2_STATUS_LENGTH=[mrd -value 0x0100800C]"
puts "B2_STATUS_TX_ADDR=[mrd -value 0x01008010]"
puts "B2_STATUS_RX_ADDR=[mrd -value 0x01008014]"
puts "B2_STATUS_FLUSH=[mrd -value 0x01008018]"
puts "B2_STATUS_INVALIDATE=[mrd -value 0x0100801C]"
puts "B2_STATUS_TX_CR=[mrd -value 0x01008020]"
puts "B2_STATUS_TX_SR=[mrd -value 0x01008024]"
puts "B2_STATUS_TX_BTT=[mrd -value 0x01008028]"
puts "B2_STATUS_RX_CR=[mrd -value 0x0100802C]"
puts "B2_STATUS_RX_SR=[mrd -value 0x01008030]"
puts "B2_STATUS_RX_BTT=[mrd -value 0x01008034]"
puts "B2_STATUS_CRC=[mrd -value 0x01008038]"
puts "B2_STATUS_FRAMES_TOTAL=[mrd -value 0x0100803C]"
puts "B2_STATUS_FRAMES_PASSED=[mrd -value 0x01008040]"
puts "B2_STATUS_FRAMES_REJECTED=[mrd -value 0x01008044]"
puts "B2_STATUS_FRAMES_FAILED=[mrd -value 0x01008048]"
puts "B2_STATUS_PRESSURE_STATUS=[mrd -value 0x0100804C]"
puts "B2_STATUS_PRESSURE_TOTAL=[mrd -value 0x01008050]"
puts "B2_STATUS_PRESSURE_PASSED=[mrd -value 0x01008054]"
puts "B2_STATUS_PRESSURE_FAILED=[mrd -value 0x01008058]"
puts "B2_STATUS_PRESSURE_CRC=[mrd -value 0x0100805C]"
puts "B2_STATUS_PRESSURE_LAST_SEQUENCE=[mrd -value 0x01008060]"
puts "B2_STATUS_BACKPRESSURE_STATUS=[mrd -value 0x01008064]"
puts "B2_STATUS_BACKPRESSURE_TOTAL=[mrd -value 0x01008068]"
puts "B2_STATUS_BACKPRESSURE_PASSED=[mrd -value 0x0100806C]"
puts "B2_STATUS_BACKPRESSURE_FAILED=[mrd -value 0x01008070]"
puts "B2_STATUS_BACKPRESSURE_CRC=[mrd -value 0x01008074]"
puts "B2_STATUS_BACKPRESSURE_LAST_SEQUENCE=[mrd -value 0x01008078]"
puts "B2_STATUS_BACKPRESSURE_STALL_CYCLES=[mrd -value 0x0100807C]"
puts "B2_STATUS_WRAP_STATUS=[mrd -value 0x01008280]"
puts "B2_STATUS_WRAP_TOTAL=[mrd -value 0x01008284]"
puts "B2_STATUS_WRAP_PASSED=[mrd -value 0x01008288]"
puts "B2_STATUS_WRAP_FAILED=[mrd -value 0x0100828C]"
puts "B2_STATUS_WRAP_CRC=[mrd -value 0x01008290]"
puts "B2_STATUS_WRAP_LAST_SEQUENCE=[mrd -value 0x01008294]"
puts "B2_STATUS_WRAP_SLOT_MASK_LO=[mrd -value 0x01008298]"
puts "B2_STATUS_WRAP_SLOT_MASK_HI=[mrd -value 0x0100829C]"
puts "B2_STATUS_WRAP_ROLLOVERS=[mrd -value 0x010082A0]"
puts "B2_STATUS_WRAP_FIRST_TX_ADDR=[mrd -value 0x010082A4]"
puts "B2_STATUS_WRAP_FIRST_RX_ADDR=[mrd -value 0x010082A8]"
puts "B2_STATUS_WRAP_LAST_TX_ADDR=[mrd -value 0x010082AC]"
puts "B2_STATUS_WRAP_LAST_RX_ADDR=[mrd -value 0x010082B0]"
puts "B2_TX_WORDS_BEGIN"
for {set index 0} {$index < 16} {incr index} {
    set address [expr {0x01006000 + ($index * 4)}]
    puts [format "B2_TX_WORD_%02d=0x%08X" $index [mrd -value $address]]
}
puts "B2_TX_WORDS_END"
puts "B2_RX_WORDS_BEGIN"
for {set index 0} {$index < 16} {incr index} {
    set address [expr {0x01007000 + ($index * 4)}]
    puts [format "B2_RX_WORD_%02d=0x%08X" $index [mrd -value $address]]
}
puts "B2_RX_WORDS_END"
puts "B2_LEDGER_BEGIN"
for {set index 0} {$index < 8} {incr index} {
    set base [expr {0x01008080 + ($index * 24)}]
    puts [format "B2_LEDGER_%02d_SEQ=0x%08X" $index [mrd -value $base]]
    puts [format "B2_LEDGER_%02d_LEN=0x%08X" $index [mrd -value [expr {$base + 4}]]]
    puts [format "B2_LEDGER_%02d_STATUS=0x%08X" $index [mrd -value [expr {$base + 8}]]]
    puts [format "B2_LEDGER_%02d_CRC=0x%08X" $index [mrd -value [expr {$base + 12}]]]
    puts [format "B2_LEDGER_%02d_ELAPSED=0x%08X" $index [mrd -value [expr {$base + 16}]]]
    puts [format "B2_LEDGER_%02d_INVALIDATE=0x%08X" $index [mrd -value [expr {$base + 20}]]]
}
puts "B2_LEDGER_END"
if {[catch {
    puts "B2_DMA_TX_CR=[mrd -force -value 0x40400000]"
    puts "B2_DMA_TX_SR=[mrd -force -value 0x40400004]"
    puts "B2_DMA_TX_ADDR=[mrd -force -value 0x40400018]"
    puts "B2_DMA_TX_BTT=[mrd -force -value 0x40400028]"
    puts "B2_DMA_RX_CR=[mrd -force -value 0x40400030]"
    puts "B2_DMA_RX_SR=[mrd -force -value 0x40400034]"
    puts "B2_DMA_RX_ADDR=[mrd -force -value 0x40400048]"
    puts "B2_DMA_RX_BTT=[mrd -force -value 0x40400058]"
} dma_error]} {
    puts "B2_DMA_PL_READ=UNAVAILABLE"
}

proc emit_probe_state {label base} {
    puts "${label}_BASE=[format 0x%08X $base]"
    puts "${label}_CONFIG=[mrd -force -value [expr {$base + 0x04}]]"
    puts "${label}_SAMPLE=[mrd -force -value [expr {$base + 0x20}]]"
    puts "${label}_BEATS=[mrd -force -value [expr {$base + 0x50}]]"
    puts "${label}_TLAST=[mrd -force -value [expr {$base + 0x80}]]"
    puts "${label}_BYTES=[mrd -force -value [expr {$base + 0x88}]]"
    puts "${label}_CYCLES=[mrd -force -value [expr {$base + 0x90}]]"
    puts "${label}_STALL=[mrd -force -value [expr {$base + 0x98}]]"
    puts "${label}_STARVE=[mrd -force -value [expr {$base + 0xA0}]]"
    puts "${label}_LAST_TKEEP=[mrd -force -value [expr {$base + 0xA8}]]"
}
if {[catch {
    emit_probe_state B2_PROBE_MM2S 0x40410000
    emit_probe_state B2_PROBE_S2MM 0x40420000
} probe_error]} {
    puts "B2_PROBE_READ=UNAVAILABLE"
    puts "B2_PROBE_ERROR=$probe_error"
}
con
disconnect
