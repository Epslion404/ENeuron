# XC7Z020 T3 真实 XPM/xsim 与 OOC 阶段报告

日期：2026-09-07  
状态：`T3_XSIM_PASS / T3_OOC_PHYSICAL_GATE_PASS`

## 1. 范围

本阶段验证“传统 INT8 NPU + ENeuron 单时钟核心 + T1 双时钟适配器 + 四条异步 FIFO”在 `xc7z020clg400-1` 上的可复现性。验证不包含 AXI、DMA、PS7、Ethernet、板级 I/O、bitstream、功耗或网口端到端吞吐。

## 2. 真实 XPM/xsim

入口：`run_vivado_npu_zynq7020_t3_xsim.ps1`  及 `vivado_npu_zynq7020_t3_xsim.tcl`

- Vivado：2024.1
- 器件：`xc7z020clg400-1`
- 仿真顶层：`tb_npu_zynq7020_t1_wrapper`
- XPM：Vivado `XPM_LIBRARIES {XPM_FIFO}` 提供的 AMD `xpm_fifo_async`
- 仓库内 `xpm_fifo_async_sim.sv`：未编译
- 结果：`RESULT=PASS`
- T1 marker：`T1_PROTOCOL_SKELETON_PASS`

这证明同一份 T1 协议切片在真实 AMD XPM 模型下完成了复位、非法命令、模型装载、mask、fence、8 beat sample、10 beat result、背压、epoch 切换和复位重入场景。

## 3. XC7Z020 OOC

入口：`run_vivado_npu_zynq7020_t3_ooc.ps1`  及 `vivado_npu_zynq7020_t3_ooc.tcl`

实现策略固定为 `phys_opt_design -directive AggressiveExplore`。最终摘要：

| 项目 | 结果 |
|---|---:|
| 总 LUT | 2467 |
| 总 FF | 2301 |
| RAMB36 | 6 |
| RAMB18 | 1 |
| DSP48E1 | 4 |
| Host WNS / WHS | `+3.639 ns / +0.105 ns` |
| NPU WNS / WHS | `+0.214 ns / +0.042 ns` |
| setup/hold failing endpoints | `0 / 0` |
| route errors | `0` |
| DRC errors / critical warnings | `0 / 0` |
| external CDC critical / warning | `0 / 0` |
| Physical gate | `PASS` |

层次化归因中，`core` 占 `2231 LUT / 1869 FF / 4 DSP48E1`；顶层其余逻辑和四条 FIFO 合计贡献 `236 LUT / 432 FF`，四条 FIFO 使用 6 个 RAMB36 和 1 个 RAMB18。完整分布见 `vivado_npu_zynq7020_t3_ooc_reports/utilization_impl_hierarchical.rpt`。

## 4. 本轮必要修正

1. Host 样本窗口改为在 Host 域实际消费合法 fence 响应后开启，删除额外的手写 toggle CDC；Vivado `report_cdc` 的外部 critical 从 1 降为 0，协议回归仍通过。
2. 乘法 lane 不再由 `compute_state` 组合门控。非 EXECUTE 状态的乘积不会被采样，因此该改动不改变状态转移或数值合同，但缩短了 `compute_state -> DSP -> lane_sum_latched` 关键路径。
3. OOC 脚本固定 `AggressiveExplore`，避免边界时序设计受默认物理优化策略影响。

## 5. 证据边界与下一步

T3 已证明当前核心、适配器和四条 XPM FIFO 的真实模型与 XC7Z020 OOC 物理门。它没有证明真实板级 I/O 时序、网口吞吐、DMA/PS 软件链路、功耗或首次完整端到端训练/推理。资源裁剪继续遵守 `RESOURCE_CUT_DEFERRED_UNTIL_FIRST_END_TO_END_RUN`；下一阶段应先完成完整端到端运行，再重新评估 C1-C9。

机器摘要：

- `vivado_npu_zynq7020_t3_xsim/xsim_signoff_summary.txt`
- `vivado_npu_zynq7020_t3_ooc_reports/signoff_summary.txt`
