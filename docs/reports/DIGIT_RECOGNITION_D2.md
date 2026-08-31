# ENeuron 数字识别 D2 报告

## 状态

`D2_FAIL_GENERALIZATION`：协议与账本合同通过，但十个固定种子均未达到学习性能门槛。

本次正式运行日期为 **2026-08-19**，命令为 `python run_digit8x8_d2.py --seeds 0 1 2 3 4 5 6 7 8 9 --epochs 3`。结果文件为 `artifacts/results/digit8x8_d2_results.json`。

本文件是执行报告，不宣称 D2 已通过。逐种子混淆矩阵、最终权重和账本摘要保存在 `artifacts/results/digit8x8_d2_results.json`，并绑定数据、代码、随机种子和训练账本哈希。

## 1. D2 目的与边界

D2 只回答一个问题：在 D0 冻结的 8×8 输入上，当前 ENeuron 机制能否在**固定特征层**上训练十个输出单元，并在未参与训练的样本上完成十分类推理。

D2 不回答以下问题：

- 16 个 patch 单元和 4 个象限单元能否通过局部教师自动学出有用特征；
- 30 个单元能否在 RTL 中逐周期 bit-exact；
- 30 核 Vivado 综合、布局布线、功耗或板级运行是否通过；
- 片上是否能够自行产生标签、奖励或训练调度；
- ENeuron 是否已经具备通用 AI 或任意任务的信用分配能力。

这些内容分别留给 D3、D5 及后续扩展，不得用 D2 结果代偿。

## 2. 冻结输入合同

| 项目 | 冻结值 |
|---|---|
| 图像 | 8×8 灰度数字 |
| 类别 | 0..9，共十类 |
| 像素量化 | 0..15 |
| 编码 | rank-order latency |
| 每图事件数 | 16 |
| 时间窗 | 16 tick |
| tie-break | 亮度相同按像素编号升序 |
| patch | 2×2，共 16 个，每个 4 输入 |
| 数据 fixture | `digit8x8_fixture.json` |
| split manifest | `digit8x8_manifest.json` |
| fixture SHA-256 | `6fa95b5b7493856708b0ab66814ef98a8f151efc2d9245ca10286860f9d21f5e` |
| train/validation/test | 1252 / 270 / 275 |

D2 runner 必须在启动时重新读取 manifest，并在结果中记录 fixture、manifest 和编码器源码哈希。不得从测试标签反向决定编码、阈值、权重或教师时间。

## 3. D2 网络与可塑性范围

```text
64 像素事件
    -> 16 个固定 patch ENeuron（每个 4 输入）
    -> 4 个固定象限 ENeuron（每个 4 输入）
    -> 10 个可训练输出 ENeuron（每个 4 输入）
```

- 总规模仍为 30 个 ENeuron、120 条逻辑连接。
- 前 20 个单元只用于产生特征，权重、阈值和学习字段在整个 D2 训练区间保持不变。
- 只有最后 10 个输出单元允许通过资格快照和调制提交改变权重。
- 输出训练前允许一次受记录的确定性初始化；训练开始后禁止直接写连接权重。
- 推理阶段冻结十个输出单元的连接和全部学习字段。动态膜电位、脉冲计数等每个 episode 可按合同清除，但不得改变持久训练结果。

默认参数沿用 `ThreeFactorNeuron` 的当前黄金模型。runner 必须把实际使用的阈值、复位值、不应期、迹线衰减、资格范围、权重范围和初始权重完整写入 manifest；不能只记录一个“默认参数”字符串。

## 4. 单图训练时序

每个样本开始前清除本样本的动态状态和资格状态，但保留已经学习的输出权重。输入事件按 D0 的 16 tick 顺序回放。为了使教师证据和输入证据处于同一个局部时间窗口，每个输入事件使用如下微窗口：

```text
t       输入事件（patch mask）
t+1     明确的 teacher-post 事件
t+2     空 tick
t+3     空 tick
t+4     空 tick
```

需要遵守以下规则：

1. `teacher-post` 是训练接口事件，只参与 post 迹线/资格迹线；它不能伪装成自然输出，也不能被计入分类结果。
2. 自然输出脉冲和 teacher-post 必须分别记录；自然输出不能默认为教师事件。
3. 隐藏层结果经过一拍 `pending` 路由后才能成为下一层输入；禁止把隐藏层当拍结果组合穿透到输出层。
4. 一个样本完成全部事件回放后，执行一次 `CAPTURE`，随后按十个输出单元各自的有符号调制执行一次 `MOD_COMMIT`。若实现选择更细粒度提交，必须在 manifest 中说明，并保持同样的来源追踪关系。
5. 目标类别输出的调制为正，其余九个输出为负。调制向量采用固定 one-hot 标签规则，训练器不得读取测试集标签。
6. 训练期不得发送 `WEIGHT_WRITE`；初始化、checkpoint 恢复和诊断写入必须与正式训练区间分开，并在账本中标记边界。

推理时只回放输入事件，不发送 teacher-post、CAPTURE、MOD_COMMIT 或直接权重写入命令。

## 5. 十分类解码

对每个样本统计十个输出单元在推理窗口内的自然发放数。严格解码规则如下：

- 只有一个输出拥有最大且非零发放数时，预测该类别；
- 最大值为零时 abstain；
- 多个输出并列最大时 abstain；
- abstain 计入错误，同时单独报告 coverage，禁止用“只报告已覆盖样本准确率”掩盖无输出。

报告至少包含 balanced accuracy、accuracy、macro-F1、coverage、abstain rate、每类召回率和 10×10 confusion matrix。所有指标必须分别给出 validation 和 test，不能用 test 反复调参后再称为留出结果。

## 6. 训练来源账本

训练账本采用逐条记录和哈希链。每一条权重变化都必须能够沿以下路径回溯：

```text
sample_id
  -> input event / teacher-post event
  -> neuron eligibility snapshot
  -> signed modulator
  -> MOD_COMMIT
  -> old_weight -> delta -> new_weight
```

### 6.1 运行级元数据

每次独立运行必须记录：

- `format`、`run_id`、UTC/本地时间和 runner 版本；
- git commit、工作树是否干净、Python 版本和依赖版本；
- fixture/manifest/编码器源码 SHA-256；
- 数据 split 名称、样本 ID 顺序哈希和标签顺序哈希；
- `model_seed`、数据顺序 seed、扰动 seed；
- 20 个固定特征单元和 10 个输出单元的参数快照；
- 初始权重、训练开始与结束账本索引；
- 训练模式、teacher 规则、每样本训练预算和解码规则版本。

### 6.2 事件级记录

每个输入/教师事件至少记录：

| 字段 | 含义 |
|---|---|
| `record_index` | 账本内单调递增编号 |
| `sample_id` / `split` / `label` | 数据来源；label 仅用于训练样本目标和离线评估 |
| `episode_index` / `tick` | 样本和微窗口中的时间位置 |
| `layer` / `neuron` | 事件到达的层和单元 |
| `input_mask` | 该 tick 的输入脉冲位图 |
| `teacher_post_mask` | 明确教师事件位图；自然输出不得填入此字段 |
| `natural_spike` | 单元自然发放结果 |
| `pre_trace` / `post_trace` / `eligibility` | 更新前或更新后的定点状态，必须注明时点 |
| `route_delay` | 跨层路由延迟，D2 固定为一拍语义 |

### 6.3 学习提交记录

每个输出单元的每次提交至少记录：

| 字段 | 含义 |
|---|---|
| `capture_id` / `commit_id` | 快照和提交的唯一关联号，禁止重复消费 |
| `neuron` / `synapse` | 具体被更新的输出单元和输入连接 |
| `eligibility_snapshot` | 提交使用的资格值 |
| `signed_modulator` | 该输出单元收到的调制值 |
| `old_weight` / `delta` / `new_weight` | 更新前、定点变化量和更新后权重 |
| `saturated` | 是否触及权重边界 |
| `source_record_indices` | 组成该资格值的事件账本编号集合或摘要 |
| `status` | CAPTURE/MOD_COMMIT 成功或拒绝原因 |

### 6.4 账本完整性门

- 训练开始索引之后，`WEIGHT_WRITE` 的出现数和成功数必须都为 0；即使命令被硬件拒绝，也要保留为失败证据。
- 每个 `MOD_COMMIT` 只能消费一个尚未消费的快照；重复 commit、过期 commit 和 pending 覆盖必须可被账本发现。
- 所有命令、响应、事件记录和提交记录生成 canonical JSON/定长编码摘要，并计算 SHA-256；账本使用前一条摘要串成 hash chain。
- 账本中的 `new_weight` 必须等于独立重算的 `old_weight + delta`，并经过相同的饱和规则；不能只相信被测模型打印的最终权重。
- 若最终权重发生变化，至少一条提交记录必须给出非零资格、非零调制和对应的成功状态。
- 推理区间不得出现权重、资格、迹线或阈值的持久变化；episode 清除造成的允许变化要单独列入白名单。

## 7. 验收门槛

### 7.1 基础门

以下条件全部满足才可称为 `D2_BASIC_PASS`：

- test coverage ≥ 80%；
- test balanced accuracy 相对“同一网络、同一初态、但不训练输出层”的无学习基线至少提升 10 个百分点；
- 至少 8/10 个独立 model seed 在 validation 通过；
- label-shuffle 负对照接近十分类机会水平，且不能达到主实验门槛；
- 训练前后输出权重确有可审计变化，变化全部来自资格快照 + 调制提交；
- 推理冻结检查通过，且训练区间直接权重写入为零；
- 全量报告包含每类指标、confusion matrix、coverage 和完整账本摘要。

无学习基线必须先运行并冻结，不能在看到训练结果后临时选择更有利的基线。D1 最近质心结果是输入可分性参考，不替代该神经元基线。

### 7.2 强门

以下条件用于允许 D2 结果进入后续 D3/D5 组合实验：

- clean test balanced accuracy ≥ 70%；
- clean test coverage ≥ 90%；
- 10 个独立 model seed 中至少 8 个 validation 通过，且 test 只在最终一次评估；
- 标签打乱、冻结权重、无 teacher-post 和错误符号调制等负对照不能通过；
- 账本哈希、命令哈希、结果哈希和源码 commit 可重放；
- 固定特征层 20 个单元在训练前后逐字段一致；
- 推理阶段十个输出单元的权重和持久学习字段逐字段一致。

dropout、±1 tick jitter、遮挡、平移和灰度扰动属于 D4；D2 必须预留结果接口，但不能把尚未执行的鲁棒性写成通过。

### 7.3 失败分类

| 现象 | 判定 |
|---|---|
| coverage 低但 covered accuracy 高 | 失败；不能用 abstain 换取准确率 |
| 权重变化但无对应 snapshot/commit | 失败；训练来源不可证明 |
| 训练区间出现 `WEIGHT_WRITE` | 失败；直接写入污染训练证据 |
| label-shuffle 也达到主实验结果 | 失败；疑似标签泄漏或评估错误 |
| 训练后权重正确但推理继续变化 | 失败；冻结推理合同不成立 |
| 只有少数 seed 通过 | 未通过；记录为稳定性不足，不得挑选最好 seed 宣称成功 |

## 8. 执行结果

### 8.1 主实验汇总

| 指标 | Validation（10 seeds） | Test（10 seeds） |
|---|---:|---:|
| Balanced accuracy 均值 | 4.61% | 4.74% |
| Balanced accuracy 最小值 | 1.11% | 1.84% |
| Coverage 均值 | 56.04% | 52.18% |
| Coverage 最小值 | 39.26% | 38.18% |
| 达到 `BAcc≥70%, coverage≥90%` 的 seed | 0/10 | 不用于调参 |

十个种子的 validation balanced accuracy 依次为：
`4.20%, 4.33%, 1.85%, 8.15%, 1.11%, 8.15%, 2.59%, 3.33%, 5.93%, 6.46%`。

主实验训练期账本均满足：自然训练脉冲为 0、直接权重写入为 0、每条更新都有教师事件和资格快照、`old + delta = new` 可重算，并生成 canonical SHA-256 与 hash-chain 尾值。

### 8.2 负对照

| 对照 | Test balanced accuracy | Test coverage | 解释 |
|---|---:|---:|---|
| 固定输出权重（seed 0） | 2.53% | 26.55% | 无学习基线；活动和类别区分均不足 |
| 标签打乱（seed 0） | 7.37% | 54.91% | 未接近主实验门槛，也没有显示标签泄漏 |

### 8.3 失败定位

- 初始输出层具有自然发放；训练后十个输出权重趋于相同的下限或相近值。
- 严格解码对全零和并列最高都弃权，因此没有用强行选最小编号来制造覆盖率。
- 负调制在十分类中每个样本作用于九个非目标单元，当前固定特征又不足以形成稳定的类别差异，导致输出层退化为单一类别、并列或全弃权。
- 这说明 D2 的**教师事件和学习来源协议是可执行的**，但“固定 64→16→4 特征 + 当前局部调制”尚不能完成十分类学习。

## 9. 逐种子结果表

| 运行 | model seed | train commits | validation BAcc | validation coverage | test BAcc | test coverage | macro-F1 | 账本哈希 | 状态 |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| D2 | 0 | 3756 | 4.20% | 47.04% | 4.39% | 48.00% | 见 JSON | 见 JSON | `FAIL` |
| D2 | 1 | 3756 | 4.33% | 65.56% | 4.81% | 57.45% | 见 JSON | 见 JSON | `FAIL` |
| D2 | 2 | 3756 | 1.85% | 39.26% | 2.20% | 38.55% | 见 JSON | 见 JSON | `FAIL` |
| D2 | 3 | 3756 | 8.15% | 68.52% | 7.14% | 64.73% | 见 JSON | 见 JSON | `FAIL` |
| D2 | 4 | 3756 | 1.11% | 47.04% | 3.33% | 42.91% | 见 JSON | 见 JSON | `FAIL` |
| D2 | 5 | 3756 | 8.15% | 61.48% | 5.71% | 57.45% | 见 JSON | 见 JSON | `FAIL` |
| D2 | 6 | 3756 | 2.59% | 63.70% | 1.84% | 57.82% | 见 JSON | 见 JSON | `FAIL` |
| D2 | 7 | 3756 | 3.33% | 39.26% | 4.33% | 38.18% | 见 JSON | 见 JSON | `FAIL` |
| D2 | 8 | 3756 | 5.93% | 64.81% | 6.59% | 56.36% | 见 JSON | 见 JSON | `FAIL` |
| D2 | 9 | 3756 | 6.46% | 63.70% | 7.04% | 60.36% | 见 JSON | 见 JSON | `FAIL` |

本阶段已经附上：

- 固定输出权重和 label-shuffle 对照；
- 每个 seed 的结果，而不是只报均值；
- 训练前/后权重矩阵；
- 训练来源账本摘要、canonical SHA-256 和 hash-chain 尾值；
- 失败样本、abstain 样本和混淆矩阵。

无 teacher-post 和反向调制对照尚未执行，因为主实验已经在多种子门槛前失败；它们不能被当作通过证据，留待批准修正后的 D2 重跑。

## 10. D2 结论

`D2_FAIL_GENERALIZATION`，并伴随部分种子的 `D2_FAIL_ACTIVITY`：协议、账本和推理冻结通过；性能没有超过十分类机会水平，coverage 也不稳定。不得进入 D3 的“解冻隐藏层”阶段，除非先批准一个最小的输出层信用分配修正并重新通过本 D2 门槛。

## 11. D2 结论模板

完成后只能从以下措辞中选择：

- `D2_BASIC_PASS`：固定特征、只训练输出层的 ENeuron 软件实验达到基础门；
- `D2_STRONG_PASS`：同时达到强门，可进入 D3 分层教师训练；
- `D2_FAIL_ACTIVITY`：输出活动或 coverage 不足；
- `D2_FAIL_SOURCE`：权重变化来源无法由账本闭合；
- `D2_FAIL_GENERALIZATION`：训练集有效但 validation/test 或多 seed 不达标；
- `D2_NOT_RUN`：尚未产生可审计结果。

无论 D2 状态如何，都不得写成“ENeuron 已完成数字识别硬件”或“通用自训练已完成”。

## 12. 进入 D3 的必要条件

只有在 D2 强门通过且账本可重放时，才进入 D3。D3 将解冻并训练 patch 层、再训练象限层，比较 ENeuron 三因子局部教师、无资格迹的二因子 STDP、Pulse-Mini-L2 和全局标量 reward。D3 必须重新定义每层教师时间位置和一拍路由，不能把 D2 输出层成功直接外推到隐藏层信用分配。
