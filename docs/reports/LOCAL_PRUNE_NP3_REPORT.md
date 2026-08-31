# NPU 局部剪枝 NP3 闭环报告

日期：2026-08-28
状态：`NP3_PASS_B2_1_PENDING`

## 1. 结论

ENeuron、Pulse-Mini-L、Pulse-Mini-L2 已分别使用 NP2 冻结的 evidence gain=`1/2/1`，从各自同一个稠密 B2 checkpoint 运行三条分支：一次 `2:4`、软件渐进 `3:4→2:4`、错误符号微调。

| 模型 | 一次剪枝后 | 渐进剪枝后 | 错误符号后 | 推荐流程 |
|---|---:|---:|---:|---|
| ENeuron | 100% | 100% | 0% | 一次剪枝 |
| Pulse-Mini-L | 100% | 100% | 0% | 一次剪枝 |
| Pulse-Mini-L2 | 100% | 100% | 0% | 一次剪枝 |

表中为 BAcc；coverage 与 BAcc 相同。一次剪枝与渐进剪枝使用相同父 checkpoint、每个 detector 相同的两次微调预算，并得到相同最终 mask 和精度。因此渐进过程没有收益，按 KISS 保留一次剪枝。

## 2. 渐进剪枝合同

渐进分支没有破坏 V1“一次真实提交”的硬件语义：

1. 从 S2 utility 形成 top-3 软件训练 mask。
2. 在 `3:4` 输入门控下完成一次真实神经元训练观察。
3. 每个 detector 只调用一次 `PRUNE_COMMIT`，得到最终 top-2。
4. 在最终 `2:4` 下完成第二次训练观察。

中间 `3:4` 明确标记为 `software_3of4_training_mask`，不是第二次提交。所有三模型的 stage1、最终提交和最终微调 BAcc/coverage 都保持 100%。

## 3. 错误符号负对照

错误符号不是只翻转 S2 控制器的非零标志，而是作用于实际神经元训练事务：

- ENeuron 对 `apply_modulator_from_eligibility()` 使用负调制。
- Pulse-Mini-L/L2 对真实 `FEEDBACK` 使用负反馈。
- 输入、mask、观察顺序和两次微调预算与正常分支相同。

两次错误微调后，三模型 BAcc/coverage 都从 100% 降到 0%。错误分支的全网络读取为 80，但这是 detector 不再发放造成的任务失败，不能计为有效节省。

## 4. TRAIN 与冻结账本

三模型、三分支全部满足：

- `mask_write_count=0`。
- 每个 detector 的真实 `prune_commit_count=1`。
- 每个 detector 恰好两次微调观察。
- 最终 mask 在提交后的每次微调前后不变。
- 最终被剪权重在微调前后不变。
- 被剪 ENeuron `pre_trace/eligibility` 为零。
- 被剪 Pulse `positive/negative evidence` 与 `captured_direction` 为零。
- 在同一批活动核心上完成 INFER 后，权重、学习历史、utility、mask 和 mask-valid 指纹不变。

这不是通过“每个样本重新复制 checkpoint”得到的平凡冻结结论；冻结探针直接在同一分支核心上运行完整 B2 输入集。

## 5. 决策

- 三模型 NP3 全部通过。
- 最终流程统一为 `S2_one_shot`。
- 不实现渐进 `3:4` 训练状态机。
- S3 继续删除。
- 仍不得启动 NP4：正常分支全网读取/发射仍为 160，只减少 33.33%；B2.1 必须把两者都降到 132 以下。

## 6. 证据与边界

- `local_prune_np3.py`：真实微调事务、软件渐进 mask、错误符号和同分支 INFER 冻结。
- `test_local_prune_np3.py`：5 项闭环合同测试。
- `run_local_prune_np3.py`、`test_run_local_prune_np3.py`：机器决定和八个源码依赖哈希。
- `artifacts/results/local_prune_np3_results.json`：逐 detector TRAIN 账本和三模型分支结果。
- 结果绑定代码提交：`56525761693c1950cb7d7e2337aee64bfbaa55c6`。

本报告证明的是合成 B2 任务的软件剪枝—微调闭环，不证明输出侧 45% 工作量门、RTL、时序、功耗或图像任务。
