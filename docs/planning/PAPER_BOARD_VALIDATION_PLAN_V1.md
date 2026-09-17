# PAPER 后续实板验证计划 V1

日期：2026-09-15
目标器件：`xc7z020clg484-2`，目标时钟：`200 MHz`

## 1. 验证目标

本计划只验证 `PAPER.md` 中仍属于 `[model]` 或 `[sim]`、且论文明确要求上板的结论：

1. QAT canonical 模型能否在目标板上逐位复现 dense 输出。
2. 片上 PL 是否能在不依赖 PS 逐组决策的前提下，无损跳过零贡献组并保持 dense 输出。
3. 纯 PL 口径下，无损零组跳过的实板连续吞吐是否严格优于 dense；早期 `1.327x` 来自同步输入/L0 权重置换的仿真条件，不是当前 canonical 实板结果。独立 PL auto-mask 和双引擎上限作为后置比较。
4. 输出精度、协议正确性、资源和 200 MHz 时序是否同时成立。
5. 连续推理时的板级功率与每次正确推理能耗是否支持论文的能效方向。

PS 仍可负责启动批次、搬运输入和收集结果，但不得参与逐组跳过决策。PS 在环的单样本延迟继续作为附录对照，不得冒充纯 PL 结果。

## 2. 当前前置事实

- 现有 `be84596` bit/XSA 已完成 group-level NPU 的 200 MHz 物理签核和板级计数器验证。
- 现有 QAT canonical packing 已通过合同测试：634 words、397 held-out，训练整数 forward 与 Python reference 逐元素一致；模型版本为 `qat-v3-val200-temp400-150ep-seed20260914`，训练池为 1200 train + 200 validation，最终 test 只评估一次。
- QAT standalone PL auto-mask 已通过 397/397 仿真和 `1861 cycles/sample`，但严格 2:4 live/static 精度失败，且该引擎未接主 NPU、未做 200 MHz 时序、未上板，因此降为后置候选。
- 可证明无损的零组跳过已完成主 NPU RTL 最小切片：397/397 logits 逐位一致，平均 `1879.136 cycles/sample`、跳过率 `34.6207%`；四轮 200 MHz OOC 均已路由但 setup 失败，当前禁止 bit/XSA 和实板验证。
- 当前 QAT live 剪枝 Python 结果为 dense `88.665%`、live `40.302%`、calibrated `29.471%`；这是精度失败，不能直接作为最终 PL-auto 方案。
- 397 样本精度矩阵和纯 PL 连续吞吐已形成实板证据（CP4/CP5b）；旧 `1.340x/1.553x` 流水吞吐来自旧严格 2:4/双引擎假设，已移到 CP7 后置研究，不作为当前 lossless 验收目标。板级功耗仍未形成对应实板证据。

## 3. 检查点与执行顺序

### CP0：冻结复现实验身份

冻结并记录：Git commit、RTL/bit/XSA/ELF、QAT 模型 SHA-256、canonical packed-word SHA-256、输入预处理、训练/测试划分、样本顺序和工具版本。

必须生成一份 QAT board manifest，至少包含论文测试集的 397 个 held-out 样本；64 样本只作为 bring-up smoke，不得替代正式精度集。manifest 为每个样本保存 `sample_id`、输入 CRC/SHA、label、dense logits、dense prediction、预期 mask 和模型身份。

**通过条件：** manifest 可复现；训练集与 held-out 无重叠；Python reference、训练整数 forward、packed decode 三方逐元素一致。

### CP1：QAT dense 板级装载与主机解析

先不启用剪枝，复用当前已签核 NPU 数据通路，仅替换模型镜像和输入清单。

- 适配 `run_b2_packet_sw_build.ps1`，支持 `eneuron_b3_qat_model_v1` 扁平 samples 和 634-word model image。
- 保留旧 fixed-vector 模式回归，禁止破坏现有 `be84596` 证据路径。
- 加入已知正数/负数 logit 对拍，验证 Host `uint32 -> int32` 符号转换。
- 先跑 8 样本 smoke，再跑 64 样本。

**通过条件：** 每个样本的输入 CRC、结果 CRC、sample ID、epoch、10 维 logits 与 Python golden 逐位一致；协议错误为 0；`execute/skip=592/0`。

### CP2：QAT 剪枝语义板级基线

在同一 bit/XSA、JTAG 状态和 QAT 模型下，先测当前协议可表达的三种模式：

1. dense；
2. calibrated static；
3. live-PS（仅作负面对照和精度/周期基线，不是论文目标架构）。

优先增加“只剪 L0”的 mask 配置，因为 `PAPER.md §9.6.1` 显示它是组级剪枝的可用折中点；两层 live 作为负对照保留。

正式样本使用 397 个 held-out；64 样本先做 bring-up。每种模式至少 3 组对称运行。

**通过条件：** 输出与 Python 预期逐位一致，mask/epoch/CRC/计数器无错；报告 `prediction_agreement`、`logit_exact_match`、dense/live accuracy、accuracy drop 和每类召回率。QAT live 若仍低于精度门，停止把它当作候选正向配置，转入 CP3 的策略修正。

### CP3：修正可上板的剪枝策略

在 RTL 接入前只做 Python/RTL 语义层筛选，候选按以下顺序：

1. 组级只剪 L0；
2. 证据量化器加宽（论文预测的 5-bit 方案）；
3. 离线重训练后固定 mask，作为静态上限；
4. 只有通过精度门的策略才进入 PL-auto。

**停止条件：** 397 样本上 `prediction_agreement`、logit 误差和 accuracy drop 不满足预设门槛时，不继续堆叠流水硬件；先锁定新的 mask 语义和 golden manifest。不得用旧 fixed-vector 的 `1024/1024` 输出保持替代 QAT 精度证据。

### CP4：无损纯 PL 模式实板接入

当前最短路径使用主 NPU 内部 `LOSSLESS_ZERO_GROUP_SKIP`，PS 不参与逐组决策。独立 PL auto-mask 保留为后置候选，不阻塞无损模式的首轮纯 PL 数据。

- dense 与 lossless 使用同一 QAT 模型、输入顺序和 packet 软件语义，只切换完整 wrapper 的 NPU 编译模式。
- lossless 判定完全位于 NPU 核内：当前组激活全零或权重全零时跳过该组，不生成、不提交逐样本 mask，也不使用 staging/epoch 决策链。
- PS 只装载模型、提交样本和收集结果；逐组 execute/skip 由 PL 独立完成。
- 当前最小切片只包含全零激活组和全零权重组；L0 ReLU 后缀早停必须作为独立增量重新过语义和物理门。
- bit/XSA/ELF、硬件 manifest、QAT manifest 和原始板级 run 必须绑定 SHA-256；软件与硬件均需 clean、同 HEAD 且物理签核通过，才能标记正式证据。

CP4 已在 clean HEAD `e155091` 完成：dense/lossless 两条完整 wrapper 均通过 `xc7z020clg484-2`、200 MHz 物理签核，397 样本 logits、sample ID、CRC 和协议状态逐项一致；核心周期 `2494→2290.272`，任务准确率均为 `88.665%`。正式证据为 `artifacts/results/b3_qat_cp4_lossless_zero_group_board_397.json`。

**CP4 通过条件：**

- Icarus：397 个样本 logits 与 Python dense golden 逐 bit 一致；
- OOC：目标器件、200 MHz、资源和时序报告可审计；
- 完整 RTL：dense/lossless 的既有 packet reset/backpressure/fail-closed 合同不退化；
- 板级 397 样本的 logits、sample ID、CRC、execute/skip 和周期全部可追溯。

### CP5：无损模式纯 PL 板级吞吐（已完成）

使用 QAT-v3 和 CP4 的正式 bit/XSA，进行 dense/lossless 连续输入流测试。PS 只提交批次和搬运数据，不参与逐组跳过决策。

- CP5a（bring-up，已完成）：编译期 replay shim 对 QAT `sample_index=201` 缓存 8 beat，预热 1000 次、计量 10000 次，中间结果不出 PL。dense/lossless 为 `2512/2302 cycles/sample`、吞吐提升 `1.091225x`，最终结果与 CRC 一致；该步只关闭 bring-up，不取代 CP5b。证据 `artifacts/results/b3_qat_cp5a_pl_replay_board_pair.json`。
- CP5b（正式，已完成）：扩展为 397 个 held-out 的 PL 内循环，对照为 dense、`LOSSLESS_ZERO_GROUP_SKIP`；每轮 1000 预热 + 10000 计量，5 轮交替 dense/lossless。dense=`2513.9998 cycles/sample`、`79554.501 samples/s`；lossless=`2310.3034 cycles/sample`、`86568.716 samples/s`；吞吐提升 `1.088168676x`、延迟下降 `8.1025%`，5 轮无抖动。CRC/结果帧/协议均通过、协议错误 0；两模式 200 MHz 物理门通过、DSP48E1=4。当前 canonical 实板跳过率约 `11.47%`，因此 `1.088x` 是当前策略的合理上限。证据 `artifacts/results/b3_qat_cp5b_pl_distribution_board_pair.json`。

**验收判据（CP5b 已满足）：**

- 吞吐严格优于 dense：实测 `1.088168676x`，与 canonical CP4 周期 roofline `2494/2290.272=1.088954x` 一致（差异来自两侧相同的 replay 固定开销）。旧 `1.3272x/1.340x` 来自同步输入/L0 权重置换的 RTL/模型仿真条件，不是 canonical 实板结果，不得引用；
- logits 与 Python golden 逐位一致；
- 无协议、乱序、丢失、重复、epoch 或 CRC 错误；
- 不得用首样本延迟代替稳态吞吐。

**速度门语义（统一口径）：**

- `B3-PL-SPEED-GATE=PASS`：由 CP5b 397 样本、5 轮纯 PL 分布 replay 关闭，提升 `1.088168676x`；
- `B3-PACKET-SPEED=MEASURED_WEAK_GAIN_1_008196X`：CP4 单样本 packet 路径仅 `1.008196x`，不称为纯 PL，也不宣称显著系统加速；
- 顶层 `B3-SPEED-GATE=PASS_PURE_PL_ONLY`：主 NPU/剪枝纯 PL 加速门已通过，但不代表 packet 端到端显著加速；
- `B3-GOAL-GATE` 仍需 accuracy + `B3-PL-SPEED-GATE` + `B3-POWER-GATE`；若论文声称 packet/end-to-end 加速，必须另给重复实测，不能引用 CP5b；
- 历史 PS-live `NO_END_TO_END_SPEEDUP` 保留为历史，不得改写成通过。

**当前下一步：** 冻结 CP5b dense/lossless 连续负载并执行 CP8 paired 功耗。

### CP6：可证明无损跳过覆盖率优化

CP6 不再是“双引擎 `D<=1606 cycles` / `1.553x`”主线，因为那来自旧严格 2:4/auto-mask 假设，与当前 lossless 候选不匹配。CP6 改为提高可证明无损跳过覆盖率，按优先级：

- **CP6a（最高优先）** canonical 等价输入通道 + L0 权重同步置换：先在 Python/RTL 层证明数学/packing/logits 等价，再做 397 样本 RTL/实板验证；不得直接引用旧 `1.327x`。
- **CP6b** L0 ReLU 后缀早停：独立增量，要求 397/397 logits exact、200 MHz、资源和实板吞吐全部通过。
- **CP6c** 条件性硬件感知 group-sparsity QAT/重训：必须重新冻结模型身份，从 CP0/精度门开始，不得沿用旧 artifact。
- **CP6d（低优先）** 连续零组快速跳转仅为微优化，先给周期上限，不能替代提高跳过率。

旧双引擎/严格 2:4 的 `1.553x` 移到 CP7 后置研究或历史理论参考，不作为当前 lossless 验收目标。

### CP7：连接级、双引擎与其他压缩路径（非主线）

CP5/CP6 完成后再做：

- 旧双引擎上限验证（`D<=1606 cycles`、`2494/1606=1.553x`）移到这里作为后置研究/历史理论参考；它来自旧严格 2:4/auto-mask 假设，不作为当前 lossless 验收目标。
- 连接级 2:4 接入，仅先验证精度和活动量；当前整字取数结构下不得预设周期收益。
- 无损位宽压缩保留为零精度损失对照；零组跳过已前移到 CP3/CP4 主候选。
- 若要证明连接级也省周期，必须改造取数粒度并重新完成 CP0–CP6 的全部身份和门禁。

### CP8：功率与能耗

功率测量必须在功能和吞吐配置冻结后进行，不与 RTL 调试混在同一轮。正式对象只使用已通过 CP5b 的两个候选：`dense idle`、`dense continuous full`、`lossless idle`、`lossless continuous full`。

- full 必须复用 CP5b 397 样本 PL-internal distribution replay、相同 1000 warmup 后持续运行；PS 不参与逐样本决策。
- idle 必须定义为相同 bit/XSA/ELF、模型已装载、JTAG/PS 状态一致、replay 未启动或停止在冻结的 idle 状态。
- 至少 5 组 paired rounds，交替顺序；同一 Type-C 串联 B10 仪表、相同 JTAG 状态。
- 记录照片/时间、V/A/W、mAh/mWh、有效正确推理数和持续时间。
- 同时报告：整板平均功率；mode-matched idle 到 full 的增量功率；整板总能耗/正确推理；mode-matched 增量能耗/正确推理；仪器精度/量化导致的可分辨性。
- 明确允许现实结论：“平均功率不可分辨，但因吞吐提高而每次推理能耗下降”；不得把整板功率称为纯 NPU 功率。
- static/PL-auto/strict 2:4/双引擎不属于本轮 CP8，只有各自精度和速度门通过后才追加。

**判定：** 先关闭“功率数据完整”子门，再判断差异是否超过仪器噪声。若差异小于噪声，诚实结论是“板级功率收益不可分辨”，不能用 Vivado 或单次读数补足。

## 4. 最短执行路径

若目标是尽快拿到论文最关键的实板数据，执行顺序固定为：

`CP0 → CP1 → CP3a/CP3b → CP3c 物理修复 → CP4 无损模式实板 → CP5a bring-up → CP5b 397 样本分布吞吐`。

CP2 严格 2:4 负对照、独立 PL auto-mask、CP6 覆盖率优化、CP7 连接级/位宽压缩和 CP8 功率测量不应提前阻塞无损纯 PL 的第一轮板级结果。CP5b 已完成，当前下一步是冻结 dense/lossless 连续负载并执行 CP8 paired 功耗；最终论文若继续声称能效或其他剪枝策略收益，必须补齐相应证据。

## 5. 结果归档要求

每个检查点保存：命令行、环境清单、git/bit/XSA/ELF/model/data SHA-256、原始 UART/JTAG/trace、逐样本账本、汇总 JSON、失败首错和“不支持结论”清单。任何阶段失败都保留原始证据，不覆盖上一次通过结果。
