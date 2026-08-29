# NPU 局部剪枝 NP4B 正式集成 TODO

状态：`IMPLEMENTATION_APPROVED`

日期：2026-08-29

范围：把已签核的公共 `2:4` 控制器接入 ENeuron、Pulse-Mini-L、Pulse-Mini-L2，并在固定 `4→8→2` 网络完成端到端功能验证。本阶段只证明功能集成，不运行 Vivado，不证明共享 BRAM 真跳读、共享 lane 周期下降或功耗收益。

## 1. 当前基线

已完成：

- NP4 V1 六项接口决定已由用户批准。
- `local_prune_gate_2of4.sv` 已实现 S2-only utility、四拍确定性 top-2、一次原子严格 `2:4` 提交、读取前 `issue_mask` 和隐藏/输出分账。
- ENeuron、Pulse-Mini-L、Pulse-Mini-L2 固定 evidence gain 已冻结为 `1/2/1`。
- 三模型各完成 20 seeds × 1000 条公共控制器 Python/RTL 协同事务，共 60000 条，零差异。
- depth=32 有限检查、成功提交可达性和两个故障变体反例均已通过。
- 当前准确状态是 `NP4A/NP5_COMMON_CONTROLLER_PASS`、`NP4B_INTEGRATION_PENDING`、`NP6_NOT_STARTED`。

尚未完成：

- ENeuron 没有正式、可综合的 committed snapshot evidence 导出端口。
- Pulse 两个核心会在合法 FEEDBACK 接受沿清理 captured direction，wrapper 必须在该沿锁存旧值。
- 现有 ENeuron 与 Pulse `4→2→2` 网络的输出核只有两个输入，不能声明输出层严格 `2:4`。
- 公共控制器验证不能替代三种神经元 wrapper、两层网络和真实事务顺序的集成验证。

## 2. NP4B 目标

NP4B 完成时，只允许声明：

> 三种神经元均已把本地训练证据接入同一个严格 `2:4` 控制器；固定 `4→8→2` 测试网络的隐藏层和输出层均能在一次原子提交后执行结构门控，并与 Python 黄金模型逐事务一致。

NP4B 不允许声明：

- 已减少真实 BRAM 访问；
- 已减少共享 lane 周期；
- 已通过 XC7Z020 100 MHz；
- 已降低动态功耗；
- 已完成图像识别或通用 NPU 剪枝。

上述声明分别留给 NP6、NP7、NP9 或独立任务能力阶段。

## 3. 已批准的八项实现决定

以下八项已于 2026-08-29 获用户明确批准，允许按 NP4B1→NP4B6 测试先行实施：

1. 允许给 `digital_lif_engine.sv` 增加只读 `eligibility_snapshot_flat_state` 端口；只导出已提交 snapshot，不导出 live eligibility 或工作副本，不修改神经元方程和事务优先级。
2. Pulse-Mini-L/L2 只增加外部 wrapper，不扩展或重定义现有 3-bit 核心 opcode，不修改两个已签核核心。
3. 新建独立 `4→8→2` 剪枝测试网络，保留现有 `4→2→2` tile/network，不用两输入输出核冒充严格 `2:4`。
4. 剪枝命令使用独立 sideband 通道，NP4B 不把 `OBSERVE/PRUNE_COMMIT` 塞入既有 Host Bridge V1 或 Pulse 核心 opcode。
5. 第一版每个四输入神经元对应一个 gate；先验证 10 个独立 gate 的正确性，不在 NP4B 引入控制器时分复用。
6. `STATE_CLEAR` 与 `PRUNE_CLEAR` 语义独立：前者清样本动态历史但保留 utility/mask，后者只在 CONFIG 恢复稠密 mask 并清 utility。
7. 成功 `PRUNE_COMMIT` 对外完成前，由 wrapper 自动完成所有相关神经元的 `STATE_CLEAR`；Host 不得在 commit 与清历史之间插入 TICK。
8. NP4B 只做功能集成；全部签核后再次提请用户批准，才进入 NP6 Vivado 物理成本。

## 4. 冻结架构

### 4.1 公共边界

三种模型共用：

- 一个 `local_prune_gate_2of4` 实现，不复制排名逻辑；
- 每个四输入神经元一个 gate；
- 独立剪枝命令/响应通道；
- 统一的 4 路、每路 2-bit evidence level；
- 固定 `issue_mask = structural_mask AND activity_mask`；
- 固定隐藏层/输出层身份，不允许 Host 每笔命令任意切换计数归属；
- 成功 commit 后阻塞运行命令，直到清历史完成；
- 所有事件提供定宽 audit 状态和计数器，不依赖字符串日志参与综合。

模型差异只留在薄适配器：

| 模型 | 原始证据 | 取值 | 固定 gain | OBSERVE 时点 |
|---|---|---:|---:|---|
| ENeuron | committed eligibility snapshot | 12-bit signed | 1 | 合法 MOD 接受边界，与同一 commit ID 原子协调 |
| Pulse-Mini-L | captured direction | `-1/0/+1` | 2 | FEEDBACK 接受沿锁存，核心成功响应后提交 |
| Pulse-Mini-L2 | captured direction | `-2..+2` | 1 | FEEDBACK 接受沿锁存，核心成功响应后提交 |

### 4.2 ENeuron 数据顺序

```text
SNAPSHOT 扫描
→ committed snapshot 原子发布
→ wrapper 验证 tile pending commit ID
→ 合法 MOD 与 gate OBSERVE 同一接受边界启动
→ 核心原子更新权重
→ gate 更新 utility
```

关键合同：

- snapshot flat 只连接 `eligibility_snapshot[]`，不能连接 `eligibility_snapshot_work[]`。
- lane `i` 固定映射到 `[i*ELIG_BITS +: ELIG_BITS]`。
- snapshot 无效时数据可以保持旧寄存值，使用者必须同时检查 valid 和 pending commit ID。
- 先扩展位宽再取绝对值，必须正确处理 12-bit 最小负数。
- 同周期多个命令时复用 tile 既有优先级；仅观察实际被选择并接受的 MOD。
- gate backpressure 必须阻止 MOD 被核心单独接受，禁止权重成功但 utility 失败。
- 零 MOD、错误 commit ID、INFER MOD、busy 或优先级冲突均不得 OBSERVE。
- 不修改核心 snapshot 的既有延迟、零 MOD 语义和 `STATE_CLEAR` 保留 snapshot 的合同。

### 4.3 Pulse 数据顺序

```text
CAPTURE 形成 captured direction
→ FEEDBACK 被核心接受时 wrapper 锁存旧 direction
→ 核心返回 ST_OK
→ 非零反馈才向 gate 发一次 OBSERVE
→ OBSERVE 成功后才向上游公开原 FEEDBACK 成功响应
```

关键合同：

- 不能等 core response 到达后再读取 direction；此时核心已清理它。
- FEEDBACK=0、`BAD_ARG`、`BAD_MODE`、`NO_PENDING` 或未被核心接受时，OBSERVE 次数必须为零。
- response 背压期间不得重复 OBSERVE。
- observation ID 只在成功非零 FEEDBACK 后递增；达到最大值后拒绝新观察，禁止回绕复用旧 ID。
- L 的非法 `-2` 编码和 L2 的非法 `-4/-3/+3` 编码必须触发断言或内部错误，不能静默量化。
- TICK 送入核心前必须先应用 `issue_mask`。
- 不应期导致的跳过单独计数，不能冒充结构剪枝节省。

### 4.4 commit 与清历史

网络级 `PRUNE_COMMIT` 固定为复合原子事务：

```text
全体 gate/core 预检
→ 同一边沿启动全部 gate commit
→ 禁止 TICK/MOD/FEEDBACK/CAPTURE
→ 等全部 gate done
→ 向全部神经元执行 STATE_CLEAR
→ 等全部 core done/ST_OK
→ 统一公开新 mask epoch 和 commit 成功响应
```

约束：

- 任一 gate 或 core 预检失败时，所有 gate 都不得启动。
- gate 内部完成先后不作为外部可见状态；运行命令在 all-done barrier 前保持阻塞。
- commit 成功而内部 `STATE_CLEAR` 异常时不尝试回滚 mask；置 sticky internal error，并停止接受运行命令。
- `PRUNE_CLEAR` 必须由 CONFIG 显式执行，不能由样本 `STATE_CLEAR` 隐式触发。

## 5. 分阶段 TODO

### NP4B0：批准与测试合同

- [x] 用户批准第 3 节八项实现决定。
- [x] 冻结 ENeuron snapshot packed lane 顺序和量化边界向量。
- [x] 冻结 Pulse FEEDBACK→OBSERVE 响应可见顺序。
- [x] 冻结 network commit、all-done barrier、异常后 sticky error 行为。
- [x] 冻结先写失败测试和黄金事务、再写 RTL 的纵向 TDD 顺序。

硬门：所有外部可见状态、命令接受条件和逐周期延迟无歧义。

NP4B0 状态：`PASS`。本批准不构成 NP4B 集成、Vivado、共享 lane 或功耗签核。

### NP4B1：ENeuron 证据旁路与 wrapper

状态：`PASS`。单核 wrapper 同时支持默认自动 clear 和网络屏障管理 clear 两种已批准部署方式；尚未计入网络级签核。

预计修改：

- `digital_lif_engine.sv`
- 现有核心与 tile 协同仿真测试

预计新增：

- `eneuron_local_prune_wrapper.sv`
- ENeuron wrapper Python oracle、testbench 和定向测试

任务：

- [x] 增加纯组合、参数化 committed snapshot flat 输出，不增加寄存器或读取协议。
- [x] 证明 snapshot 扫描期间导出保持旧值，只在 commit 沿原子变化。
- [x] wrapper 在合法 MOD 接受边界锁存/量化同一份 snapshot，并与 gate OBSERVE 原子协调。
- [x] 把 `issue_mask` 应用于核心输入之前。
- [x] 默认成功剪枝提交后自动清动态学习历史；参数关闭时由网络 barrier 管理 clear，权重与 utility/mask 均保持。
- [x] 在 `mask_valid=0` 的旁路模式与原核心逐事务 bit-exact。
- [x] 不依赖层次路径，不复制 eligibility、STDP 或 LIF 方程。

定向门：

- snapshot 原子导出、signed lane 顺序、最小负数绝对值；
- snapshot 后再修改 live eligibility，MOD 与 OBSERVE仍使用旧 snapshot；
- 非零/零 MOD、错误 commit、优先级冲突和 gate backpressure；
- 核心与 tile 在 MOD 尾部的一拍 valid 差异不得导致重复或漏观察；
- `STATE_CLEAR` 与硬复位的 snapshot 语义保持原合同。

### NP4B2：Pulse-Mini-L/L2 wrapper

状态：`PASS`。L/L2 均通过公开接口、原子 FEEDBACK/OBSERVE、双 commit-clear 部署、TICK 门控、不应期分账和未提交 mask 旁路等价验证；wrapper/network 形式性质仍留在 NP4B5。

预计新增：

- `pulse_mini_prune_bridge.sv`
- `pulse_mini_l_prune_wrapper.sv`
- `pulse_mini_l2_prune_wrapper.sv`
- 两个 wrapper 的 Python oracle、testbench 和定向测试

任务：

- [x] 共享 bridge 负责 FEEDBACK response 暂存、OBSERVE exactly-once、observation ID 和 commit→clear 编排。
- [x] 两个薄 wrapper 只负责实例化原核心、规范化 evidence 宽度和接入固定 gain。
- [x] 不修改 `pulse_mini_core.sv`、`pulse_mini_l2_core.sv` 或其 opcode。
- [x] TICK 接受前应用 `issue_mask`，非法、CONFIG、pending 或不应期 TICK 不虚增工作量计数。
- [x] 成功非零 FEEDBACK 恰好产生一次 OBSERVE；零反馈和所有错误响应不观察。
- [x] 上游看到 FEEDBACK 成功时，utility 更新已经成功完成。
- [x] 在 `mask_valid=0` 的旁路模式分别与裸 L/L2 核心逐事务 bit-exact。

建议最小 bridge 状态：

```text
IDLE
WAIT_FEEDBACK_RSP
ISSUE_OBSERVE
WAIT_OBSERVE_RSP
PASS_CORE_RSP
COMMIT_WAIT
ISSUE_STATE_CLEAR
WAIT_STATE_CLEAR_RSP
PASS_PRUNE_RSP
ERROR_HALT
```

### NP4B3：真正严格 `2:4` 的 `4→8→2` 测试网络

当前进度：网络级 `commit→STATE_CLEAR` 原子屏障和固定 `4→8→2` TICK/route-flush 调度均已实现为独立参数化模块；10 个 wrapper 接线与训练命令调度仍待完成。

预计新增：

- 一个公共网络调度/屏障模块；
- ENeuron、Pulse-Mini-L、Pulse-Mini-L2 三个薄模型顶层；
- 网络级 Python oracle 和 testbench。

固定拓扑：

- 输入为 4-bit 脉冲事件。
- 隐藏层为 8 个四输入 detector。
- 输出层为 2 个四输入神经元；output 0 接 detector 0..3，output 1 接 detector 4..7。
- detector→output 使用固定一逻辑 tick 注册路由，不允许组合穿透。
- 共 10 个四输入组、10 个 gate；隐藏与输出都严格 `2:4`。

任务：

- [ ] 共用一个调度/屏障实现，三个模型顶层只做核心适配，避免复制三套网络控制器。
- [x] TICK 同时启动 8 个 detector 和 2 个 output；输出层只读取 tick 开始前的 pending detector 路由。
- [x] episode 尾部 route flush 只排空输出层，不再推进隐藏层，并在完成后清 pending 路由。
- [x] 多 gate commit 先全体预检、统一启动；使用 sticky done 汇合错拍响应，并在全部自动 `STATE_CLEAR` 后统一公开。
- [ ] Host 只提供已有调制/反馈；tile 不生成标签、损失或 reward。
- [ ] 隐藏/输出 mask、读取、发射、结构节省和非活动跳过分别审计。

硬门：任何时刻都不能用现有两输入输出核替代四输入 output group。

### NP4B4：三模型端到端协同仿真

每个模型独立运行：

```text
dense warm-up
→ 本地 evidence observation
→ 一次 network PRUNE_COMMIT
→ sparse fine-tune
→ INFER
```

最低规模：

- ENeuron：20 seeds × 1000 混合事务；
- Pulse-Mini-L：20 seeds × 1000 混合事务；
- Pulse-Mini-L2：20 seeds × 1000 混合事务；
- 不能只报告三模型合计 60000 条而隐藏单模型缺口。

逐周期比对：

- 所有 gate 的 utility、mask、valid、observation/commit ID；
- 核心权重、动态学习状态、pending 和响应；
- hidden/output pending route 与 spike；
- 隐藏/输出读取、发射、结构节省、非活动和不应期跳过；
- Python/RTL 所有可见状态。

必须通过：

- 隐藏与输出的每个有效 mask 都严格 `2:4`；
- 多 gate 不出现部分可运行公开；
- 被剪权重、trace/evidence、utility 不再变化；
- 输出稀疏恢复只来自正常 MOD/FEEDBACK；
- INFER 中全部学习状态冻结；
- `issue_mask` 在核心输入和发射前形成；
- hidden/output 计数不串账；
- 未启用剪枝时 wrapper/network 不改变原核心行为。

### NP4B5：负向控制与形式检查修复

负向实现至少包含：

1. MOD/FEEDBACK 完成后才读取 evidence，必须出现漏观察或错误 utility 反例。
2. 只掩 TICK 数值、不阻止被剪连接学习历史，必须出现冻结反例。
3. 多 gate 逐个公开且允许中途 TICK，必须出现部分 mask epoch 反例。
4. 输出层仍使用两输入核，却宣称严格 `2:4`，结构检查必须拒绝。

Pulse 旧形式 harness 修复：

- [x] 改为一次启动 reset，之后 release，消除不可满足复位假设。
- [x] 增加 CAPTURE→FEEDBACK 成功可达性。
- [x] 增加 TICK/CAPTURE/FEEDBACK 实际路径 reach witness。
- [x] L/L2 分别重跑 depth 20：不变量检查通过，各找到四类成功路径 witness。
- [x] 修复前的旧 Pulse 形式日志标为失效证据，不再用于签核。

Pulse harness 当前状态：`NP4B5_PULSE_CORE_FORMAL_REPAIRED`。该结果只覆盖两个裸核心的有限深度不变量与可达性；wrapper/network 形式性质仍未完成。

wrapper/network 形式性质：

- 一次成功非零反馈对应一次且仅一次 OBSERVE；
- ENeuron MOD 与 OBSERVE 要么同时接受，要么都不接受；
- commit 成功响应蕴含所有 gate exact-two 且全部 `STATE_CLEAR` 已完成；
- commit 复合事务期间无运行命令被接受；
- INFER 不产生 OBSERVE，不改变 utility/mask/权重/学习历史；
- response 背压期间响应字段和状态稳定；
- 成功 commit 路径可达，禁止空证明。

### NP4B6：签核与进入 NP6 的条件

以下项目必须全部完成：

- [ ] ENeuron、Pulse-Mini-L、Pulse-Mini-L2 wrapper 全部通过。
- [ ] `4→8→2` 的 10 个神经元均为四输入组，隐藏/输出全部严格 `2:4`。
- [ ] 三模型端到端协同仿真全部通过。
- [ ] 修复后的 Pulse 形式检查为非空证明。
- [ ] 无剪枝旁路与原核心 bit-exact。
- [ ] 全仓回归不低于当前 318 项，且零退化。
- [ ] 机器摘要绑定所有 RTL、oracle、testbench、脚本和结果 SHA-256。
- [ ] 文档明确 NP4B 不证明物理成本与真加速。
- [ ] 用户再次批准进入 NP6。

只有以上全部通过，状态才能改为：

```text
NP4B_INTEGRATION_PASS
NP6_REVIEW_REQUIRED
```

## 6. 停止条件

出现以下任一情况，停止扩展并回到设计审核：

- 为取得 evidence 必须复制或改写神经元学习方程；
- 无法保证核心更新与 OBSERVE 的 exactly-once 对应；
- 多 gate commit 期间存在可接受的 TICK/MOD/FEEDBACK；
- 被剪连接仍能改变权重或学习历史；
- 需要修改 Host Bridge V1 才能完成 NP4B；
- 只能依赖层次路径读取内部状态；
- 形式检查不可达、仅凭“无反例”却没有成功路径；
- 现有核心旁路行为发生非预期变化。

## 7. NP6/NP7 边界

NP4B 完成前禁止运行 NP6。NP4B 通过后：

- NP6 使用已知 Vivado 2024.1 路径 `G:\Xilinx\Vivado\2024.1\bin\unwrapped\win64.o\vivado.exe`，测量单 gate、三个 wrapper 和 `4→8→2` 顶层的资源/时序增量。
- NP7 才实现共享 BRAM 格式、真实读请求跳过和共享 lane 周期下降。
- NP4B 的 `issue_mask` 与逻辑计数只证明门控位置和功能合同，不能冒充 NP7 的 BRAM、周期或功耗实测。
