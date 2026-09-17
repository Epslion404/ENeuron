# B3 批量样本协议合同 V1（草案）

状态：`DRAFT / REVIEW_REQUIRED`

日期：2026-09-14

## 1. 背景与目标

B3-22.4 已在不改变帧格式的前提下，将 dense 端到端中位数从约 `157 us` 降至 `63–64 us`，calibrated static 从约 `154 us` 降至 `60 us`。当前每样本仍有约 `18 us` fence、`19–22 us` DMA（含 NPU）和 `10–11 us` result 处理；继续获得量级收益需要验证批量样本传输和 fence 摊销。

本合同只验证固定协议开销是否可摊销，不改变模型、mask 算法或任务精度口径。

## 2. 第一阶段范围

- 对照模式：`dense`、`calibrated_static`。
- 每批样本共享一个已发布 `mask_epoch`；第一阶段不在批内更新 mask。
- 先实现候选批大小 `B ∈ {4, 8, 16}` 中的一个，由缓冲区和 RTL 资源检查决定；不得预设批大小或接口一定更快。
- 保留现有逐样本帧作为控制组和回退路径。
- `live-ENeuron` 批量更新属于第二阶段，必须另行证明 mask 更新边界，不能用第一阶段 static 结果外推。

## 3. 必须保持的语义

每个批内样本必须独立保存和校验：

- `sample_id` 唯一且按请求顺序返回；禁止重复、遗漏和乱序未报告。
- 每个样本携带或可唯一关联 `input_crc`、`result_crc`、`mask_epoch` 和批内索引。
- fence 只允许在明确的批边界生效；pending mask 不得在批内隐式切换。
- 任一长度、TLAST、CRC、ID、epoch、响应计数或 DMA 错误必须 fail-closed，整批标记失败并保存首错上下文。
- 结果响应必须逐样本可解析；不能只返回整批聚合 CRC 代替逐样本结果。
- 不得因为批量化而扩大未验证的 cache 失效范围。当前 `RX_GUARD_BYTES=256` 仅适用于现有短响应，不适用于批量响应。

## 4. 候选请求/响应抽象

具体 opcode、word 排布和版本号在 RTL 评审后冻结；以下只冻结语义：

- 请求头：`magic/version/opcode/sequence/batch_id/model_id/mask_epoch/sample_count`。
- 请求记录：`batch_index/sample_id/input_words/input_crc`。
- 响应头：`magic/version/opcode/sequence/batch_id/model_id/sample_count/status`。
- 响应记录：`batch_index/sample_id/mask_epoch/result_status/logits[10]/result_crc`。
- 响应顺序必须与请求顺序一致；若实现支持乱序内部执行，也必须按请求顺序序列化或显式返回索引。

## 5. Fence 方案

第一阶段比较两种可审计方案：

1. `per_batch_fence`：批开始前发送一次 fence，批内样本不再重复 fence。
2. `per_sample_fence_control`：保留现有逐样本 fence，仅改变 sample DMA/结果收集，用于隔离 fence 摊销收益。

任何省略或合并 fence 的实现都必须验证：批开始时 pending→active 的 epoch、批内 epoch 不变、批结束后结果已全部提交，且异常不会让下一批继承未确认状态。

## 6. 失败注入矩阵

至少覆盖：批长度为 0/超上限、截断记录、额外记录、缺失/错误 TLAST、重复 `sample_id`、乱序 `sample_id`、epoch mismatch、输入 CRC 错误、结果 CRC 错误、RX 响应溢出、DMA 超时和批中途复位。

每个失败用例都应返回明确失败阶段、批 ID、批内索引和首错字段；不得静默丢弃或继续执行下一批。

## 7. 板级验收

- 同一 `be84596` bit/XSA、ELF、JTAG 状态、样本顺序和 warm-up。
- 至少 64 个 held-out 样本，至少 3 组 `dense`/`calibrated_static` 对称 A/B。
- 记录逐样本请求→结果总窗口、DMA、fence、result、PS 时间及批大小。
- 两种模式协议错误、ID/epoch/CRC 错误均为 0；输出与现有逐样本基线逐 logit 一致。
- 建议继续条件：相对 B3-22.4 优化后逐样本基线，批量路径中位数至少下降 `10%`，且三组方向一致；该条件只评估 packet 路径摊销，不能替代 CP5b 的 `B3-PL-SPEED-GATE` 证据、改变 `B3-SPEED-GATE=PASS_PURE_PL_ONLY` 边界或外推 packet/end-to-end 加速。

## 8. RTL/软件改动面

- ingress：新增批量 opcode、长度/记录计数、TLAST 和 malformed frame 检查；保留单样本 opcode。
- adapter：批内记录拆分、sample FIFO/缓冲、逐样本状态和结果回压；明确 fence 与批边界关系。
- NPU wrapper：保持现有 model/mask/epoch 语义，不允许批内隐式 mask 切换。
- response serializer：逐样本输出 ID、epoch、logits 和 CRC，处理 RX 容量边界。
- status/probe：增加 batch accept/complete/fail 计数和首错索引；既有 sample 计数继续有效。
- PS runner：新增 batch 模式、缓冲区大小、cache flush/invalidate 范围和解析器；逐样本结果落盘。
- 验证：新增 RTL testbench、Python 合同、失败注入和至少 64 样本板级 A/B；单样本回归必须继续通过。

## 9. 明确不做

- 不在本合同中接入 PL auto-mask。
- 不把 calibrated static 的批内复用写成 live 动态剪枝收益。
- 不删除逐样本正确性字段，不以整批 CRC 或平均延迟替代逐样本证据。
- 不把“批量接口实现完成”写成速度门通过。
