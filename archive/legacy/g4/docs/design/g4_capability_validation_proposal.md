# G4 多任务自训练与推理能力验证方案（V3 审核稿）

日期：2026-08-13  
状态：V3 六项冻结决策已于 2026-08-13 获用户批准，当前按 T0、T1/T2、T3、P5、P6 顺序实施；核心训练模型或 RTL 仅在对应阶段和测试合同冻结后修改。

## 1. 结论先行

本阶段不是为了把实验调到 PASS，而是回答五个可证伪问题：

1. 固定 4->2->2 数字网络是否能在严格留出集上学习多种二分类规则？
2. 失败来自输入活动不足、网络表征容量、学习规则，还是隐藏层信用分配？
3. 哪些结果能由当前无 WTA Tile 直接实现，哪些只是 Python 中的候选扩展？
4. 训练后的同一网络是否能保留多个任务，而不是只记住最后一个任务？
5. 固定 Tile 的结论能否扩展为资源、吞吐和状态存储边界明确的可复制网络基石？

即使 P0-P6 全部通过，也只能支持“固定任务族上的训练、泛化、无 replay 持续学习、RTL 闭环，以及三个有限参数点的扩展性证据”，不能直接宣布通用 AI 自训练、任意拓扑扩展或开放世界泛化已经解决。

## 2. 当前证据缺口

- `make_dataset()` 只有两个固定样本；当前 `clean_accuracy` 不是留出集。
- `make_noisy_dataset()` 与训练模板同源，扰动空间很小。
- 历史 teacher sweep 没有使用独立模型初始化；`artifacts/results/network_sweep_results.json` 还早于当前 `network_sim.py`。
- 当前 reward-only 历史结果约为 22.5%，不能支持隐藏层信用分配已经解决。
- 现有 Tile RTL 没有层级 WTA；Python reward/hybrid 历史 sweep 开启了 WTA，不能直接映射为当前 RTL 能力。
- Host Bridge 的协议和传输已 bit-exact，但还没有让真实 RTL 执行完整的“数据集训练 -> 延迟 MOD_COMMIT -> 留出推理 -> 任务准确率”闭环。
- 最新 `vivado_tile_reports` 原始报告为 3152 LUT / 1972 FF、WNS +0.213 ns、WHS +0.026 ns；T0 已将独立 Tile 摘要、原始报告复核、资源预算与 README/审计/设计文档统一。
- 二分类下，Host 同时知道动作 `a` 和 `reward in {-1,+1}` 时可恢复真实标签；因此按动作定向发送 neuron-specific modulation 不能作为纯 reward-only 证据。
- 旧 Temporal 序列 `ABABABAB/BABABABA` 的首事件直接给出类别，不能证明时间顺序学习。
- 当前 Host 协议不能读回完整 eligibility、trace、threshold、membrane 等内部状态；P5 必须区分 Host 黑盒证据和 testbench 白盒证据。
- V2 Temporal 的 `AABABBAB/ABBAABAB` 仍可由第 2 或第 5 个 symbol、前后半计数和多个固定位置 bigram 100% 分类，必须改为类条件低阶统计严格配平的任务分布。
- V2 P4 没有限制 Host replay、旧标签和额外片外状态，可能只证明 Host 保存全部历史数据后联合重训，而不是网络保持旧任务。
- V2 P5 没有隔离 stimulus/golden-vector/scoreboard 实现，且完整系统 Icarus cosim 使用接口等价 FIFO 而非真实 AMD XPM，不能把两类证据混称为同一个“真实 XPM 全系统闭环”。
- V3 Temporal 的只读容量预判在 32 个 phase/时间骨架样本上检查 6929 个唯一隐藏签名组合，并为每组穷举 225x225 个输出读出器，当前最好为 25/32；独立 `DigitalSNN2Layer` 重放一致。这既不是容量不可能证明，也不是验收结果，但说明固定 2-hidden 拓扑存在明确容量风险。

## 3. 固定实验对象

第一轮不同时改变拓扑、协议和学习规则：

- 输入：4 个事件通道。
- 隐藏层：2 个三因子 LIF 神经元。
- 输出层：2 个三因子 LIF 神经元。
- 隐藏到输出：固定 1 个逻辑 tick 路由延迟。
- 权重：signed 4-bit 有效范围 `[-7, 7]`。
- 隐藏阈值：4；输出阈值：2。
- Host：负责标签/环境奖励、探索、训练顺序、事件编码和 signed modulator。
- Tile：只负责确定性事件计算、eligibility 快照和权重提交。

第一轮禁止通过降低阈值、扩大权重范围、增加隐藏神经元或读取 test 数据调参来制造通过。这些改动只能在第一轮边界已经测清后，作为新架构版本重新立项。

## 4. 输入活动校准

探索性 48-tick 探测中，Temporal 和 XOR 几乎全部返回 `prediction=-1`。这首先表示四事件输入没有建立有效输出活动，不能直接解释成“网络不会时间顺序或 XOR”。V3 Temporal 已改为 10 symbols、统一 episode 改为 64 tick，因此旧 `B=2` 活动结果只保留为探索证据，不能作为正式 P0b。

正式训练前增加独立、label-blind 的 activity calibration split：

1. 每个逻辑 symbol 展开为连续 `B` tick 的同通道脉冲，候选 `B in {1,2,3,4}`。
2. 使用独立 calibration seed、固定全 2 初始权重、关闭学习，只统计活动，不查看标签或分类正确率。
3. 对每个任务、每个类别/组合分别检查 hidden-active 和 output-active。
4. 选择能让所有任务 output-active >=95% 的最小全局 `B`，将选择结果、样本 hash 和 seed 写入 manifest 后冻结。
5. 若 `B<=4` 均不满足，判定“当前事件编码不适配固定硬件动力学”，停止训练；不能直接降低性能门槛。

该步骤只改变片外事件编码，不改变神经元状态方程、RTL 参数或权重范围。它只证明固定全 2 初态下事件编码能够激活网络，不保证随机初态或训练后的网络仍有活动；各训练模式的 activity/coverage 必须在各自 P1/P2/P3 中重新验收，禁止继续增大 `B` 掩盖 dead network。

## 5. 三个任务族

统一 episode 长度为 64 tick。所有 symbol 起点必须保持顺序且展开后不重叠；即使 `B=4`，10-symbol Temporal 仍保留 24 tick 供 9 个间隔和 OOD 拉伸使用。生成器拒绝重复样本。每个任务先生成与标签无关的时间骨架，再在同一骨架上构造各类别或组合的 counterfactual；抖动、拒绝采样次数、首尾 tick、间隔分布和总事件数均不得携带标签。

### 5.1 Spatial：空间通道任务

- label 0 使用通道对 `(0,1)`。
- label 1 使用通道对 `(2,3)`。
- 每个样本包含 8 个 symbol，在类内两个通道间交替。
- symbol 起点从允许时间范围随机采样，标签不能由总事件数、episode 长度或固定 tick 泄漏。

该任务验证最基本的通道选择性。它允许计数型特征完成分类，因此是最低难度基线。

### 5.2 Temporal：至少需要 4-symbol 上下文的时序 motif 任务

- 只使用通道 A=0、B=2。
- label 0 的循环基 motif 为 `AABABABB`；label 1 为 `AABBABAB`。
- 每个样本先用 label-independent 的均匀 phase `r in [0,7]` 循环移位，再输出完整 8-symbol cycle，并重复旋转后开头 2 个 symbol，得到 10-symbol 序列。
- 每个 split 内 `(label, phase, time_skeleton_id)` 严格配对且等频；相同 phase 的两类 counterfactual 使用完全相同的时间骨架。
- IID 只改变各 symbol 的合法时间抖动；OOD 使用训练范围之外的间隔拉伸和抖动范围，但不改变 motif、phase 配平或低阶统计合同。

生成器在训练前必须静态断言：

- 两类最终序列集合不相交；
- 对每个绝对位置，`P(symbol_at_i | label)` 完全相同；
- 对每个固定邻接位置，`P(bigram_at_i | label)` 完全相同；
- `P(front_A_count, back_A_count | label)` 完全相同；
- 全局 unigram、bigram、trigram histogram 的类条件分布完全相同；
- 类别差异首次允许出现在 4-gram 及更长顺序结构。

因此该任务只检验“网络是否利用至少 4-symbol 上下文的 motif”，不泛称任意时间推理能力。任一静态断言失败直接判定 P0a 失败，禁止进入训练；nuisance-only 分类器只是附加反证，不能补救先天泄漏的数据定义。

### 5.3 XOR：非线性组合任务

- 早时间窗用通道 0/1 one-hot 编码 bit A。
- 晚时间窗用通道 2/3 one-hot 编码 bit B。
- 每个时间窗包含 4 个同类 symbol，四种 `(A,B)` 组合严格平衡。
- 标签为 `A xor B`。
- IID 改变窗内 symbol 起点；OOD 改变窗间距离和 burst 间隔，但不改变 bit 定义。

XOR 是容量和信用分配判别任务。如果直接权重搜索能够找到高准确率权重，而三因子训练失败，失败才可归因于训练/信用分配；如果直接权重搜索也找不到，只能记为“当前拓扑容量未证实”，不能武断归因。

## 6. 数据合同与 seed 隔离

每个任务生成一份固定数据集，所有 development/final model seeds 共享同一组样本：

| Split | 数量 | 用途 |
|---|---:|---|
| Calibration | 128 | 只选择全局 burst 宽度；固定全 2 权重、关闭学习 |
| Train | 32 | 权重学习 |
| Validation | 128 | 选择 epoch 和 Host 超参数；不得重新选择已冻结的 `B` |
| IID test | 512 | 同分布最终验收 |
| OOD test | 512 | 分布外最终验收 |

另设 5 个 development model seeds 做方案调试；最终验收使用 20 个完全不同的 model seeds。它们只改变模型初始化、训练顺序和探索随机性，不改变 Calibration/Train/Validation/IID/OOD 输入。各模式在相同样本上运行，统计按 paired model-seed 计算。

seed 不使用简单相加复用，分为两个互不混用的域：

- 共享数据由 `SHA256(master_seed, task, split, null, dataset)` 派生；数据 API 不接受 `model_seed`。
- 初始化、训练顺序、探索、bootstrap 和 evaluation permutation 由含 `model_seed` 的独立 purpose 派生。

每个样本按规范 JSON 序列化后计算 SHA-256。硬门槛：

- 同一 split 内无重复样本；
- Calibration/Train/Validation/IID/OOD 哈希集合两两不相交；
- Spatial/Temporal 每类严格平衡；XOR 四组合严格平衡；
- 最终 test seed 和 test 标签不能进入任何调参、早停或编码选择路径；
- 所有 split 都写入 manifest；分别输出只绑定 `episode_ticks/events` 的 `input_hashes/input_sha256`，以及绑定标签、phase、seed、sample/skeleton ID 和顺序的 `example_hashes/example_sha256`。
- validator 必须使用冻结的 `master_seed/B` 重放生成器并对五个 split 做 canonical exact comparison；manifest 的源码哈希固定绑定实际 `g4_benchmark.py`，不得由调用方传入任意路径。

## 7. 训练模式与 RTL 映射

### 7.1 当前 RTL 兼容组（主结论）

- `teacher_no_wta`：标签生成四个 neuron-specific signed modulator，WTA 关闭。
- `reward_global_no_wta`：Host 选择动作、环境只返回标量 reward，同一个 signed modulation 广播到四个神经元，WTA 关闭。
- `hybrid_no_wta`：先 teacher 塑造隐藏层，再把隐藏层 modulator 固定为 0，只冻结隐藏权重并用 reward 训练输出层，WTA 关闭。

这三项不要求修改当前 Tile 数据通路，最终可进入真实 RTL 任务闭环。`hybrid_no_wta` 不得简称“冻结隐藏层”：当前 episode 级 `learn_enable` 仍会更新隐藏层 trace、eligibility 和自适应阈值。若要冻结隐藏层全部学习状态，必须新增分层 `learn_enable` 并重新完成 bit-exact、formal 和 Vivado 签核。

### 7.2 Python WTA 候选组（只作为扩展上限）

- `teacher_wta`
- `reward_global_wta`
- `hybrid_wta`

WTA 组用于回答“增加数字层级仲裁是否值得”。在 WTA RTL 实现、bit-exact 回归和 Vivado 重签核完成前，任何 WTA 结果都不能计入当前硬件能力。

### 7.3 纯全局 reward 与反馈对齐候选

当前 `reward_modulator(label, result)` 在无输出时没有独立探索动作，不足以作为正式 reinforcement learning 对照。更关键的是，二分类环境中 Host 可由 `(action, reward)` 精确恢复 label；任何再按 action/恢复出的 label 定向构造输出或隐藏调制的实现，本质上具有 teacher 等价信息，不能标为纯 reward-only。

P3 主结论只允许 `reward_global_no_wta`：

1. Host 根据输出 spike count 做严格解码；无决策时必须探索。
2. epsilon-greedy 选择动作，epsilon 日程在 validation 后冻结。
3. 环境只返回动作正确/错误的 `+1/-1`。
4. 独立模块公开的纯 reward API 固定为 `reward_to_modulation(reward) -> (m,m,m,m)`；不得接收 label、action、prediction、sample 或 environment 对象，也不得按被选择动作寻址。
5. 用 AST/依赖检查禁止该模块读取训练器全局数据或闭包；调用边界变形测试要求在 reward 相同而 label/action/prediction 任意变化时，四路 modulation 逐位不变。训练日志只作审计记录，不单独充当无泄漏证明。

另设 `feedback_alignment_no_wta` 候选：在读取任何数据前冻结常量反馈向量 `b[j]`，使用 `mod[j] = clip(reward * b[j])`。反馈向量不能依赖 action、label、任务或样本。该组单独报告为 feedback-alignment，不计入纯 reward-only 的 P3 主结论。

## 8. 解码、活动率和推理冻结

主解码器固定为 strict spike-count：

```text
count0 > count1 -> class 0
count1 > count0 -> class 1
count0 == count1 -> abstain (-1)
```

`abstain` 一律计错。不能沿用“非零平局默认 class 0”，否则会产生类别偏置。

每个 split 同时报告：

- overall accuracy；
- output-active rate：至少一个输出 spike；
- decision coverage：两个输出 count 不相等；
- conditional accuracy：仅在非 abstain 样本上统计；
- 每类/每组合混淆矩阵；
- 每 seed 的最终权重、饱和率和 spike 分布。

推理冻结按 sample 检查：

- `begin_episode(train=False)` 后锁存全部 weights、pre/post trace、eligibility、threshold、snapshot/commit 元数据和 weight_epoch；
- 运行所有 tick、ROUTE_FLUSH 和 EP_END；
- 上述学习状态必须逐字段不变；
- current、membrane、refractory、spike count 等推理动态状态允许变化；
- 整个 test split 前后权重和 commit 元数据必须完全一致。

## 9. 负对照和容量对照

每个任务必须同时运行：

- majority baseline：平衡二分类固定为 50%。
- untrained/frozen network：20 个独立初始化，不提交 MOD。
- evaluation-label permutation：保持同一模型预测完全不变，只置换 test 标签，构造活动率和 coverage 完全相同的经验零分布。
- training-label shuffle：保持输入不变，打乱训练标签；单独报告其 output-active、coverage 和 conditional accuracy，作为训练路径诊断，不以低 overall accuracy 单独判定通过。
- temporal order-destroy：打乱 4-symbol 以上结构后不得保留可预测标签。
- temporal nuisance-only：绝对位置 unigram、固定位置 bigram、前后半计数、全局 1..3-gram 直方图和时间骨架特征均不得显著优于 50%。
- direct-weight search：Host 直接搜索 12 个 `[-7,7]` 整数权重，只在 Train/Validation 优化，test 只评估一次。

direct-weight search 只用于构造“当前拓扑可表达”的正证据，不属于自训练结果。搜索失败不能证明数学上不可表达，只能标为容量未证实。

对每个任务，direct-weight search 若在 Validation 和一次性 Test 上达到 P1 同等级门槛，则构成固定拓扑的容量正证据；若未达到，仍允许训练实验继续，但 Teacher 失败时不得把责任单独归于学习规则。所有搜索预算、候选生成、停止条件和已检查权重数必须预注册并报告，禁止只公布最好结果而隐藏搜索范围。

## 10. 统计方法

- 统计单位是 20 个独立 model seeds，不把 512 个 test 样本伪装成 512 个独立模型。
- 报告 mean、median、standard deviation、worst seed 和逐 seed 原始值。
- 95% CI 使用固定 seed、10000 次按 model seed 重采样的 bootstrap。
- evaluation-label permutation 对每个 model seed 使用由 manifest 派生的 10000 次平衡标签 Monte Carlo randomization；固定预测和 coverage，只置换标签，报告一侧 p-value 和零分布分位数。
- 与 untrained、evaluation-label permutation、training-label shuffle 的 overall/conditional accuracy 差值使用 paired bootstrap；同时报告 activity/coverage 的配对差值。
- 所有任务逐项判定；禁止用一个简单任务的高分补偿另一个任务失败。

## 11. 分级验收门槛

### P0a：数据、测量与冻结有效性

- split 哈希、seed 隔离、类别/组合平衡全部通过。
- Temporal 的序列集合、phase/time-skeleton 配对、逐位置 unigram/bigram、半程计数和全局 1..3-gram 静态等分布断言全部通过。
- 三任务 episode 均为 64 tick；Temporal 在 `B<=4` 时对所有允许 IID/OOD 时间骨架均满足 10 个 burst 不重叠且不越界。
- 20 个独立最终初始化得到验证。
- 推理学习状态 100% 冻结。
- nuisance-only 基线不得超过对应 10000 次 randomization 的 95th percentile；该 percentile 必须 <=55%。
- evaluation-label permutation 是准确率零假设的硬门槛；training-label shuffle 是辅助诊断。后者若大面积全 abstain，只能记录为训练崩溃，不能充当“接近随机”的通过证据。
- 结果文件晚于全部源文件，并记录源码 SHA-256。

### P0b：固定编码活动正对照

- 独立 Calibration split、固定全 2 初始权重、关闭学习。
- 选定的最小全局 `B` 使每个任务、类别/组合的 output-active >=95%。
- 高层模型与 `RtlReferenceNeuron` 对相同 calibration 样本的 hidden/output spike count 完全一致。
- P0b 只证明编码正对照；训练后各模式仍必须单独满足自己的 activity/coverage 门槛。
- V3 Temporal 的只读 128 样本探针已经观察到：`B=1` 全静默，`B=2/3/4` hidden/output active 均为 100%，高层模型与四个 `RtlReferenceNeuron` 全部一致；正式 P0b 仍须由最终生成器、manifest 和独立 calibration seed 重跑，不能直接复用该探针。

### P1：Teacher，多任务监督前置

每个任务分别满足：

- IID mean accuracy >=90%。
- IID 95% bootstrap CI lower bound >=85%。
- OOD mean accuracy >=80%。
- 至少 18/20 seeds 同时达到 IID 80% 和 OOD 70%。
- IID output-active/decision coverage 均值 >=95%，OOD >=90%；不得用无决策样本规避准确率。

P0a+P0b+P1 只支持“固定 4->2->2 在三类二分类任务上具备监督训练和留出泛化证据”。

### P2：Hybrid

每个任务分别满足：

- IID mean >=85%。
- OOD mean >=75%。
- 至少 16/20 seeds 同时达到 IID 75% 和 OOD 65%。
- 各 split 的 activity/coverage 与 P1 使用相同报告和门槛。

### P3：纯全局 Reward-only 信用分配

每个任务分别满足：

- IID mean >=75%。
- IID 95% CI lower bound >60%。
- 至少 15/20 seeds 达到 IID 70%。
- OOD mean >=65%。
- 相对 evaluation-label permutation 和 training-label shuffle 的 overall 与 conditional accuracy 配对改善下界均 >10 个百分点。
- 各 split 的 activity/coverage 与 P1 使用相同报告和门槛。

本门槛只判定 `reward_global_no_wta`。`feedback_alignment_no_wta` 单列结果，不得代偿 P3；不能因为当前 reward-only 结果差而降低门槛。

### P4：Task-aware、无 replay 的持续学习

使用同一网络按任务序列训练，并在每个阶段后评估所有任务，得到测试矩阵 `R[i,j]`。

P4 按训练模式分别运行：`teacher_no_wta`、`hybrid_no_wta`、`reward_global_no_wta` 只有在各自 P1/P2/P3 已通过时才进入对应 P4；每种模式独立判定，Teacher 的持续学习不得代偿 Hybrid 或纯 reward 的失败。若 P3 未通过，仍可报告 Teacher/Hybrid 的 P4，但不得称为“纯奖励持续自训练”。

为避免同一事件流在不同任务中出现冲突标签，第一版明确命名为 task-aware/task-incremental continual learning：Host 在 episode 开头加入固定、label-independent 的任务上下文前缀；输入宽度仍为 4。所有单任务基线和 `R[i,j]` 都必须使用完全相同的 context。另行报告无上下文的 task-agnostic 探索结果，但不把不可判定的标签冲突算作遗忘，也不把 task-aware 结果泛称为 task-agnostic 持续学习。

主结论使用 no-replay Host 合同：离开任务 `j` 后，Host 不得访问该任务的训练样本、标签、逐样本预测、eligibility、modulation 历史或其可逆编码；不得联合重训。允许保留的片外状态只有预注册超参数、RNG 状态、任务序号和与样本无关的固定计数器，全部序列化并写入 manifest。任何样本 replay 或生成式 replay 单列为 replay-assisted 候选，不得计入 P4 主结论。

增加 joint-training upper bound：使用相同 context、相同训练样本和相同总更新预算，将三个任务均匀混合训练。若 joint-training 也不能同时达到三任务门槛，则顺序训练失败首先记为固定拓扑的联合表达能力未证实，不能直接归因于灾难性遗忘。

运行 10 个独立 model seeds；每个 seed 内运行全部 6 种任务排列。6 个排列是同一模型 seed 下的重复测量，不计为 60 个独立样本。先在每个 seed 内聚合排列结果，再以 model seed 为统计单位：

- 最终三个任务 IID accuracy 均 >=75%。
- 每个任务相对刚学完时的下降 <=10 个百分点。
- `ACC >=75%`，`BWT >= -0.10`。
- 至少 8/10 model seeds 在其 6 个排列聚合后同时通过。
- CI 和 bootstrap 只按 10 个 model seeds 重采样，不按 60 个排列运行重采样。

`ACC/BWT/FWT` 使用 GEM 论文定义的任务测试矩阵指标；这里只借用评价方法，不声称实现 GEM 算法。

### P5：RTL 任务级闭环

所有已通过 P1/P2/P3 的当前 RTL 兼容模式，以及至少一个预注册失败模式/任务，进入本门槛；reference 基于 `RtlReferenceNeuron + HostBridgeOracle`。`network_sim.py` 不能直接作为 P5 oracle，因为其 pending 容量、默认权重和旧解码语义与真实 Host Bridge 合同不同。

P5 禁止同一软件链自证：dataset/训练策略只生成语义级 episode 与 modulation；独立 golden-vector 生成器按冻结协议直接生成原始 128-bit 命令和期望状态；scoreboard 使用另一套独立 mask/shift 代码解码原始响应，不复用 stimulus codec、DUT helper 或训练器内部状态。golden vectors、两套实现源码哈希和协议版本全部进入 manifest，并用固定手算向量分别验证。

每个 RTL model seed 开始前必须：hard reset；执行 12 次 `WEIGHT_WRITE` 装入 reference 初态；执行 12 次 `WEIGHT_READ` 回读；检查 snapshot/commit/epoch 初态；全部一致后才进入训练。

Host 黑盒证据：

1. Host 发送 `EP_START -> TICK_BEGIN/INPUT_EVENT/TICK_COMMIT* -> EP_END`。
2. 只在 `host_rsp_valid && host_rsp_ready` 时累计响应，校验 status、episode ID 和 tick ID；`TICK_COMMIT.arg0[3:2]` 为普通 tick 输出 spike，`EP_END.arg0[3:2]` 为 route flush 输出 spike。禁止按 `valid` 电平逐拍重复累计。
3. 每个 TRAIN `EP_END` 捕获单槽 snapshot 后，必须完成对应 `MOD_COMMIT` 才能开始下一 TRAIN episode；commit ID 在单次 run 内使用 16-bit 严格单调、不回绕范围。
4. INFER episode 禁止所有权重写回。
5. 每个响应、输出计数、权重、snapshot/commit 元数据和 weight_epoch 与独立 RTL oracle bit-exact。

Testbench 白盒证据：

- 通过层次路径比较 eligibility snapshot、pre/post trace、threshold、membrane、refractory 等内部状态。
- 白盒字段不得描述为 Host wire-level 可读；若未来要求 Host 读回，必须另立 debug/state-read 协议并重新签核。

P5a 使用真实 Controller + Tile RTL 和接口等价 async FIFO 模型执行完整 cohort：至少覆盖每个通过任务/模式 5 个预注册 model seeds、每 seed 完整 Train 和不少于 128 IID + 128 OOD 样本。seed 集必须包含 development 中观察到的 worst、边界、失败、abstain 和负对照路径，不能只挑通过 seed。另预注册至少一个失败模式或失败任务，证明 dead network、饱和和拒绝路径同样 bit-exact。RTL accuracy 必须与同一 seed 的 RTL-reference 完全一致。

P5b 使用 Vivado xsim、真实 AMD `xpm_fifo_async`、Controller 和 Tile 跑代表性短 cohort：每个进入 P5 的成功模式至少 1 个 seed，并包含一个预注册失败路径；每个 seed 至少 16 个 TRAIN、32 个 IID 和 32 个 OOD episode。P5a 证明任务规模下的 RTL 行为，P5b 证明真实 XPM 全系统集成；两者均通过后才能称“完整真实 Host Bridge 仿真闭环”。

P5 仍是仿真/OOC 证据，不等于板级 G3b。

### P6：可复制性与扩展性边界

P0-P5 仍只证明固定 4->2->2。要把结果称为“可扩展网络基石”，必须另行建立共享流水线 + 同步 RAM 架构，而不是继续直接复制四个寄存器型核心：

- Host Bridge V1 不能直接承载 P6：其 `INPUT_EVENT` 只允许 synapse 0..3，权重地址固定 H0/H1/O0/O1，`MOD_COMMIT` 只携带四路调制。P6 必须冻结可寻址流式协议 V2，至少提供 `network/tile/neuron/synapse` 地址、逐神经元 modulation staging、批量权重读写和 snapshot/commit 队列；V1 与 V2 分开做 oracle、cosim、formal/CDC 和 Vivado 签核。
- 至少实现并验证三个参数点：4->2->2 基线、16->16->2、64->32->2；三者复用同一神经元状态方程和 Host modulation/commit 语义。
- 权重、pre trace、eligibility 和 snapshot 必须进入同步 RAM；报告每 tick 周期数、最大可持续事件率、训练提交延迟和 Host 带宽上限。
- 每个参数点完成 cycle-accurate reference 对照和 Vivado OOC；要求目标频率时序通过，资源随突触数的增长主要进入 BRAM，控制 LUT 不出现未经解释的超线性增长。
- 小规模共享引擎必须对所有已通过 P1/P2/P3 的模式各选至少一个任务，与 4->2->2 并行 Tile 的逐 tick 输出、学习状态和最终权重一致；若 P3 通过，不能只用 Teacher 代替纯 reward 等价。更大参数点至少运行一个 P1 任务，并在 P3 已通过时再运行一个 P3 任务，同时完成活动、饱和、吞吐和状态容量压力测试。

P6 失败不推翻固定 Tile 的 P0-P5 结果，但禁止把固定原型表述为“已证明可扩展”。P6 是完整 G4/基石扩展声明的独立硬门。

### 声明绑定矩阵

| 可对外声明 | 必须通过 | 不可代偿 |
|---|---|---|
| 数据和测量有效 | P0a + P0b | 高准确率不能掩盖数据泄漏或 dead network |
| 限定任务监督训练与推理 | P0 + P1 | Hybrid/reward 或某一简单任务不能代偿 |
| 两阶段 Host 训练 | P0 + P1 + P2 | Teacher 结果不能代偿 Hybrid |
| 纯全局奖励自训练 | P0 + P3 | Teacher、Hybrid、feedback-alignment 均不能代偿 |
| 对应模式的无 replay 持续学习 | 前置模式门槛 + 该模式 P4 | 不同训练模式之间不能代偿 |
| 固定 4->2->2 的 RTL 任务闭环 | 对应模式门槛 + P5a + P5b | 协议随机测试或 Python 准确率不能代偿 |
| 可扩展数字网络基石 | P0-P5 的相应声明 + P6 | 固定 Tile 的资源/时序不能外推到更大网络 |

`verify_g4.py` 必须按此矩阵逐项输出 PASS/FAIL/NOT-RUN 和证据路径；只有所有行通过，才允许输出 `G4_FULL_PASS`。任一行失败时仍保留其他已通过的窄结论，但不得输出总通过。

## 12. 失败分类规则

按以下顺序解释失败，禁止跳步：

1. P0a 失败：数据、测量、负对照或推理冻结合同无效，后续准确率不得解释。
2. P0b 失败：输入编码与固定全 2 动力学不匹配。
3. direct-weight search 找到高分，但 teacher 失败：学习规则或 Host learning signal 失败。
4. teacher 通过、hybrid/reward 失败：输出探索或隐藏层信用分配失败。
5. Python no-WTA 通过、RTL 失败：模型/协议/实现等价失败。
6. 单任务通过、持续学习失败：灾难性遗忘或任务干扰。
7. direct-weight search 也未找到高分：只能说当前拓扑容量未证实，不能当作学习规则反例。
8. joint-training 上限失败：固定拓扑的多任务联合表达能力未证实，不能把 P4 失败单独归因于遗忘。
9. P5a 通过而 P5b 失败：真实 XPM/全系统仿真集成失败，不是学习能力反例。
10. P6 失败：固定 Tile 仍有效，但可扩展基石声明未证明。

## 13. 预期产物

V3 批准后按阶段创建：

- `g4_benchmark.py`：任务生成、manifest、strict decoder、统计。
- `g4_training.py`：teacher/reward/hybrid Host 策略。
- `g4_capability_results.json`：逐 seed 原始结果和源码哈希。
- `g4_capability_report.md`：门槛、CI、负对照和失败分类。
- `g4_rtl_task_cosim.py`：Host Bridge + 真实 Tile 任务级闭环。
- `g4_xpm_task_cosim.py`：Vivado xsim + 真实 XPM 的代表性短 cohort。
- `g4_scaling_protocol_v2.md`：可寻址流式 Host 协议、队列和错误合同。
- `g4_scaling_report.md`：共享 RAM 引擎三个参数点的资源、时序、吞吐和等价结果。
- `verify_g4.py`：独立 G4 验收器；不让 G4 失败掩盖既有 G1-G3a 已通过事实。

实现顺序：

1. T0 修复证据新鲜度和 Tile 文档漂移；让 `verify_goal.py` 独立审计 Tile runner、RTL/Tcl 新鲜度、资源预算、timing、route、DRC 和功耗置信度。T0 生成机器可读 PASS 摘要及依赖哈希；T0 非 PASS 时，T4-T7 必须拒绝运行。
2. T1 先写数据/seed/hash/decoder/冻结的失败测试。
3. T2 实现三任务生成器和 activity calibration。
4. T3 实现负对照、统计和当前 RTL 兼容训练模式。
5. T4 跑 development cohort，冻结所有超参数。
6. T5 一次性运行 20-seed final cohort。
7. T6 将通过模式和预注册失败模式接入 P5a，并用真实 XPM 执行 P5b 短 cohort。
8. T7 先冻结可寻址 Host 协议 V2，再实现并签核 P6 共享 RAM 扩展架构；根据证据决定是否立项 WTA 或新的信用反馈。

## 14. 需要用户审核的六项决策

1. **硬件范围**：no-WTA 作为当前 RTL 主结论；`hybrid_no_wta` 只冻结隐藏权重；WTA 或冻结隐藏全部状态都属于需重签的候选扩展。
2. **任务与测量**：采用独立 Calibration split、P0a/P0b、strict spike-count，以及低阶统计严格配平、类别差异首次出现在 4-gram 的 Temporal motif 任务。
3. **奖励证据**：P3 只接受四核相同的纯全局标量 reward 广播；固定 neuron-specific feedback 单列为 feedback-alignment，不得代偿 P3。
4. **持续学习与统计**：P4 明确为 task-aware/task-incremental、no-replay；同一 context 用于单任务、joint-training 上限和测试矩阵；统计单位是 model seed，不是排列或样本。
5. **RTL 闭环**：P5 接受 Host 黑盒与 testbench 白盒分层证据，隔离 golden-vector/scoreboard，并拆分接口等价 FIFO 完整 cohort 与真实 XPM 短 cohort。
6. **扩展性**：P0-P5 只签固定 4->2->2；P6 必须新建可寻址 Host 协议 V2 和共享 RAM 架构，完成多参数点资源、时序、吞吐和等价门槛后，才允许声明“已证明可扩展基石”。

## 15. 原始资料

- Bellec et al., *A solution to the learning dilemma for recurrent networks of spiking neurons*, Nature Communications 11, 3625 (2020), DOI: `10.1038/s41467-020-17236-y`。原文将局部 eligibility trace 与 top-down learning signal 组合，并区分 neuron-specific feedback 与 global learning-signal baseline。
- Lopez-Paz and Ranzato, *Gradient Episodic Memory for Continual Learning*, NeurIPS 2017 / arXiv `1706.08840`。本方案只采用其测试矩阵、ACC、BWT、FWT 评价定义，不预设采用 GEM 训练算法。
