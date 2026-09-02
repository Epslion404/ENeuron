# NP7 lane 内插一拍流水（P1）周期合同裁定

- 裁定来源：**PR #6 仓库管理员 review 5085536010**（CHANGES_REQUESTED，
  2026-09-02T04:21:41Z，针对 head `537eb7a`，Epslion404）。本文件是该产品决者在仓库内
  记录该裁定的正式副本；引用以 PR 内原文为准。
- 生效范围：**修订** `NPU_PRUNING_NP7_DECISION_B_V1_V2.md` 的 lane 结果返回时刻与执行器
  周期合同（V1 零路径语义、V2 同拍 retire/accept 语义、背压语义、8 项裁定本身不变），
  并把 `537eb7a` 及之前的全部周期数字/账本/形式证明/物理结论**降级为历史证据**。
  `NPU_PRUNING_NP7_FREEZE_DECISIONS.md` 第 5 条与 `NPU_PRUNING_NP7_DECISION_B_V1_V2.md`
  §2 的周期账本口径同样按本文件重述。
- 授权边界：本裁定**只**允许在 lane 的饱和加法/事件计数路径插入**一拍**流水寄存器；
  不允许改变突触和的算术语义、gate 语义、饱和语义、lane 数扫描口径、G1-G6 门槛。

## 1. 管理员裁定原文（逐字引用）

### 1.1 一、实现裁定

> 允许在每个 lane 的饱和加法/事件计数路径中插入一拍流水寄存器，以缩短 L4/L8 的关键路径，
> 目标是让 sparse/dense × L=1/2/4/8 共 8 个配置都满足 100 MHz。
>
> 这会改变 lane 结果返回时刻和执行器周期合同，不能只修改 RTL 后直接复用旧证据。必须同步更新：
>
> - Python cycle oracle 与逐拍账本；
> - dense/sparse RTL、testbench 和协同仿真；
> - B-V1+V2 的 result/retire/accept 时序证明；
> - 三模型逐样本状态等价；
> - formal、reachability 和 mutation；
> - G1–G6 以及绝对周期/吞吐重算；
> - Vivado XSim 与 8 配置 OOC 综合。

### 1.2 二、物理验收裁定

> 本轮不接受"L1/L2 收敛、L4/L8 排除"的部分通过口径。NP7.7 最终必须满足：
>
> - sparse/L1、sparse/L2、sparse/L4、sparse/L8；
> - dense/L1、dense/L2、dense/L4、dense/L8；
>
> 共 8/8 在 xc7z020clg400-1、100 MHz 下满足：
>
> - WNS > 0；
> - WHS > 0；
> - setup failing endpoints = 0；
> - hold failing endpoints = 0；
> - DRC errors = 0；
> - route errors = 0。
>
> 未达到 8/8 前，不得宣称 NP7.7 完成，也不得用软件周期收益补偿未收敛配置。

### 1.3 三、证据与状态

> 当前 HEAD 537eb7a 的软件门和 4/8 物理收敛结果保留为历史证据，但不再作为最终签核。
> 插入流水后，NP7.1–NP7.7 必须按新周期合同全量重跑；旧的周期数字、账本、形式证明和
> 物理结论不得直接沿用。
>
> 在 8/8 收敛及全量证据完成前，本 PR 保持 CHANGES_REQUESTED，不得合并。

## 2. P1 周期合同正文

### 2.1 lane 内部的两段划分（唯一的实现改动）

`np7_shared_synapse_lane.sv` 由纯组合改为**两级流水**，切点选在饱和加法树的
`stage2`（2×12-bit）之后，使两段的 CARRY4 级数大致均衡：

| 段 | 内容 | 时域 |
|---|---|---|
| Stage A | `gated[8]`（结构 AND 活动的符号扩展 + 未用 lane 绑 0）→ `stage1[4]` → `stage2[2]` | 组合；在 `op_valid=1` 的拍末写入 `stage2_q[0:1]` 与 `valid_q` |
| 流水寄存器 | `stage2_q[0:1]`、`valid_q` | 1 拍 |
| Stage B | `tree_value = sat12(stage2_q[0], stage2_q[1])` → `raw_next = acc_seed + tree_value` → `acc_next`/`saturated` | 组合；输出与本拍的顶层 `acc` 寄存器对齐 |

算术语义逐字保持不变：仍是同一棵 balanced 12-bit 带符号饱和加法树，仍是
`acc_next = sat_add(acc_seed, tree_value)`，未使用 lane 仍参与 8→4→2→1 的加 0 结构，
`x+0` 不改变饱和值。**因此任意一批的 `acc_next` 数值与插流水前逐 bit 相同**，
只有产生时刻晚 1 拍。

新增端口：`clk`、`rst`、`op_valid`（本拍 Stage A 采样一个 batch）、
`fold_hold`（= 顶层 `lane_stall`：Stage B 不折叠、不写回、in-flight 保持）、
`fold_valid`（本拍 Stage B 有 in-flight 且未被 hold）。

`op_valid` 与 `fold_hold` 由顶层互斥保证（两者都由同一个 `lane_stall` 门控）；
即便如此，lane 内的写回优先级仍写成"`op_valid` 优先"，保证任何非法组合都是确定的。

### 2.2 顶层新增状态 `S_DRAIN`（state_code = 6）

```
S_IDLE(0) -> S_RD0(1) -> [S_RD1(2)] -> S_LAT(3) -> S_BATCH(4) -*-> S_DRAIN(6) -> {S_IDLE | S_HOLD}
V1 零路径：S_IDLE + accept 同拍完成（不进 lane，不受本裁定影响）
```

- `S_BATCH` 发射最后一批（`pending_mask & ~batch_mask == 0`）后进入 `S_DRAIN`，
  **不再**在发射拍直接出结果；
- `S_DRAIN` 的折叠拍（`lane_stall=0`）产生 `result_valid`/`result_sum`，并在
  `result_ready=1` 时与旧口径完全一样地**同拍 retire + accept**（V2 折叠仍然有效）；
  `result_ready=0` 时锁存 `hold_sum` 进 `S_HOLD`；
- `S_DRAIN` 期间若 `lane_stall=1`：**停在 DRAIN、不折叠、不出结果、不接受下一笔**
  （该拍归 `LANE_STALL` 类），以保持 P6/P10"lane stall 不提前完成、不提前接受"；
- `acc` 寄存器改由 Stage B 的折叠拍写回（`fold_commit`），accept 拍的 `acc <= 0`
  仍优先于折叠写回，与旧口径同一条 if/else 结构。

### 2.3 逐拍互斥类别与恒等式（类别集合不变）

优先级仍为 `RAM > LANE > LAT > LANE_STALL > BACKPRESSURE > HOLD_RETIRE > ZERO > ACCEPT`，
**不新增互斥类别**；`S_DRAIN` 的非 stall 拍计入 `LAT`（即 `latency_cycles`），
stall 拍计入 `LANE_STALL`。因此 NP7.6 验证器的恒等式结构不变：

```
total = busy + latency + lane_stall + backpressure + hold_retire + zero_single + accept_own
stall = lane_stall + backpressure
```

### 2.4 单笔事务闭式周期（合同公式，oracle/test/报告共用）

| 事务 | 旧合同（B-V1+V2） | 新合同（P1） |
|---|---|---|
| 非零（sparse，words=1，batches=k） | `3 + batches` = accept+read+lat+batches | `4 + batches`（+1 个 DRAIN 折叠拍） |
| 非零（dense，words=2，batches=k） | `4 + batches` | `5 + batches` |
| V1 零路径 | `1`（accept 与 result 同拍） | `1`（**不变**：零路径不进 lane） |
| lane 吞吐 | 1 batch/拍 | 1 batch/拍（**不变**，仅延迟 +1 拍） |

推论：每个非零事务 `total_cycles` 恰好多 1 拍、`latency_cycles` 恰好多 1；
`busy/stall/accept/retire/overlap/saturation/ops/权重槽读取` 全部不变，
故 G1、G2、G4 数字不变，G3（每逻辑 tick 周期下降）因分子分母同时变大而**下降**，
必须实测复核是否仍 >= 25%。

## 3. 裁定"必须同步更新的 7 项" → 仓库落点

| # | 裁定项 | 本仓库落点 |
|---|---|---|
| 1 | Python cycle oracle 与逐拍账本 | `np7_shared_lane_oracle.py`（DRAIN 建模、fold 与 issue 解耦、`retire_latch` 改在折叠拍）、`test_np7_shared_lane_oracle.py`（闭式周期 + 新增流水用例） |
| 2 | dense/sparse RTL、testbench、协同仿真 | `np7_shared_synapse_lane.sv`、`np7_exec_unit_sparse.sv`、`np7_exec_unit_dense.sv`、`tb_np7_exec_unit.sv`/`tb_np7_negative.sv`/`np7_negative_controls.sv`、`np7_shared_lane_cosim.py`、`np7_ledger_reconstruction.py`（STATE_DRAIN=6 分类） |
| 3 | B-V1+V2 的 result/retire/accept 时序证明 | `formal_np7_exec_unit.sv`（P1/P2/P8/P9/P10 + `e_lat` 拆成 `e_lat_val`/`e_lat`）、`formal_np7_exec_unit*.ys`（深度） |
| 4 | 三模型逐样本状态等价 | `np7_three_model_integration_cosim.py`（`_solo_total` 合同公式 +1、`v2_evidence`） |
| 5 | formal / reachability / mutation | 6 个 `.ys` + `np7_formal_and_mutations.py`（新增 lane 流水 mutation）+ `test_np7_verifier_mutations.py` |
| 6 | G1-G6 与绝对周期/吞吐重算 | `verify_np7_software_cost.py` 全量重跑 + `generate_np7_manifest.py` 重绑 |
| 7 | Vivado XSim 与 8 配置 OOC | `run_np7_vivado_xsim.py`（16 用例）+ `run_np7_vivado_ooc.py`（8 配置）+ `verify_np7_physical_cost.py`（按 §二 改为 8/8 硬判据） |

## 4. 物理验收判据（P1 口径，覆盖旧"excluded"口径）

`verify_np7_physical_cost.py` 从本轮起把"8/8 全部 timing met"作为 NP7.7 的**必要条件**：
任一配置 `WNS<=0`、`WHS<=0`、setup/hold failing endpoints != 0、DRC errors != 0、
route errors != 0 或未 ROUTED，都直接判 `NP7_PHYSICAL_SUMMARY overall=FAIL`，
不再允许"部分通过 + excluded 清单"。旧的 `4/8 + excluded sparse/L4,L8,dense/L4,L8`
结论按 §三 降级为历史证据，只保留在报告 §9 的历史小节里。

## 5. 未达 8/8 时的处置（禁止事项）

1. 不得宣称 NP7.7 完成，不得勾选维护者的 TODO 复选框；
2. 不得用 G1-G6 的软件周期收益去补偿未收敛配置；
3. 不得擅自改算术语义（例如砍掉饱和、改位宽、改 gate）来凑时序；
4. 若一拍流水实测仍不满足 8/8，必须**如实上报**并请求新的裁定，不得静默降级口径。