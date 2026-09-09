if {$argc != 3} {
    error "usage: program_b2.tcl <bitstream> <ps7-init-tcl> <elf>"
}

set bitstream [file normalize [lindex $argv 0]]
set ps7_init_script [file normalize [lindex $argv 1]]
set elf_file [file normalize [lindex $argv 2]]

connect -url tcp:localhost:3121
puts "B2_TARGETS_BEGIN"
puts [targets]
puts "B2_TARGETS_END"
targets -set -nocase -filter {name =~ "APU*"}
rst -system
after 1000
targets -set -nocase -filter {name =~ "xc7z020*"}
fpga -file $bitstream
puts "B2_FPGA_PROGRAM_PASS"
targets -set -nocase -filter {name =~ "*Cortex-A9*#0*"}
source $ps7_init_script
ps7_init
ps7_post_config
rst -processor
dow $elf_file
puts "B2_ELF_DOWNLOAD_PASS"
con
puts "B2_CPU_RUN_PASS"
after 1000
disconnect
