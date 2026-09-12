# B2 packet-NPU routed timing failure: `70e8caf`

- 日期：2026-09-10
- 目标器件：`xc7z020clg484-2`
- Vivado：2024.1
- 顶层：`design_1_wrapper`
- 源码提交：`70e8caf7dde10a2a23f851693a38019be1df401f`
- 时钟：`clk_fpga_0`，200 MHz，5.0 ns
- route errors：`0`
- DRC hard errors：`0`（报告含 warnings/advisories）
- 时序：失败，`WNS=-1.595 ns`、`TNS=-1103.714 ns`、`3304` 个 setup failing endpoints，`WHS=+0.036 ns`、`THS=0`
- 最差路径：`mac_accumulator_lo[3]_i_15_psdsp/C` → `mac_accumulator_hi_reg[13]/D`
- 最差路径数据延迟：`6.530 ns`（logic `3.740 ns`，route `2.790 ns`），15 个逻辑级
- bit/XSA：已生成，仅用于失败分析，禁止下载到目标板

本轮在响应路径复制 `mask_response_epoch` 后，最差路径重新落在 MAC 高位累加器链；该局部修复未获得 200 MHz 顶层 setup 签核。B2-06～B2-10 和 B2-GATE 保持未完成，ENeuron 动态剪枝吞吐/功耗 A/B 不得开始。
