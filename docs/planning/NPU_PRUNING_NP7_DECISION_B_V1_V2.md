# NP7 周期合同 B-V1+V2 冻结决策（PR #6 管理员裁定）
> **[P1 revision 2026-09-02]** PR #6 管理员 review 5085536010 允许在 lane 的饱和加法/
> 事件计数路径插入一拍流水寄存器。本文件的 V1/V2 语义、8 项裁定与门槛全部维持，但
> **lane 结果返回时刻与周期账本口径已被 `NPU_PRUNING_NP7_DECISION_LANE_PIPELINE_P1.md`
> 修订**：非零事务多 1 个 `S_DRAIN` 折叠拍（计入 `latency_cycles`），V1 零路径不变；
> 按该裁定 §三，本文件引用的旧周期数字/账本/形式证明/物理结论降级为历史证据。

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

## 3. B-V1+V2 逐拍账本规范（oracle / RTL / testbench / 验证器四方一致）

账本的唯一事实来源是 testbench 每拍打印的一行观测：

```text
CYC <n> st=<0..5> ce=<0|1> ad=<addr> lf=<n> bm=<hex> rv=<0|1> rr=<0|1>
    ap=<0|1> zp=<0|1> sum=<-?n> ls=<0|1> cmp=<0|1>
```

`tb_np7_exec_unit.sv`（golden）与 `tb_np7_negative.sv`（两个负向实现）用**完全相同**的格式；
`np7_ledger_reconstruction.py` 只解析这些行重建账本，**不引用 RTL 内部计数器**。
RTL 计数器只作为"自报"副本参与交叉比对。

1. **流水窗**：第一次 `ap=1` 的拍到最后一次 `rv&&rr=1` 的拍（含端点）。窗口之外的
   冷启动前/排空后空闲拍不计入 `total_cycles`。
2. **互斥类别与优先级**（`classify_row`，与 `np7_shared_lane_oracle.classify` 一致）：
   `RAM(ce) > LANE(lf) > LAT(st=3) > LANE_STALL(st=4 && ls) > BACKPRESSURE(rv && !rr)`
   `> HOLD_RETIRE(st=5 && rv && rr) > ZERO(ap && zp && rv && rr) > ACCEPT(ap) > IDLE`。
   每一拍恰好落进一个类别，因此各类之和等于该窗口内非 IDLE 拍数。
3. **派生字段**：
   `busy_cycles = RAM + LANE`；`stall_cycles = LANE_STALL + BACKPRESSURE`；
   `total_cycles = 窗口拍数 - IDLE 拍数`；`completed_groups = #(rv&&rr)`；
   `accept_events = #ap`；`overlap_cycles = #(ap && rv && rr)` 且排除 V1 单拍零路径
   （零路径的 accept/result 同拍是 V1 语义，不得重复记为 V2 收益）；
   `retire_latch_cycles = #(lf && rv && !rr)`；`zero_single_cycles = ZERO 类拍数`；
   `startup_cycles` = 窗口首拍为纯 ACCEPT 时为 1；`drain_cycles` = 最后一个
   `ce|lf|LAT` 拍到窗口末拍的间隔；`weight_values_fetched = #(ce) x 槽/字`（2）。
4. **必须闭合的恒等式**（验证器逐配置重算）：
   - `total = busy + latency + lane_stall + backpressure + hold_retire + zero_single + accept_own`
   - `stall = lane_stall + backpressure`
   - `accept_events = retire_events = completed_groups`（每 accept 恰好一个 result）
   - `zero_single_cycles <= zero_fast_paths`、`overlap_cycles <= accept_events`
5. **作废口径**：旧恒等式 `total = busy + stall + 3*(completed-zero) + 2*zero`（独立 DONE 拍、
   零路径两拍）自本裁定起不再成立。验证器对"新口径不闭合、只在旧口径闭合"的账本直接判为
   **裁定之前的旧证据**并拒绝，而不是当成算术错误。
6. **真实路径覆盖**：证据必须真的出现过 `startup / drain / overlap / backpressure /
   lane_stall / hold_retire / retire_latch / zero_single` 全部 8 类非零计数，且 dense 与
   sparse **各自**的 `zero_single_cycles > 0`；否则相应形式性质可能只在空真（vacuous）上通过。
   formal 侧另设 5 个可达性见证寄存器 `saw_zero_single / saw_zero_hold / saw_fold /
   saw_backpressure / saw_lane_stall`，并要求它们与软件计数一致。
7. **单槽不变量**：任意时刻最多一个未退出结果；背压期间 `hold_sum`/`hold_zero` 必须稳定保持，
   不得丢失、重复或被下一事务覆盖；`lane_stall=1` 时不得提前完成或接受下一事务。

## 4. 全量重跑范围与判据（裁定 §三）

旧 NP7.1-NP7.6 证据（HEAD `398dc1a` 及其之前）全部作废，本轮从新 HEAD 重跑下列全部项目：

| 步骤 | 命令 | 判据（不满足即验证器拒绝） |
|------|------|------|
| NP7.1 | `python -m unittest test_np7_shared_lane_oracle -v` | oracle 逐拍模型覆盖零路径 ready/背压、最后一批、连续请求、同拍 retire/accept、冷启动、尾部排空 |
| NP7.3 | `python np7_shared_lane_cosim.py` | dense+sparse x {1,2,4,8} x >=20 seed = >=160 配置、>=160000 事务、连续无气泡流 + 随机背压、逐拍三方一致、恒等式闭合、8 类覆盖非零 |
| NP7.4 | `python np7_three_model_integration_cosim.py` | 三模型逐样本输出+完整膜状态比对，且每模型每 lane 的 `overlap_cycles>0`、`folded_cycles_saved>0`、`solo_segment_cycles>stream_cycles`、`zero_single_cycles>0`（证明上游确实利用 V2） |
| NP7.5 | `python np7_formal_and_mutations.py` | 每 accept 恰好一个 result、背压稳定、同拍不覆盖元数据、`lane_stall` 不提前完成；>=9 个 RTL mutation 全部给出反例，含新增"同拍覆盖旧元数据""背压时错误接受下一事务"两类 x dense/sparse |
| NP7.6 | `python generate_np7_manifest.py` 后 `python verify_np7_software_cost.py <head>` | 从原始逐拍账本重算 G1-G6；拒绝旧恒等式与只改摘要；清单绑定 version/build/执行机与逐拍日志字节 |

停止条件：若重跑后 G3 仍 <25%，**立即停止**，不自动改选 A（降阈值）或 D（随机流量口径），
也不得静默退回 V1-only；NP7.7 的 8 配置 Vivado 综合只在 NP7.0-NP7.6 全绿后运行。
