# PAPER 后续实板验证计划 V1

日期：2026-09-15  
目标器件：`xc7z020clg484-2`，目标时钟：`200 MHz`

## 1. 验证目标

本计划只验证 `PAPER.md` 中仍属于 `[model]` 或 `[sim]`、且论文明确要求上板的结论：

1. QAT canonical 模型能否在目标板上逐位复现 dense 输出。
2. 片上 PL 是否能在不依赖 PS 逐组决策的前提下，无损跳过零贡献组并保持 dense 输出。
3. 纯 PL 口径下，无损零组跳过的实板吞吐是否接近 RTL 估算 `1.327x`；独立 PL auto-mask 和双引擎上限作为后置比较。
4. 输出精度、协议正确性、资源和 200 MHz 时序是否同时成立。
5. 连续推理时的板级功率与每次正确推理能耗是否支持论文的能效方向。

PS 仍可负责启动批次、搬运输入和收集结果，但不得参与逐组跳过决策。PS 在环的单样本延迟继续作为附录对照，不得冒充纯 PL 结果。

## 2. 当前前置事实

- 现有 `be84596` bit/XSA 已完成 group-level NPU 的 200 MHz 物理签核和板级计数器验证。
- 现有 QAT canonical packing 已通过合同测试：634 words、397 held-out，训练整数 forward 与 Python reference 逐元素一致；模型版本为 `qat-v3-val200-temp400-150ep-seed20260914`，训练池为 1200 train + 200 validation，最终 test 只评估一次。
- QAT standalone PL auto-mask 已通过 397/397 仿真和 `1861 cycles/sample`，但严格 2:4 live/static 精度失败，且该引擎未接主 NPU、未做 200 MHz 时序、未上板，因此降为后置候选。
- 可证明无损的零组跳过已完成主 NPU RTL 最小切片：397/397 logits 逐位一致，平均 `1879.136 cycles/sample`、跳过率 `34.6207%`；四轮 200 MHz OOC 均已路由但 setup 失败，当前禁止 bit/XSA 和实板验证。
- 当前 QAT live 剪枝 Python 结果为 dense `88.665%`、live `40.302%`、calibrated `29.471%`；这是精度失败，不能直接作为最终 PL-auto 方案。
- 论文中的 397 样本精度矩阵、`1.340x/1.553x` 流水吞吐和板级功耗仍未形成对应实板证据。

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

- 引擎在样本 `n` 的 NPU 计算期间，计算样本 `n+1` 的 mask。
- 使用现有 `staging/published/active` 语义；mask 只能在样本边界切换。
- 增加 `decision_sample_id`、`mask_epoch`、ready/underflow/overflow/fail 状态。
- 当前最小切片只包含全零激活组和全零权重组；L0 ReLU 后缀早停必须作为独立增量重新过语义和物理门。
- 首样本 warm-up 和末样本 drain 单独报告，不得混入稳态吞吐。

当前阻塞点是主 NPU 的模型取数关键路径。先用同步 BRAM/明确读延迟，或隔离零组判定取数路径，使目标器件 200 MHz 达到 `WNS/WHS>=0`、`TNS/THS=0`；在此之前不得生成正式 bit/XSA。

**CP4 通过条件：**

- Icarus：397 个样本 logits 与 Python dense golden 逐 bit 一致；
- OOC：目标器件、200 MHz、资源和时序报告可审计；
- 完整 RTL：dense/lossless 在 reset、backpressure、首尾样本和错误注入下 fail-closed；
- 板级 8/64/397 样本的 logits、sample ID、CRC、execute/skip 和周期全部可追溯。

### CP5：无损模式纯 PL 板级吞吐

使用 QAT-v3 和 CP4 的正式 bit/XSA，进行 dense/lossless 连续输入流测试。PS 只提交批次和搬运数据，不参与逐组跳过决策。

- 对照：dense、`LOSSLESS_ZERO_GROUP_SKIP`；strict 2:4/static/独立 PL-auto 只在各自精度门通过后追加。
- 预热至少 1000 样本，正式统计至少 10,000 样本；资源不足时先做 397 样本功能轮，再做长跑。
- 至少 5 轮，交替 dense/PL-auto 顺序；记录温度、供电、bit/XSA/ELF/model hash。
- 同时记录稳态 throughput、首样本延迟、p50/p95/p99、NPU cycles、decision cycles、队列等待、underflow/overflow、ID/epoch/CRC 错误。

**验收判据：**

- 吞吐相对 dense `>=1.30x`，否则论文的 `1.340x` 仅保留为模型预测；
- logits 与 Python golden 逐位一致；
- 无协议、乱序、丢失、重复、epoch 或 CRC 错误；
- 不得用首样本延迟代替稳态吞吐。

### CP6：双引擎上限验证

仅当 CP5 单引擎通过且资源余量允许时，复制决策通路或采用等价双发射结构，使决策预算目标为 `D <= 1606 cycles`。

验收指标：同一 QAT、同一策略、同一输入流下，稳态纯 PL 吞吐接近 `2494/1606 = 1.553x`；若未达到，拆分损失来自决策、仲裁、BRAM、边界气泡还是 NPU 本身，并更新论文数字。

### CP7：连接级与其他压缩路径（非主线）

CP5/CP6 完成后再做：

- 连接级 2:4 接入，仅先验证精度和活动量；当前整字取数结构下不得预设周期收益。
- 无损位宽压缩保留为零精度损失对照；零组跳过已前移到 CP3/CP4 主候选。
- 若要证明连接级也省周期，必须改造取数粒度并重新完成 CP0–CP6 的全部身份和门禁。

### CP8：功率与能耗

功率测量必须在功能和吞吐配置冻结后进行，不与 RTL 调试混在同一轮。

- 统一 Type-C 串联测点、同一 JTAG 连接状态、同一 bit/XSA/ELF 和相同 warm-up。
- 至少测 `idle / dense / static / PL-auto live`；若 CP6 完成，再增加双引擎。
- 每个模式至少 5 个 paired rounds，记录起止照片、时间、V/A/W、mAh、mWh、有效推理数。
- 同时报告板级平均功率、每次正确推理能耗和仪器分辨率/重复性；不得把整板功率写成“纯 NPU 功率”。

**判定：** 先关闭“功率数据完整”子门，再判断差异是否超过仪器噪声。若差异小于噪声，诚实结论是“板级功率收益不可分辨”，不能用 Vivado 或单次读数补足。

## 4. 最短执行路径

若目标是尽快拿到论文最关键的实板数据，执行顺序固定为：

`CP0 → CP1 → CP3a/CP3b → CP3c 物理修复 → CP4 无损模式实板 → CP5`。

CP2 严格 2:4 负对照、独立 PL auto-mask、CP6 双引擎、CP7 连接级/位宽压缩和 CP8 功率测量不应提前阻塞无损纯 PL 的第一轮板级结果，但最终论文若继续声称能效或其他剪枝策略收益，必须补齐相应证据。

## 5. 结果归档要求

每个检查点保存：命令行、环境清单、git/bit/XSA/ELF/model/data SHA-256、原始 UART/JTAG/trace、逐样本账本、汇总 JSON、失败首错和“不支持结论”清单。任何阶段失败都保留原始证据，不覆盖上一次通过结果。
