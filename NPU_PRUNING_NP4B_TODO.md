# NPU 局部剪枝 NP4B 正式集成 TODO

状态：`NP4B_INTEGRATION_PASS / NP6_REVIEW_REQUIRED`

日期：2026-08-29

范围：把已签核的公共 `2:4` 控制器接入 ENeuron、Pulse-Mini-L、Pulse-Mini-L2，并在固定 `4→8→2` 网络完成端到端功能验证。本阶段只证明功能集成，不运行 Vivado，不证明共享 BRAM 真跳读、共享 lane 周期下降或功耗收益。

## 1. 当前基线

已完成：

- NP4 V1 六项接口决定已由用户批准。
- `local_prune_gate_2of4.sv` 已实现 S2-only utility、四拍确定性 top-2、一次原子严格 `2:4` 提交、读取前 `issue_mask` 和隐藏/输出分账。
- ENeuron、Pulse-Mini-L、Pulse-Mini-L2 固定 evidence gain 已冻结为 `1/2/1`。
- 三模型各完成 20 seeds × 1000 条公共控制器 Python/RTL 协同事务，共 60000 条，零差异。
- depth=32 有限检查、成功提交可达性和两个故障变体反例均已通过。
- 当前准确状态是 `NP4B_INTEGRATION_PASS`、`NP6_REVIEW_REQUIRED`；NP6 尚未启动。

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

状态：`PASS`。ENeuron、Pulse-Mini-L、Pulse-Mini-L2 均使用真正的十个四输入 wrapper；共享一拍调度器与十参与者 commit barrier 已完成网络级接线和定向验证。

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

- [x] 共用一个调度/屏障实现，三个模型顶层只做核心适配，避免复制三套网络控制器。
- [x] TICK 同时启动 8 个 detector 和 2 个 output；输出层只读取 tick 开始前的 pending detector 路由。
- [x] episode 尾部 route flush 只排空输出层，不再推进隐藏层，并在完成后清 pending 路由。
- [x] 多 gate commit 先全体预检、统一启动；使用 sticky done 汇合错拍响应，并在全部自动 `STATE_CLEAR` 后统一公开。
- [x] Host 只提供已有调制/反馈；tile 不生成标签、损失或 reward。
- [x] 隐藏/输出 mask、读取、发射、结构节省和非活动跳过分别审计。（定向网络合同已通过；长事务统计继续由 NP4B4 签核）

三模型网络状态：`NP4B3_NETWORK_PASS`。

硬门：任何时刻都不能用现有两输入输出核替代四输入 output group。

### NP4B4：三模型端到端协同仿真

当前状态：`ENEURON_PASS / PULSE_L_PASS / PULSE_L2_PASS`。

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

ENeuron 已通过 20 个独立 seed × 1000，共 20,000 个事务。剪枝后被剪权重变化 0 次、utility 变化 0 次；277 次 committed snapshot 变化全部是显式后续 SNAPSHOT 将旧非零容器值覆盖为 0，未出现 0→非零。按第 3 节冻结合同，live eligibility 不对外导出，`STATE_CLEAR` 保留 committed snapshot；因此这类 nonzero→0 容器发布不计作被剪连接继续学习。

Pulse-Mini-L 已通过 seed 201..220 各 1000 条，共 20,000 条；Pulse-Mini-L2 已通过 seed 301..320 各 1000 条，共 20,000 条。两者均逐事务比较十核、十 gate、路由、响应和分层账本，且各完成 20 次原子 commit、133,400 次 strict-exact-two 检查、266,800 次被剪 lane 冻结检查；被剪权重、evidence 和 utility 变化均为 0。

Pulse-Mini-L 逻辑账本汇总：隐藏 dense/issued/saved=`140739/94655/46084`，输出=`27770/20414/7356`，接受沿 issue-mask 检查 125,040 次，响应背压保持 15,005 拍。Pulse-Mini-L2 对应为隐藏 `113667/77786/35881`，输出 `39749/27756/11993`，issue-mask 检查 125,698 次，背压保持 14,954 拍。这些只证明功能门控和逻辑计数，不证明共享 BRAM 真跳读、实际周期下降或功耗收益。

NP4B4 状态：`PASS`。三个模型分别保留独立 20,000 条结果，不以合计 60,000 条替代单模型签核。

### NP4B5：负向控制与形式检查修复

负向控制与形式检查状态：`PASS`。四类显式错误模型和 7 项真实 RTL mutation 均被对应验收器拒绝；三个 wrapper、公共 gate 和十参与者 barrier 的 depth=32 proof/reach 与非空成功 witness 全部通过。

负向实现至少包含：

1. MOD/FEEDBACK 完成后才读取 evidence，必须出现漏观察或错误 utility 反例。
2. 只掩 TICK 数值、不阻止被剪连接学习历史，必须出现冻结反例。
3. 多 gate 逐个公开且允许中途 TICK，必须出现部分 mask epoch 反例。
4. 输出层仍使用两输入核，却宣称严格 `2:4`，结构检查必须拒绝。

四类负向控制已完成：

- [x] 事后读取 evidence 的错误模型被拒绝；接受沿锁存模型通过。
- [x] 只掩数值路径、仍更新被剪学习历史的错误模型被拒绝；完整冻结模型通过。
- [x] 十 gate 逐个公开并中途接受 TICK 的错误模型被拒绝；原子 barrier 模型通过。
- [x] 两输入 output 伪 `2:4` 被静态结构验收器拒绝；当前四输入 ENeuron 顶层通过。

Pulse 旧形式 harness 修复：

- [x] 改为一次启动 reset，之后 release，消除不可满足复位假设。
- [x] 增加 CAPTURE→FEEDBACK 成功可达性。
- [x] 增加 TICK/CAPTURE/FEEDBACK 实际路径 reach witness。
- [x] L/L2 分别重跑 depth 20：不变量检查通过，各找到四类成功路径 witness。
- [x] 修复前的旧 Pulse 形式日志标为失效证据，不再用于签核。

Pulse harness 当前状态：`NP4B5_PULSE_CORE_FORMAL_REPAIRED / PULSE_L_WRAPPER_FORMAL_PASS / PULSE_L2_WRAPPER_FORMAL_PASS`。L/L2 wrapper 均完成 depth=32 的非零 FEEDBACK→OBSERVE/utility 顺序检查，并找到成功非零反馈 witness；该结果尚未覆盖 ENeuron wrapper 或十核网络屏障。

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

- [x] ENeuron、Pulse-Mini-L、Pulse-Mini-L2 wrapper 全部通过。
- [x] `4→8→2` 的 10 个神经元均为四输入组，隐藏/输出全部严格 `2:4`。
- [x] 三模型端到端协同仿真全部通过。
- [x] 修复后的 Pulse 形式检查为非空证明。
- [x] 无剪枝旁路与原核心 bit-exact。
- [x] 全仓回归达到 359 项，零失败、零错误。
- [x] 机器摘要绑定 87 个 RTL、oracle、testbench、脚本、日志、witness 和结果文件 SHA-256。
- [x] 文档明确 NP4B 不证明物理成本与真加速。
- [ ] 用户再次批准进入 NP6。

前八项完成功能集成签核；最后一项是进入下一阶段的独立人工门。当前状态为：

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

## 8. 当前收口 TODO（2026-08-29）

本节只细化已批准的 NP4B4→NP4B6，不改变第 3 节八项架构决定。执行顺序固定为“短 tracer 校准 → 单模型长事务 → 小范围形式检查 → 全仓签核”；任一步失败先修同一步，不并行扩张证明范围。

### A. 整理当前未提交证据

- [x] A1：Pulse 随机 oracle/cosim 已独立编译并使用公开 audit 端口；形式证明文件保持独立提交边界。
- [x] A2：Pulse-L `1 seed × 64 transactions` tracer 逐事务零差异。
- [x] A3：Pulse-L2 `1 seed × 64 transactions` tracer 逐事务零差异；L/L2 使用同一驱动但独立黄金状态和结果。
- [x] A4：本阶段提交只包含 Pulse 长事务基础设施、结果和文档；形式证明文件未混入。

验收门：L、L2 的 64 事务 tracer 均为零差异；`python -m compileall -q .`、相关定向测试和 `git diff --check` 通过。

### B. 完成 NP4B4 Pulse 长事务

- [x] B1：Pulse-Mini-L 独立完成 `20 seeds × 1000`，全部指定审计统计已写入摘要。
- [x] B2：Pulse-Mini-L2 独立完成 `20 seeds × 1000`，未与 L 合并冒充单模型结果。
- [x] B3：两模型未提交 mask 旁路由既有定向测试保持 bit-exact；随机矩阵在接受沿检查 hidden/output issue mask，并分开统计不应期跳过。
- [x] B4：两个机器摘要及独立 verifier 已通过，并显式把物理加速、BRAM 跳读和功耗证明置为 0。

验收门：`PULSE_L_NP4B4_PASS` 与 `PULSE_L2_NP4B4_PASS` 必须分别出现；任一缺失时 NP4B4 保持未完成。

### C. 完成 NP4B5 非空形式检查

- [x] C1：Pulse-L wrapper depth=32 证明已复验；成功响应前 OBSERVE/utility 完成、失败零观察、双响应口背压稳定，成功 witness VCD 非空。
- [x] C2：Pulse-L2 wrapper 同强度 depth=32 证明已复验，并提供 utility 非零的成功 witness。
- [x] C3：ENeuron wrapper depth=32 harness 证明合法 MOD 与 OBSERVE 同时接受或同时拒绝，并提供公开非零 MOD 成功 witness。
- [x] C4：公共 commit barrier 的 N=10 小状态证明和真实三个顶层绑定通过；成功公开前已完成十 gate exact-two 与十核 clear。
- [x] C5：INFER 完整冻结由三模型各 20,000 条随机协同仿真逐周期证明；形式检查补齐关键控制不变量。

验收门：每类不变量同时具备“无反例”和“成功路径可达”两类证据；空证明不得签核。

### D. 完成 NP4B6 全仓签核

- [x] D1：重新运行 ENeuron、Pulse-L、Pulse-L2 各 20,000 条正式矩阵，生成三个独立结果文件。
- [x] D2：最终运行 `python -m unittest discover -v`，359 项零失败、零错误。
- [x] D3：`compileall`、8 个 `iverilog -Wall -tnull` 目标、全部 formal verifier 和 `git diff --check` 通过。
- [x] D4：生成 NP4B 机器摘要，绑定 87 个 RTL、Python oracle、testbench、形式脚本、日志、witness 与结果文件 SHA-256，并由独立 verifier 校验。
- [x] D5：同步全部规划文件和项目报告，并写入 `NP4B_INTEGRATION_PASS / NP6_REVIEW_REQUIRED`。
- [x] D6：提交 NP4B6 签核后停止；等待用户再次批准 NP6，不调用 Vivado。

### E. 建议提交边界

1. `test: add Pulse pruning network random cosim`：A、B 的 oracle、driver、tests 和两模型长事务结果。
2. `test: prove Pulse pruning wrapper atomicity`：先独立签入已经完成的 C1/C2，避免与尚未实现的 C3 混成一个不可审计提交。
3. `test: prove ENeuron pruning wrapper atomicity`：C3 的 harness、脚本、日志、witness 与 verifier。
4. `test: prove pruning network commit barrier`：C4/C5 的抽象证明、真实顶层绑定和控制级冻结检查。
5. `docs: sign off NP4B pruning integration`：D 的全仓结果、机器摘要和文档状态。

## 9. 最终执行记录（2026-08-29，已完成）

本节记录第 8 节的实际执行结果，不改变已批准的八项架构决定。P0、P1、P2/P3、P4 和 P5 均已形成独立证据提交；最终总 verifier 通过。NP6 仍须用户另行批准，本阶段未运行 Vivado。

### P0：固化 Pulse-L/L2 已完成证据

- [x] P0.1：复验两个独立 verifier，并对两个 verifier 执行 Python 编译检查。
- [x] P0.2：只签入正式 harness、`.ys`、runner、verifier、两份正式 `.log` 和两份非空成功 witness。
- [x] P0.3：明确排除 `*_cex.vcd`、`*.tmp.log` 和其他失败/中间产物；被 `.gitignore` 忽略的四份正式证据使用显式文件名强制加入，不修改全局忽略规则。
- [x] P0.4：对源码、脚本和文档执行 `git diff --check`；Yosys 原生日志保留工具生成的 ASCII 横幅行尾空格并以 SHA-256 保真。提交为 `test: prove Pulse pruning wrapper atomicity`。

P0 验收标记：

```text
PULSE_PRUNE_WRAPPER_FORMAL_CONTRACT_PASS
PULSE_L2_PRUNE_WRAPPER_FORMAL_CONTRACT_PASS
```

P0 状态：`PASS`。Yosys 0.56 新鲜重跑；Pulse-L/L2 正式日志分别为 551,887/580,073 bytes，成功 witness 分别为 15,561/16,787 bytes。两套证明各自包含 invariant proof 和非零反馈 reach，不共享 witness。

### P1：ENeuron MOD/OBSERVE 原子性形式闭环

- [x] P1.1：先写有限深度 harness 与失败敏感断言；不修改神经元方程，不增加综合接口。
- [x] P1.2：用验证专用 bind/内部断言证明：合法非零 MOD 在接受沿上，核心 MOD 与 gate OBSERVE 同拍接受；任一侧不能接受时，两侧均不得部分启动。
- [x] P1.3：用公开状态证明事务级结果：成功 `done` 前 utility 与 observation ID 已更新，pending snapshot 已消费；错误模式、错误 ID、重复 ID 和 gate 反压不得产生部分更新。
- [x] P1.4：证明在途事务阻止新的运行/剪枝事务；剪枝响应背压期间 status、ID、mask 和相关状态稳定。
- [x] P1.5：成功 witness 必须从公开命令走完 `TRAIN→非零 snapshot→非零 MOD→utility 非零变化→成功 done`，不得直接假设内部 snapshot 或 utility 非零。
- [x] P1.6：生成独立 runner、proof/reach 脚本、正式日志、非空 witness 和 fail-closed verifier。
- [x] P1.7：精确暂存 P1 文件和四份规划文档，强制加入正式 `.log`/成功 witness，排除 `*_cex.vcd` 与临时产物；复核 staged diff 后独立提交 `test: prove ENeuron pruning wrapper atomicity`。

P1 验收门：同一性质同时具备“不变量无反例”和“真实成功路径可达”；只凭外部最终状态不得宣称已经证明内部同拍接受。

P1 状态：`PASS`，提交 `c811bcf`。Yosys 0.56 depth=32 proof 无反例；公开路径 witness 由 TRAIN TICK 产生非零 eligibility，经 SNAPSHOT 后执行非零 MOD，utility 与 observation ID 在成功 done 前更新，pending snapshot 被消费。正式日志 862,510 bytes，witness 24,069 bytes。

### P2：十参与者 commit/clear barrier 组合证明

- [x] P2.1：直接实例化真实 `local_prune_commit_barrier.sv`，固定 `N_GATES=10`；参与者响应采用小状态抽象，不展开十个完整神经元。
- [x] P2.2：证明预检失败时十路 gate 全不启动；安全提交时十路同拍启动且 ID 一致；每路 gate/clear response 最多接受一次。
- [x] P2.3：证明收齐十个成功 gate response 前不启动 clear，十路 clear 同拍启动，收齐十个成功 clear response 前不公开成功。
- [x] P2.4：证明成功只增加一次 epoch；commit 全程 `runtime_blocked=1`；响应背压期间 status、ID、40-bit mask 和 epoch 稳定。
- [x] P2.5：exact-two 采用组合证明：公共 gate 的既有证明负责 `ST_OK commit→mask 恰有两位`；barrier harness 只假设成功 gate 响应满足该合同；总 verifier 必须同时绑定 gate 与 barrier 两组证据。
- [x] P2.6：成功 witness 固定十参与者，允许 gate/clear 错拍返回，并覆盖 `10 gate done→10 clear done→success→epoch+1→背压保持→消费后解除阻塞`。
- [x] P2.7：三个真实 `4→8→2` 顶层都做 elaboration/结构检查，确认实例化同一公共 barrier、10 个四输入 wrapper、两组输出路由无重叠且覆盖 detector 0..7。
- [x] P2.8：三个真实顶层用定向/随机协同仿真证明 `runtime_blocked` 期间 `tick_ready`、`route_flush_ready`、`host_cmd_ready` 均不接受命令；单纯编译不能替代该性质。

P2 验收门：抽象环境假设必须在机器摘要中列出来源；不得把 barrier 自身未检查的 exact-two 当作无条件结论。

P2 状态：`PASS`。公共 gate proof/reach/verifier 与 N=10 barrier proof/reach/verifier 已组合绑定；三个真实顶层均通过 `iverilog -Wall` elaboration 和 runtime-ready 定向合同检查。barrier witness 覆盖错拍 gate、响应背压和消费后解除阻塞。

### P3：INFER 冻结与负向控制补强

- [x] P3.1：形式检查只覆盖控制级不变量：INFER 不产生 OBSERVE、不接受 PRUNE_COMMIT，被拒绝命令不改变 utility、mask、observation/commit ID。
- [x] P3.2：完整学习状态冻结由冻结点 `33e0aed` 后的三模型各 20,000 条随机协同仿真逐周期比较通过，不展开十个完整核心做大规模 SAT。
- [x] P3.3：把前三类 Python 玩具负向控制升级为至少一个真实 RTL mutation/接线变体检查，确认验收器能抓到“事后读取 evidence”“只掩数值路径”“部分 epoch 可见”；第四类结构检查扩展到 Pulse-L/L2 顶层。
- [x] P3.4：所有 mutation 必须“错误版本失败、正式 RTL 通过”，且错误版本不得进入正式 RTL 文件。

P3 状态：`PASS`。7 项负向控制全部先拒绝真实源码 mutation、再接受正式 RTL；相关 35 项 wrapper/network 回归通过。完整三模型 INFER/被剪学习状态冻结已由 P4 新鲜 60,000 条独立矩阵签核。

### P4：冻结源码后重跑正式签核

- [x] P4.0：先完成 P1.7；记录冻结后的 HEAD 和工作树状态。P1 已提交为 `c811bcf`，允许进入 P4.1。
- [x] P4.1：冻结 RTL、oracle、testbench、runner 与形式脚本；冻结点为 `33e0aed`，seed 固定为 ENeuron `101..120`、Pulse-L `201..220`、Pulse-L2 `301..320`，每个 seed 恰好 1000 条事务。
- [x] P4.2：新增 ENeuron 正式 runner、独立结果文件和 fail-closed verifier；冻结点后新鲜重跑三模型各自 20,000 条，三个摘要 verifier 全部通过。
- [x] P4.3：按 runner→verifier 顺序新鲜重跑 ENeuron wrapper、Pulse-L wrapper、Pulse-L2 wrapper、公共 gate、十参与者 barrier 的全部 proof/reach；五个 runner 与五个独立 verifier 均通过。
- [x] P4.4：最终完整重跑 `python -m unittest discover -v`，实际 `Ran 359 tests in 378.291s`，零失败、零错误。
- [x] P4.5：`python -m compileall -q .` 通过；公共 gate/barrier、三个 wrapper、三个 `4→8→2` 顶层共 8 个目标通过 `iverilog -Wall -tnull`；人工文件 diff-check 通过。
- [x] P4.6：三份模型结果、全部新鲜形式证据、Python 3.14.2、Icarus 12.0、Yosys 0.56、命令、退出码和时间均写入总证据索引；原始 Yosys 日志只做标记与哈希验证，未清洗工具生成空白。

P4 硬门：三模型必须分别出现 20,000 条通过结论；任一模型、任一 verifier、任一编译或全仓测试失败，立即停在 P4 修复，不生成总签核摘要。

### P5：fail-closed 总摘要、文档与停止点

- [x] P5.1：新增 `np4b_signoff_summary.json` 和独立 `verify_np4b_signoff.py`；固定检查三组 seed、各 20,000 事务、精确统计/恒等式、零差异、INFER 冻结、strict `2:4`、epoch、背压和旁路 bit-exact。
- [x] P5.2：摘要记录 Python/Icarus/Yosys 版本、形式深度、完整 runner 命令与退出码、执行时间、实际 unittest 数量、正式 witness 数量和字节数。
- [x] P5.3：SHA-256 精确绑定 87 个 RTL、oracle、testbench、runner、tests、formal harness/脚本、正式日志、成功 witness、结果文件和总 verifier 自身；键集合缺失、多余、文件陈旧或出现 cex/tmp 证据均失败。
- [x] P5.4：总 verifier 重算逻辑账本恒等式；这些计数只代表功能级访问/发射门控，不代表物理 BRAM 跳读、墙钟周期、功耗或 Vivado 时序。
- [x] P5.5：同步 `NPU_PRUNING_NP4B_TODO.md`、`task_plan.md`、`progress.md`、`findings.md` 与 `PROJECT_REPORT.md`，只引用证据索引，不复制整份日志。
- [x] P5.6：所有硬门通过后提交 `docs: sign off NP4B pruning integration`，最终状态只写入：

```text
NP4B_INTEGRATION_PASS
NP6_REVIEW_REQUIRED
```

- [x] P5.7：提交后停止，等待用户再次批准 NP6；此前不调用 Vivado，不声称物理周期、BRAM 访问或功耗收益。

P5 状态：`PASS`。权威机器入口为 `python verify_np4b_signoff.py`，最终标记为：

```text
NP4B_SIGNOFF_VERIFY_PASS models=3 transactions=60000 tests=359 formal=5 next=NP6_REVIEW_REQUIRED
```

### 当前批准后执行顺序

```text
P1.7 证据入库
  → P4.1 冻结源码与 seed
  → P4.2 三模型各 20,000 条
  → P4.3 全部形式 runner/verifier
  → P4.4/P4.5 全仓回归与编译
  → P4.6 证据索引
  → P5 fail-closed 总摘要与文档签核
  → NP4B_INTEGRATION_PASS
  → NP6_REVIEW_REQUIRED（停止）
```

建议只保留两个后续提交边界：

1. `test: prove ENeuron pruning wrapper atomicity`：仅 P1 正式证据和同步规划记录。
2. `docs: sign off NP4B pruning integration`：P4/P5 新鲜结果、总摘要/verifier 和最终文档；若 P4 需要修改 RTL 或测试逻辑，则先单独提交修复，再从冻结点重跑 P4。

### 执行顺序与并行边界

```text
P0 Pulse 证据固化
  ├─ P1 ENeuron wrapper 形式证明
  └─ P2 barrier 形式证明与顶层绑定
       \                    /
        └──── P3 冻结补强 ─┘
                  ↓
              P4 全量重跑
                  ↓
              P5 总签核
```

P1 与 P2 可并行开发，但 P4 必须等待 P0→P3 的源码和脚本全部冻结。任何阶段出现空 witness、mutation 未被捕获、三模型任一零差异失败或测试数低于 318，立即停在当前阶段修复，不向后生成签核摘要。
