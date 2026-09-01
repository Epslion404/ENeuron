# NP7 周期合同 B-V1+V2 冻结决策（PR #6 管理员裁定）

- 裁定来源：**PR #6 仓库管理员评论 5498372499**（Epslion404，2026-09-01T18:16:30Z），
  即本仓库既有的"批准链必须出现在 PR 内"口径下的正式授权凭据。本文是该裁定的仓库内副本，
  任何与评论原文的冲突以评论为准，并需在下一份 PR 回复中显式更正。
- 生效范围：替换 `NPU_PRUNING_NP7_FREEZE_DECISIONS.md` 决策 5 的旧周期合同（ACCEPT+READ+LAT+
  BATCH+DONE 五段式）；决策 1/2/3/4/6/7/8 由管理员逐项批准维持，决策 8 追加"允许
  Vivado 2024.1 或 2024.2，但每份证据必须绑定准确 version/build/执行机，不得跨版本外推"。
- 本文同时冻结 B-V1+V2 的**逐拍账本口径**（§3），oracle、RTL、testbench、验证器四方必须
  与之一致；旧账本恒等式 `total = accept + latency + busy + stall + done` 自本文起作废。

## 1. 八项裁定的仓库内记录

| # | 管理员裁定 | 实现落点 |
|---|---|---|
| 1 | 批准"独立共享突触执行单元，再接三模型网络"两阶段边界 | np7_exec_unit_{dense,sparse}.sv 与 np7_three_model_integration_cosim.py 分层不变 |
| 2 | 批准"两权重 + 两个 2-bit 位置索引"，不保存第二份结构掩码 | 掩码仅由索引组合重建；非规范索引在 CONFIG 写入侧硬件拒绝（`cfg_wr_ok`） |
| 3 | 批准 CONFIG 写入、运行期只读，无训练期权重写回 | np7_weight_ram.sv 只有 CONFIG 写端口；运行期写被丢弃并锁存 cfg_error |
| 4 | 批准扫描 1/2/4/8 lane，与同 lane 数 dense 基线比较 | LANE_COUNTS=(1,2,4,8)，G1-G6 按 lane 分别报告 |
| 5 | **原周期合同不批准继续沿用，正式修订为 B-V1+V2** | 本文 §2；oracle 的 run_stream 与两个 RTL 顶层同步改造 |
| 6 | 批准三模型全部使用冻结 4->8->2 B2.1 任务，不允许单模型或随机流量代偿 | NP7.4 保持三模型独立签核，随机流量只作为 NP7.3 压力测试，不用于 G1-G6 |
| 7 | 保持 G1/G2 >=45%、G3 >=25%，**不把 G3 降到 20%** | 验证器阈值不变 |
| 8 | 保持 NP7.0-NP7.6 全绿后才允许进入 Vivado；允许 2024.1 或 2024.2，证据必须绑定准确 version/build/执行机 | verify_np7_software_cost.py 强制 tool_versions 非空且绑定 frozen_head |

A（阈值降到 20%）、C（维持 25% 停在功能阶段）、D（随机流量口径）均不采用；选择 B 且明确
V1+V2，不是 V1-only。

## 2. B-V1+V2 合同原文（管理员裁定 §二）

### V1：零路径单拍

当 `issue_valid && issue_ready && issue_mask==0`：不得产生 RAM 请求或 lane 操作；结果为 0，
`result_zero_path=1`；`result_ready=1` 时，accept 与 result 必须在同一边沿完成，只计 1 个周期；
`result_ready=0` 时必须锁存并稳定保持结果，不能丢失、重复或覆盖；上层神经元仍须推进泄放、
阈值、睡眠和时间状态，不能把零突触解释成跳过整个神经元 tick。

### V2：结果退出与下一事务接受重叠

非零事务最后一个 BATCH 成功发射并得到最终 `acc_next` 时，若 `result_ready=1`，允许当拍完成
当前结果，不再进入独立 DONE 拍；同一边沿允许 `issue_ready=1` 并接受下一事务；当前结果和下一
事务元数据必须严格分离，不能串数据；任意时刻最多保存一个未退出结果，属于单槽弹性流水，不是
多事务队列；若结果背压，则锁存旧结果并停止接收，只有旧结果退出的同一边沿才可接收下一事务；
`lane_stall=1` 时不得提前完成或接受下一事务。

Dense 与 sparse 必须采用完全相同的 V1+V2 协议、输入流和背压口径。

