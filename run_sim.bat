@echo off
set "VIVADO_ROOT=C:\Users\MGL\Documents\Codex\Vivado2024_2"

call "%VIVADO_ROOT%\bin\xvlog.bat" --incr --relax -L uvm -prj tb_neuron_gate_vlog.prj -log xvlog.log
if errorlevel 1 exit /b 1

call "%VIVADO_ROOT%\bin\xelab.bat" --incr --debug typical --relax --mt 2 -L xil_defaultlib -L uvm -L unisims_ver -L unimacro_ver -L secureip --snapshot tb_neuron_gate_behav xil_defaultlib.tb_neuron_gate xil_defaultlib.glbl -log elaborate.log
if errorlevel 1 exit /b 1

call "%VIVADO_ROOT%\bin\xsim.bat" tb_neuron_gate_behav -tclbatch run_xsim.tcl -log simulate.log
if errorlevel 1 exit /b 1

exit /b 0
