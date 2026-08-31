# NPU 局部剪枝原始 Goal 签核

日期：2026-08-28
状态：`GOAL_COMPLETE_NP4_REVIEW_REQUIRED`

## 1. 原始目标

本签核只覆盖以下用户目标：

1. 批准并冻结 NP0 八项决策。
2. ENeuron、Pulse-Mini-L、Pulse-Mini-L2 三种神经元分别运行，不以一个模型结果代替另一个。
3. 实验、发现、边界和 TODO 及时写入项目文档。
4. 各阶段及时提交到仓库。

NP4-NP9 的 RTL、协同仿真、Vivado、共享 lane、功耗和系统签核不属于上述原始目标的完成条件；它们是软件证据通过后新开启的后续阶段。

## 2. 要求级证据

### 2.1 NP0 八项批准

`docs/planning/NPU_PRUNING_TODO.md` 的 NP0 八项均已勾选，覆盖严格 `2:4`、TRAIN 安全边界、读取前动态门控、S0-S3 对照、状态预算、V1 禁止自动恢复、B0/B1/B2 顺序及四类证据边界。

批准记录提交：

- `5c34d8f docs: approve local NPU pruning plan`

### 2.2 三种神经元全部运行

| 阶段 | ENeuron | Pulse-Mini-L | Pulse-Mini-L2 | 证据 |
|---|---|---|---|---|
| NP1/B1 | 已运行 | 已运行 | 已运行 | `artifacts/results/local_prune_b1_results.json` |
| B2 | 已运行 | 已运行 | 已运行 | `artifacts/results/local_prune_b2_results.json` |
| NP2 | gain 1，通过 | gain 2，通过 | gain 1，通过 | `artifacts/results/local_prune_np2_results.json` |
| NP3 | 一次剪枝通过 | 一次剪枝通过 | 一次剪枝通过 | `artifacts/results/local_prune_np3_results.json` |
| B2.1 | output-2:4 通过 | output-2:4 通过 | output-2:4 通过 | `artifacts/results/local_prune_b21_results.json` |

最终三模型均为 BAcc/coverage 100%，推荐 output-2:4 后全网络 Python 读取/发射计数均为 120，相对稠密 240 减少 50%。

### 2.3 文档记录

阶段报告已经独立保存：

- `docs/reports/LOCAL_PRUNE_B1_REPORT.md`
- `docs/reports/LOCAL_PRUNE_B2_REPORT.md`
- `docs/reports/LOCAL_PRUNE_NP2_REPORT.md`
- `docs/reports/LOCAL_PRUNE_NP3_REPORT.md`
- `docs/reports/LOCAL_PRUNE_B21_REPORT.md`
- `docs/planning/NPU_PRUNING_TODO.md`
- `docs/planning/TODO.md` 以及根目录的 `findings.md`、`progress.md`、`task_plan.md`

报告明确保留以下边界：B2.1 是人为冗余任务，learned 与随机 mask 都可达到 100%；当前只证明软件冗余消除与 Python 发射计数，不证明评分优于随机、RTL、周期、Vivado 或功耗。

### 2.4 分阶段提交

主要提交链：

- `eabd2ed`：NP1 公共黄金模型。
- `2b8bd55`、`d475177`：三模型 B1 与报告。
- `11d40fb`、`0eb0229`：B2 与决策报告。
- `0f3bda1`、`bb15296`、`9585b20`：NP2 实现、结果绑定和报告。
- `8da00b6`、`5652576`、`5e57012`：NP3 实现、结果绑定和报告。
- `78b221c`、`d03cc6b`、`e047d9c`：B2.1 实现、结果绑定和报告。

代码、机器结果与文档没有堆积到单一最终提交。

## 3. 验证

- 2026-08-28 全仓回归：312/312 通过。
- NP2、NP3、B2.1 的所有 `source_sha256` 与当前源码一致。
- B2.1 的两个前置结果哈希与 NP2/NP3 机器结果一致。
- 三模型分别满足 `np2_pass=true`、`np3_pass=true`、`b21_joint_gate_pass=true`。
- 签核前工作树干净。

## 4. 后续边界

原始 Goal 至此完成。后续 NP4 必须重新通过用户审核，当前冻结建议为：隐藏/输出统一严格 `2:4`、gain=`1/2/1`、一次原子提交、无 detector gate、输出恢复只走既有训练事务、读取前形成 `issue_mask`。

在用户明确批准 NP4 六项决定前，不创建剪枝 RTL，也不运行 Vivado 签核。
