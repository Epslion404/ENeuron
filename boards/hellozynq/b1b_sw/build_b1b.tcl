if {$argc != 3} {
    error "usage: build_b1b.tcl <xsa-copy> <bsp-dir> <app-dir>"
}

set xsa_file [file normalize [lindex $argv 0]]
set bsp_dir [file normalize [lindex $argv 1]]
set app_dir [file normalize [lindex $argv 2]]
set extract_dir [file dirname $xsa_file]

set hw_design [hsi::open_hw_design -outdir $extract_dir $xsa_file]
set sw_design [hsi::create_sw_design b1b_standalone -proc ps7_cortexa9_0 -os standalone]
hsi::set_property CONFIG.stdin ps7_uart_0 [hsi::get_os]
hsi::set_property CONFIG.stdout ps7_uart_0 [hsi::get_os]
hsi::generate_bsp -dir $bsp_dir -hw $hw_design -sw $sw_design
hsi::generate_app -dir $app_dir -hw $hw_design -sw $sw_design -app empty_application
hsi::close_sw_design $sw_design
hsi::close_hw_design $hw_design

puts "B1B_HSI_GENERATE_PASS"
