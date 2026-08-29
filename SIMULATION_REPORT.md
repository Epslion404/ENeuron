# NeuronGate V1 Vivado 仿真报告

日期：2026-08-29

## 结论

Vivado 2024.2 XSim 仿真通过：

```text
GATE_TB keep=0011 candidate=0011 scores=7f7f7f88 cooldown=0000 count=2
GATE_TB_PASS
```

仿真顶层为 `tb_neuron_gate`，被验证设计为 `neuron_gate_core`。测试覆盖复位、8 个训练 tick、`image_end`、`epoch_end` 以及 2:4 结构化掩码提交。

## 发现并修正的问题

1. 原测试平台存在 `posedge` 竞态：在 `posedge` 之后置位 `tick_valid/pre_mask`，在下一个 `posedge` 之前又清零，导致 RTL 永远采样不到活动 tick。已改为在 `negedge` 建立激励，再等待 `posedge` 采样。

2. RTL 使用 `$signed(score_reg[i])` 解释 8 位分数，导致初始值 `0x80 = 128` 被解释为 `-128`，训练后分数被错误钳制到 0。分数模型应为无符号 0..255，已改为直接以 `score_reg[i]` 赋值。

3. 原检查点期望 `keep_mask == 4'b1111`，与 `MAX_KEEP=2` 的 2:4 合约不符；修正为 `keep_mask == 4'b0011`，并同时检查 `score[0]=136`、`score[1..3]=127`。

## 环境与复现

本机 Vivado 安装在包含空格的路径中，且随附 `settings64.bat` 仍指向旧安装目录 `D:\vivado2`。本次仿真通过创建无空格 junction `C:\Users\MGL\Documents\Codex\Vivado2024_2` 指向实际安装目录来规避 XSim 生成 C 代码编译时的路径问题。

复现命令：

```powershell
cd C:\Users\MGL\Documents\Codex\2026-08-29\vivado\outputs
cmd.exe /c run_sim.bat
```

Python 黄金模型交叉验证：

```text
Ran 9 tests in 0.001s
OK
```

## 产物

- `neuron_gate_core.sv`：修正后的 RTL 副本
- `tb_neuron_gate.sv`：修正后的测试平台副本
- `tb_neuron_gate_vlog.prj`：XSim 编译工程文件
- `run_sim.bat` / `run_xsim.tcl`：可重复仿真脚本
- `simulate.log` / `xvlog.log` / `elaborate.log`：仿真与编译日志
- `tb_neuron_gate_behav.wdb`：XSim 波形数据库

## 边界说明

本次只验证了单组四连接门控核心的仿真行为，尚未覆盖完整 NPU、真实 CNN 数据通路、BRAM/DSP 稀疏跳过、板级 DDR 与网口协议。原始项目文件未改动，修正版本仅保存在本输出目录。
