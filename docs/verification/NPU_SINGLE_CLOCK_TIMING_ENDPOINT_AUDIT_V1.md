# NPU 单时钟 DSP V1 全部失败端点审计

状态：`EVIDENCE_COMPLETE / DESIGN_UNCHANGED`

日期：2026-09-04

## 1. 目的与边界

冻结的 `timing_impl.rpt` 只展开最差 20 条 setup 路径，而时序摘要报告共有 22 个失败端点。本审计从保留的 routed checkpoint 重新生成最多 50 条路径，仅补齐端点分类，不修改 RTL、约束、实现结果或原始 OOC manifest。

本审计证明的是：当前 22 个 setup 失败端点已经全部落入两个已知路径族。它不证明 100 MHz 已通过，也不证明 TR7-TR12 一定能一次修复成功。

## 2. 证据身份

- 设计：`npu_eneuron_single_clock_skeleton`
- 器件：`xc7z020clg400-1`
- 工具：Vivado 2024.1 build 5076996
- 时钟：100 MHz（10 ns）
- routed checkpoint：`vivado_npu_single_clock_ooc_reports/npu_eneuron_single_clock_skeleton_impl.dcp`
- checkpoint SHA-256：`A4E290DD4CE8FDA2852A03F1BE3EFA244BE5E1DB3CBE172C19CCCAAE187840C3`
- 扩展命令：`report_timing_summary -delay_type min_max -max_paths 50`
- 扩展 Tcl SHA-256：`3D58CED03DDA57BA990D168A2C7C74C0A5036F8FD7645A507A1638FCD4E3EF31`
- 扩展报告 SHA-256：`BE8F1BF268553E9BDAEB31FF7DB348D6F4573011DF6CBDB699D840A71D91F04D`
- 扩展报告摘要：`WNS=-0.673 ns`、`TNS=-6.462 ns`、22 个 setup 失败端点；`WHS=+0.090 ns`、0 个 hold 失败端点

checkpoint、Tcl 和扩展报告均保留在仓库外或被 `.gitignore` 排除；仓库只持久化可复核的身份、命令、哈希与端点清单。原始 manifest 仍绑定实现提交 `50550733e4af4779f3d6933738fa043ecb919970` 及冻结报告，本审计不覆盖该 manifest。

扩展报告头部的主机时间为 `2026-09-05 03:12:19`，晚于本会话采用的当前日期 `2026-09-04`；因此该时间只视为主机时钟元数据，不作为证据先后关系。证据身份以 checkpoint、命令和 SHA-256 为准。

## 3. 22 个失败端点

### 3.1 动态激活选择到 lane 求和寄存器：14 个

这 14 条路径均从 `compute_group_index_reg[1]_rep__1/C` 出发，经动态激活选择、一个 DSP48E1 和四乘积求和链，到达 `lane_sum_latched`。TR7/TR8 针对这一族：在 FETCH 锁存四个激活操作数，使 EXECUTE 不再携带动态数组选择器。

| 序号 | Slack (ns) | Destination |
|---:|---:|---|
| 1 | -0.673 | `lane_sum_latched_reg[30]/D` |
| 2 | -0.562 | `lane_sum_latched_reg[16]/D` |
| 3 | -0.559 | `lane_sum_latched_reg[13]/D` |
| 4 | -0.538 | `lane_sum_latched_reg[15]/D` |
| 5 | -0.464 | `lane_sum_latched_reg[14]/D` |
| 6 | -0.448 | `lane_sum_latched_reg[12]/D` |
| 7 | -0.445 | `lane_sum_latched_reg[9]/D` |
| 8 | -0.424 | `lane_sum_latched_reg[11]/D` |
| 9 | -0.350 | `lane_sum_latched_reg[10]/D` |
| 10 | -0.334 | `lane_sum_latched_reg[8]/D` |
| 11 | -0.331 | `lane_sum_latched_reg[5]/D` |
| 12 | -0.310 | `lane_sum_latched_reg[7]/D` |
| 13 | -0.236 | `lane_sum_latched_reg[6]/D` |
| 14 | -0.220 | `lane_sum_latched_reg[4]/D` |

### 3.2 组号到 logit 分布式存储写使能：8 个

这 8 条路径均从 `compute_group_index_reg[3]/C` 出发，到同一 `logit_values` 分布式存储实例的八个写使能端点，slack 均为 `-0.071 ns`。TR9 的统一 WRITEBACK 针对这一族，使数组写入只发生在独立写回状态。

| 序号 | Slack (ns) | Destination |
|---:|---:|---|
| 15 | -0.071 | `logit_values_reg_0_15_18_23/RAMA/WE` |
| 16 | -0.071 | `logit_values_reg_0_15_18_23/RAMA_D1/WE` |
| 17 | -0.071 | `logit_values_reg_0_15_18_23/RAMB/WE` |
| 18 | -0.071 | `logit_values_reg_0_15_18_23/RAMB_D1/WE` |
| 19 | -0.071 | `logit_values_reg_0_15_18_23/RAMC/WE` |
| 20 | -0.071 | `logit_values_reg_0_15_18_23/RAMC_D1/WE` |
| 21 | -0.071 | `logit_values_reg_0_15_18_23/RAMD/WE` |
| 22 | -0.071 | `logit_values_reg_0_15_18_23/RAMD_D1/WE` |

## 4. 审计结论

- 完整分类为 `14 + 8 = 22`，不存在剩余未分类的 setup 失败端点。
- V2 仍需同时处理两族路径；只增加 WRITEBACK 会漏掉最差 DSP 输入路径，只锁存激活值会留下写使能路径。
- TR7-TR12 的方案边界不需要因本次补证改变，但其证据基础从“前 20 条抽样”提升为“全部 22 个失败端点”。
- 继续强制恰好 4 个 DSP48E1；任何 V2 结果仍须重新运行完整功能回归和同器件同约束 OOC，不能用本审计替代。
