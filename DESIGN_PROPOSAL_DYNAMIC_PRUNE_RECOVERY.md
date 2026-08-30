# 设计提案（待审）：动态恢复型局部剪枝门控 V2-draft

状态：`PROPOSED_NOT_APPROVED` · 提案日期：2026-08-30 · 本 PR **不含该方案的任何 RTL**

## 1. 为什么要单独提案

原提交里那套 `neuron_gate_core.sv`（8 位 score、lane cooldown、自动 regrow、`image_end`/`epoch_end`
协议）与已经冻结的 V1 合同 `LOCAL_PRUNE_RTL_CONTRACT.md` 是两套互不兼容的设计：

| 维度 | V1 冻结合同（已签核） | 原提交里的设计（未批准） |
|---|---|---|
| 分数 | 4 位 utility，范围 0..15，非零调制才更新 | 8 位 score，0..255 |
| 选择 | `PRUNE_COMMIT` 扫描全部四路，一次原子提交严格 2:4 | 在 `raw_mask` 内选 top-2 |
| 恢复 | 训练中禁止自动 regrow，只有 CONFIG 下 `PRUNE_CLEAR` | lane 计数到期后自动 regrow |
| 事务 | 单槽 valid/ready 命令 + 响应 + observation/commit ID | `image_end`/`epoch_end` 广播 |
| 审计 | 原子 `PRUNE_COMMIT`、非法命令计数、分层工作量 | 无 ID/exactly-once 语义 |

因此按评审意见：**该设计从本 PR 移除**，只以提案形式进入评审；本 PR 的仿真交付物改为直接验证
`local_prune_gate_2of4.sv`（见 `SIMULATION_REPORT.md`）。

## 2. 提案要解决的问题

V1 一旦提交 2:4 结构掩码就永久冻结，被剪两路的 utility 也不再更新。若训练后期特征分布漂移，
被剪掉的连接没有恢复通道。提案目标是在**不破坏 V1 原子性与 exactly-once 语义**的前提下，
给每一组增加一次受控的恢复窗口。

## 3. 规范语义（必须先解决的一致性缺陷）

评审给出的反例：`mask=1100`、`scores=[250,200,150,100]`、`lane0 cooldown=1` 时
Python 输出 `0011`、RTL 输出 `0110`。根因是两套实现选择了不同的**候选集合**：

- 参考实现先按 cooldown 过滤，再从**全部四条**排序取前二；
- RTL 只在 `raw_mask` 内取 top-2。

提案规定唯一真源（golden model 与 RTL 必须同序）：

```
candidate_mask = raw_mask & ~cooldown_mask          # 允许参与竞争的 lane
kept           = top2(candidate_mask, score, tie = 小序号优先)   # 只在 candidate 内排名
```

并且：

1. `popcount(candidate_mask) < 2` 时命令**拒绝**，架构状态零副作用（沿用 V1 的 fail-closed 与
   非法命令计数），绝不允许提交 0/1/3/4 个置位的结构掩码；
2. `raw_mask` 与 `cooldown_mask` 都必须是寄存器态，且在同一拍采样，禁止组合回环；
3. 每次恢复窗口只允许把掩码改回稠密 `1111`，改回之后必须重新走一次 `PRUNE_COMMIT`；
4. 恢复事件计数、cooldown 到期事件必须可见（审计端口），便于逐事务对拍。

## 4. 与 V1 的接口差异（增量，不改既有端口）

- 新增 `REGROW_ARM`（CONFIG 专用）与 `REGROW_WINDOW`（TRAIN，带 commit ID 严格递增）两个 opcode；
- 新增 `cooldown_flat[3:0][7:0]` 与 `regrow_events[31:0]` 审计输出；
- `MASK_READ` 语义不变，仍返回数据路径实际使用的掩码；
- INFER 模式仍然冻结一切结构变化（含 regrow）。

## 5. 验收门（沿用 NP5，另加三条）

1. exact-two：任何时刻可见结构掩码只能是六种双位值，未提交时为 `1111`；
2. 同分确定性：固定 0-1-2-3 扫描序，同分保留小序号；
3. 饱和与衰减：4 位（或提案的 8 位）上限处不溢出；
4. INFER 冻结与拒绝路径零副作用；
5. Python/RTL 逐事务协同仿真：多 seed、比较 score、mask、candidate、cooldown 与全部可见协议状态；
6. **新增**：反例回归 `mask=1100, scores=[250,200,150,100], cooldown lane0=1` 必须 bit-exact；
7. **新增**：`popcount(candidate) < 2` 的注入必须被拒绝且零副作用；
8. **新增**：失败敏感变异（去掉 exact-two、破坏原子性、把同分规则反过来）必须全部被捕获。

## 6. 请评审裁决的问题

1. 恢复窗口是每 epoch 一次还是每 `REGROW_WINDOW` 个 observation 一次？
2. cooldown 用 lane 计数器还是全局窗口 ID？位宽？
3. 恢复是否要求 host 显式命令（V1 风格），还是允许硬件自主（原提交风格）？
4. score 位宽是否维持 4 位以复用已签核的 S2 更新与形式化结论？
5. `popcount(candidate) < 2` 时是拒绝（本提案）还是退回旧掩码？

**在得到答复之前，本仓库只维护 `local_prune_gate_2of4.sv` 这一套实现。**
