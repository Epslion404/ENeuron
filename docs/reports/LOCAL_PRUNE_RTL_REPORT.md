# NPU 局部剪枝 NP4/NP5 公共控制器报告

日期：2026-08-29  
状态：`COMMON_CONTROLLER_NP4_NP5_PASS_INTEGRATION_PENDING`

## 结论

已实现独立 `local_prune_gate_2of4.sv` 和三种固定 gain 适配器。公共控制器只实现已冻结的 S2：四路 4-bit utility、一次四拍原子 top-2 提交、严格 `2:4` mask、读取/发射前 `issue_mask`，以及隐藏层/输出层互不重叠的工作量计数。

三模型 Python/RTL 协同仿真各运行 20 seeds × 1000 个混合事务，总计 60000 条，全部逐事务一致。两个故障变体均被拒绝：扫描中提前写 mask 会触发原子性反例；把严格比较改为偏向后到编号会在完全同分时产生错误 mask。

Yosys 0.56 完成 depth=32 有限形式检查，并用独立 SAT 可达性约束证明一次真实 `PRUNE_COMMIT` 能到达，避免把不可达轨迹写成证明。检查覆盖严格双位 mask、扫描期旧 mask 稳定、确定性 top-2、响应背压、第二次提交拒绝、重复 observation ID 拒绝和 INFER 写命令冻结。

## 精确硬件合同

- 普通命令在接受沿完成，不增加扫描周期；
- `PRUNE_COMMIT` 接受后依次扫描四路 utility，共四个额外时钟；
- 前三个扫描拍以及第四拍边沿前对外仍是旧 mask，第四拍边沿一次发布最终双位 mask；
- mask-valid 后拒绝第二次提交，直到 CONFIG `PRUNE_CLEAR`；
- `issue_mask=activity_mask & effective_structural_mask` 为组合输出；
- issue 当拍按 hidden/output 标记分别累计稠密请求、实际读取/操作和结构节省；
- `activity_mask=0` 只计 inactive，不冒充结构收益。

## 重要边界

这次通过的是“公共剪枝控制器与固定 gain 接口”，不是完整 NPU 集成：

1. 当前 ENeuron 多周期核没有正式导出四路 eligibility snapshot。正式 wrapper 不能依赖层次路径，必须增加只读快照旁路或单独适配器，并重新验证核心接口。
2. Pulse-Mini-L/L2 的 captured direction 会在成功 FEEDBACK 时被清除。正式 wrapper 必须在 FEEDBACK 接受沿先锁存证据，核心返回成功后再发 OBSERVE。
3. 现有 `4→2→2` tile 的输出核只有两路输入，不满足严格 `2:4`；B2.1 的输出 `2:4` 属于四 detector 输出分组，不能直接套入该 tile。
4. 当前 `issue_mask` 与计数器证明了门控意图和不重叠账本；现有 ENeuron 引擎仍逐项扫描权重。真实 BRAM 跳读、共享 lane 周期下降属于 NP7，尚未证明。
5. 尚未运行 Vivado NP6，因此没有新增 LUT/FF、100 MHz routed 或功耗结论。

## 证据

- `docs/design/LOCAL_PRUNE_RTL_CONTRACT.md`：接口、拒绝、周期和声明边界；
- `local_prune_rtl_reference.py`：逐事务黄金模型；
- `local_prune_gate_cosim.py`：60000 条协同仿真和两个负向变体；
- `formal_local_prune_gate.sv`：有限形式断言；
- `formal_local_prune_gate_reach.ys`：真实提交可达性；
- `local_prune_rtl_results.json`：源码哈希、工具和机器结果。

下一步不是直接跑 Vivado，而是先审核并实现两个核心证据旁路 wrapper 和适合输出 `2:4` 的四路分组拓扑。它们逐事务通过后，NP4 才能从“公共控制器通过”升级为“三核心正式接入通过”。
