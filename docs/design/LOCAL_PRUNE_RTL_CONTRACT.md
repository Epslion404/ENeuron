# 局部 `2:4` 剪枝 RTL V1 合同

日期：2026-08-29  
状态：`IMPLEMENTATION_CONTRACT_FROZEN`

## 1. 边界

本合同实现用户已批准的 NP4 V1 六项决定。控制器只负责四路局部分数、一次原子 `2:4` 提交、读取前门控和审计计数；不复制神经元方程，不生成标签、奖励或训练调度，不实现 detector/channel enable、渐进剪枝或自动恢复。

三种神经元只在证据适配器处不同：

- ENeuron：gain 1；
- Pulse-Mini-L：gain 2，二位饱和后映射 `0/1/2/3 -> 0/2/3/3`；
- Pulse-Mini-L2：gain 1。

适配后的控制器输入统一为四路二位非负证据。控制器固定使用已签核的 S2 更新，不实现 S0/S1/S3 选择器。

## 2. 运行命令

控制器使用单槽 `valid/ready` 请求与响应。响应被背压时保持，且不接受新命令。

| opcode | 命令 | 合法模式 | 行为 |
|---:|---|---|---|
| 0 | `OBSERVE` | TRAIN | 以严格递增 observation ID 原子更新四路 utility |
| 1 | `PRUNE_CLEAR` | CONFIG | 清 utility、mask-valid、last observation/commit；不清工作量计数 |
| 2 | `PRUNE_COMMIT` | TRAIN | 安全边界内顺序扫描四路 utility，一次提交严格 `2:4` mask |
| 3 | `MASK_READ` | CONFIG/TRAIN/INFER | 返回数据路径当前实际使用的 mask |

其他 opcode 返回错误且不改变架构状态。CONFIG 专用 mask 写入口与运行命令分离，只接受六种严格双位 mask，用于测试、初始化和故障注入，不计作本地剪枝提交。

模式直接复用神经元或上层 wrapper 的同步模式状态，避免控制器与神经元各保存一份可能失配的模式。Host 必须在命令响应完成后再切换模式。

## 3. 分数更新

每条连接保存四位 utility，范围 `0..15`。只有非零调制才更新：先把旧值向零减一，再加二位证据并饱和到 15。调制正负只决定神经元权重更新方向；剪枝控制器只累计证据幅度。

未提交时四路都可更新。提交后只有结构 mask 中仍保留的两路可更新，被剪两路冻结。即使调制为零，合法 observation ID 仍被消费，以保持 exactly-once 事务语义。

## 4. 原子提交和周期

`PRUNE_COMMIT` 只在以下条件同时满足时接受：TRAIN、核心空闲、无 pending snapshot、无 pending mod commit、当前无有效剪枝 mask、commit ID 严格递增。

接受后用四个时钟依次扫描编号 0、1、2、3，只保存当前第一名和第二名。utility 大者优先；相同时编号小者优先。第四拍结束时一次性写入最终双位 mask，扫描中对外 mask 始终保持旧值，因此不会出现瞬时 `1:4`、`3:4` 或未知位。

单拍命令在接受后的第一个响应周期返回；`PRUNE_COMMIT` 在四个扫描拍完成后返回。扫描或响应背压期间 `cmd_ready=0`。

V1 在 mask-valid 后拒绝所有第二次提交，不因更大的 commit ID 放宽；只有 CONFIG 下显式 `PRUNE_CLEAR` 才回到稠密 `1111` 并允许下一轮提交。

## 5. 读取前门控和分账

数据路径始终组合产生：

```text
issue_mask = activity_mask & (mask_valid ? structural_mask : 1111)
```

该输出必须连接到权重读取请求和计算 lane 发射使能之前。`issue_valid` 到来时，以同一拍的旧结构状态累计实际工作量；mask 在时钟边沿原子提交后，下一拍请求才使用新结构。

每次 issue 同时携带 hidden/output 层标记，分别累计稠密请求、实际读取、突触操作和结构节省。`activity_mask=0` 单列为 inactive；非零活动被结构完全挡住单列为 skipped，二者不能重复算作结构收益。

## 6. 错误与审计

错误响应至少区分非法 opcode、非法模式、不安全提交、过期/重复 ID、已经提交和非法参数。所有拒绝路径只增加非法命令计数和错误脉冲，不改变 utility、mask、ID、提交数或工作量计数。

综合可见审计端口包括：四路 utility、结构 mask、mask-valid、last observation/commit ID 与 valid、提交数、非法命令数、hidden/output 工作量计数、inactive/skipped 计数。字符串日志只存在于 Python 测试，不是综合依赖。

## 7. NP5 验证门

- 定向覆盖六种合法 mask、完全同分、边界分数、饱和/衰减、零调制、重复/倒退 ID、忙时输入和响应背压；
- 三个固定 gain 适配器逐向量验证；
- Python/Icarus 至少 20 seeds × 1000 个已接受混合命令，逐事务比较全部可见状态；
- 检查任何时刻有效 mask 只能是六种严格双位值，未提交时实际 mask 必须为 `1111`；
- 检查 INFER 冻结、拒绝路径无副作用和隐藏/输出计数互不串账；
- 负向实现取消原子提交或编号破同分后，固定反例必须失败。

NP5 通过前，本合同只代表设计冻结，不代表 RTL、时序、资源、周期收益或功耗已经成立。
