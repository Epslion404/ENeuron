# G4 V3 T3 执行规格（审核稿）

日期：2026-08-13（星期四）  
状态：`REVIEW_REQUIRED`  
适用范围：固定 `4 -> 2 -> 2`、no-WTA 的 Python 能力验证 P0-P4

## 1. 目标与边界

本规格把已批准的 V3 六项架构决策展开为可执行合同。它不修改神经元学习方程，不增加 WTA，不扩大权重范围，不把 Teacher、Hybrid、纯全局 Reward、feedback-alignment、Python 或 RTL 结果互相代偿。

T3 只复用数字网络的逐 tick 动力学、eligibility 快照和延迟 commit 接口。正式数据、严格解码、训练权限、负对照、统计和结果 manifest 放入新的 G4 模块；历史 `HostTrainingController` 只保留为旧实验代码，不能进入正式证据链。

正式实现前必须先批准本文的 12 项二级冻结决策。批准后按测试先行拆分实现任务；批准前不编写训练 runner，不修改 RTL 或冻结的神经元方程。

## 2. 当前已确认的阻塞事实

1. 当前完整 `DigitalSNN2Layer.inference()` 会在 episode 开始时清除 pre/post trace、eligibility 并恢复 threshold，因此“调用推理前后全部状态逐字段不变”当前为 `FAIL`。这不自动等于实现错误，但证明现有证据只能支持“复位后的推理区间冻结”，不能支持更宽的全调用等价表述。
2. 历史 `reward_modulator(label, result)` 读取 label 和神经元活动；历史 hybrid 又按 action 定向输出调制。二者都不是 P3 的纯全局 reward。
3. 历史 `NetworkEpisode.prediction` 在非零平局时偏向类别 0。P0-P4 的计分和动作生成必须从 `output_spikes` 重新调用 `strict_decode()`；禁止读取该字段作为正式结论。
4. Temporal 只使用输入通道 0/2，12 个权重中只有 8 个实际影响该任务。既有结构化探针在 Train 32 上最好为 `25/32 = 78.125%`、coverage 100%；这是明确容量风险，但不是数学不可能证明。
5. 当前调制 commit 会把任意非零幅值压成符号。因此不改方程/RTL时，feedback-alignment 只允许 `{-1, 0, +1}` 系数。

本文所有确定性 shuffle、候选生成和随机统计统一使用 `g4_rng_v1`，禁止各模块自行定义随机算法：

1. `key = SHA256(canonical_json(domain_payload))`，payload 必须包含 `master_seed`、`purpose` 和该用途的全部域标签。
2. 第 `counter` 个 64-bit 字为 `u = be64(SHA256(b"g4-rng-v1\0" || key || counter_be64)[0:8])`，counter 从 0 单调递增。
3. 取模 `m` 时令 `limit = 2^64 - (2^64 mod m)`；仅接受 `u < limit`，返回 `u mod m`，否则继续消耗 counter。
4. Fisher-Yates 从 `i=n-1` 递减到 1，并用上述原语取 `j in [0,i]`。

golden vector：当 payload 为 `{"master_seed":5130818532108422994,"permutation_index":0,"purpose":"evaluation_permutation","split":"iid_test","task":"temporal"}` 时，key 为 `332db7a88aeaf061f2494291b4efcc642f2eea548686f04362e4cec3dde67d73`；置换 `[0..7]` 得 `[5,4,7,2,1,0,3,6]`，字节序列 SHA-256 为 `a7da4409e5116c3f178eac7604aa9686e92eed1bb58a6dc31d9b7c9f40b83f06`。

## 3. 十二项二级冻结决策

### D1：拆分 P0a

P0a 拆成两个互不代偿的硬门：

- `P0a-pretrain`：三任务生成器/validator、split/hash/seed 隔离、类别或组合平衡、64-tick payload、20 个 final 初始化独立、EP_START 基线转换与其后推理区间冻结，以及源码哈希。
- `P0a-postrun`：evaluation-label permutation、nuisance-only、结果新鲜度、逐 seed 原始记录和统计复算。

执行顺序固定为 `P0a-pretrain -> P0b -> direct-weight/P1-P3 -> P0a-postrun`。`P0a-postrun` 未通过时，准确率只能保留为未签核测量，不得形成能力结论。

推理冻结拆成两个可审计区间，避免把有意的 episode 初始化误报为学习：

- `EP_START` 前后逐字段白名单如下；除表中字段外，全部网络/神经元字段必须 bit-exact 不变：

| 字段 | INFER EP_START 后基线 |
|---|---|
| network `active_episode_id` | 请求的 episode ID |
| network `episode_active` | `True` |
| network `episode_train/train_enable` | `False` |
| network `episode_label` | 仅 evaluator metadata；不得进入 model adapter/网络执行，正式 adapter 内固定为 `0` |
| network `hidden_counts/output_counts` | 全 0 |
| network `pending_hidden` | 空 tuple |
| each neuron `v/current/refractory/spike_count` | `reset_value/0/0/0` |
| each neuron `spike_ticks` | 空序列 |
| each neuron `pre_trace/post_trace/eligibility` | 对应维度的全 0 |
| each neuron `threshold` | `base_threshold` |

`weights`、`weight_epoch`、pending commit/snapshot、commit 次序元数据、`ops/saturation_count`、WTA 指针、`last_episode_*` 和 `next_episode_id` 不得被 EP_START 改写；显式 episode ID 的正式 adapter 不允许隐式推进 `next_episode_id`。
- `EP_START` 接受后到 `EP_END` 完成：weights、pre/post trace、eligibility、eligibility snapshot、threshold、pending commit 元数据和 weight epoch 必须逐字段完全不变；仅动态推理状态可变化。

整笔 INFER 的持久训练状态硬门为：weights、eligibility snapshot、pending commit 元数据和 weight epoch 在调用前后完全相等。INFER 只允许在没有未提交 snapshot/commit 的协议状态进入，防止 episode 初始化丢弃尚未结算的信用。

适配器必须显式维护信用状态机，且禁用 legacy `commit_id=None` 路径：

```text
QUIESCENT -> TRAIN_ACTIVE -> AWAITING_CAPTURE -> PENDING_COMMIT -> QUIESCENT
```

| API | 合法源状态 | 成功目标状态 |
|---|---|---|
| `TRAIN_EP_START` | `QUIESCENT` | `TRAIN_ACTIVE` |
| `TRAIN_EP_END` | `TRAIN_ACTIVE` | `AWAITING_CAPTURE` |
| `CAPTURE(commit_id)` | `AWAITING_CAPTURE` | `PENDING_COMMIT` |
| `MOD_COMMIT(commit_id)` | `PENDING_COMMIT` | `QUIESCENT` |
| `INFER` | `QUIESCENT` | 完成后回到 `QUIESCENT` |
| `ABORT/STATE_CLEAR` | 任意非执行中状态 | `QUIESCENT` |

非法 API 必须拒绝且全状态原子不变。`ABORT/STATE_CLEAR` 清除 active episode、`last_episode_train/id`、全部 pending commits/snapshot、`next_commit_to_apply` 和本 run 的 capture metadata；D12 的 hard reset 还把 `max_captured_commit_id/weight_epoch` 恢复到初态。正常任务交接不得调用该清除路径，而是使用 D5 `P4TransferState` 延续已提交 commit 元数据。

因此第一版不改变现有学习方程，也不要求跨 episode 保留 trace/eligibility/threshold；需要修正的是 API 前置条件、状态分类、测试拍摄点和结论措辞。若实际探针发现 `EP_START` 改动超出白名单，才进入 Python/reference/RTL 修复并重新完成 bit-exact、formal 和 Vivado 签核。

### D2：evaluation-label permutation 硬门

每个被声明通过的任务、模式和最终 test split，都固定预测与 decision mask，只置换平衡标签 10000 次。

- 每个 `(task, split, permutation_index)` 只生成一份公共置换；派生键不得包含 `model_seed` 或训练模式。20 个 model seeds 和 direct-weight 见证都复用同一序列。
- 每个 split 增加独立整数 `sample_index`，validator 必须断言 generator 输出顺序中的该字段恰好为 `0..N-1`；字符串 `sample_id` 继续只作 provenance。公共置换按 `sample_index` 对完整平衡标签向量执行 `g4_rng_v1` Fisher-Yates。这是正式三任务 schema 的 breaking change，实施时必须重生成 Temporal manifest。
- 20-seed cohort：同一 `permutation_index` 下先计算各 seed 的指标，再求 cohort mean，形成 10000 个零分布均值。共享数据的 20 次测量不得被当作 20 份独立标签置换。
- 单模型 direct-weight：使用同一公共置换序列，直接形成该模型的 10000 个零分布值。
- 硬门：观测 overall accuracy 必须严格大于零分布 type-7 95th percentile，且一侧加一修正 p-value `p = (1 + count(null >= observed)) / 10001 <= 0.05`。
- conditional accuracy 使用固定的非 abstain 子集重复同一计算；coverage 为 0 时 conditional 记为 `null`，不能通过任何 conditional 门槛。

置换器必须记录绑定 `sample_index`、label 和 split manifest SHA-256 的 canonical label vector、10000 个 permutation digest 和总序列 SHA-256；标签计数、样本顺序或任一 digest 不一致时直接失败。

### D3：P4 六排列的 seed 内聚合

每个 model seed 对 6 个任务排列分别产生完整 `R[i,j]`。对排列 `pi=(pi_1,pi_2,pi_3)`，冻结：`R[0,j]` 为同一初态、未训练时任务 `j` 的准确率；`R[i,j]` 为完成第 `i` 阶段训练后任务 `j` 的准确率。每个矩阵点都在训练状态 snapshot 的 clone 上只读评估，禁止让评估改变后续训练实例。

每个排列先计算：

- `ACC = (R[3,pi_1] + R[3,pi_2] + R[3,pi_3]) / 3`。
- `BWT = ((R[3,pi_1]-R[1,pi_1]) + (R[3,pi_2]-R[2,pi_2])) / 2`。
- `FWT = ((R[1,pi_2]-R[0,pi_2]) + (R[2,pi_3]-R[0,pi_3])) / 2`。

然后先在 seed 内对 6 个排列做算术平均，再把 10 个 seed 作为唯一统计单位：

- 每任务最终 IID accuracy：该任务在 6 个排列末态 accuracy 的均值。
- 每任务遗忘：只统计该任务不是最后学习的 4 个排列，令 `k_j` 为该任务刚学完的阶段，计算 `max(0, R[k_j,j]-R[3,j])` 后求均值。后续提升不抵消遗忘，两个最后学习且恒为零的排列不进入该均值。
- ACC/BWT/FWT：使用上式逐排列计算，再对 6 个排列求均值；FWT 只报告，不设第一版硬门。
- seed 通过：三个任务最终均值均 `>=75%`，三个任务平均正向遗忘均 `<=10pp`，`ACC>=75%`，`BWT>=-0.10`。
- cohort 通过：至少 `8/10` seeds 通过。bootstrap 只重采样 10 个 seed。

最差排列、每个任务最差末态和最大正向遗忘必须报告，但第一版不额外增加 worst-order 硬门。

### D4：P4 task context 合同

P0-P3 的原始 payload 保持 64 tick。P4 使用 `g4_task_context_v1`，episode 固定扩展为 80 tick：

- context 区域为 tick `0..15`，payload 原样右移 16 tick，占 `16..79`。
- 三任务通道固定为：Spatial=`0`、Temporal=`1`、XOR=`2`。
- context 包含 4 个同任务 symbol，起点固定为 `[0, 4, 8, 12]`；每个 symbol 使用 P0b 已冻结的全局 burst width `B`。
- context 不含 label、组合、sample、model seed 或训练模式信息；通道 3 保留。
- P4 不重新选择 B。contextized Calibration 只验证冻结 B 的活动和高层/reference 等价。
- context 后的完整 80-tick `input` 计算正式 `input_hash`；同时记录原 64-tick `payload_input_hash`，建立一一映射。

隐藏层到输出层固定有一拍路由延迟，因此 context 来源的输出可能持续到 tick 16。正式 accuracy/coverage 只累计 tick `17..79` 和 `EP_END` 的 route flush；tick `0..16` 只用于 context-origin 活动审计，不进入分类。validator 必须从 `(task, B, 64-tick payload)` 精确重放完整 80-tick 输入，同时检查 context hash 和原始 payload hash，禁止 context 包装掩盖跨任务 train/test 重复。

contextized Calibration 使用同一正式窗口，逐任务及每个类别/组合检查 output-active `>=95%`，并要求高层/reference hidden/output spike count 完全一致。失败时对应 P4 为 `NOT-RUN/FAIL`，不得重新选择 B。

P4 对应模式进入持续学习前，必须用完全相同 context 重新运行完整单任务前置门，而不只是 accuracy：包括 activity/coverage、CI、evaluation permutation、training-label shuffle，以及 P3 的四组 paired improvement。该产物命名为 `context_admission_baseline`，按 D11 的 Validation checkpoint 规则选择；另生成 `p4_budget_matched_single_endpoint`，跑满预算且不回滚，只用于遗忘和 joint 对照。single-task、顺序训练、`R[i,j]` 和 joint upper bound 必须使用相同 context、B 和数据。

`g4_task_context_v1` 使用独立 manifest，并验证唯一映射 `(context_version, task, B, payload_input_hash) -> input_hash` 与完整 80-tick exact replay。三任务所有 train/validation 选择集与三任务 IID/OOD final test 联合集的 payload hash 必须互斥；任意跨任务重复直接失败。若 P5 未执行同一 80-tick continual cohort，P4 结论只能声明 Python/reference 持续学习，不能声明 RTL 持续学习闭环。

### D5：no-replay 的可执行权限隔离

P4 主训练采用 broker/worker 分进程边界：

- 父进程 `NoReplayDataBroker` 独占全部生成器、master seed、样本和标签。
- 每个任务用 `sys.executable` 的绝对路径启动新 worker，参数固定为 `-I -S -u`；`shell=False`、`close_fds=True`、`cwd` 为新建临时目录、环境变量使用最小 allowlist，Windows 上设置 `CREATE_NO_WINDOW`。本机 Python 3.14.2 已确认 `-I` 仍加载全局 `site-packages`，因此缺少 `-S` 必须失败。
- worker 固定执行受审计 bootstrap，再由 bootstrap 加载内容寻址、自包含的单文件 model-only bundle；禁止把 bundle 直接作为 Python 入口，也禁止导入旧 `network_sim.py/neuron_sim.py` 中的 trainer 或数据 helper。本机实测 `-I -S` 不把脚本目录加入 `sys.path`，直接运行旧多文件模型会因同目录导入失败；因此禁止靠 `PYTHONPATH` 或全局安装补路径。bootstrap 与 bundle 的规范化绝对路径、文件清单和 SHA-256 均写入冻结配置；broker 在每次启动前验证这些值以及仅驻留 broker 的 HMAC-SHA256。这里证明单次运行中的完整性，不把 HMAC 表述为第三方代码签名。
- IPC 为 `uint32_le length + canonical JSON bytes` 的逐帧流，每帧只包含一个 JSON object，并按模式使用独立 schema。Reward worker 只接收当前输入/允许状态，先输出 action，随后只接收标量 reward，绝不能接收 label；Teacher 与 Hybrid feature worker才允许接收当前样本标签。
- 固定 bootstrap 先预载冻结清单中的必要标准库，再在读取或编译任何 model bundle 字节前安装 `sys.addaudithook()`；bundle 源码不得含 `import`，所需标准库对象由 bootstrap 通过固定 globals 白名单注入。加载器状态机固定为 `LOADING_VERIFIED_BUNDLE -> SEALED`：在 `LOADING_VERIFIED_BUNDLE` 中，只允许读取配置中唯一的 bundle 规范化绝对路径，只允许一次 `compile(bundle_bytes, bundle_path, "exec")`，且 audit hook 必须逐字节复算 SHA-256 并匹配冻结值；随后只允许对该次返回的 code object 发生一次外层 `exec`。hook 在放行该 `exec` 事件时先原子切到 `SEALED`，因此 bundle 第一条语句执行前加载窗口已经关闭。`SEALED` 中拒绝全部 `compile/exec/import`，也拒绝 network、subprocess 和 ctypes；任何额外 bundle 读取、第二次 compile/exec、路径/字节/code-object 不匹配或状态回退都立即终止 run。普通文件读取只允许三个规范化绝对根：由 `sys.base_prefix` 验证出的只读 Python stdlib 根、已验哈希且只读的 bundle 根、该 worker 的临时目录；其中 `site-packages`、用户 site、workspace 和其他驱动器均拒绝。manifest 记录 bootstrap/bundle 哈希、预载模块清单、注入 globals 清单、状态迁移和全部拒绝事件。audit hook 只称为 trusted-worker 的 fail-closed 审计断言，不宣称是抵抗恶意本机代码的安全沙箱。
- broker 是单调 push-only 状态机：`PRE_TASK -> ACTIVE(task) -> REVOKED(task) -> ACTIVE(next_task)`。worker 不提供 sample request API；broker 只能按预注册 `RandomPlan` 主动推送当前任务帧。离开任务后，当前 train-vault capability 永久撤销且不可重新进入；跨阶段评估使用独立只读 eval-vault，其输出不得进入 worker。
- 离开任务后销毁 worker 和当前任务缓冲。下一任务使用新进程，只接收上一阶段允许保留的网络状态。
- 允许跨任务保留的 canonical `P4TransferState` 精确限定为：12 个 signed 4-bit 权重；各神经元当前 trace 的 unsigned 8-bit 值、eligibility 的 signed 12-bit 值、threshold 的 unsigned 5-bit 值；32-bit `weight_epoch`；1-bit `last_commit_valid`、16-bit `last_commit_id/next_commit_id`；256-bit `random_plan_sha256`、32-bit plan cursor、2-bit task index和预注册的定宽诊断计数器。任务交接时必须为 episode/tick idle、`snapshot_valid=false`、无 pending commit，且 `next_commit_id=0`（无历史提交）或 `last_commit_id+1`；不得在同一 sequential run 的任务边界重置 commit 元数据。禁止无界 Python int、自由字符串、dict 扩展字段或可变长度容器进入该 schema；canonical 编码固定为字段顺序明确的无空白 JSON 十进制整数/小写十六进制 digest。
- 禁止保留样本、标签、prediction、逐 episode/逐样本的 eligibility 或 modulation 历史、输入哈希列表或其可逆编码；“当前架构值”与“历史序列”必须使用不同 schema 字段，validator 拒绝任何可变长度历史容器。
- 父进程 evaluator 可在阶段后只读评估全部任务，但其预测和标签不得返回训练 worker。

manifest 必须记录 broker 请求/拒绝日志、启动参数、环境 allowlist、worker 包清单/哈希/HMAC、IPC schema、允许状态 schema 和每次进程生命周期。本合同证明受审计 runner 的 no-replay，不宣称能抵抗任意恶意本机原生代码。

### D6：负对照配对合同

每个任务/模式/model seed 的主实验与负对照共享同一初态和确定性随机流：

- `untrained`：克隆主实验训练前的完整初态，不做任何 MOD_COMMIT。
- broker 在启动前生成不可变 `RandomPlan`，训练循环不得自行调用 RNG。先用 payload `(model_seed, mode, task, stage, local_epoch, purpose="training_order")` 对该 epoch 的 `sample_index` 列表执行 `g4_rng_v1` Fisher-Yates；该步骤不读取 `sample_position/sample_id`。选中样本后，再以 `(model_seed, mode, task, stage, local_epoch, sample_position, sample_index, sample_id, purpose="exploration"|"candidate_action")` 派生样本级随机量。
- 每条计划记录至少包含 `mode, task, task_order, stage, local_epoch, sample_position, sample_index, sample_id, exploration_uniform, candidate_action`。`task_order` 只作 provenance，不进入随机 payload；`random_core_sha256` 对去除 `task_order` 后的计划计算，`random_plan_sha256` 对完整计划计算。因此六排列共享同一任务局部随机核心，但各自完整计划仍可审计。
- `training-label-shuffle`：克隆同一初态，并接收与主实验字节完全相同的 `RandomPlan`；复用相同 epoch 输入顺序、checkpoint、探索 uniform 和候选 action，唯一变化是训练标签。两者必须记录相同 `random_plan_sha256` 和 canonical `initial_state_digest`。
- 每个 `(task, mode, model_seed)` 使用 1 个固定的平衡 `sample_index -> shuffled_label` 映射，并跨全部 epochs 复用。attempt 从 0 到 1023 依次进入 `g4_rng_v1` payload；若恒等或标签改变率 `<50%` 就重派生，1024 次仍无合格映射则 run 失败。manifest 记录全部 attempt digest 和选中 attempt。
- evaluation permutation 不重跑网络，固定主实验预测和 coverage 做 10000 次标签置换。
- Temporal order-destroy 与 nuisance-only 复用同一 skeleton/sample index，保持事件数和时间域配对。

P4 六排列的初态对同一 `(mode, model_seed)` 完全相同。canonical `initial_state_digest` 必须覆盖：12 个 signed 4-bit 权重、四核 trace/eligibility/threshold、动态状态基线、WTA 开关/指针、episode 状态、pending snapshot/commit、commit 次序元数据和 weight epoch；整数按上文硬件位宽编码，并断言状态为 `QUIESCENT`。任务局部随机核心不含任务在排列中的位置，避免把次序效应与初始化或探索噪声混淆，同时保持不同 model seeds 的训练顺序和探索流独立。

所有 paired bootstrap 都以同一 model seed 的主实验与对照差值为输入。

### D7：direct-weight search 预算与容量门槛

搜索只读取 Train 和 Validation；选定权重后 IID/OOD 各评估一次，禁止回到搜索。

Temporal：缓存每个有效隐藏权重在 Train+Validation 上的完整逐 tick spike sequence 签名，禁止只用 spike count；覆盖全部唯一双隐藏签名组合，并对每组覆盖全部 `225 x 225` 输出读出器。若单隐藏唯一签名数为 `U`，有序双隐藏组合数必须严格为 `U^2`，输出读出检查数必须严格为 `U^2 * 225^2`。等价签名只计算一次，但 manifest 必须记录原权重覆盖数、`U`、组合数和全部读出检查数。

Temporal 的双隐藏签名按 `(hidden_0_signature, hidden_1_signature)` 有序组合；隐藏身份会改变输出层输入，因此禁止在没有同时变换输出权重并证明等价时使用交换商。

Spatial/XOR：每任务固定 5 个 search seeds，每 seed 20000 个全局去重候选，共 100000 个唯一 12-weight 向量。`k` 在每个 search seed 内从 0 重新开始。分层置换的 `g4_rng_v1` payload 精确为 `purpose="direct_search_stratum", task, search_seed, block, coordinate`；邻域和回退路径不使用 RNG。确定性算法固定为：

```text
for search_seed in [0, 1, 2, 3, 4]:
    生成 4096 个未见分层候选，完整评分该批次，再更新全局 top-64
    从该 top-64 生成 15904 个未见邻域候选，完整评分该批次，再更新 top-64
```

对分层候选编号 `k`，令 `block=k//15`、`slot=k%15`；坐标 `c` 的值等于由上述 payload 派生的 `[-7..7]` `g4_rng_v1` Fisher-Yates 置换的第 `slot` 项。这样每连续 15 个候选在每个坐标上恰好覆盖 15 个值；重复候选继续消耗 `k`，直到批次达到规定的唯一数量。邻域中心按当前排序键排列；先枚举单坐标，再枚举双坐标。单坐标顺序为 `center_rank -> coordinate -> delta`；双坐标顺序为 `center_rank -> (coordinate_a,coordinate_b) 字典序 -> (delta_a,delta_b) 字典积`。delta 固定为 `+1,-1,+2,-2,...,+14,-14`，越过 `[-7,7]` 的值跳过。若邻域未凑满预算，回退到 `[-7,7]^12` 的字典序未见向量。候选必须在完整固定批次评分后才能更新 top-64，禁止边评分边改变生成中心。

Spatial、search seed 0 的首 10 个分层候选 golden vectors 固定为：

```text
[-3,-3,-2,-7, 0,-6, 7,-2,-7, 1, 0, 0]
[ 0, 6, 7,-3,-4,-5,-6, 4, 2, 7, 5, 4]
[ 4, 2,-3,-4, 5, 7, 3, 5,-3, 3, 7, 2]
[-1,-6,-4,-6, 4, 0,-1,-3, 4, 5,-4,-4]
[ 6, 7, 6, 5, 7, 5,-3,-4, 0,-5, 2,-2]
[ 2, 3,-5,-2,-5, 1, 1, 6, 7, 0,-7, 7]
[ 7,-7,-1, 4,-7,-7, 2, 1,-2, 4, 6,-3]
[-6, 0,-7, 6,-6,-4,-7,-1,-1,-6,-1,-1]
[-7,-5, 4, 1, 3, 3,-4, 7,-4,-2, 4,-7]
[-2,-1, 0, 3, 1,-3, 0,-6,-5, 6, 1, 5]
```

排序键固定为降序 `Validation overall accuracy, Validation coverage, Train overall accuracy, Train coverage`，再升序 `weight_bound_count, 权重字典序`；其中 `weight_bound_count` 是 12 个最终权重中等于 `-7` 或 `+7` 的数量，不读取运行期累计 saturation counter。

容量 PASS 为单个确定性见证，不套 18/20 seed 或 bootstrap CI：

- Validation：accuracy `>=90%` 且 coverage `>=95%`。
- IID：accuracy `>=90%` 且 coverage `>=95%`。
- OOD：accuracy `>=80%` 且 coverage `>=90%`。
- 任意平局均 abstain 并计错。

搜索失败只输出“当前预注册预算下容量未证实”，不能输出“拓扑不可表达”。

### D8：统计边界细节

- cohort statistic 固定为 model-seed 算术平均。
- standard deviation 使用 sample SD，`ddof=1`。
- bootstrap 为 ordinary nonparametric percentile bootstrap；每次有放回重采样 N 个 model seeds，共 10000 次。
- 95% CI 使用 type-7 线性分位数的 `[2.5%, 97.5%]`；所有 lower-bound 硬门使用 2.5% 分位点。
- 对每个 seed 和 metric，定义 `eval_baseline_s` 为 D2 的 10000 次公共 evaluation permutation 指标的算术均值。P3 分别构造 `main-eval` 与 `main-training_shuffle`，以及 overall 与 conditional 两类指标，共四组逐 seed delta；每组独立执行 10000 次 paired bootstrap。P3 的 `>10pp` 要求四组 95% lower bound 都严格大于 0.10。
- 任一 seed 的主实验或对应 control coverage 为 0、使 conditional metric 为 `null` 时，该 conditional improvement 硬门直接 `FAIL`；禁止删除该 seed、插补数值或缩小 bootstrap 样本数。
- Monte Carlo p-value 使用 D2 的加一修正；并列按 `null >= observed` 计入尾部。
- accuracy/coverage 门槛的 `>=` 按原文执行；P3 CI 和 paired improvement 中写明的 `>` 必须严格执行。
- bootstrap 重采样矩阵的 `g4_rng_v1` payload 固定为 `(claim, task, split, mode, replicate, purpose="bootstrap_seed_resample")`，明确不含 control 或 metric。同一 claim/task/split/mode 下四组 paired 指标复用同一份 `replicate x seed_position` 索引矩阵；control/metric 只进入结果记录，不改变重采样。manifest 记录矩阵 digest。evaluation permutation 使用 D2 的公共域，禁止使用全局 RNG。

### D9：P2 的 CI 只报告

P2 继续报告 IID/OOD 95% CI，但不增加 CI lower-bound 硬门。P2 只按已批准的 mean、seed 成功数和 activity/coverage 门槛判定。验收器不得自行把 P1/P3 的 CI 条件复制到 P2。

### D10：Spatial/XOR 数据合同

所有样本均为 64 tick，使用与 Temporal 相同的 split 数量、共享数据集和全局 B。每个 symbol 展开为 B 个连续同通道事件；同一 counterfactual group 完全共享时间骨架。

canonical 空间一律按最坏边界 `B=4` 预先生成，因此最终选择 `B=2/3/4` 不改变 skeleton 列表、index 或 split。bit code 使用小端位序，具体字段映射由各任务条目冻结；原始产品枚举以 `first_start` 为外层升序、code 数值为内层升序。每个产品先记录从 0 连续编号的 `product_ordinal`，过滤越界项后，再给合法列表分配从 0 连续编号的稠密 `canonical_index`。随后对每个 `(task, domain)` 的完整合法 canonical group 做一次由 master seed 和 purpose=`canonical_split` 派生的 `g4_rng_v1` Fisher-Yates 无放回置换，再按本节固定 offset 切分；manifest 必须记录 product count、合法 canonical count、置换 digest 和切片 offset/count。split 内保留置换顺序，再按 counterfactual 顺序排列；整数 `sample_index` 从 0 连续编号，字符串 `sample_id` 固定包含 task/split/skeleton/counterfactual provenance。`time_skeleton_id` 固定为 `<task>:<domain>:<canonical_index:08x>`，样本 seed 由冻结 master seed、task、split、canonical index、counterfactual index 派生。正式 seed 值必须写入 `g4_t3_config.json`，批准后只允许机械落盘本规格冻结的值，不得现场挑选。

seed 根固定为 `master_seed=0x473454454D504F52`。development model seed IDs 固定为 `[0,1,2,3,4]`，final model seed IDs 固定为 `[100..119]`，P4 使用 final 的 `[100..109]`，direct search IDs 固定为 `[0,1,2,3,4]`。所有实际 64-bit seeds 均按 D2/D6 的完整域标签和 SHA-256 counter 派生；purpose 分域使同值 ID 不会复用随机流。

Spatial `g4_spatial_dataset_v1`：

- 每个 skeleton 生成 label 0/1 两个 counterfactual。
- label 0 使用通道 `(0,1)`，label 1 使用 `(2,3)`；8 个 symbol 按共享 alternation phase 交替。
- IID 相邻起点间隔只取 `{5,6}`，OOD 只取 `{7,8}`；first start 和 7-bit interval code 确定 skeleton。
- IID `first_start=0..18`，OOD `first_start=0..4`；以 `B=4` 过滤最后 burst 越过 tick 63 的骨架。
- IID group offset/count 固定为：Calibration `0/64`、Train `64/16`、Validation `80/64`、IID test `144/256`；OOD test 为 OOD canonical 的 `0/256`。每个 group 的 counterfactual 顺序固定为 `label 0, label 1`，总样本数对应 `128/32/128/512/512`。
- alternation phase 由 `canonical_index & 1` 派生；label、phase、事件数、first/last tick 和间隔分布严格配对。
- golden skeleton：IID `product_ordinal=canonical_index=0` 为 `first_start=0, code=0, starts=[0,5,10,15,20,25,30,35]`；OOD `product_ordinal=canonical_index=639` 为 `first_start=4, code=127, starts=[4,12,20,28,36,44,52,60]`。

XOR `g4_xor_dataset_v1`：

- 每个 skeleton 生成 `(A,B) in {00,01,10,11}` 四个 counterfactual，标签为 `A xor B`。
- 早窗 4 个 symbol：A=0/1 分别使用通道 0/1；晚窗 4 个 symbol：B=0/1 分别使用通道 2/3。
- IID 窗内间隔只取 `{4,5}`，早晚窗间隔只取 `{8,9,10,11}`。
- OOD 窗内间隔只取 `{6,7}`，早晚窗间隔只取 `{12,13,14,15}`。
- early window 使用 3 个窗内间隔，late window 使用 3 个窗内间隔；`inter_window_gap` 精确定义为 `start[4] - start[3]`。8-bit code 的 bit `0..1` 按升序选择四个 gap，bit `2..4` 编码 early intervals，bit `5..7` 编码 late intervals；连续且 4 的倍数个 group 会均匀覆盖四个 gap。
- IID/OOD `first_start=0..4`，以 `B=4` 过滤最后 burst 越过 tick 63 的骨架。
- IID group offset/count 固定为：Calibration `0/32`、Train `32/8`、Validation `40/32`、IID test `72/128`；OOD test 为 OOD canonical 的 `0/128`。每个 group 的 counterfactual 顺序固定为 `00,01,10,11`，总样本数对应 `128/32/128/512/512`。
- 四组合共享相同 8-symbol 时间骨架；各 split 使用互不重叠的 canonical skeleton index 区间。
- golden skeleton：IID `product_ordinal=canonical_index=0` 为 `first_start=0, code=0, gap=8, starts=[0,4,8,12,20,24,28,32]`；OOD 的产品 `product_ordinal=1279`（`first_start=4, code=255`）因末 burst 结束于 tick 65 被过滤，故最后合法项为 `canonical_index=1278, product_ordinal=1278, code=254, starts=[4,11,18,25,39,46,53,60]`。

两个 validator 都必须检查 exact schema、generator replay、split/input hash 隔离、counterfactual 直接配对、平衡、域不交、B、非重叠和 64-tick 边界；并报告每个 split 的 `first_start`、每个 interval bit 和 XOR gap 的边际计数。IID split 是同一冻结合法池经无放回置换后的切片，不得用原枚举连续区间；若 canonical 空间不足或任一入选 skeleton 在 `B<=4` 时越界，生成阶段立即失败，不允许运行期拒绝采样悄悄改变分布。

### D11：训练预算、探索和停止条件

共同合同：

- 权重初态：12 个权重各自从 `{1,2,3}` 均匀派生；所有 no-WTA 开关显式设为 `False` 并断言。
- final runner 固定训练满预算，不 early-stop。Validation checkpoint 为 `{1,2,4,8,16,32,64,128}`。
- 每个 epoch 的 Train 样本顺序来自 D6 `RandomPlan` 的 `g4_rng_v1` Fisher-Yates；主实验和配对对照字节完全相同。epsilon 固定为精确有理数 `(1270 - 9*epoch) / 2540`，epoch 为 `0..127`。令 `u53` 为随机 64-bit 字右移 11 位；abstain 强制探索，否则仅当 `u53 * 2540 < (1270 - 9*epoch) * 2^53` 时探索。候选 action 使用独立随机字的最低 bit，二者无条件消费。
- `context_admission_baseline` 和 P1/P2/P3 单任务最终模型使用 `max((accuracy, coverage, -weight_bound_count, -completed_epoch_count))` 选择 checkpoint。每个 checkpoint 只在完整 epoch 最后一笔 MOD_COMMIT 完成、snapshot 已清空且网络 idle 时拍摄，并在完整训练状态的 clone 上只读评估，不回写 spike/saturation/trace 等计数；checkpoint 必须冻结完整可恢复训练状态与 digest。IID/OOD 只评选定 checkpoint 一次。
- `p4_budget_matched_single_endpoint`、P4 sequential 和 joint 均跑满预算，不做 checkpoint 回滚；它们与 admission baseline 是两个独立产物，不得混用。
- 正式计分和 exploitation action 只使用 `strict_decode(output_spikes)`。

`teacher_no_wta`：

- 128 epochs，即每任务 `128 x 32 = 4096` 次完成的 MOD_COMMIT。
- label 0 调制 hidden/output 均为 `(+1,-1)`；label 1 均为 `(-1,+1)`。

`hybrid_no_wta`：

- feature phase 64 epochs：hidden 使用 Teacher 调制，output 固定 `(0,0)`。
- output phase 128 epochs：hidden 固定 `(0,0)`；output 对所选 action 使用 signed reward，未选 action 为 0。
- P2 的 checkpoint `n in {1,2,4,8,16,32,64,128}` 精确定义为全部 64 个 feature epochs 完成后，再完成 `n` 个 output-local epochs；epsilon 的 epoch 也只指 output-local `0..127`。feature-only endpoint 不进入 checkpoint 候选。
- 两阶段之间不重置任何权重；“冻结隐藏”只指 output phase 不提交隐藏权重更新，不声称冻结隐藏 trace/eligibility/threshold。

`reward_global_no_wta`：

- 128 epochs，即 4096 次完成的 MOD_COMMIT。
- 环境只返回 action 是否正确的 `+1/-1`。
- `reward_to_modulation(+1)=(+1,+1,+1,+1)`，`reward_to_modulation(-1)=(-1,-1,-1,-1)`；API 只接收 reward。

Hybrid output phase 与 P3 的 epsilon-greedy 均使用上述精确公式和比较规则。

`feedback_alignment_no_wta` 只作候选：四核固定符号向量为 `(+1,-1,+1,-1)`，modulation 为 `reward * vector`；不得进入 P3 主结论。

### D12：P4 joint-training 总预算

P4 预算单位固定为“成功接受并完成的训练 episode 对应 MOD_COMMIT 次数”，不要求权重实际改变；eligibility 为 0、右移后 delta 为 0 或权重饱和造成的 no-op commit 仍计预算。另行报告 no-op commit rate、各权重的 bound-hit rate 和饱和率。wall-clock 和 validation 次数不计预算。

- Teacher：每任务 4096 commits；顺序总计 12288。joint 也总计 12288，并按任务严格轮转，每任务各 4096。
- Reward：每任务 4096 commits；顺序和 joint 总计同上。
- Hybrid：每任务 2048 个 hidden-feature commits 加 4096 个 output-reward commits，共 6144；三任务总计 18432。joint 先均匀混合三个任务的 feature phase，再均匀混合 output phase。
- sequential 严格按给定任务排列执行；joint 的严格轮转起点固定为 Spatial，随后 Temporal、XOR。Hybrid joint 必须先让三个任务各完成全部 2048 个 feature commits 后统一切换 output phase，禁止任何任务提前进入 output；随后三个任务各完成 4096 个 output commits。
- validation、IID/OOD inference 不计预算。正式 Python/P4 能力 run 中任何 abort、reject、snapshot busy、commit mismatch 或 episode 部分执行后失败都立即使该 run 失败，禁止补跑；P5 的预注册错误路径使用独立 cohort。只有尚未被 DUT 接受且已证明零副作用的同一传输命令允许原样重发，不能重启训练 episode。
- 每个排列、每个 single-task endpoint 和每个 joint run 都从同一 canonical 初态独立 hard reset/clone，`commit_id` 从 0 重启。单 run 最大为 18432 commits，最高 ID 为 18431；必须断言 16-bit `commit_id` 不回绕。六排列不得连续共用同一 commit 序列。
- P4 sequential、`p4_budget_matched_single_endpoint` 和 joint upper bound 全部跑满预算，不做 checkpoint 回滚；`context_admission_baseline` 仍按 D11 选择 checkpoint。

## 4. 实现文件边界

批准后建议按以下边界实现：

- `g4_benchmark.py`：三任务数据、hash、strict decoder、静态 validator。
- `g4_statistics.py`：bootstrap、permutation、paired delta 和门槛复算。
- `g4_training.py`：label-blind model adapter、三种正式训练策略和 feedback-alignment 候选。
- `g4_no_replay.py`：P4 broker/worker、状态 schema 和访问审计。
- `g4_direct_search.py`：Temporal 结构化覆盖及 Spatial/XOR 固定预算搜索。
- `g4_t3_config.json`：本文所有 seed、预算、checkpoint、context 和阈值的机器可读冻结值。
- `verify_g4.py`：逐声明输出 `PASS/FAIL/NOT-RUN`，不复用训练器内部判定。

旧 `HostTrainingController` 不作为上述模块的依赖。正式 model adapter 只接收 `sample["input"]`；label 只存在于训练环境/evaluator，不能进入网络执行 API。

## 5. 测试先行的批准后任务顺序

1. T3.0：为 D1、strict decoder、label-blind API、纯 reward API 写 RED 测试；冻结 EP_START 白名单和 INFER 前置条件。只有现有实现超出白名单时才修改 clear 路径并重签 Python/reference/RTL。
2. T3.1：实现 Spatial/XOR 生成器、validator 和统一 manifest；通过 P0a-pretrain 静态部分。
3. T3.2：实现三任务 P0b calibration，冻结全局 B，并完成高层/reference spike-count 等价。
4. T3.3：实现统计、负对照和 freshness 验证器；不运行 final test 调参。
5. T3.4：先运行三任务 direct-weight；优先产出 Temporal 容量边界。
6. T3.5：实现并运行 P1/P2/P3 development cohort；冻结结果后运行 20-seed final cohort。
7. T3.6：仅对已通过前置门槛的模式运行 contextized single-task、P4 sequential 和 joint upper bound。
8. T3.7：生成结果 JSON/报告和独立 `verify_g4.py` 结论。

## 6. 预计运行成本

当前本机只读测量：64-tick inference 约 0.622 ms/episode，train+snapshot/commit 约 0.894 ms/episode，朴素 32-sample direct search 约 49 candidates/s。

- P1-P3 三任务、三模式、20 seeds：工程预算约 30-45 分钟。
- 5 个 development seeds：约 10-15 分钟。
- P4 三模式全部具备进入资格时，纳入 context admission、budget-matched single、六排列矩阵和 joint 后，纯 Python 粗略下限约 91 分钟；工程预算 2-3 小时，仍需根据 worker/audit/统计实测刷新。
- 49 candidates/s 只覆盖 Train 32；D7 每候选评分 Train+Validation 共 160 样本。按线性外推，Spatial/XOR 每任务 100000 个朴素候选约 170 分钟，两任务约 5.7 小时；正式实现必须缓存或批处理。
- Temporal 的 Train+Validation 唯一签名数不能沿用旧 Train-only 的 `6929` 组合口径。当前只读参考探针观察到 `U=129`，对应 `16641` 个有序组合和 `842450625` 次输出读出检查；该值不是批准后 manifest 的冻结结果。实施必须先报告实际 `U` 并验证 `U^2*225^2`，再做 chunk/vectorized benchmark、冻结 wall-clock 预期和 chunk 大小。
- `15^12` 全穷举不可行；direct-weight 失败只按 D7 的有限预算解释。

## 7. 审核结论格式

用户批准本文后，将 `状态` 改为 `APPROVED`，生成 `g4_t3_config.json` 并按第 5 节拆分实现任务。若只修改其中某项，应提升规格版本并重新计算所有依赖该项的 manifest/hash；不得在 runner 中静默覆盖。
